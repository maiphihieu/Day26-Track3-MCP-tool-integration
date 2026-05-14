"""
Initialize the SQLite database with schema and seed data.

Run directly:  python init_db.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "university.db")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    cohort      TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    score       REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    department  TEXT    NOT NULL,
    credits     INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS enrollments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    course_id   INTEGER NOT NULL,
    semester    TEXT    NOT NULL,
    grade       REAL,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id)  REFERENCES courses(id)
);
"""

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
SEED_SQL = """
INSERT INTO students (name, cohort, email, score) VALUES
    ('Alice Nguyen',    'A1', 'alice@university.edu',    92.5),
    ('Bob Tran',        'A1', 'bob@university.edu',      85.0),
    ('Charlie Le',      'A2', 'charlie@university.edu',  78.3),
    ('Diana Pham',      'A2', 'diana@university.edu',    95.1),
    ('Edward Vo',       'B1', 'edward@university.edu',   88.7),
    ('Fiona Hoang',     'B1', 'fiona@university.edu',    91.2),
    ('George Dao',      'A1', 'george@university.edu',   72.4),
    ('Hannah Bui',      'B2', 'hannah@university.edu',   83.9);

INSERT INTO courses (name, department, credits) VALUES
    ('Intro to AI',         'Computer Science', 3),
    ('Data Structures',     'Computer Science', 4),
    ('Linear Algebra',      'Mathematics',      3),
    ('Database Systems',    'Computer Science', 3),
    ('Statistics 101',      'Mathematics',      3);

INSERT INTO enrollments (student_id, course_id, semester, grade) VALUES
    (1, 1, '2025-Spring', 9.2),
    (1, 2, '2025-Spring', 8.8),
    (2, 1, '2025-Spring', 7.5),
    (2, 3, '2025-Spring', 8.0),
    (3, 2, '2025-Fall',   6.9),
    (3, 4, '2025-Fall',   7.8),
    (4, 1, '2025-Spring', 9.5),
    (4, 5, '2025-Spring', 9.0),
    (5, 3, '2025-Fall',   8.2),
    (5, 4, '2025-Fall',   8.5),
    (6, 1, '2025-Spring', 9.1),
    (7, 2, '2025-Fall',   6.5);
"""


def create_database(db_path: str = DB_PATH) -> str:
    """Create the database, apply schema, seed data, and return the path."""
    # Remove stale database so we start fresh
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()
        print(f"[OK] Database created at {db_path}")
    finally:
        conn.close()

    return db_path


if __name__ == "__main__":
    create_database()
