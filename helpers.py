"""
A module for helper functions.
"""

import socket
from dataclasses import dataclass
from typing import Tuple


def communicate(host: str, port: int, request: str) -> str:
    """
    Sends a request to the server and returns the response
    Fields:
        host: str - the host of the server
        port: int - the port of the server
        request: str - the request to send to the server
    Note: Can only accept responses up to 1024 bytes
    Example:
    >>> communicate("localhost", 8888, "status")
    'OK'
    Returns:
        str: the response from the server
    """
    # AF_INET = (internet socket host name(like an ip addr), TCP port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.send(request.encode())
        response = sock.recv(1024).decode()
        return response


def receive_len(sock: socket.socket, message: str) -> Tuple[socket.socket, str]:
    """
    Receives a socket and a message of the form
    '<CMD>:<metadata>:<len(message)>:<Potentially unfinished message>' and returns the
    full message along with the socket it was received on.
    Precondition: message at least contains the length of the message
                  There are no ':' in the cmd, metadata, or len
    Example:
    >>> receive_len(self.request, "show:7:let")
    (request, "show:7:lettuce")
    """
    length = int(message.split(":")[2])
    # if the message has a lot of ':' in it then we overshoot how much to recv but we strip anyways
    amount_received = sum([len(x) for x in message.split(":")[3:]])

    if amount_received >= length:
        return sock, message

    data = sock.recv(length - amount_received).strip().decode()

    return sock, message + data


@dataclass
class Address:
    """
    Stores the host and port of a server
    """

    host: str
    port: int
