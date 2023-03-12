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
import typing
import argparse
import subprocess
import unittest
import errno

import helpers
from helpers import Address


class TestingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    dispatcher_server: Address # Holds the dispatcher server host/port information
    last_communication = None # Keeps track of last communication from dispatcher
    busy = False # Status flag
    dead = False # Status flag
    repo_folder: os.PathLike # Holds the path to the repo folder


class TestHandler(socketserver.BaseRequestHandler):
    """
    The RequestHandler class for our server.
    """
	# matches commands like "commit:commit_id" and creates command and target groups
    command_re = re.compile(r"(\w+)(:.+)*")
    # handles incoming requests from the dispatcher
    # 2 commands are supported:
    # ping - checks if the server is alive
    # runtest:commit_id - runs the tests for the given commit
    def handle(self):
        # self.request is the TCP socket connected to the client
        self.data = self.request.recv(1024).strip()
        command_groups = self.command_re.match(self.data.decode("utf-8"))
        if not command_groups:
            self.request.sendall("Invalid command")
            return

        command = command_groups.group(1)
        if not command:
            self.request.sendall("Invalid command")
            return

        if command == "ping":
            print("ping request")
            self.server.last_communication = time.time() # type: ignore
            self.request.sendall("pong".encode())
        elif command == "runtest":
            print(f"runtest request - busy:{self.server.busy}") # type: ignore
            if self.server.busy: # type: ignore
                self.request.sendall("BUSY".encode())
            else:
                self.request.sendall("OK".encode())
                print("running")
                commit_id = command_groups.group(2)[1:]
                self.server.busy = True # type: ignore
                self.run_tests(commit_id, self.server.repo_folder) # type: ignore
                self.server.busy = False # type: ignore
        else:
            self.request.sendall("Invalid command")

    # get the test runner server to actually run the tests
    # this runs the test in a separate process
    # this allows the runner to service respond to heartbeats and not get dropped
    def run_tests(self, commit_id: str, repo_folder: os.PathLike):
        # update repo
        output = subprocess.check_output(["./test_runner_script.sh",
                                        repo_folder, commit_id])
        print(output)
        # run the tests
        test_folder = os.path.join(repo_folder, "tests")
        # loads all the tests in test_folder
        suite = unittest.TestLoader().discover(test_folder)
        with open("results", "w") as result_file:
            unittest.TextTestRunner(result_file).run(suite)
        with open("results", "r") as result_file:
            # give the dispatcher the results
            output = result_file.read()
            helpers.communicate(self.server.dispatcher_server.host, # type: ignore
                                self.server.dispatcher_server.port, # type: ignore
                                f"results:{commit_id}:{len}:{output}")


def serve():
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

    runner_host = args.host
    runner_port = None
    tries = 0
    server = None
    if not args.port:
        runner_port = range_start  # default port
        while tries < 100:
            try:
                server = TestingServer((runner_host, runner_port), TestHandler)
                print(server)
                print(runner_port)
                break
            # loop through 100 ports
            except socket.error as e:
                if e.errno == errno.EADDRINUSE:
                    tries += 1
                    runner_port = runner_port + tries
                    continue
                else:
                    raise e
        else:
            raise Exception(f"Could not bind to ports in range {range_start}-{range_start + tries}")
    else:
        runner_port = int(args.port)
        server = TestingServer((runner_host, runner_port), TestHandler)

    server.repo_folder = args.repo

    dispatcher_host, dispatcher_port = args.dispatcher_server.split(":")
    server.dispatcher_server = Address(dispatcher_host, int(dispatcher_port))
    response = helpers.communicate(server.dispatcher_server.host,
                                   server.dispatcher_server.port,
                                   f"register:{runner_host}:{runner_port}")
    if response != "OK":
        raise Exception("Can't register with dispatcher!")

    def dispatcher_checker(server):
        # Checks if the dispatcher went down. If it is down, we will shut down
        # if since the dispatcher may not have the same host/port
        # when it comes back up.
        while not server.dead:
            time.sleep(5)
            if (time.time() - server.last_communication) > 10:
                try:
                    response = helpers.communicate(
                                       server.dispatcher_server["host"],
                                       int(server.dispatcher_server["port"]),
                                       "status")
                    if response != "OK":
                        print("Dispatcher is no longer functional")
                        server.shutdown()
                        return
                except socket.error as e:
                    print(f"Can't communicate with dispatcher: {e}")
                    server.shutdown()
                    return

    t = threading.Thread(target=dispatcher_checker, args=(server,))
    try:
        t.start()
        # Activate the server; this will keep running until we interrupt the program with Ctrl-C
        server.serve_forever()
    except (KeyboardInterrupt, Exception):
        # if any exception occurs, kill the thread
        server.dead = True
        t.join()


if __name__ == "__main__":
    serve()