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


DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Provision a PostgreSQL database first."
    )


# ---------------- Connection ----------------
@contextmanager
def get_conn():
    """Open a PostgreSQL connection that returns rows as dicts."""
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
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
    # 1. Date arithmetic
    sql = _JULIANDAY_NOW_RE.sub("CURRENT_DATE", sql)
    sql = _JULIANDAY_COL_RE.sub(r"(\1)::date", sql)
    sql = _DATE_NOW_PLUS_RE.sub(r"(CURRENT_DATE + INTERVAL '\1 days')", sql)
    sql = _DATE_NOW_MINUS_RE.sub(r"(CURRENT_DATE - INTERVAL '\1 days')", sql)
    sql = _DATE_NOW_RE.sub("CURRENT_DATE", sql)

    # 2. INSERT OR REPLACE INTO milk_records
    if re.search(r"INSERT\s+OR\s+REPLACE\s+INTO\s+milk_records", sql, re.IGNORECASE):
        sql = re.sub(
            r"INSERT\s+OR\s+REPLACE\s+INTO\s+milk_records",
            "INSERT INTO milk_records",
            sql,
            flags=re.IGNORECASE,
        )
        if "ON CONFLICT" not in sql.upper():
            sql += (
                " ON CONFLICT (animal_id, record_date, shift) "
                "DO UPDATE SET litres = EXCLUDED.litres"
            )

    # 3. Generic INSERT OR IGNORE -> ON CONFLICT DO NOTHING
    sql = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO",
        "INSERT INTO",
        sql,
        flags=re.IGNORECASE,
    )

    # 4. Escape literal % (e.g. inside LIKE '%Cash%') so psycopg2 does
    #    not treat them as parameter placeholders, then convert SQLite
    #    `?` placeholders into psycopg2 `%s` placeholders.
    sql = sql.replace("%", "%%")
    sql = sql.replace("?", "%s")

    return sql


# ---------------- Schema (PostgreSQL) ----------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS farms (
    farm_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT
);

