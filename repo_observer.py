"""
The observer polls a downstream cloned repository for changes
It pulls those changes and checks if there are any new commits
If there are new commits, it sends a request to the dispatcher server
to dispatch a test for the latest commit
"""

import argparse
import subprocess
import os
import socket
import time

import helpers

def poll():
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
                try:
                    # send a status request to the dispatcher server
                    response = helpers.communicate(dispatcher_host,
                                                   int(dispatcher_port),
                                                   "status")
                    if response == "OK":
                        commit = ""
                        with open(".commit_id", "r") as f:
                            commit = f.readline()
                        # send a test request for given commit id to the dispatcher server
                        response = helpers.communicate(dispatcher_host,
                                                        int(dispatcher_port),
                                                        f"commit {commit}")
                        if response != "OK":
                            raise Exception(f"Could not dispatch the test: {response}")
                        print("dispatched!")
                    else:
                        raise Exception(f"Could not dispatch the test: {response}")
                except socket.error as e:
                    raise Exception(f"Could not communicate with the dispatcher server: {e}")
                # repeat the process every 5 seconds
                time.sleep(5)
        except subprocess.CalledProcessError as e:
            raise Exception("Could not update and check repository. " +
                            f"Reason: {e.output}")

if __name__ == "__main__":
    poll()