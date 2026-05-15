from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import qrcode
import requests

from user_agents import parse
from PIL import Image
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)

# ---------- MODELS ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))

class Scan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(100))
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))
    country = db.Column(db.String(100))
    device = db.Column(db.String(200))
    browser = db.Column(db.String(200))
    os = db.Column(db.String(200))
    time = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- HOME ----------
@app.route("/")
def home():
    return render_template("index.html")

# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        user = User(username=username, password=password)

        db.session.add(user)
        db.session.commit()

        return redirect("/login")

    return render_template("register.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):

            session["user"] = username

            return redirect("/dashboard")

    return render_template("login.html")

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    scans = Scan.query.order_by(Scan.time.desc()).all()

    return render_template("dashboard.html", scans=scans)

# ---------- GENERATE QR ----------
@app.route("/generate")
def generate():

    if "user" not in session:
        return redirect("/login")

    track_url = request.host_url + "track"

    qr = qrcode.make(track_url)

    qr_path = "static/qr.png"

    qr.save(qr_path)

    return render_template("generate.html", qr=qr_path)

# ---------- TRACK ----------
@app.route("/track")
def track():

    # REAL USER IP FOR RENDER
    forwarded = request.headers.get("X-Forwarded-For")

    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.remote_addr

    # LOCALHOST TEST
    if ip == "127.0.0.1":
        ip = "8.8.8.8"

    # LOCATION API
    try:

        response = requests.get(f"http://ip-api.com/json/{ip}")

        data = response.json()

        city = data.get("city", "Unknown")
        region = data.get("regionName", "Unknown")
        country = data.get("country", "Unknown")

    except:

        city = "Unknown"
        region = "Unknown"
        country = "Unknown"

    # DEVICE INFO
    ua_string = request.headers.get("User-Agent")

    user_agent = parse(ua_string)

    device = user_agent.device.family
    browser = user_agent.browser.family
    os_name = user_agent.os.family

    # SAVE DATABASE
    scan = Scan(
        ip=ip,
        city=city,
        region=region,
        country=country,
        device=device,
        browser=browser,
        os=os_name
    )

    db.session.add(scan)
    db.session.commit()

    return render_template(
        "track.html",
        ip=ip,
        city=city,
        region=region,
        country=country,
        device=device,
        browser=browser,
        os=os_name
    )

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():

    session.pop("user", None)

    return redirect("/login")

# ---------- MAIN ----------
if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(host="0.0.0.0", port=5000, debug=True)