"""Durable approval handoff to an independently committed order registry."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA synchronous = FULL")
    return db


def initialize(directory):
    directory = Path(directory)
    with closing(connect(directory / "approvals.sqlite")) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY, payload TEXT NOT NULL, registered_id INTEGER
        )""")
    with closing(connect(directory / "orders.sqlite")) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY, approval_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL
        )""")


def crash_if(point, crash):
    if point == crash:
        os._exit(77)


def approve(directory, approval_id, order, crash=None):
    if not approval_id:
        raise ValueError("Approval identifier is required.")
    payload = json.dumps(order, ensure_ascii=False, sort_keys=True)
    with closing(connect(directory / "approvals.sqlite")) as db:
        with db:
            db.execute("INSERT INTO approvals(approval_id, payload) VALUES (?, ?) "
                       "ON CONFLICT(approval_id) DO NOTHING", (approval_id, payload))
            row = db.execute("SELECT payload FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if row[0] != payload:
                raise ValueError("Approval identifier already binds another order.")
            crash_if("before_approval_commit", crash)
        crash_if("after_approval_commit", crash)


def register(directory, approval_id, payload, crash):
    with closing(connect(directory / "orders.sqlite")) as db:
        with db:
            db.execute("INSERT INTO orders(approval_id, payload) VALUES (?, ?) "
                       "ON CONFLICT(approval_id) DO NOTHING", (approval_id, payload))
            order_id, actual = db.execute("SELECT order_id, payload FROM orders WHERE approval_id=?",
                                          (approval_id,)).fetchone()
            if actual != payload:
                raise ValueError("Registration key already binds another order.")
            crash_if("before_registry_commit", crash)
        crash_if("after_registry_commit_before_reply", crash)
    return order_id


def dispatch(directory, crash=None):
    with closing(connect(directory / "approvals.sqlite")) as db:
        pending = db.execute("SELECT approval_id, payload FROM approvals "
                             "WHERE registered_id IS NULL ORDER BY rowid").fetchall()
        receipts = {}
        for approval_id, payload in pending:
            order_id = register(directory, approval_id, payload, crash)
            crash_if("after_registry_reply", crash)
            with db:
                db.execute("UPDATE approvals SET registered_id=? "
                           "WHERE approval_id=? AND registered_id IS NULL", (order_id, approval_id))
                crash_if("before_ack_commit", crash)
            crash_if("after_ack_commit", crash)
            receipts[approval_id] = order_id
    return receipts


def receipt(directory, approval_id):
    with closing(connect(directory / "approvals.sqlite")) as db:
        row = db.execute("SELECT registered_id FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    return row[0] if row else None


def registry(directory):
    with closing(connect(directory / "orders.sqlite")) as db:
        return {key: (order_id, json.loads(payload)) for key, order_id, payload in db.execute(
            "SELECT approval_id, order_id, payload FROM orders")}
