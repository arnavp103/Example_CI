"""
A module for helper functions.
"""

import socket
import typing
from dataclasses import dataclass

def communicate(host: str, port: int, request: str) -> str:
    """
    Sends a request to the server and returns the response
    Fields:
        host: str - the host of the server
        port: int - the port of the server
        request: str - the request to send to the server
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

@dataclass
class Address:
    """
    Stores the host and port of a server
    """
    host: str
    port: int