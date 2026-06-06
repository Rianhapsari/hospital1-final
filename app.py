from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
# Memastikan secret key terdaftar secara absolut untuk mengaktifkan Flask Session
app.config['SECRET_KEY'] = "hospital126_admin_secret_key"
socketio = SocketIO(app)

DB_NAME = "queue.db"
DOCTORS = {
    "Dokter Umum": "dr. Andi Pratama",
    "Dokter Gigi": "drg. Anita Putri",
    "Obgyn": "dr. Siti Rahma, Sp.OG",
    "Farmasi": "Apoteker Budi Santoso",
    "Bedah Umum": "dr. Rudi Hartono, Sp.B"
}

PREFIX = {
    "Dokter Umum": "U",
    "Dokter Gigi": "G",
    "Obgyn": "O",
    "Farmasi": "F",
    "Bedah Umum": "B"
}

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # TABEL ANTRIAN
    c.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT NOT NULL,
        category TEXT NOT NULL,
        queue_number INTEGER NOT NULL,
        status TEXT DEFAULT 'waiting',
        created_at TEXT
    )
    """)

    # TABEL ADMIN
    c.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    # Bersihkan spasi dan cek ketersediaan akun admin default
    c.execute("SELECT * FROM admin WHERE TRIM(username)=?", ("hospital1",))
    if not c.fetchone():
        c.execute("""
        INSERT INTO admin (username, password)
        VALUES (?, ?)
        """, ("hospital1", "hospital126#"))
        conn.commit()
    conn.close()

# Jalankan init database
init_db()

# =========================
# HOME PAGE
# =========================
@app.route("/")
def home():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    categories = ["Dokter Umum", "Dokter Gigi", "Obgyn", "Farmasi", "Bedah Umum"]
    queue_data = {}

    for category in categories:
        c.execute("""
        SELECT queue_number, patient_name
        FROM queue
        WHERE category=? AND status='called'
        ORDER BY id DESC LIMIT 1
        """, (category,))
        called = c.fetchone()

        c.execute("SELECT MAX(queue_number) FROM queue WHERE category=?", (category,))
        last = c.fetchone()[0]
        if last is None:
            last = 0

        queue_data[category] = {
            "called": called,
            "last": last
        }

    c.execute("SELECT COUNT(*) FROM queue WHERE status='waiting'")
    total_waiting = c.fetchone()[0]

    c.execute("SELECT MAX(queue_number) FROM queue")
    last_queue = c.fetchone()[0]
    if last_queue is None:
        last_queue = 0

    conn.close()
    return render_template(
        "index.html",
        queue_data=queue_data,
        total_waiting=total_waiting,
        last_queue=last_queue
    )

# =========================
# AMBIL ANTRIAN
# =========================
@app.route("/take", methods=["POST"])
def take_queue():
    patient_name = request.form["patient_name"]
    category = request.form["category"]
    doctor_name = DOCTORS.get(category)
    prefix = PREFIX.get(category)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT MAX(queue_number) FROM queue")
    last = c.fetchone()[0]
    if last is None:
        last = 0

    new_queue = last + 1
    people_before = last

    c.execute("""
    INSERT INTO queue (patient_name, category, queue_number, created_at)
    VALUES (?, ?, ?, ?)
    """, (patient_name, category, new_queue, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

    return render_template(
        "take.html",
        queue_number=new_queue,
        patient_name=patient_name,
        category=category,
        doctor_name=doctor_name,
        people_before=people_before,
        prefixes=prefix
    )

# =========================
# AUTHENTICATION (LOGIN/LOGOUT)
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Ambil input dan bersihkan spasi yang tidak sengaja terketik
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE username=? AND password=?", (username, password))
        admin_account = c.fetchone()
        conn.close()

        if admin_account:
            session.clear() # Reset session lama untuk keamanan
            session["admin"] = username
            return redirect("/admin")
        else:
            return render_template("login.html", error="Username atau Password salah!")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# =========================
# ADMIN DASHBOARD & ACTIONS
# =========================
@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM queue ORDER BY queue_number ASC")
    queues = c.fetchall()
    conn.close()

    return render_template("admin.html", queues=queues)

@app.route("/done/<int:id>")
def done_queue(id):
    if "admin" not in session:
        return redirect("/login")
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM queue WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/call/<int:id>")
def call_queue(id):
    if "admin" not in session:
        return redirect("/login")
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE queue SET status='called' WHERE id=?", (id,))
    conn.commit()

    socketio.emit("queue_updated", {"message": "refresh"})
    conn.close()
    return redirect("/admin")

if __name__ == "__main__":
    socketio.run(app, debug=True)