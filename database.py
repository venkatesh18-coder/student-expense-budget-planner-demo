"""SQLite setup: schema, connection helper and optional demo data."""
import os
import sqlite3
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "finance.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('Income','Expense')),
    category TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, category, month, year)
);
CREATE TABLE IF NOT EXISTS savings_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_name TEXT NOT NULL,
    target_amount REAL NOT NULL CHECK (target_amount > 0),
    saved_amount REAL NOT NULL DEFAULT 0 CHECK (saved_amount >= 0),
    target_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_budget_user ON budgets(user_id, year, month);
CREATE INDEX IF NOT EXISTS idx_goal_user ON savings_goals(user_id);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def seed_demo():
    """Create demo user (demo@student.com / demo1234). Run: python database.py --demo"""
    init_db()
    conn = get_db()
    if conn.execute("SELECT 1 FROM users WHERE email='demo@student.com'").fetchone():
        conn.close()
        return False
    uid = conn.execute("INSERT INTO users (full_name,email,password_hash) VALUES (?,?,?)",
                       ("Demo Student", "demo@student.com", generate_password_hash("demo1234"))).lastrowid
    today = date.today()
    rows = []
    for back in range(4):  # last 4 months
        m, y = today.month - back, today.year
        while m < 1:
            m += 12
            y -= 1
        d = lambda day: f"{y}-{m:02d}-{min(day, 28):02d}"
        rows += [
            ("Scholarship", 6000, "Income", "Scholarship", d(1)),
            ("Part-Time Job", 3500 + back * 200, "Income", "Part-Time Income", d(5)),
            ("Parent Allowance", 4000, "Income", "Other", d(2)),
            ("Hostel Rent", 5000, "Expense", "Rent / Hostel", d(3)),
            ("Mess & Canteen", 2600 + back * 150, "Expense", "Food", d(8)),
            ("Bus Pass", 600, "Expense", "Travel", d(10)),
            ("Books & Stationery", 900 + back * 100, "Expense", "Education", d(12)),
            ("Mobile Recharge", 299, "Expense", "Bills", d(15)),
            ("Movie & Snacks", 700 + back * 90, "Expense", "Entertainment", d(18)),
        ]
    for desc, amt, typ, cat, dt in rows:
        if dt <= today.isoformat():
            conn.execute("INSERT INTO transactions (user_id,description,amount,transaction_type,category,transaction_date) "
                         "VALUES (?,?,?,?,?,?)", (uid, desc, amt, typ, cat, dt))
    for cat, amt in [("Food", 3000), ("Travel", 800), ("Entertainment", 900), ("Education", 1500), ("Bills", 400)]:
        conn.execute("INSERT INTO budgets (user_id,category,amount,month,year) VALUES (?,?,?,?,?)",
                     (uid, cat, amt, today.month, today.year))
    for name, target, saved, months in [("New Laptop", 45000, 32000, 5), ("College Trip", 8000, 3000, 3), ("Emergency Fund", 10000, 9500, 2)]:
        conn.execute("INSERT INTO savings_goals (user_id,goal_name,target_amount,saved_amount,target_date) VALUES (?,?,?,?,?)",
                     (uid, name, target, saved, (today + timedelta(days=30 * months)).isoformat()))
    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    import sys
    init_db()
    print("Database ready at", DB_PATH)
    if "--demo" in sys.argv:
        print("Demo user created (demo@student.com / demo1234)" if seed_demo() else "Demo user already exists")
