import os
import glob

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
def get_last_commit():
    path = 'web/static'
    files = glob.glob(f"{path}/*.json")
    latest = max(files, key=os.path.getctime)   # get last created file
    to_send = latest.split("/")[-1]
    logger.debug("to be sent %s", to_send)
    return app.send_static_file(to_send)

