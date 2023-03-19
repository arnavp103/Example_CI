import os, glob

from flask import Flask
from flask import render_template
from datetime import datetime
from . import app

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

fh = logging.FileHandler('webapp.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    path = 'web/static'
    latestTime = float("-inf")
    latest = ""
    for filename in glob.glob(os.path.join(path, '*.json')):
        curr = os.path.getmtime(filename) # returns the time in s since epoch
        logger.debug("%s was last changed at %s", filename, curr)
        if curr > latestTime:
            latestTime = curr
            latest = filename
    to_send = latest.split("/")[-1]
    logger.debug("to be sent %s", to_send)
    return app.send_static_file(to_send)

