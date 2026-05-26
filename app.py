from flask import Flask, render_template, request, redirect
import sqlite3
from datetime import datetime

app = Flask(__name__)

DB_NAME = "queue.db"

# =========================
# INIT DATABASE
# =========================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT NOT NULL,
        queue_number INTEGER NOT NULL,
        status TEXT DEFAULT 'waiting',
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# =========================
# HOME PAGE
# =========================
@app.route("/")
def home():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Ambil antrian terakhir
    c.execute("SELECT MAX(queue_number) FROM queue")
    last_queue = c.fetchone()[0]

    if last_queue is None:
        last_queue = 0

    # Ambil antrian yang sedang dipanggil
    c.execute("""
    SELECT queue_number, patient_name
    FROM queue
    WHERE status='called'
    ORDER BY id DESC
    LIMIT 1
    """)

    current = c.fetchone()

    conn.close()

    return render_template(
        "index.html",
        last_queue=last_queue,
        current=current
    )

# =========================
# AMBIL ANTRIAN
# =========================
@app.route("/take", methods=["POST"])
def take_queue():
    patient_name = request.form["patient_name"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT MAX(queue_number) FROM queue")
    last = c.fetchone()[0]

    if last is None:
        last = 0

    new_queue = last + 1

    c.execute("""
    INSERT INTO queue (patient_name, queue_number, created_at)
    VALUES (?, ?, ?)
    """, (
        patient_name,
        new_queue,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return f"""
    <h1>Nomor Antrian Anda: {new_queue}</h1>
    <a href="/">Kembali</a>
    """

# =========================
# ADMIN PAGE
# =========================
@app.route("/admin")
def admin():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    SELECT * FROM queue
    ORDER BY queue_number ASC
    """)

    queues = c.fetchall()

    conn.close()

    return render_template("admin.html", queues=queues)

# =========================
# PANGGIL ANTRIAN
# =========================
@app.route("/call/<int:id>")
def call_queue(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # reset called sebelumnya
    c.execute("UPDATE queue SET status='waiting' WHERE status='called'")

    # set antrian dipanggil
    c.execute("""
    UPDATE queue
    SET status='called'
    WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")

# =========================
# SELESAI
# =========================
@app.route("/done/<int:id>")
def done_queue(id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    UPDATE queue
    SET status='done'
    WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")

if __name__ == "__main__":
    app.run(debug=True)