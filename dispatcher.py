"""
In charge of dispatch commits to test runners
Listens on a websocket port for requests from test runners and observer
Gracefully handles potential errors with test runners
redistributes tests to other test runners if a test runner fails
"""

import argparse
import socket
import threading
import socketserver
import time
import os
import re
from typing import Type, List, Dict

import helpers
from helpers import Address

# Our dispatcher server - TCP ensures continuous ordered stream of messages
class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    runners: List[Type[Address]] = [] # Keeps track of test runner pool
    dead = False # Indicate to other threads that we are no longer running
    dispatched_commits = {} # Keeps track of commits we dispatched
    pending_commits = [] # Keeps track of commits we have yet to dispatch

class DispatcherHandler(socketserver.BaseRequestHandler):
    """
    The RequestHandler class for our dispatcher.
    This will dispatch test runners against the incoming commit
    and handle their requests and test results
    """
    # matches commands like "commit:commit_id" and creates command and target groups
    command_re = re.compile(r"(\w+)(:.+)*")
    BUF_SIZE = 1024
    # handles incoming requests from test runners and observer
    # 4 commands are supported:
    # status - checks if the dispatcher is alive
    # register - registers a test runner with the dispatcher
    # dispatch - dispatches a test to a test runner
    # results - sends the results of a test to the dispatcher (for test runners)
    # format of results - results:<commit_id>:<len(result_data) as bytes>:<results>
    def handle(self):
        # store the incoming data in self.data
        self.data = self.request.recv(self.BUF_SIZE).strip()
        command_groups = self.command_re.match(self.data.decode("utf-8"))
        if not command_groups:
            self.request.sendall("Invalid command".encode())
            return
        command = command_groups.group(1)
        if command == "status":
            print("status request")
            self.request.sendall("OK".encode())
        elif command == "register":
            # Add this test runner to the pool
            print("register request")
            address = command_groups.group(2)[1:]
            r = Address(address.split(":")[0], int(address.split(":")[1]))
            self.server.runners.append(r) # type: ignore
            self.request.sendall("OK".encode())
        elif command == "dispatch":
            print("dispatch request")
            commit_id = command_groups.group(2)[1:]
            if not self.server.runners: # type: ignore
                self.request.sendall("No runners registered")
                return
            else:
                # now we guarantee to dispatch the test
                self.request.sendall("OK".encode())
                dispatch_tests(self.server, commit_id) # type: ignore
        elif command == "result":
            print("result request")
            commit_id, result_len, = command_groups.group(2)[1:].split(":")
            # there were 3 ":" in the sent command
            # size of the remaining data after the command, commit_id, and result_len
            remaining = self.BUF_SIZE - (len(command) + len(commit_id) + len(result_len) + 3)
            if int(result_len) > remaining:
                # add the extra data if needed
                self.data = (self.data.encode() + \
                             self.request.recv(int(result_len) - remaining).strip()).decode()
            # remove it from dispatched commits since it is done
            del self.server.dispatched_commits[commit_id] # type: ignore
            if not os.path.exists("test_results"):
                os.mkdir("test_results")
            with open(f"test_results/{commit_id}", "w") as f:
                # data has the full results so we split every test result and write it
                data = self.data.split(":")[3:]
                data = "\n".join(data)
                f.write(data)

            self.request.sendall("OK".encode())


# shared dispatcher code
# sends a runtest request to a free test runner
# if none are available, it will check again in 2 seconds
# Once accepted, it will move the commit id to the dispatched_commits list
# and log the test runner it was assigned to as the value
def dispatch_tests(server: Type[ThreadingTCPServer], commit_id):
    # NOTE: usually we don't run this forever
    while True:
        print("trying to dispatch to runners")
        # note that if there are many runners the load will be heavily skewed to
        for runner in server.runners:
            response = helpers.communicate(runner.host,
                                           runner.port,
                                           f"runtest:{commit_id}")
            if response == "OK":
                print(f"adding id {commit_id}")
                server.dispatched_commits[commit_id] = runner
                if commit_id in server.pending_commits:
                    server.pending_commits.remove(commit_id)
                return
        time.sleep(2)




def serve():
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
    server = ThreadingTCPServer((args.host, int(args.port)), DispatcherHandler)
    print(f"Serving on {args.host}:{args.port}")

    # heartbeats are sent every 2 seconds
    # pings the test runners to see if they are alive
    # if they are not alive, it reassigns the commits assigned to them to pending
    def runner_checker(server: ThreadingTCPServer):
        # goes through the dispatched commits and reassigns every single commit assigned to runner to pending
        def manage_commit_lists(runner):
            for commit, assigned_runner in server.dispatched_commits.items():
                if assigned_runner == runner:
                    del server.dispatched_commits[commit]
                    server.pending_commits.append(commit)
                    break
        while not server.dead:
            for runner in server.runners:
                try:
                    response = helpers.communicate(runner.host,
                                                runner.port,
                                                "ping")
                    if response != "pong":
                        manage_commit_lists(runner)
                except socket.error:
                    manage_commit_lists(runner)
            time.sleep(2)

    # assigns pending commits to test runners
    def redistribute(server: Type[ThreadingTCPServer]):
        while not server.dead:
            # how is this not a race
            for commit in server.pending_commits:
                print("running redistribute")
                print(f"{server.pending_commits}")
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
    except (KeyboardInterrupt, Exception):
        # If any thread throws we kill them all
        server.dead = True
        runner_heartbeat.join()
        redistributor.join()


if __name__ == "__main__":
    serve()