CREATE TABLE IF NOT EXISTS pens (
    pen_id SERIAL PRIMARY KEY,
    farm_id INTEGER NOT NULL REFERENCES farms(farm_id),
    name TEXT NOT NULL,
    capacity INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS animals (
    animal_id SERIAL PRIMARY KEY,
    tag TEXT UNIQUE NOT NULL,
    rfid_tag TEXT UNIQUE,
    breed TEXT,
    dob DATE,
    sex TEXT DEFAULT 'F',
    status TEXT DEFAULT 'Active',
    farm_id INTEGER REFERENCES farms(farm_id),
    pen_id INTEGER REFERENCES pens(pen_id),
    mother_id INTEGER REFERENCES animals(animal_id),
    created_at DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS animal_movements (
    id SERIAL PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(animal_id),
    from_pen_id INTEGER REFERENCES pens(pen_id),
    to_pen_id INTEGER REFERENCES pens(pen_id),
    move_date DATE NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS rfid_scans (
    id SERIAL PRIMARY KEY,
    rfid_tag TEXT NOT NULL,
    animal_id INTEGER REFERENCES animals(animal_id),
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    location TEXT
);

CREATE TABLE IF NOT EXISTS milk_records (
    id SERIAL PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(animal_id),
    record_date DATE NOT NULL,
    shift TEXT NOT NULL,
    litres DOUBLE PRECISION NOT NULL,
    UNIQUE(animal_id, record_date, shift)
);

CREATE TABLE IF NOT EXISTS calvings (
    id SERIAL PRIMARY KEY,
    mother_id INTEGER NOT NULL REFERENCES animals(animal_id),
    calving_date DATE NOT NULL,
    calving_type TEXT NOT NULL,
    calf1_id INTEGER REFERENCES animals(animal_id),
    calf2_id INTEGER REFERENCES animals(animal_id),
    note TEXT
);

CREATE TABLE IF NOT EXISTS weights (
    id SERIAL PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(animal_id),
    weight_date DATE NOT NULL,
    weight_kg DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS stores (
    store_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    item_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    store_id INTEGER NOT NULL REFERENCES stores(store_id),
    uom TEXT NOT NULL DEFAULT 'kg',
    unit_cost DOUBLE PRECISION DEFAULT 0,
    UNIQUE(name, store_id)
);

CREATE TABLE IF NOT EXISTS feed_recipes (
    recipe_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS feed_recipe_items (
    id SERIAL PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES feed_recipes(recipe_id),
    item_id INTEGER NOT NULL REFERENCES items(item_id),
    qty DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_allocations (
    id SERIAL PRIMARY KEY,
    pen_id INTEGER NOT NULL REFERENCES pens(pen_id),
    recipe_id INTEGER NOT NULL REFERENCES feed_recipes(recipe_id),
    alloc_date DATE NOT NULL,
    servings DOUBLE PRECISION NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS diseases (
    disease_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS treatments (
    id SERIAL PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(animal_id),
    treat_date DATE NOT NULL,
    disease_id INTEGER REFERENCES diseases(disease_id),
    medicine_item_id INTEGER REFERENCES items(item_id),
    qty DOUBLE PRECISION NOT NULL,
    uom TEXT,
    cost DOUBLE PRECISION DEFAULT 0,
    note TEXT
);

CREATE TABLE IF NOT EXISTS stock_moves (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(item_id),
    move_date DATE NOT NULL,
    move_type TEXT NOT NULL,
    qty DOUBLE PRECISION NOT NULL,
    unit_cost DOUBLE PRECISION DEFAULT 0,
    ref_type TEXT,
    ref_id INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS parties (
    party_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    party_type TEXT NOT NULL,
    phone TEXT,
    address TEXT
);

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id SERIAL PRIMARY KEY,
    purchase_date DATE NOT NULL,
    vendor_id INTEGER REFERENCES parties(party_id),
    item_id INTEGER REFERENCES items(item_id),
    animal_id INTEGER REFERENCES animals(animal_id),
    qty DOUBLE PRECISION NOT NULL,
    unit_cost DOUBLE PRECISION NOT NULL,
    total DOUBLE PRECISION NOT NULL,
    kind TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id SERIAL PRIMARY KEY,
    sale_date DATE NOT NULL,
    customer_id INTEGER REFERENCES parties(party_id),
    kind TEXT NOT NULL,
    animal_id INTEGER REFERENCES animals(animal_id),
    qty DOUBLE PRECISION NOT NULL,
    unit_price DOUBLE PRECISION NOT NULL,
    total DOUBLE PRECISION NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    entry_id SERIAL PRIMARY KEY,
    entry_date DATE NOT NULL,
    description TEXT,
    ref_type TEXT,
    ref_id INTEGER
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id SERIAL PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES journal_entries(entry_id),
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    debit DOUBLE PRECISION DEFAULT 0,
    credit DOUBLE PRECISION DEFAULT 0
);

CREATE TABLE IF NOT EXISTS employees (
    emp_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    phone TEXT,
    salary DOUBLE PRECISION DEFAULT 0,
    farm_id INTEGER REFERENCES farms(farm_id)
);

CREATE TABLE IF NOT EXISTS salary_payments (
    id SERIAL PRIMARY KEY,
    emp_id INTEGER NOT NULL REFERENCES employees(emp_id),
    pay_date DATE NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    exp_date DATE NOT NULL,
    category TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS bulls (
    bull_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    breed TEXT,
    bull_type TEXT DEFAULT 'AI',
    note TEXT
);

CREATE TABLE IF NOT EXISTS ai_protocols (
    protocol_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS breeding_events (
    event_id SERIAL PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(animal_id),
    event_date DATE NOT NULL,
    event_type TEXT NOT NULL,
    bull_id INTEGER REFERENCES bulls(bull_id),
    semen_item_id INTEGER REFERENCES items(item_id),
    straws_used DOUBLE PRECISION DEFAULT 0,
    cost DOUBLE PRECISION DEFAULT 0,
    protocol_id INTEGER REFERENCES ai_protocols(protocol_id),
    result TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'Vet',
    active INTEGER DEFAULT 1,
    created_at DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS milk_store_moves (
    id SERIAL PRIMARY KEY,
    move_date DATE NOT NULL,
    move_type TEXT NOT NULL,
    litres DOUBLE PRECISION NOT NULL,
    use_type TEXT,
    rate DOUBLE PRECISION DEFAULT 0,
    ref_type TEXT,
    ref_id INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS vaccine_schedules (
    sched_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    interval_days INTEGER DEFAULT 180,
    note TEXT
);

CREATE TABLE IF NOT EXISTS vaccinations (
    vacc_id SERIAL PRIMARY KEY,
    animal_id INTEGER NOT NULL REFERENCES animals(animal_id),
    vacc_date DATE NOT NULL,
    sched_id INTEGER REFERENCES vaccine_schedules(sched_id),
    vaccine_name TEXT NOT NULL,
    item_id INTEGER REFERENCES items(item_id),
    qty DOUBLE PRECISION DEFAULT 1,
    cost DOUBLE PRECISION DEFAULT 0,
    next_due DATE,
    note TEXT
);
"""
