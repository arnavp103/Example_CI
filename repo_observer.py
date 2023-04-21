"""
The observer is a script that sends a commit id to the dispatcher using sockets
It's called by the post-commit hook which writes the commit id to a file
If there are new commits, it sends a request to the dispatcher server
to dispatch a test for the latest commit
"""

import argparse
import os
import socket

import helpers
from helpers import Address
from exceptions import InvalidResponse, BusyServer


def request_dispatcher(dispatcher: Address) -> None:
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
        response = helpers.communicate(dispatcher.host, dispatcher.port, "status")
        if response == "OK":
            commit = ""
            with open(".commit_id", "r", encoding="utf-8") as latest_commit:
                commit = latest_commit.readline()
            # send a test request for given commit id to the dispatcher server
            response = helpers.communicate(
                dispatcher.host, dispatcher.port, f"dispatch:{commit}"
            )
            if response == "Invalid command":
                print(response)
                raise InvalidResponse(f"Could not dispatch the test: {response}")
            if response != "OK":
                raise BusyServer(f"Could not dispatch the test: {response}")
            print("dispatched!")
        else:
            raise InvalidResponse(f"Could not dispatch the test: {response}")
    except socket.error as err:
        raise socket.error(f"Could not communicate with the dispatcher server: {err}")


def send() -> None:
    """In charge of reading the .commit_id and asking the dispatcher
    to handle test runs. Should only really be called by the post-commit hook.
    Takes in the dispatcher server host and port as arguments
    Example:
        python repo_observer.py --dispatcher-server=localhost:8888

    Returns:
        Calls request_dispatcher and returns None

    Raises:
        request_dispatcher's errors
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dispatcher-server",
        help="dispatcher host:port, \
            by default it uses localhost:8888",
        default="localhost:8888",
        action="store",
    )
    args = parser.parse_args()

    dispatcher_host, dispatcher_port = args.dispatcher_server.split(":")

    if os.path.isfile(".commit_id"):
        request_dispatcher(Address(dispatcher_host, int(dispatcher_port)))

    return None


if __name__ == "__main__":
    send()
