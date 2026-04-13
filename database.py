"""
database.py — SQLite setup and all DB helper functions
"""
import sqlite3, hashlib, os
from datetime import datetime

DB_PATH = "interview_bot.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        email           TEXT NOT NULL UNIQUE,
        password        TEXT NOT NULL,
        phone           TEXT,
        college         TEXT,
        target_company  TEXT,
        role            TEXT DEFAULT 'user',
        created_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS interviews (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        job_role    TEXT,
        experience  TEXT,
        test_type   TEXT,
        avg_score   REAL,
        history     TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS recommendations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL UNIQUE,
        content     TEXT DEFAULT '',
        updated_at  TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Seed default admin if not exists
    admin = c.execute("SELECT id FROM users WHERE email='admin@bot.com'").fetchone()
    if not admin:
        c.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'admin')
        """, ("Admin", "admin@bot.com", _hash("admin123")))
        print("Default admin created: admin@bot.com / admin123")

    conn.commit()
    conn.close()

# ── Password ──────────────────────────────────────────────────────────────────
def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(plain: str, hashed: str) -> bool:
    return _hash(plain) == hashed

# ── User helpers ──────────────────────────────────────────────────────────────
def create_user(name, email, password, phone, college, target_company):
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO users (name, email, password, phone, college, target_company)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, _hash(password), phone, college, target_company))
        conn.commit()
        return True, ""
    except sqlite3.IntegrityError:
        return False, "Email already registered."
    finally:
        conn.close()

def get_user_by_email(email: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(uid: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_users():
    conn = get_db()
    rows = conn.execute("""
        SELECT u.*, COUNT(i.id) as interview_count,
               ROUND(AVG(i.avg_score), 1) as avg_score
        FROM users u
        LEFT JOIN interviews i ON i.user_id = u.id
        WHERE u.role = 'user'
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_user(uid: int):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()

# ── Interview helpers ─────────────────────────────────────────────────────────
def save_interview(user_id, job_role, experience, test_type, avg_score, history):
    import json
    conn = get_db()
    conn.execute("""
        INSERT INTO interviews (user_id, job_role, experience, test_type, avg_score, history)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, job_role, experience, test_type, avg_score, json.dumps(history)))
    conn.commit()
    conn.close()

def get_user_interviews(user_id: int):
    import json
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM interviews WHERE user_id=? ORDER BY created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["history"] = json.loads(d["history"] or "[]")
        result.append(d)
    return result

def get_interview_by_id(iid: int):
    import json
    conn = get_db()
    row = conn.execute("SELECT * FROM interviews WHERE id=?", (iid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["history"] = json.loads(d["history"] or "[]")
    return d

def get_user_stats(user_id: int):
    conn = get_db()
    row = conn.execute("""
        SELECT COUNT(*) as total,
               ROUND(AVG(avg_score), 1) as avg_score,
               MAX(created_at) as last_interview
        FROM interviews WHERE user_id=?
    """, (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"total": 0, "avg_score": None, "last_interview": None}

# ── Recommendation helpers ────────────────────────────────────────────────────
def get_recommendation(user_id: int) -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT content FROM recommendations WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row["content"] if row else ""

def save_recommendation(user_id: int, content: str):
    conn = get_db()
    conn.execute("""
        INSERT INTO recommendations (user_id, content, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at
    """, (user_id, content))
    conn.commit()
    conn.close()
