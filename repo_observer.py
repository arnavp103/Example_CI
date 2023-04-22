"""
The observer is a script that sends a commit id to the dispatcher using sockets
It's called by the post-commit hook which writes the commit id to a file
If there are new commits, it sends a request to the dispatcher server
to dispatch a test for the latest commit
"""

import argparse
import socket

import helpers
from helpers import Address
from exceptions import InvalidResponse, BusyServer


def request_dispatcher(dispatcher: Address, commit_id: str) -> None:
    """Sends a request to the dispatcher server to dispatch a test
    for the latest commit
    Example:
    >>> request_dispatcher(Address("localhost", 8888), "17eb587b44f6480db31987602f703c7f7b8628cb")
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
            # send a test request for given commit id to the dispatcher server
            response = helpers.communicate(
                dispatcher.host, dispatcher.port, f"dispatch:{commit_id}"
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
    """In charge of reading the commit_id and asking the dispatcher
    to handle test runs. Should only really be called by the post-commit hook.
    Takes in the dispatcher server host, port, and commit id as arguments
    Calls request_dispatcher to dispatch tests according to the repo at commit_id
    Example:
        python repo_observer.py --dispatcher-server=localhost:8888 --commit-id=17eb587b44f6480db31987602f703c7f7b8628cb

    Returns:
        Side Effect Only - None

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
    parser.add_argument(
        "--commit-id",
        help="commit id to be sent to the dispatcher server",
        action="store",
    )
    args = parser.parse_args()

    dispatcher_host, dispatcher_port = args.dispatcher_server.split(":")


    request_dispatcher(Address(dispatcher_host, int(dispatcher_port)), args.commit_id)

    return None


if __name__ == "__main__":
    send()
