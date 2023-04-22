"""
The orchestrator of the test runners
In charge of dispatching commits to test runners
Listens on a socket for requests from test runners and observer
Gracefully handles potential errors with test runners
Writes the results to a txt file (and optionally a json file from the args) for other processes to use

Fault tolerant: against test runners crashing, against sockets crashing
"""

import argparse
import socket
import threading
import socketserver
import time
import os
import json
import re
import copy
from typing import List, Dict, Optional
import logging

import helpers
from helpers import Address

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# create file handler that logs errors
fh = logging.FileHandler('spam.log')
fh.setLevel(logging.WARNING)
fh.setFormatter(formatter)
logger.addHandler(fh)
# create console handler that logs everything
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)


# Our dispatcher server - TCP ensures continuous ordered stream of messages
class Dispatcher(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    Our dispatcher server
    It keeps track of the test runners to dispatches tests to them
    We have dead to signal the other threads to stop
    TODO: Augment this to have a list of last dispatched to
      test runners to do some load balancing
    Fields:
        runners: List[Address] - Keeps track of test runner pool
        dead: bool - Indicate to other threads that we are no longer running
        dispatched_commits: Dict[<commit_id>, Address] - Keeps track of commits we dispatched
        pending_commits: List[<commit_id>] - Keeps track of commits we have yet to dispatch
        target: Optional[os.PathLike] - Holds the path to the folder to write the json upon dispatch results
    """
    runners: List[Address] = []
    dead = False
    dispatched_commits: Dict[str, Address] = {}
    pending_commits: List[str] = []
    target: Optional[os.PathLike] = None

class DispatcherHandler(socketserver.BaseRequestHandler):
    """
    The RequestHandler class for our dispatcher.
    This accepts commit_id's from the observer and dispatches them
    This will dispatch test runners against the incoming commit
      and handle their requests and test results
    """
    # matches commands like "commit:commit_id" and creates command and target groups
    command_re = re.compile(r"(\w+)(:.+)*")
    BUF_SIZE = 1024    # 1 KiB

    def handle(self) -> None:
        """
        Handles incoming requests from test runners and observer
        4 commands are supported:
            status - checks if the dispatcher is alive
            register:<runner_addr> - registers a test runner with the dispatcher
            dispatch:<commit_id> - dispatches a test to a test runner
            results:<commit_id>:<len(result_data) as bytes>:<results> - \
                accepts the results of a test and write it to a txt file, and maybe a json file
        """
        assert isinstance(self.server, Dispatcher)
        assert isinstance(self.request, socket.socket) # default for tcp servs

        self.data = self.request.recv(self.BUF_SIZE).strip().decode("utf-8")
        command_groups = self.command_re.match(self.data)
        if not command_groups:
            self.request.sendall("Invalid command".encode())
            logger.info("Invalid command %s", self.data)
            return

        command = command_groups.group(1)
        match command:
            case "status":
                logger.debug("status request")
                self.request.sendall("OK".encode())

            case "register":
                # Add this test runner to the pool
                logger.debug("register request")
                address = command_groups.group(2)[1:] # first char is :
                runner = Address(address.split(":")[0], int(address.split(":")[1]))
                self.server.runners.append(runner)
                self.request.sendall("OK".encode())

            case "dispatch":
                logger.debug("dispatch request")
                commit_id = command_groups.group(2)[1:]
                if not self.server.runners:
                    self.request.sendall("No runners registered".encode())
                    logger.warning("out of runners")
                    return
                # now we guarantee to dispatch the test
                self.request.sendall("OK".encode())
                dispatch_tests(self.server, commit_id)

            case "results":
                logger.debug("result request")
                commit_id, _, _ = command_groups.group(2)[1:].split(":")

                if commit_id not in self.server.dispatched_commits:
                    # we didn't dispatch this commit
                    self.request.sendall("Invalid Command".encode())
                    logger.error("Invalid commit id %s", commit_id)
                    return
                logger.debug("commit id %s has been serviced by %s", commit_id,
                             self.server.dispatched_commits[commit_id])
                del self.server.dispatched_commits[commit_id]

                # receive the rest of the data if there is any
                self.request, self.data = helpers.receive_len(self.request, self.data)

                create_result_file(commit_id, self.data)
                if self.server.target:
                    create_json_result_file(commit_id, self.data, self.server.target)
                self.request.sendall("OK".encode())

            case _:
                self.request.sendall("Invalid command".encode())
                logger.info("Invalid command %s from %s", command, self.data)



def create_result_file(commit_id: str, results: str) -> None:
    """
    Creates a file with the results of the test
    The file will be stored in the test_results directory
    If the directory does not exist, it will be created
    It preprocesses the results to add newlines
    """
    if not os.path.exists("test_results"):
        logger.info("creating test_results directory")
        os.mkdir("test_results")
    with open(f"test_results/{commit_id}.txt", "w", encoding="utf-8") as resultfile:
        resultfile.write(results)

def create_json_result_file(commit_id: str, results: str, path: os.PathLike) -> None:
    """
    Creates a file with the results of the test
    The file will be stored in the results directory command line arg
    If the directory was not passed, do nothing
    It preprocesses the results to add newlines
    """
    if not os.path.exists(path):
        logger.info("creating results directory at %s", path)
        os.mkdir(path)

    results_obj = {"commit_id": commit_id, "results": []}

    results = results.strip()
    if results[-2] == "OK":
        pass
    else:
        for result in results.split('='*70)[1:]:
            # logger.debug("result: %s", result)
            result_obj = {}

            if result[:result.index(':')].strip() == "FAIL":
                result_obj["type"] = "fail"
            else:
                result_obj["type"] = "error"

            name, reasons, *_ = result.split('-'*70)
            result_obj["test_name"] = name[name.index(':')+1 : ].strip()

            result_obj["reasons"] = []
            res = ""
            for reason in reasons.splitlines(keepends=True):
                if reason[0].isspace:
                    res += reason
                    continue
                result_obj["reasons"].append(res)
                res = reason
            # they always end with a whitespace line
            # so we need to manually add the last reason
            result_obj["reasons"].append(res)

            results_obj["results"].append(result_obj)

    with open(f"{path}/{commit_id}.json", "w", encoding="utf-8") as resultfile:
        json.dump(results_obj, resultfile)

def dispatch_tests(server: Dispatcher, commit_id: str) -> None:
    """
    shared dispatcher code
    If none are available, it will check again in 2 seconds
    Once accepted, it will move the commit id to the dispatched_commits dict
    and log the test runner it was assigned to as the value
    """
    # NOTE: usually we don't run this forever
    while True:
        logger.debug("dispatch to runners...")
        # note that if there are many runners
        # the load will be heavily skewed to the first ones in the list
        # TODO: asyncio to send every test at once
        for runner in server.runners:
            response = helpers.communicate(runner.host,
                                           runner.port,
                                           f"runtest:{commit_id}")
            if response == "OK":
                logger.debug("tracking id %s with runner at %s:%s",
                             commit_id, runner.host, runner.port)
                server.dispatched_commits[commit_id] = runner
                if commit_id in server.pending_commits:
                    server.pending_commits.remove(commit_id)
                return
        time.sleep(2)


def serve() -> None:
    """
    Starts the dispatcher server
    Opens a socket on the given host and port
    Services requests from the observer and test runners using DispatcherHandler

    Example:
        python3 dispatcher.py --host=localhost --port=8888 --results=web/static
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--host",
                        help="dispatcher's host, by default it uses localhost",
                        default="localhost",
                        action="store")
    parser.add_argument("--port",
                        help="dispatcher's port, by default it uses 8888",
                        default=8888,
                        action="store")
    parser.add_argument("--results", type=str, default=None, action="store",
                        help="directory to store the json results of the tests")

    args = parser.parse_args()

    server = Dispatcher((args.host, int(args.port)), DispatcherHandler)
    server.target = args.results
    logger.debug("Serving on %s:%s", args.host, args.port)


    def runner_checker(server: Dispatcher) -> None:
        """
        heartbeats are sent every 2 seconds
        pings the test runners to see if they are alive
        if they are not alive, it reassigns the commits assigned to them to pending
        """
        # goes through the dispatched commits and
        # reassigns every single commit assigned to runner to pending
        def remove_runner(runner: Address) -> None:
            rcopy = copy.copy(runner)
            server.runners.remove(runner)
            for commit_id, assigned_runner in server.dispatched_commits.items():
                if assigned_runner == rcopy:
                    # this makes changes to the thread
                    del server.dispatched_commits[commit_id]
                    server.pending_commits.append(commit_id)
                    break

        while not server.dead:
            for runner in server.runners:
                try:
                    response = helpers.communicate(runner.host,
                                                   runner.port,
                                                   "ping")
                    if response != "pong":
                        remove_runner(runner)
                        logger.info("removing runner %s:%s",
                                    runner.host, runner.port)
                except socket.error:
                    remove_runner(runner)
                    logger.info("removing runner %s:%s",
                                runner.host, runner.port)
            time.sleep(2)

    # assigns pending commits to test runners
    def redistribute(server: Dispatcher) -> None:
        while not server.dead:
            # how is this not a race
            for commit in server.pending_commits:
                logger.debug("distributing commits: %s",
                             server.pending_commits)
                dispatch_tests(server, commit)
                time.sleep(5)

    # run them in separate threads
    runner_heartbeat = threading.Thread(target=runner_checker, args=(server,))
    redistributor = threading.Thread(target=redistribute, args=(server,))
    try:
        runner_heartbeat.start()
        redistributor.start()
        # Activate the server; this will keep running until you kill it with Ctrl-C
        server.serve_forever()
    except KeyboardInterrupt:
        # If any thread throws we kill them all
        server.dead = True
        runner_heartbeat.join()
        redistributor.join()
        logger.info("Dispatcher shutting down")
        server.server_close()



if __name__ == "__main__":
    serve()
