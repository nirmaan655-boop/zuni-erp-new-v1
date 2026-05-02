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


# Idempotent ALTER TABLE migrations (added later)
_ALTER_COLUMNS = [
    ("calvings", "sire_tag", "TEXT"),
    ("calvings", "calf1_weight", "DOUBLE PRECISION DEFAULT 0"),
    ("calvings", "calf2_weight", "DOUBLE PRECISION DEFAULT 0"),
    ("calvings", "delivery_status", "TEXT DEFAULT 'Normal'"),
    ("calvings", "complications", "TEXT"),
    ("animals", "is_pregnant", "INTEGER DEFAULT 0"),
    ("animals", "is_dry", "INTEGER DEFAULT 0"),
    ("animals", "category", "TEXT DEFAULT 'Milking Cow'"),
    ("animals", "purchase_value", "DOUBLE PRECISION DEFAULT 0"),
    ("animals", "preg_start_date", "DATE"),
    ("animals", "expected_calving_date", "DATE"),
    ("animals", "last_ai_date", "DATE"),
    ("animals", "last_calving_date", "DATE"),
    ("breeding_events", "expected_calving_date", "DATE"),
    ("breeding_events", "ai_event_id", "INTEGER"),
    ("journal_lines", "party_id", "INTEGER"),
    ("milk_store_moves", "pen_id", "INTEGER"),
    ("milk_store_moves", "expense_code", "TEXT"),
]


_INIT_DONE = False


