"""
The orchestrator of the test runners
In charge of dispatching commits to test runners
Listens on a socket for requests from test runners and observer
Gracefully handles potential errors with test runners

Fault tolerant: against test runners crashing, against sockets crashing
"""

import argparse
import socket
import threading
import socketserver
import time
import os
import re
from typing import List, Dict
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
    """
    runners: List[Address] = []
    dead = False
    dispatched_commits: Dict[str, Address] = {}
    pending_commits: List[str] = []


class DispatcherHandler(socketserver.BaseRequestHandler):
    """
    The RequestHandler class for our dispatcher.
    This accepts commit_id's from the observer and dispatches them
    This will dispatch test runners against the incoming commit
      and handle their requests and test results
    """
    # matches commands like "commit:commit_id" and creates command and target groups
    command_re = re.compile(r"(\w+)(:.+)*")
    BUF_SIZE = 1024

    def handle(self) -> None:
        """
        Handles incoming requests from test runners and observer
        4 commands are supported:
            status - checks if the dispatcher is alive
            register:<runner_addr> - registers a test runner with the dispatcher
            dispatch:<commit_id> - dispatches a test to a test runner
            results:<commit_id>:<len(result_data) as bytes>:<results> - \
                accepts the results of a test and write it to a file
        """
        assert isinstance(self.server, Dispatcher)

        self.data = self.request.recv(self.BUF_SIZE).strip().decode("utf-8")
        command_groups = self.command_re.match(self.data)
        if not command_groups:
            self.request.sendall("Invalid command".encode())
            logger.info("Invalid command")
            return
        command = command_groups.group(1)

        if command == "status":
            logger.debug("status request")
            self.request.sendall("OK".encode())
        elif command == "register":
            # Add this test runner to the pool
            logger.debug("register request")
            address = command_groups.group(2)[1:]
            runner = Address(address.split(":")[0], int(address.split(":")[1]))
            self.server.runners.append(runner)
            self.request.sendall("OK".encode())
        elif command == "dispatch":
            logger.debug("dispatch request")
            commit_id = command_groups.group(2)[1:]
            if not self.server.runners:
                self.request.sendall("No runners registered")
                logger.warning("out of runners")
                return
            # now we guarantee to dispatch the test
            self.request.sendall("OK".encode())
            dispatch_tests(self.server, commit_id)
        elif command == "result":
            logger.debug("result request")
            commit_id, result_len, = command_groups.group(2)[1:].split(":")
            # there were 3 ":" in the sent command
            # size of the remaining data after the command, commit_id, and result_len
            remaining = self.BUF_SIZE - \
                (len(command) + len(commit_id) + len(result_len) + 3)
            if int(result_len) > remaining:
                # add the extra data if needed
                self.data = (self.data.encode() +
                             self.request.recv(int(result_len) - remaining).strip()).decode()
            # remove it from dispatched commits since it is done
            del self.server.dispatched_commits[commit_id]
            if not os.path.exists("test_results"):
                logger.info("creating test_results directory")
                os.mkdir("test_results")
            with open(f"test_results/{commit_id}", "w", encoding="utf-8") as f:
                # data has the guaranteed full results
                # we split every test result and write it
                data = self.data.split(":")[3:]
                data = "\n".join(data)
                f.write(data)

            self.request.sendall("OK".encode())
        else:
            self.request.sendall("Invalid command".encode())
            logger.info("Invalid command")


def dispatch_tests(server: Dispatcher, commit_id: str) -> None:
    """
    shared dispatcher code
    sends a runtest request to a free test runner
    if none are available, it will check again in 2 seconds
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
                logger.debug("adding id %s to %s:%s",
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
    args = parser.parse_args()
    server = Dispatcher((args.host, int(args.port)), DispatcherHandler)
    logger.debug("Serving on %s:%s", args.host, args.port)

    def runner_checker(server: Dispatcher) -> None:
        """
        heartbeats are sent every 2 seconds
        pings the test runners to see if they are alive
        if they are not alive, it reassigns the commits assigned to them to pending
        """
        # goes through the dispatched commits and
        # reassigns every single commit assigned to runner to pending
        def remove_runner(runner):
            for commit, assigned_runner in server.dispatched_commits.items():
                if assigned_runner == runner:
                    del server.dispatched_commits[commit]
                    server.pending_commits.append(commit)
                    del server.runners[server.runners.index(runner)]
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


if __name__ == "__main__":
    serve()
