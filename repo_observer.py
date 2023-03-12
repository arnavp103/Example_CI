"""
The observer is a script that sends socket messages, but doesn't receive
It polls a downstream cloned repository for changes
It pulls those changes and checks if there are any new commits
If there are new commits, it sends a request to the dispatcher server
to dispatch a test for the latest commit
"""

import argparse
import subprocess
import os
import socket
import time
from typing import NoReturn, Type

import helpers
from helpers import Address
from exceptions import InvalidResponse, BusyServer

def request_dispatcher(dispatcher: Type[Address]) -> None:
    """Sends a request to the dispatcher server to dispatch a test
    for the latest commit
    Example:
    >>> request_dispatcher(Address("localhost", 8888))
    prints 'dispatched!' if the request was successful
    Returns:
		None
    Raises:
		socket.error: if there was an error communicating with the dispatcher server
		InvalidResponse: if the dispatcher server responds with an invalid response
		BusyServer: if the dispatcher server is unable to handle the request
    """
    try:
        # send a status request to the dispatcher server
        response = helpers.communicate(dispatcher.host,
                                       dispatcher.port,
                                       "status")
        if response == "OK":
            commit = ""
            with open(".commit_id", "r", encoding="utf-8") as latest_commit:
                commit = latest_commit.readline()
            # send a test request for given commit id to the dispatcher server
            response = helpers.communicate(dispatcher.host,
                                           dispatcher.port,
                                           f"commit {commit}")
            if response != "OK":
                raise BusyServer(f"Could not dispatch the test: {response}")
            print("dispatched!")
        else:
            raise InvalidResponse(f"Could not dispatch the test: {response}")
    except socket.error as err:
        raise socket.error(f"Could not communicate with the dispatcher server: {err}")

def poll() -> NoReturn:
    """In charge of polling the repo and asking the dispatcher
    to handle test runs if there's been new commits

    Example:
        python repo_observer.py --dispatcher-server=localhost:8888 test_repo_clone_obs/

    Returns:
		Runs indefinitely, polling the repo and sending requests to the dispatcher

    Raises:
        subprocess.CalledProcessError: if the update_repo.sh script fails
        request_dispatcher's errors
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--dispatcher-server",
                        help="dispatcher host:port, \
                        by default it uses localhost:8888",
                        default="localhost:8888",
                        action="store")
    parser.add_argument("repo", metavar="REPO", type=str,
                        help="path to repository to observe") # test_repo_clone_obs/ here
    args = parser.parse_args()

    dispatcher_host, dispatcher_port = args.dispatcher_server.split(":")

    while True:
        try:
            # call the bash script that will update the repo and check
            # for changes. If there's a change, it will drop a .commit_id file
            # with the latest commit in the current working directory
            subprocess.check_output(["./update_repo.sh", args.repo])
            if os.path.isfile(".commit_id"):
                request_dispatcher(Address(dispatcher_host, dispatcher_port))
                # repeat the process every 5 seconds
                time.sleep(5)
        except subprocess.CalledProcessError as err:
            raise subprocess.CalledProcessError("Could not update and check repository. " +
                            f"Reason: {err}", "update_repo.sh")

if __name__ == "__main__":
    poll()
