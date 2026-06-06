from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO
from datetime import datetime
import os
import urllib.parse as urlparse
import pymysql # Menggunakan PyMySQL untuk koneksi ke MySQL

app = Flask(__name__)
app.config['SECRET_KEY'] = "hospital126_admin_secret_key"
socketio = SocketIO(app)

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

# Fungsi untuk membedah URL MySQL Aiven dan melakukan koneksi
def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Membedah url mysql://avnadmin:...
    url = urlparse.urlparse(DATABASE_URL)
    
    conn = pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:], # Menghapus tanda '/' di awal nama database
        port=url.port,
        ssl={'ssl': {}} # Aiven MySQL mewajibkan koneksi SSL aman
    )
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # TABEL ANTRIAN (Menggunakan AUTO_INCREMENT khas MySQL)
    c.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INT AUTO_INCREMENT PRIMARY KEY,
        patient_name VARCHAR(255) NOT NULL,
        category VARCHAR(100) NOT NULL,
        queue_number INT NOT NULL,
        status VARCHAR(50) DEFAULT 'waiting',
        created_at VARCHAR(100)
    )
    """)

    # TABEL ADMIN
    c.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) UNIQUE,
        password VARCHAR(255)
    )
    """)
    conn.commit()

    # Cek admin default menggunakan placeholder %s
    c.execute("SELECT * FROM admin WHERE TRIM(username)=%s", ("hospital1",))
    if not c.fetchone():
        c.execute("""
        INSERT INTO admin (username, password)
        VALUES (%s, %s)
        """, ("hospital1", "hospital126#"))
        conn.commit()
        
    c.close()
    conn.close()

# Jalankan inisialisasi database saat aplikasi dinyalakan
init_db()

# =========================
# HOME PAGE
# =========================
@app.route("/")
def home():
    conn = get_db_connection()
    c = conn.cursor()

    categories = ["Dokter Umum", "Dokter Gigi", "Obgyn", "Farmasi", "Bedah Umum"]
    queue_data = {}

    for category in categories:
        c.execute("""
        SELECT queue_number, patient_name
        FROM queue
        WHERE category=%s AND status='called'
        ORDER BY id DESC LIMIT 1
        """, (category,))
        called = c.fetchone()

        c.execute("SELECT MAX(queue_number) FROM queue WHERE category=%s", (category,))
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

    c.close()
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

    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT MAX(queue_number) FROM queue")
    last = c.fetchone()[0]
    if last is None:
        last = 0

    new_queue = last + 1
    people_before = last

    c.execute("""
    INSERT INTO queue (patient_name, category, queue_number, created_at)
    VALUES (%s, %s, %s, %s)
    """, (patient_name, category, new_queue, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    c.close()
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
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE username=%s AND password=%s", (username, password))
        admin_account = c.fetchone()
        c.close()
        conn.close()

        if admin_account:
            session.clear() 
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
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM queue ORDER BY queue_number ASC")
    queues = c.fetchall()
    c.close()
    conn.close()

    return render_template("admin.html", queues=queues)

@app.route("/done/<int:id>")
def done_queue(id):
    if "admin" not in session:
        return redirect("/login")
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM queue WHERE id=%s", (id,))
    conn.commit()
    c.close()
    conn.close()
    return redirect("/admin")

@app.route("/call/<int:id>")
def call_queue(id):
    if "admin" not in session:
        return redirect("/login")
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE queue SET status='called' WHERE id=%s", (id,))
    conn.commit()

    socketio.emit("queue_updated", {"message": "refresh"})
    c.close()
    conn.close()
    return redirect("/admin")

if __name__ == "__main__":
    socketio.run(app, debug=True)