def init_db():
    """Create schema, run column-level migrations, and seed defaults.

    Uses an advisory lock to safely serialize concurrent initialization
    attempts from multiple Streamlit sessions.
    """
    global _INIT_DONE
    if _INIT_DONE:
        return
    with get_conn() as c:
        cur = c.cursor()
        # Serialize concurrent init across processes/sessions
        cur.execute("SELECT pg_advisory_xact_lock(73482911)")
        # Schema
        cur.execute(SCHEMA_SQL)

        # Idempotent column adds
        for table, col, decl in _ALTER_COLUMNS:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {decl}"
            )

        # ---- Seed defaults ----
        cur.execute("SELECT COUNT(*) AS n FROM stores")
        if cur.fetchone()["n"] == 0:
            for s in ["Feed Store", "Medicine Store", "Vaccine Store",
                      "Semen Store", "Fuel & General Store"]:
                cur.execute("INSERT INTO stores(name) VALUES(%s)", (s,))

        cur.execute("SELECT COUNT(*) AS n FROM accounts")
        if cur.fetchone()["n"] == 0:
            coa = [
                ("1000", "Cash", "Asset"),
                ("1100", "Bank", "Asset"),
                ("1200", "Inventory", "Asset"),
                ("1300", "Livestock Asset", "Asset"),
                ("1400", "Accounts Receivable", "Asset"),
                ("2000", "Accounts Payable", "Liability"),
                ("3000", "Owner Equity", "Equity"),
                ("4000", "Milk Sales", "Income"),
                ("4100", "Animal Sales", "Income"),
                ("5000", "Feed Expense", "Expense"),
                ("5100", "Medicine Expense", "Expense"),
                ("5200", "Salary Expense", "Expense"),
                ("5300", "General Expense", "Expense"),
                ("5400", "Animal Purchase", "Expense"),
                ("5500", "Calf Milk Cost", "Expense"),
                ("5510", "Mess Milk Cost", "Expense"),
                ("5520", "Farm Use Milk Cost", "Expense"),
                ("5600", "Breeding & Semen Expense", "Expense"),
            ]
            for code, name, t in coa:
                cur.execute(
                    "INSERT INTO accounts(code,name,type) VALUES(%s,%s,%s)",
                    (code, name, t),
                )

        cur.execute("SELECT COUNT(*) AS n FROM vaccine_schedules")
        if cur.fetchone()["n"] == 0:
            for n, d, note in [
                ("FMD (Foot & Mouth)", 180, "Every 6 months"),
                ("HS (Haemorrhagic Septicaemia)", 365, "Yearly"),
                ("Black Quarter (BQ)", 365, "Yearly"),
                ("Brucellosis", 730, "Once for heifers 4-8 months"),
                ("LSD (Lumpy Skin Disease)", 365, "Yearly"),
                ("Theileriosis", 365, "Yearly, calves"),
                ("Anthrax", 365, "Yearly in endemic areas"),
                ("Deworming", 90, "Every 3 months"),
            ]:
                cur.execute(
                    "INSERT INTO vaccine_schedules(name, interval_days, note) "
                    "VALUES(%s,%s,%s)", (n, d, note),
                )

        cur.execute("SELECT COUNT(*) AS n FROM users")
        if cur.fetchone()["n"] == 0:
            for u, pw, fn, role in [
                ("admin", "admin123", "System Admin", "Admin"),
                ("vet", "vet123", "Farm Vet", "Vet"),
                ("account", "account123", "Accountant", "Accountant"),
            ]:
                cur.execute(
                    "INSERT INTO users(username, password_hash, full_name, role) "
                    "VALUES(%s,%s,%s,%s)",
                    (u, hash_password(pw), fn, role),
                )

        cur.execute("SELECT COUNT(*) AS n FROM ai_protocols")
        if cur.fetchone()["n"] == 0:
            for n, d in [
                ("Ovsynch", "GnRH (d0) → PGF2α (d7) → GnRH (d9) → AI (d10)"),
                ("CIDR-Synch", "CIDR insert + GnRH (d0) → CIDR remove + PGF (d7) → GnRH + AI (d9)"),
                ("Double Ovsynch", "Pre-Ovsynch + Ovsynch sequence"),
                ("Modified Ovsynch", "GnRH-7d-PGF-56h-GnRH-16h-AI"),
                ("Presynch-Ovsynch", "PGF (d0) → PGF (d14) → Ovsynch (d26)"),
                ("Heat Detection + AI", "AM/PM rule — AI 12 hrs after observed standing heat"),
                ("GnRH + PGF2α", "Single GnRH followed by PGF2α at 7 days"),
                ("5-day CIDR", "CIDR for 5 days + PGF + GnRH + AI"),
            ]:
                cur.execute(
                    "INSERT INTO ai_protocols(name, description) VALUES(%s,%s)",
                    (n, d),
                )

        cur.execute("SELECT COUNT(*) AS n FROM farms")
        if cur.fetchone()["n"] == 0:
            cur.execute("INSERT INTO farms(name, location) VALUES(%s,%s)",
                        ("Main Farm", "HQ"))

    _INIT_DONE = True


# ---------------- Generic helpers ----------------
def query(sql, params=()):
    """SELECT helper. Returns list of dicts."""
    sql_t = _translate_sql(sql)
    with get_conn() as c:
        cur = c.cursor()
        cur.execute(sql_t, params)
        try:
            rows = cur.fetchall()
        except psycopg2.ProgrammingError:
            return []
        return [dict(r) for r in rows]


def execute(sql, params=()):
    """INSERT/UPDATE/DELETE helper. Returns the new PK for INSERTs."""
    sql_t = _translate_sql(sql)
    is_insert = sql_t.lstrip().upper().startswith("INSERT")
    has_returning = "RETURNING" in sql_t.upper()

    with get_conn() as c:
        cur = c.cursor()
        if is_insert and not has_returning:
            sql_t = sql_t.rstrip().rstrip(";") + " RETURNING *"
        cur.execute(sql_t, params)
        if is_insert:
            try:
                row = cur.fetchone()
                if row is None:
                    return None
                # Find the PK: prefer "<table>_id", then "id", else first column
                m = _INSERT_TABLE_RE.match(sql_t)
                if m:
                    table = m.group(1).lower()
                    pk_candidate = f"{table[:-1]}_id" if table.endswith("s") else f"{table}_id"
                    if pk_candidate in row:
                        return row[pk_candidate]
                if "id" in row:
                    return row["id"]
                # Fall back: first value
                return next(iter(row.values()))
            except psycopg2.ProgrammingError:
                return None
        return None


