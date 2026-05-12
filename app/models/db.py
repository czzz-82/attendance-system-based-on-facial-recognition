"""SQLite 数据访问层 —— 用 sqlite3 + 行工厂封装常用查询"""
import os
import sqlite3
import threading
from contextlib import contextmanager

import config

_LOCK = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('teacher','student')),
    student_id INTEGER,                     -- role=student 时关联 students.id
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_no TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    class_name TEXT,
    photo_path TEXT,
    encoding BLOB,                          -- 128 维 float32 人脸特征
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    student_no TEXT,
    name TEXT,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,                   -- success / fail / unknown
    liveness_passed INTEGER NOT NULL,       -- 0/1
    emotion TEXT,
    note TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    held_on TEXT NOT NULL,
    photo_path TEXT,
    detected INTEGER DEFAULT 0,
    matched INTEGER DEFAULT 0,
    analysis_json TEXT,                    -- 保存合照分析档案：原图/标注图/超分样本/识别结果
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_participation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    UNIQUE(activity_id, student_id),
    FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS emotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    student_no TEXT,
    name TEXT,
    emotion TEXT NOT NULL,
    source TEXT NOT NULL,                   -- attendance / group_photo
    timestamp TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_records_ts ON attendance_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_records_sid ON attendance_records(student_id);
CREATE INDEX IF NOT EXISTS idx_emotions_sid ON emotions(student_id);
"""


def init_schema():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # 兼容旧数据库：为历史活动补充完整分析 JSON 列
        cols = [row[1] for row in conn.execute("PRAGMA table_info(activities)").fetchall()]
        if "analysis_json" not in cols:
            conn.execute("ALTER TABLE activities ADD COLUMN analysis_json TEXT")


def execute(sql, params=()):
    with _LOCK, get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def query_all(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_one(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None
