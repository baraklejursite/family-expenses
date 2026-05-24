import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "expenses.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store TEXT,
            date TEXT,
            total REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            chat_id TEXT
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id INTEGER,
            name TEXT,
            quantity REAL DEFAULT 1,
            unit_price REAL,
            total_price REAL,
            category TEXT DEFAULT 'Altro',
            FOREIGN KEY (receipt_id) REFERENCES receipts(id)
        );
    """)
    conn.commit()
    conn.close()


def save_receipt(store: str, date: str, total: float, items: list, chat_id: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO receipts (store, date, total, chat_id) VALUES (?, ?, ?, ?)",
        (store, date, total, str(chat_id)),
    )
    receipt_id = cur.lastrowid
    for item in items:
        conn.execute(
            "INSERT INTO items (receipt_id, name, quantity, unit_price, total_price, category) VALUES (?, ?, ?, ?, ?, ?)",
            (
                receipt_id,
                item.get("name", ""),
                item.get("quantity", 1),
                item.get("unit_price"),
                item.get("total_price"),
                item.get("category", "Altro"),
            ),
        )
    conn.commit()
    conn.close()
    return receipt_id


def get_monthly_summary(year: int, month: int) -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT COALESCE(SUM(total), 0) as total, COUNT(*) as count FROM receipts WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?",
        (str(year), f"{month:02d}"),
    ).fetchone()
    categories = conn.execute(
        """SELECT i.category, COALESCE(SUM(i.total_price), 0) as total
           FROM items i JOIN receipts r ON i.receipt_id = r.id
           WHERE strftime('%Y', r.date) = ? AND strftime('%m', r.date) = ?
           GROUP BY i.category ORDER BY total DESC""",
        (str(year), f"{month:02d}"),
    ).fetchall()
    conn.close()
    return {
        "total": row["total"],
        "count": row["count"],
        "categories": [dict(c) for c in categories],
    }


def get_all_months_summary() -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT strftime('%Y-%m', date) as month, COALESCE(SUM(total), 0) as total, COUNT(*) as count
           FROM receipts GROUP BY month ORDER BY month DESC LIMIT 12"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_receipts(limit: int = 20) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, store, date, total, created_at FROM receipts ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_receipt_items(receipt_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT name, quantity, unit_price, total_price, category FROM items WHERE receipt_id = ?",
        (receipt_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_category_summary_year(year: int) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT i.category, COALESCE(SUM(i.total_price), 0) as total
           FROM items i JOIN receipts r ON i.receipt_id = r.id
           WHERE strftime('%Y', r.date) = ?
           GROUP BY i.category ORDER BY total DESC""",
        (str(year),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