def get_account_id(code):
    r = query("SELECT account_id FROM accounts WHERE code=?", (code,))
    return r[0]["account_id"] if r else None


def post_journal(entry_date, description, lines, ref_type=None, ref_id=None):
    """lines: list of (account_code, debit, credit) or (account_code, debit, credit, party_id)"""
    with get_conn() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO journal_entries(entry_date, description, ref_type, ref_id) "
            "VALUES(%s,%s,%s,%s) RETURNING entry_id",
            (str(entry_date), description, ref_type, ref_id),
        )
        eid = cur.fetchone()["entry_id"]
        for ln in lines:
            if len(ln) == 4:
                code, debit, credit, pid = ln
            else:
                code, debit, credit = ln
                pid = None
            cur.execute("SELECT account_id FROM accounts WHERE code=%s", (code,))
            acc = cur.fetchone()
            if not acc:
                continue
            cur.execute(
                "INSERT INTO journal_lines(entry_id, account_id, debit, credit, party_id) "
                "VALUES(%s,%s,%s,%s,%s)",
                (eid, acc["account_id"], debit, credit, pid),
            )
        return eid


def add_stock_move(item_id, move_date, move_type, qty, unit_cost=0,
                   ref_type=None, ref_id=None, note=None):
    return execute(
        "INSERT INTO stock_moves(item_id,move_date,move_type,qty,unit_cost,ref_type,ref_id,note) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (item_id, str(move_date), move_type, qty, unit_cost, ref_type, ref_id, note),
    )


def add_milk_move(move_date, move_type, litres, use_type, rate=0,
                  ref_type=None, ref_id=None, note=None,
                  pen_id=None, expense_code=None):
    return execute(
        "INSERT INTO milk_store_moves(move_date,move_type,litres,use_type,rate,"
        "ref_type,ref_id,note,pen_id,expense_code) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (str(move_date), move_type, litres, use_type, rate,
         ref_type, ref_id, note, pen_id, expense_code),
    )


def milk_store_balance():
    r = query(
        "SELECT COALESCE(SUM(CASE WHEN move_type='IN' THEN litres ELSE -litres END),0) AS bal "
        "FROM milk_store_moves")
    return float(r[0]["bal"]) if r else 0


def latest_milk_rate():
    r = query("SELECT unit_price FROM sales WHERE kind='Milk' ORDER BY sale_id DESC LIMIT 1")
    return float(r[0]["unit_price"]) if r else 0


def account_balance(code):
    r = query("""
        SELECT a.type, COALESCE(SUM(l.debit),0) dr, COALESCE(SUM(l.credit),0) cr
        FROM accounts a LEFT JOIN journal_lines l ON l.account_id=a.account_id
        WHERE a.code=? GROUP BY a.account_id, a.type
    """, (code,))
    if not r:
        return 0
    row = r[0]
    if row["type"] in ("Asset", "Expense"):
        return float(row["dr"] or 0) - float(row["cr"] or 0)
    return float(row["cr"] or 0) - float(row["dr"] or 0)


def stock_balance(item_id):
    r = query(
        "SELECT COALESCE(SUM(CASE WHEN move_type='IN' THEN qty ELSE -qty END),0) AS bal "
        "FROM stock_moves WHERE item_id=?", (item_id,))
    return float(r[0]["bal"]) if r else 0


# ---------------- Auth helpers ----------------
def hash_password(pw: str) -> str:
    return hashlib.sha256(("zuni::" + pw).encode("utf-8")).hexdigest()


def verify_user(username: str, password: str):
    r = query("SELECT user_id, username, full_name, role, active "
              "FROM users WHERE username=? AND password_hash=?",
              (username, hash_password(password)))
    if r and r[0]["active"]:
        return r[0]
    return None


# ---------------- Role permissions ----------------
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
