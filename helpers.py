import socket
import typing
from dataclasses import dataclass

def communicate(host: str, port: int, request: str) -> str:
    # AF_INET = (internet socket host name(like an ip addr), TCP port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.send(request.encode())
        response = s.recv(1024).decode()
        return response

@dataclass
class Address:
	host: str
	port: int