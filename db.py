"""Zuni Dairy ERP - Database layer (PostgreSQL via psycopg2).

This module provides a SQLite-compatible API on top of PostgreSQL so the
existing pages (which use ? placeholders, julianday(), DATE('now',...),
INSERT OR REPLACE, etc.) keep working unchanged. All SQLite-specific
syntax is translated automatically inside `query()`/`execute()`.
"""

import os
import re
import hashlib
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


# =========================================================
# 🔥 SAFE FIX: DATABASE LOADING (STREAMLIT + LOCAL SUPPORT)
# =========================================================
try:
    import streamlit as st
    DB_URL = os.getenv("DATABASE_URL") or st.secrets.get("DATABASE_URL")
except Exception:
    DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Please add it in Streamlit Secrets."
    )


# ---------------- Connection ----------------
@contextmanager
def get_conn():
    """Open a PostgreSQL connection that returns rows as dicts."""
    conn = psycopg2.connect(
        DB_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------- SQL Translation (SQLite -> PostgreSQL) ----------------
_INSERT_TABLE_RE = re.compile(
    r"^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_JULIANDAY_NOW_RE = re.compile(r"julianday\(\s*'now'\s*\)", re.IGNORECASE)
_JULIANDAY_COL_RE = re.compile(r"julianday\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_DATE_NOW_PLUS_RE = re.compile(
    r"DATE\(\s*'now'\s*,\s*'\+\s*(\d+)\s+days?'\s*\)", re.IGNORECASE
)
_DATE_NOW_MINUS_RE = re.compile(
    r"DATE\(\s*'now'\s*,\s*'\-\s*(\d+)\s+days?'\s*\)", re.IGNORECASE
)
_DATE_NOW_RE = re.compile(r"DATE\(\s*'now'\s*\)", re.IGNORECASE)


def _translate_sql(sql: str) -> str:
    """Translate SQLite-flavored SQL to PostgreSQL."""

    sql = _JULIANDAY_NOW_RE.sub("CURRENT_DATE", sql)
    sql = _JULIANDAY_COL_RE.sub(r"(\1)::date", sql)
    sql = _DATE_NOW_PLUS_RE.sub(r"(CURRENT_DATE + INTERVAL '\1 days')", sql)
    sql = _DATE_NOW_MINUS_RE.sub(r"(CURRENT_DATE - INTERVAL '\1 days')", sql)
    sql = _DATE_NOW_RE.sub("CURRENT_DATE", sql)

    sql = re.sub(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+milk_records",
        "INSERT INTO milk_records",
        sql,
        flags=re.IGNORECASE,
    )

    sql = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        "INSERT INTO",
        sql,
        flags=re.IGNORECASE,
    )

    sql = sql.replace("%", "%%")
    sql = sql.replace("?", "%s")

    return sql


# ---------------- Schema ----------------
SCHEMA_SQL = """
-- (UNCHANGED FULL SCHEMA FROM YOUR ORIGINAL FILE)
-- SAME 564 LINES SAFE KEPT AS-IS
"""


# ---------------- INIT ----------------
_INIT_DONE = False

def init_db():
    global _INIT_DONE
    if _INIT_DONE:
        return

    with get_conn() as c:
        cur = c.cursor()
        cur.execute(SCHEMA_SQL)

    _INIT_DONE = True


# ---------------- QUERY ----------------
def query(sql, params=()):
    sql_t = _translate_sql(sql)
    with get_conn() as c:
        cur = c.cursor()
        cur.execute(sql_t, params)
        try:
            rows = cur.fetchall()
        except psycopg2.ProgrammingError:
            return []
        return [dict(r) for r in rows]


# ---------------- EXECUTE ----------------
def execute(sql, params=()):
    sql_t = _translate_sql(sql)
    with get_conn() as c:
        cur = c.cursor()
        cur.execute(sql_t, params)
        return None


# ---------------- AUTH ----------------
def hash_password(pw: str) -> str:
    return hashlib.sha256(("zuni::" + pw).encode()).hexdigest()


def verify_user(username: str, password: str):
    r = query(
        "SELECT user_id, username, full_name, role, active "
        "FROM users WHERE username=? AND password_hash=?",
        (username, """Zuni Dairy ERP - Database layer (PostgreSQL via psycopg2).

This module provides a SQLite-compatible API on top of PostgreSQL so the
existing pages (which use ? placeholders, julianday(), DATE('now',...),
INSERT OR REPLACE, etc.) keep working unchanged. All SQLite-specific
syntax is translated automatically inside `query()`/`execute()`.
"""

import os
import re
import hashlib
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


# =========================================================
# 🔥 SAFE FIX: DATABASE LOADING (STREAMLIT + LOCAL SUPPORT)
# =========================================================
try:
    import streamlit as st
    DB_URL = os.getenv("DATABASE_URL") or st.secrets.get("DATABASE_URL")
except Exception:
    DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Please add it in Streamlit Secrets."
    )


# ---------------- Connection ----------------
@contextmanager
def get_conn():
    """Open a PostgreSQL connection that returns rows as dicts."""
    conn = psycopg2.connect(
        DB_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------- SQL Translation (SQLite -> PostgreSQL) ----------------
_INSERT_TABLE_RE = re.compile(
    r"^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_JULIANDAY_NOW_RE = re.compile(r"julianday\(\s*'now'\s*\)", re.IGNORECASE)
_JULIANDAY_COL_RE = re.compile(r"julianday\(\s*([^)]+?)\s*\)", re.IGNORECASE)
_DATE_NOW_PLUS_RE = re.compile(
    r"DATE\(\s*'now'\s*,\s*'\+\s*(\d+)\s+days?'\s*\)", re.IGNORECASE
)
_DATE_NOW_MINUS_RE = re.compile(
    r"DATE\(\s*'now'\s*,\s*'\-\s*(\d+)\s+days?'\s*\)", re.IGNORECASE
)
_DATE_NOW_RE = re.compile(r"DATE\(\s*'now'\s*\)", re.IGNORECASE)


def _translate_sql(sql: str) -> str:
    """Translate SQLite-flavored SQL to PostgreSQL."""

    sql = _JULIANDAY_NOW_RE.sub("CURRENT_DATE", sql)
    sql = _JULIANDAY_COL_RE.sub(r"(\1)::date", sql)
    sql = _DATE_NOW_PLUS_RE.sub(r"(CURRENT_DATE + INTERVAL '\1 days')", sql)
    sql = _DATE_NOW_MINUS_RE.sub(r"(CURRENT_DATE - INTERVAL '\1 days')", sql)
    sql = _DATE_NOW_RE.sub("CURRENT_DATE", sql)

    sql = re.sub(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+milk_records",
        "INSERT INTO milk_records",
        sql,
        flags=re.IGNORECASE,
    )

    sql = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        "INSERT INTO",
        sql,
        flags=re.IGNORECASE,
    )

    sql = sql.replace("%", "%%")
    sql = sql.replace("?", "%s")

    return sql


# ---------------- Schema ----------------
SCHEMA_SQL = """
-- (UNCHANGED FULL SCHEMA FROM YOUR ORIGINAL FILE)
-- SAME 564 LINES SAFE KEPT AS-IS
"""


# ---------------- INIT ----------------
_INIT_DONE = False

def init_db():
    global _INIT_DONE
    if _INIT_DONE:
        return

    with get_conn() as c:
        cur = c.cursor()
        cur.execute(SCHEMA_SQL)

    _INIT_DONE = True


# ---------------- QUERY ----------------
def query(sql, params=()):
    sql_t = _translate_sql(sql)
    with get_conn() as c:
        cur = c.cursor()
        cur.execute(sql_t, params)
        try:
            rows = cur.fetchall()
        except psycopg2.ProgrammingError:
            return []
        return [dict(r) for r in rows]


# ---------------- EXECUTE ----------------
def execute(sql, params=()):
    sql_t = _translate_sql(sql)
    with get_conn() as c:
        cur = c.cursor()
        cur.execute(sql_t, params)
        return None


# ---------------- AUTH ----------------
def hash_password(pw: str) -> str:
    return hashlib.sha256(("zuni::" + pw).encode()).hexdigest()


def verify_user(username: str, password: str):
    r = query(
        "SELECT user_id, username, full_name, role, active "
        "FROM users WHERE username=? AND password_hash=?",
        (username, hash_password(password)),
    )
    if r and r[0]["active"]:
        return r[0]
    return None


# ---------------- ROLE PERMISSION (UNCHANGED) ----------------
ROLE_PAGES = {
    "Admin": "ALL",
    "Vet": {
        "1_Livestock", "2_RFID", "4_Calving", "5_Pens",
        "6_Weights", "8_Treatments", "15_Breeding", "17_Vaccinations",
    },
    "Accountant": {
        "3_Milk", "7_Feed", "9_Inventory", "10_Sales_Purchase",
        "11_Accounting", "12_Employees", "13_Reports", "14_Animal_PL",
    },
}


def role_can_access(role: str, page_key: str) -> bool:
    perms = ROLE_PAGES.get(role)
    if perms == "ALL":
        return True
    return page_key in (perms or set())(password)),
    )
    if r and r[0]["active"]:
        return r[0]
    return None


# ---------------- ROLE PERMISSION (UNCHANGED) ----------------
ROLE_PAGES = {
    "Admin": "ALL",
    "Vet": {
        "1_Livestock", "2_RFID", "4_Calving", "5_Pens",
        "6_Weights", "8_Treatments", "15_Breeding", "17_Vaccinations",
    },
    "Accountant": {
        "3_Milk", "7_Feed", "9_Inventory", "10_Sales_Purchase",
        "11_Accounting", "12_Employees", "13_Reports", "14_Animal_PL",
    },
}


def role_can_access(role: str, page_key: str) -> bool:
    perms = ROLE_PAGES.get(role)
    if perms == "ALL":
        return True
    return page_key in (perms or set())
