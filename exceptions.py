"""A general module for exceptions relating to the distributed system

"""


class InvalidCommand(Exception):
    """A server will respond with this error
    when it receives an invalid command
    """

class InvalidResponse(Exception):
    """A client will raise this error
    when it receives an invalid response
    """

class BusyServer(Exception):
    """A server will respond with this error
    when, for whatever reason it's still capable
    to respond to requests, but it's unable to service them
    """

class DroppedConnection(Exception):
    """A client will raise this error
    when it loses connection with the server

    The dispatcher will raise this error
    when it loses connection with a worker
    """
