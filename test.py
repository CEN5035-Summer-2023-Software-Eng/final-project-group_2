import os
import uuid
import base64
import json
from flask import Flask, request, render_template, jsonify, send_file
from io import BytesIO



app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/login")
def login():
    return render_template("login.html")

if __name__ == "__main__":
    app.run(host="localhost", port=5678)
