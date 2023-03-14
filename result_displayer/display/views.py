from flask import Flask
from flask import render_template
from datetime import datetime
from . import app

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    return app.send_static_file("cid_result.json")

