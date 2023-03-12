"""
The test runner worker servers.
The test runner requires a clone of the repo to run tests on.
In this example, that's test_repo_clone_runner/
Handles testrun requests in a separate process and sends the results back to the dispatcher
"""

import time
import socket
import threading
import socketserver
import os
import re
from typing import Optional, NoReturn
import argparse
import subprocess
import unittest
import errno

import helpers
from helpers import Address
from exceptions import InvalidResponse, FailedSetup

class Tester(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """
    Our test runner server
    Fields:
        dispatcher_server: Address - Holds the dispatcher server host/port information
        last_ping: float = -Inf - Keeps track of last ping from dispatcher
        busy = False - Status flag
        dead = False - Status flag
        repo_folder: os.PathLike - Holds the path to the repo folder
    """
    dispatcher_server: Address
    last_ping: float = float("-inf")
    busy = False
    dead = False
    repo_folder: os.PathLike


class TestHandler(socketserver.BaseRequestHandler):
    """
    The RequestHandler class for our server.
    This will handle incoming requests from the dispatcher
    This will also return the results of the tests to the dispatcher
    """
	# matches commands like "commit:commit_id" and creates command and target groups
    command_re = re.compile(r"(\w+)(:.+)*")

    def handle(self) -> None:
        """
        handles incoming requests from the dispatcher
        2 commands are supported:
            ping - checks if the server is alive
            runtest:commit_id - runs the tests for the given commit
        """
        # this should only be called by the test runner server
        assert isinstance(self.server, Tester)

        # self.request is the TCP socket connected to the client
        self.data = self.request.recv(1024).strip().decode("utf-8")
        command_groups = self.command_re.match(self.data)
        if not command_groups:
            self.request.sendall("Invalid command".encode())
            return

        command = command_groups.group(1)
        if not command:
            self.request.sendall("Invalid command".encode())
            return

        if command == "ping":
            print("ping request")
            self.server.last_ping = time.time()
            self.request.sendall("pong".encode())
        elif command == "runtest":
            print(f"runtest request - busy:{self.server.busy}")
            if self.server.busy:
                self.request.sendall("BUSY".encode())
            else:
                self.request.sendall("OK".encode())
                print("running")
                commit_id = command_groups.group(2)[1:]
                self.server.busy = True
                self.run_tests(commit_id, self.server.repo_folder)
                self.server.busy = False
        else:
            self.request.sendall("Invalid command".encode())

    # get the test runner server to actually run the tests
    # this runs the test in a separate process
    # this allows the runner to service respond to heartbeats and not get dropped
    def run_tests(self, commit_id: str, repo_folder: os.PathLike) -> None:
        """
        runs the tests for the given commit
        returns the results to the dispatcher im a message
        """
        # this should only be called by the test runner server
        assert isinstance(self.server, Tester)

        # setup: update repo to the commit id state
        subprocess.call(["./test_runner_script.sh",
                                        repo_folder, commit_id])
        # run the tests
        # NOTE: We only run the tests in the tests folder
        test_folder = os.path.join(repo_folder, "tests")
        # loads all the tests for the given commit
        suite = unittest.TestLoader().discover(test_folder)
        with open("results", "w", encoding="utf-8") as result_file:
            unittest.TextTestRunner(result_file).run(suite)
        with open("results", "r", encoding="utf-8") as result_file:
            # give the dispatcher the results
            output = result_file.read()
            helpers.communicate(self.server.dispatcher_server.host,
                                self.server.dispatcher_server.port,
                                f"results:{commit_id}:{len(output)}:{output}")


def connect_range(runner: Address, tries: int) -> Optional[Tester]:
    """
    Creates a Tester instance and attempts to connect to it
    a range of ports

    runner: Address - The runner's host and port with which to attempt create
    tries: int - Tests ports in range runner.port -> runner.port + tries in order
    Example:
        connect_range(Address("localhost", 8900), 100)
    """
    runner_port = runner.port
    while runner_port < runner_port + tries:
        try:
            server = Tester((runner.host, runner_port), TestHandler)
            print(runner_port)
            return server
        # loop through 100 ports
        except socket.error as err:
            # if the address is already in use
            # presumably by another test runner
            if err.errno == errno.EADDRINUSE:
                runner_port += 1
                continue

            print(f"Could not bind to ports in range \
                    {runner.port}-{runner.port + tries}")
            break
    return None

def serve() -> None:
    """
    starts the test runner server
    attempts to connect to the dispatcher
    accepts requests from the dispatcher and runs testsuites
    Example:
        python test_runner.py --dispatcher-server=localhost:8888 test_repo_clone_runner
    """
    range_start = 8900
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",
                        help="runner's host, by default it uses localhost",
                        default="localhost",
                        action="store")
    parser.add_argument("--port",
                        help=f"runner's port, by default it uses values >={range_start}",
                        action="store")
    parser.add_argument("--dispatcher-server",
                        help="dispatcher host:port, by default it uses " \
                        "localhost:8888",
                        default="localhost:8888",
                        action="store")
    parser.add_argument("repo", metavar="REPO", type=str,
                        help="path to the repository this will observe")
    args = parser.parse_args()

    runner = Address(args.host, range_start)  # default port
    server = None
    if not args.port:
        server = connect_range(runner, 100)
    else:
        server = Tester((runner.host, int(args.port)), TestHandler)

    if server is None:
        raise FailedSetup("Could not establish socket connection!")
    server.repo_folder = args.repo

    # connect to the dispatcher
    dispatcher_host, dispatcher_port = args.dispatcher_server.split(":")
    server.dispatcher_server = Address(dispatcher_host, int(dispatcher_port))
    response = helpers.communicate(server.dispatcher_server.host,
                                   server.dispatcher_server.port,
                                   f"register:{runner.host}:{runner.port}")
    if response != "OK":
        raise InvalidResponse("Can't register with dispatcher!")

    def dispatcher_checker(server: Tester):
        """
        Checks if the dispatcher went down. If it is down, we will shut down
        if since the dispatcher may not have the same host/port
        when it comes back up.
        """
        def shutdown():
            server.dead = True
            server.shutdown()

        while not server.dead:
            time.sleep(5)
            # if we haven't heard from the dispatcher in 10 seconds
            if (time.time() - server.last_ping) > 10:
                try:
                    response = helpers.communicate(
                                       server.dispatcher_server.host,
                                       int(server.dispatcher_server.port),
                                       "status")
                    if response != "OK":
                        print("Dispatcher is no longer functional")
                        shutdown()
                        return
                except socket.error as err:
                    print(f"Can't communicate with dispatcher: {err}")
                    shutdown()
                    return

    heartbeat = threading.Thread(target=dispatcher_checker, args=(server,))
    try:
        heartbeat.start()
        # Activate the server;
        # this will keep running until we interrupt the program with Ctrl-C
        server.serve_forever()
    except KeyboardInterrupt:
        # if any exception occurs, kill the thread
        server.dead = True
        heartbeat.join()
        print("Shutting down server")
    except Exception as err:
        server.dead = True
        heartbeat.join()
        print(f"Unexpected error: {err}")
        print("Shutting down server")


if __name__ == "__main__":
    serve()
