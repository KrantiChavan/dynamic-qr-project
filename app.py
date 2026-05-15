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
    username = db.Column(db.String(100))
    password = db.Column(db.String(200))


class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    data = db.Column(db.Text)
    image = db.Column(db.String(200))
    scans = db.Column(db.Integer, default=0)
    expiry = db.Column(db.String(50))
    created_at = db.Column(db.String(50))


class Scan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qr_id = db.Column(db.Integer)
    ip = db.Column(db.String(50))
    city = db.Column(db.String(50))
    country = db.Column(db.String(50))
    device = db.Column(db.String(50))
    scan_time = db.Column(db.String(50))


# ---------- INIT ----------
with app.app_context():
    db.create_all()

os.makedirs("static/images", exist_ok=True)

# IMPORTANT:
# Yaha apna Render URL dalo
BASE_URL = "https://dynamic-qr-project-1.onrender.com"


# ---------- QR GENERATE ----------
def generate_qr(data, filename):

    qr = qrcode.make(data)

    img = qr.convert('RGB')

    try:

        logo = Image.open(
            "static/logo.png"
        ).resize((80, 80))

        pos = (
            (img.size[0] - 80) // 2,
            (img.size[1] - 80) // 2
        )

        img.paste(logo, pos)

    except:
        pass

    img.save(f"static/images/{filename}")


# ---------- HELPERS ----------
def get_ip():

    # Render Real IP
    ip = request.headers.get(
        'X-Forwarded-For'
    )

    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()

    if not ip:
        ip = request.remote_addr

    return ip


def get_location(ip):

    try:

        # localhost/private IP
        private_ips = (
            "127.",
            "192.168.",
            "10.",
            "172.",
            "::1"
        )

        if ip.startswith(private_ips):
            return "Localhost", "Local"

        url = f"http://ip-api.com/json/{ip}"

        response = requests.get(
            url,
            timeout=5
        )

        data = response.json()

        print("LOCATION:", data)

        city = data.get(
            "city",
            "Unknown"
        )

        country = data.get(
            "country",
            "Unknown"
        )

        return city, country

    except Exception as e:

        print("Location Error:", e)

        return "Unknown", "Unknown"


# ---------- LOGIN ----------
@app.route('/', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        user = User.query.filter_by(
            username=request.form['username']
        ).first()

        if user and check_password_hash(
            user.password,
            request.form['password']
        ):

            session['user_id'] = user.id

            return redirect('/dashboard')

    return render_template("login.html")


# ---------- SIGNUP ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if request.method == 'POST':

        new = User(
            username=request.form['username'],
            password=generate_password_hash(
                request.form['password']
            )
        )

        db.session.add(new)
        db.session.commit()

        return redirect('/')

    return render_template("signup.html")


# ---------- DASHBOARD ----------
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect('/')

    data = QRCode.query.filter_by(
        user_id=session['user_id']
    ).all()

    active_qr = 0

    for qr in data:

        qr.status = "Active"

        if qr.expiry:

            try:

                exp_date = datetime.strptime(
                    qr.expiry,
                    "%Y-%m-%d"
                ).date()

                if exp_date < datetime.now().date():

                    qr.status = "Expired"

                else:

                    active_qr += 1

            except:

                active_qr += 1

        else:

            active_qr += 1

    return render_template(
        "dashboard.html",
        data=data,
        active_qr=active_qr
    )


# ---------- CREATE QR ----------
@app.route('/create', methods=['GET', 'POST'])
def create():

    if 'user_id' not in session:
        return redirect('/')

    if request.method == 'POST':

        data = request.form['data']

        filename = f"{datetime.now().timestamp()}.png"

        qr_link = f"{BASE_URL}/qr/{filename}"

        generate_qr(
            qr_link,
            filename
        )

        expiry = request.form.get("expiry") or None

        qr = QRCode(
            user_id=session['user_id'],
            data=data,
            image=filename,
            expiry=expiry,
            created_at=str(datetime.now())
        )

        db.session.add(qr)
        db.session.commit()

        return redirect('/dashboard')

    return render_template("create_qr.html")


# ---------- SCAN QR ----------
@app.route('/qr/<img>')
def scan(img):

    qr = QRCode.query.filter_by(
        image=img
    ).first()

    if not qr:

        return render_template(
            "error.html",
            message="Invalid QR"
        )

    # Expiry check
    if qr.expiry:

        if datetime.now().date() > datetime.strptime(
            qr.expiry,
            "%Y-%m-%d"
        ).date():

            return render_template(
                "error.html",
                message="QR Expired"
            )

    # Visitor IP
    ip = get_ip()

    print("REAL IP:", ip)

    # Location
    city, country = get_location(ip)

    # Device
    ua = parse(
        request.headers.get('User-Agent')
    )

    device = "Mobile" if ua.is_mobile else "PC"

    # Save scan
    scan_data = Scan(
        qr_id=qr.id,
        ip=ip,
        city=city,
        country=country,
        device=device,
        scan_time=str(datetime.now())
    )

    qr.scans += 1

    db.session.add(scan_data)
    db.session.commit()

    # Redirect
    target = (
        qr.data
        if qr.data.startswith("http")
        else "https://" + qr.data
    )

    return redirect(target)


# ---------- ANALYTICS ----------
@app.route('/analytics/<int:id>')
def analytics(id):

    scans = Scan.query.filter_by(
        qr_id=id
    ).all()

    return render_template(
        "analytics.html",
        scans=scans
    )


# ---------- DELETE ----------
@app.route('/delete/<int:id>')
def delete(id):

    if 'user_id' not in session:
        return redirect('/')

    qr = QRCode.query.get(id)

    if qr:

        image_path = os.path.join(
            "static/images",
            qr.image
        )

        if os.path.exists(image_path):
            os.remove(image_path)

        Scan.query.filter_by(
            qr_id=id
        ).delete()

        db.session.delete(qr)
        db.session.commit()

    return redirect('/dashboard')


# ---------- ADMIN ----------
@app.route('/admin')
def admin():

    users = User.query.all()

    qrs = QRCode.query.all()

    return render_template(
        "admin.html",
        users=users,
        qrs=qrs
    )


# ---------- LOGOUT ----------
@app.route('/logout')
def logout():

    session.clear()

    return redirect('/')


# ---------- RUN ----------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )