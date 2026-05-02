"""Admin: Edit / Delete Records.

Lets the Admin user fix wrong entries across the system. Picks a table,
loads recent records, then shows an edit form for any selected row, with
a Save and a Delete button. All changes are logged to admin_audit_log.
"""
import streamlit as st
from datetime import date, datetime
import pandas as pd
from auth import require_login, render_user_sidebar
from db import query, execute, get_conn
from utils import export_excel_button

st.set_page_config(page_title="Admin: Edit Records", layout="wide")

user = require_login()
render_user_sidebar()

if user.get("role") != "Admin":
    st.error("Access denied — only Admin users can edit / delete records.")
    st.info("Contact Admin to fix wrong entries.")
    st.stop()

st.title("Admin — Edit / Delete Records")
st.caption(
    "Use this page carefully — changes are saved immediately. "
    "Every edit and delete is logged in the audit trail at the bottom."
)


# ---------------- Audit log table ----------------
def _ensure_audit_table():
    with get_conn() as c:
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                action TEXT,
                table_name TEXT,
                record_id INTEGER,
                before_json TEXT,
                after_json TEXT,
                note TEXT
            )
        """)


_ensure_audit_table()


def log_audit(action, table_name, record_id, before, after, note=""):
    import json
    def _ser(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v
    b = json.dumps({k: _ser(v) for k, v in (before or {}).items()},
                   default=str) if before else None
    a = json.dumps({k: _ser(v) for k, v in (after or {}).items()},
                   default=str) if after else None
    execute(
        "INSERT INTO admin_audit_log("
        "username, action, table_name, record_id, before_json, after_json, note"
        ") VALUES(?,?,?,?,?,?,?)",
        (user["username"], action, table_name, record_id, b, a, note),
    )


# ---------------- Lookup loaders (cached per-rerun) ----------------
def _animals():
    return query("SELECT animal_id, tag FROM animals ORDER BY tag")


def _items():
    return query(
        "SELECT i.item_id, i.name, s.name AS store FROM items i "
        "JOIN stores s ON s.store_id=i.store_id ORDER BY s.name, i.name"
    )


def _pens():
    return query("SELECT pen_id, name FROM pens ORDER BY name")


def _parties(kind=None):
    if kind:
        return query(
            "SELECT party_id, name, party_type FROM parties "
            "WHERE party_type=? ORDER BY name", (kind,))
    return query("SELECT party_id, name, party_type FROM parties ORDER BY name")


def _employees():
    return query("SELECT emp_id, name FROM employees ORDER BY name")


def _accounts():
    return query("SELECT account_id, code, name FROM accounts ORDER BY code")


def _recipes():
    return query("SELECT recipe_id, name FROM feed_recipes ORDER BY name")


def _bulls():
    return query("SELECT bull_id, name FROM bulls ORDER BY name")


def _protocols():
    return query("SELECT protocol_id, name FROM ai_protocols ORDER BY name")


def _diseases():
    return query("SELECT disease_id, name FROM diseases ORDER BY name")


def _schedules():
    return query("SELECT sched_id, name FROM vaccine_schedules ORDER BY name")


def _farms():
    return query("SELECT farm_id, name FROM farms ORDER BY name")


# ---------------- Field rendering helpers ----------------
def _ref_widget(label, rows, value_col, label_cols, current_id, key):
    """Generic reference dropdown. Returns selected ID (or None)."""
    options = [(None, "— (none) —")] + [
        (r[value_col],
         " / ".join(str(r.get(c, "")) for c in label_cols if r.get(c) is not None)
         + f"  [#{r[value_col]}]")
        for r in rows
    ]
    ids = [o[0] for o in options]
    labels = [o[1] for o in options]
    idx = ids.index(current_id) if current_id in ids else 0
    pick = st.selectbox(label, range(len(options)), index=idx,
                        format_func=lambda i: labels[i], key=key)
    return ids[pick]


def _date_or_none(v):
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except Exception:
        return None


def _render_field(field, current_value, key_prefix):
    """Render one editor input. Returns the new value (Python type)."""
    col = field["col"]
    label = field.get("label", col)
    ftype = field.get("type", "text")
    key = f"{key_prefix}__{col}"

    if ftype == "text":
        return st.text_input(label, value=current_value or "", key=key)
    if ftype == "textarea":
        return st.text_area(label, value=current_value or "", key=key, height=80)
    if ftype == "int":
        return int(st.number_input(
            label, value=int(current_value or 0), step=1, key=key))
    if ftype == "bool_int":
        return 1 if st.checkbox(
            label, value=bool(current_value), key=key) else 0
    if ftype == "float":
        return float(st.number_input(
            label, value=float(current_value or 0.0),
            step=field.get("step", 0.1),
            min_value=field.get("min", 0.0), key=key))
    if ftype == "date":
        # Preserve NULL: if DB value is None, render an empty date input
        # so saving without touching it does NOT create a false update.
        d = _date_or_none(current_value)
        return st.date_input(label, value=d, key=key, format="YYYY-MM-DD")
    if ftype == "select":
        opts = field["options"]
        idx = opts.index(current_value) if current_value in opts else 0
        return st.selectbox(label, opts, index=idx, key=key)
    if ftype == "ref":
        rows = field["loader"]()
        return _ref_widget(label, rows, field["value_col"],
                           field["label_cols"], current_value, key)
    return st.text_input(label, value=str(current_value or ""), key=key)


# ---------------- Table configurations ----------------
def _animal_options():
    return _animals()


TABLES = {
    "Animals (Livestock)": {
        "table": "animals", "pk": "animal_id",
        "list_cols": ["animal_id", "tag", "breed", "sex", "category",
                      "status", "is_pregnant", "dob"],
        "order_by": "animal_id DESC", "limit": 500,
        "fields": [
            {"col": "tag", "label": "Tag", "type": "text"},
            {"col": "rfid_tag", "label": "RFID Tag", "type": "text"},
            {"col": "breed", "label": "Breed", "type": "text"},
            {"col": "category", "label": "Category", "type": "select",
             "options": ["Milking Cow", "Dry Cow", "Heifer", "Calf",
                         "Bull", "Other"]},
            {"col": "sex", "label": "Sex", "type": "select",
             "options": ["F", "M"]},
            {"col": "status", "label": "Status", "type": "select",
             "options": ["Active", "Sold", "Dead", "Culled"]},
            {"col": "dob", "label": "Date of Birth", "type": "date"},
            {"col": "is_pregnant", "label": "Pregnant?", "type": "bool_int"},
            {"col": "is_dry", "label": "Dry?", "type": "bool_int"},
            {"col": "purchase_value", "label": "Purchase Value",
             "type": "float", "step": 100.0},
            {"col": "farm_id", "label": "Farm", "type": "ref",
             "loader": _farms, "value_col": "farm_id",
             "label_cols": ["name"]},
            {"col": "pen_id", "label": "Pen", "type": "ref",
             "loader": _pens, "value_col": "pen_id",
             "label_cols": ["name"]},
            {"col": "mother_id", "label": "Mother", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
        ],
    },
    "Milk Records": {
        "table": "milk_records", "pk": "id",
        "list_cols": ["id", "record_date", "shift", "animal_id", "litres"],
        "order_by": "record_date DESC, id DESC", "limit": 300,
        "date_col": "record_date",
        "fields": [
            {"col": "record_date", "label": "Date", "type": "date"},
            {"col": "shift", "label": "Shift", "type": "select",
             "options": ["Morning", "Evening", "Night"]},
            {"col": "animal_id", "label": "Animal", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "litres", "label": "Litres", "type": "float",
             "step": 0.1},
        ],
    },
    "Weights": {
        "table": "weights", "pk": "id",
        "list_cols": ["id", "weight_date", "animal_id", "weight_kg"],
        "order_by": "weight_date DESC, id DESC", "limit": 300,
        "date_col": "weight_date",
        "fields": [
            {"col": "weight_date", "label": "Date", "type": "date"},
            {"col": "animal_id", "label": "Animal", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "weight_kg", "label": "Weight (kg)", "type": "float",
             "step": 0.5},
        ],
    },
    "Treatments": {
        "table": "treatments", "pk": "id",
        "list_cols": ["id", "treat_date", "animal_id", "qty", "cost"],
        "order_by": "treat_date DESC, id DESC", "limit": 300,
        "date_col": "treat_date",
        "fields": [
            {"col": "treat_date", "label": "Date", "type": "date"},
            {"col": "animal_id", "label": "Animal", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "disease_id", "label": "Disease", "type": "ref",
             "loader": _diseases, "value_col": "disease_id",
             "label_cols": ["name"]},
            {"col": "medicine_item_id", "label": "Medicine", "type": "ref",
             "loader": _items, "value_col": "item_id",
             "label_cols": ["store", "name"]},
            {"col": "qty", "label": "Qty", "type": "float", "step": 0.1},
            {"col": "uom", "label": "UOM", "type": "text"},
            {"col": "cost", "label": "Cost", "type": "float", "step": 1.0},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Vaccinations": {
        "table": "vaccinations", "pk": "vacc_id",
        "list_cols": ["vacc_id", "vacc_date", "animal_id",
                      "vaccine_name", "next_due"],
        "order_by": "vacc_date DESC, vacc_id DESC", "limit": 300,
        "date_col": "vacc_date",
        "fields": [
            {"col": "vacc_date", "label": "Date", "type": "date"},
            {"col": "animal_id", "label": "Animal", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "sched_id", "label": "Schedule", "type": "ref",
             "loader": _schedules, "value_col": "sched_id",
             "label_cols": ["name"]},
            {"col": "vaccine_name", "label": "Vaccine Name", "type": "text"},
            {"col": "item_id", "label": "Item Used", "type": "ref",
             "loader": _items, "value_col": "item_id",
             "label_cols": ["store", "name"]},
            {"col": "qty", "label": "Qty", "type": "float", "step": 0.1},
            {"col": "cost", "label": "Cost", "type": "float", "step": 1.0},
            {"col": "next_due", "label": "Next Due", "type": "date"},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Breeding Events": {
        "table": "breeding_events", "pk": "event_id",
        "list_cols": ["event_id", "event_date", "animal_id",
                      "event_type", "result", "cost"],
        "order_by": "event_date DESC, event_id DESC", "limit": 300,
        "date_col": "event_date",
        "fields": [
            {"col": "event_date", "label": "Date", "type": "date"},
            {"col": "animal_id", "label": "Animal", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "event_type", "label": "Type", "type": "select",
             "options": ["AI", "Bull Service", "PD Check", "Heat",
                         "Synchronization"]},
            {"col": "bull_id", "label": "Bull", "type": "ref",
             "loader": _bulls, "value_col": "bull_id",
             "label_cols": ["name"]},
            {"col": "semen_item_id", "label": "Semen Item", "type": "ref",
             "loader": _items, "value_col": "item_id",
             "label_cols": ["store", "name"]},
            {"col": "straws_used", "label": "Straws Used",
             "type": "float", "step": 1.0},
            {"col": "cost", "label": "Cost", "type": "float", "step": 1.0},
            {"col": "protocol_id", "label": "Protocol", "type": "ref",
             "loader": _protocols, "value_col": "protocol_id",
             "label_cols": ["name"]},
            {"col": "result", "label": "Result", "type": "text"},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Calvings": {
        "table": "calvings", "pk": "id",
        "list_cols": ["id", "calving_date", "mother_id",
                      "calving_type", "delivery_status"],
        "order_by": "calving_date DESC, id DESC", "limit": 200,
        "date_col": "calving_date",
        "fields": [
            {"col": "calving_date", "label": "Date", "type": "date"},
            {"col": "mother_id", "label": "Mother", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "calving_type", "label": "Type", "type": "select",
             "options": ["Single", "Twins"]},
            {"col": "calf1_id", "label": "Calf 1", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "calf2_id", "label": "Calf 2", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "calf1_weight", "label": "Calf 1 Weight (kg)",
             "type": "float", "step": 0.5},
            {"col": "calf2_weight", "label": "Calf 2 Weight (kg)",
             "type": "float", "step": 0.5},
            {"col": "delivery_status", "label": "Delivery Status",
             "type": "select",
             "options": ["Normal", "Assisted", "C-Section", "Difficult"]},
            {"col": "sire_tag", "label": "Sire Tag", "type": "text"},
            {"col": "complications", "label": "Complications",
             "type": "textarea"},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Sales": {
        "table": "sales", "pk": "sale_id",
        "list_cols": ["sale_id", "sale_date", "kind", "customer_id",
                      "qty", "unit_price", "total"],
        "order_by": "sale_date DESC, sale_id DESC", "limit": 300,
        "date_col": "sale_date",
        "fields": [
            {"col": "sale_date", "label": "Date", "type": "date"},
            {"col": "kind", "label": "Kind", "type": "select",
             "options": ["Milk", "Animal", "Other"]},
            {"col": "customer_id", "label": "Customer", "type": "ref",
             "loader": lambda: _parties("Customer"),
             "value_col": "party_id", "label_cols": ["name"]},
            {"col": "animal_id", "label": "Animal (if applicable)",
             "type": "ref", "loader": _animals,
             "value_col": "animal_id", "label_cols": ["tag"]},
            {"col": "qty", "label": "Qty", "type": "float", "step": 0.1},
            {"col": "unit_price", "label": "Unit Price",
             "type": "float", "step": 1.0},
            {"col": "total", "label": "Total", "type": "float", "step": 1.0},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Purchases": {
        "table": "purchases", "pk": "purchase_id",
        "list_cols": ["purchase_id", "purchase_date", "kind",
                      "vendor_id", "qty", "unit_cost", "total"],
        "order_by": "purchase_date DESC, purchase_id DESC", "limit": 300,
        "date_col": "purchase_date",
        "fields": [
            {"col": "purchase_date", "label": "Date", "type": "date"},
            {"col": "kind", "label": "Kind", "type": "select",
             "options": ["Item", "Animal", "Other"]},
            {"col": "vendor_id", "label": "Vendor", "type": "ref",
             "loader": lambda: _parties("Vendor"),
             "value_col": "party_id", "label_cols": ["name"]},
            {"col": "item_id", "label": "Item (if applicable)",
             "type": "ref", "loader": _items, "value_col": "item_id",
             "label_cols": ["store", "name"]},
            {"col": "animal_id", "label": "Animal (if applicable)",
             "type": "ref", "loader": _animals,
             "value_col": "animal_id", "label_cols": ["tag"]},
            {"col": "qty", "label": "Qty", "type": "float", "step": 0.1},
            {"col": "unit_cost", "label": "Unit Cost",
             "type": "float", "step": 1.0},
            {"col": "total", "label": "Total", "type": "float", "step": 1.0},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Expenses": {
        "table": "expenses", "pk": "id",
        "list_cols": ["id", "exp_date", "category", "amount"],
        "order_by": "exp_date DESC, id DESC", "limit": 300,
        "date_col": "exp_date",
        "fields": [
            {"col": "exp_date", "label": "Date", "type": "date"},
            {"col": "category", "label": "Category", "type": "text"},
            {"col": "amount", "label": "Amount", "type": "float",
             "step": 1.0},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Salary Payments": {
        "table": "salary_payments", "pk": "id",
        "list_cols": ["id", "pay_date", "emp_id", "amount"],
        "order_by": "pay_date DESC, id DESC", "limit": 300,
        "date_col": "pay_date",
        "fields": [
            {"col": "pay_date", "label": "Date", "type": "date"},
            {"col": "emp_id", "label": "Employee", "type": "ref",
             "loader": _employees, "value_col": "emp_id",
             "label_cols": ["name"]},
            {"col": "amount", "label": "Amount", "type": "float",
             "step": 1.0},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Vendors / Customers (Parties)": {
        "table": "parties", "pk": "party_id",
        "list_cols": ["party_id", "name", "party_type", "phone"],
        "order_by": "name", "limit": 500,
        "fields": [
            {"col": "name", "label": "Name", "type": "text"},
            {"col": "party_type", "label": "Type", "type": "select",
             "options": ["Vendor", "Customer"]},
            {"col": "phone", "label": "Phone", "type": "text"},
            {"col": "address", "label": "Address", "type": "textarea"},
        ],
    },
    "Items (Inventory Master)": {
        "table": "items", "pk": "item_id",
        "list_cols": ["item_id", "name", "store_id", "uom", "unit_cost"],
        "order_by": "item_id DESC", "limit": 500,
        "fields": [
            {"col": "name", "label": "Item Name", "type": "text"},
            {"col": "uom", "label": "UOM", "type": "text"},
            {"col": "unit_cost", "label": "Unit Cost",
             "type": "float", "step": 0.5},
        ],
    },
    "Pens": {
        "table": "pens", "pk": "pen_id",
        "list_cols": ["pen_id", "name", "capacity", "farm_id"],
        "order_by": "pen_id", "limit": 500,
        "fields": [
            {"col": "name", "label": "Pen Name", "type": "text"},
            {"col": "capacity", "label": "Capacity", "type": "int"},
            {"col": "farm_id", "label": "Farm", "type": "ref",
             "loader": _farms, "value_col": "farm_id",
             "label_cols": ["name"]},
        ],
    },
    "Employees": {
        "table": "employees", "pk": "emp_id",
        "list_cols": ["emp_id", "name", "role", "phone", "salary"],
        "order_by": "name", "limit": 500,
        "fields": [
            {"col": "name", "label": "Name", "type": "text"},
            {"col": "role", "label": "Role", "type": "text"},
            {"col": "phone", "label": "Phone", "type": "text"},
            {"col": "salary", "label": "Salary", "type": "float",
             "step": 100.0},
            {"col": "farm_id", "label": "Farm", "type": "ref",
             "loader": _farms, "value_col": "farm_id",
             "label_cols": ["name"]},
        ],
    },
    "Stock Moves (manual/adjustments)": {
        "table": "stock_moves", "pk": "id",
        "list_cols": ["id", "move_date", "item_id", "move_type",
                      "qty", "unit_cost", "ref_type"],
        "order_by": "move_date DESC, id DESC", "limit": 300,
        "date_col": "move_date",
        "fields": [
            {"col": "move_date", "label": "Date", "type": "date"},
            {"col": "item_id", "label": "Item", "type": "ref",
             "loader": _items, "value_col": "item_id",
             "label_cols": ["store", "name"]},
            {"col": "move_type", "label": "Type", "type": "select",
             "options": ["IN", "OUT"]},
            {"col": "qty", "label": "Qty", "type": "float", "step": 0.1},
            {"col": "unit_cost", "label": "Unit Cost",
             "type": "float", "step": 0.5},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Feed Allocations": {
        "table": "feed_allocations", "pk": "id",
        "list_cols": ["id", "alloc_date", "pen_id", "recipe_id", "servings"],
        "order_by": "alloc_date DESC, id DESC", "limit": 300,
        "date_col": "alloc_date",
        "fields": [
            {"col": "alloc_date", "label": "Date", "type": "date"},
            {"col": "pen_id", "label": "Pen", "type": "ref",
             "loader": _pens, "value_col": "pen_id",
             "label_cols": ["name"]},
            {"col": "recipe_id", "label": "Recipe", "type": "ref",
             "loader": _recipes, "value_col": "recipe_id",
             "label_cols": ["name"]},
            {"col": "servings", "label": "Servings",
             "type": "float", "step": 1.0},
        ],
    },
    "Animal Movements": {
        "table": "animal_movements", "pk": "id",
        "list_cols": ["id", "move_date", "animal_id",
                      "from_pen_id", "to_pen_id"],
        "order_by": "move_date DESC, id DESC", "limit": 300,
        "date_col": "move_date",
        "fields": [
            {"col": "move_date", "label": "Date", "type": "date"},
            {"col": "animal_id", "label": "Animal", "type": "ref",
             "loader": _animals, "value_col": "animal_id",
             "label_cols": ["tag"]},
            {"col": "from_pen_id", "label": "From Pen", "type": "ref",
             "loader": _pens, "value_col": "pen_id",
             "label_cols": ["name"]},
            {"col": "to_pen_id", "label": "To Pen", "type": "ref",
             "loader": _pens, "value_col": "pen_id",
             "label_cols": ["name"]},
            {"col": "note", "label": "Note", "type": "textarea"},
        ],
    },
    "Journal Entries (header only)": {
        "table": "journal_entries", "pk": "entry_id",
        "list_cols": ["entry_id", "entry_date", "description",
                      "ref_type", "ref_id"],
        "order_by": "entry_date DESC, entry_id DESC", "limit": 300,
        "date_col": "entry_date",
        "fields": [
            {"col": "entry_date", "label": "Date", "type": "date"},
            {"col": "description", "label": "Description", "type": "textarea"},
        ],
        "warn": ("Editing only the header date/description is supported here. "
                 "To change amounts, delete and re-enter the journal."),
    },
}


# ---------------- UI ----------------
table_label = st.selectbox(
    "Choose a table to manage",
    list(TABLES.keys()),
    key="admin_edit_table",
)
cfg = TABLES[table_label]

if cfg.get("warn"):
    st.warning(cfg["warn"])

# Filter row
filt_col1, filt_col2, filt_col3 = st.columns([2, 2, 6])
date_filter_on = False
if "date_col" in cfg:
    date_filter_on = filt_col1.checkbox("Filter by date range", value=False,
                                        key="admin_filter_on")
    if date_filter_on:
        d_from = filt_col2.date_input("From", value=date.today().replace(day=1),
                                      key="admin_filter_from")
        d_to = filt_col3.date_input("To", value=date.today(),
                                    key="admin_filter_to")

# Load records
sql = f"SELECT * FROM {cfg['table']}"
params = ()
if date_filter_on and "date_col" in cfg:
    sql += f" WHERE {cfg['date_col']} BETWEEN ? AND ?"
    params = (str(d_from), str(d_to))
sql += f" ORDER BY {cfg['order_by']} LIMIT {cfg.get('limit', 300)}"

records = query(sql, params)
df_list = pd.DataFrame(records)

st.subheader(f"Recent {table_label}  —  {len(records)} record(s)")
if df_list.empty:
    st.info("No records to display.")
else:
    show_cols = [c for c in cfg["list_cols"] if c in df_list.columns]
    st.dataframe(df_list[show_cols], use_container_width=True,
                 hide_index=True)
    export_excel_button(df_list, f"{cfg['table']}_export.xlsx")

st.divider()
st.subheader("Edit a Record")

pk = cfg["pk"]

if not records:
    st.info("No records available to edit or delete in this table.")
else:
    def _label_for(r):
        parts = [str(r.get(c, "")) for c in cfg["list_cols"][:4]
                 if c != pk]
        return f"#{r[pk]}  —  {' / '.join(p for p in parts if p)}"

    pick_idx = st.selectbox(
        "Pick a record",
        range(len(records)),
        format_func=lambda i: _label_for(records[i]),
        key=f"admin_pick_{cfg['table']}",
    )
    rec = records[pick_idx]
    rec_id = rec[pk]

    # Two-column edit form
    with st.form(f"admin_edit_form_{cfg['table']}_{rec_id}"):
        new_values = {}
        fields = cfg["fields"]
        cols = st.columns(2)
        for i, fld in enumerate(fields):
            with cols[i % 2]:
                new_values[fld["col"]] = _render_field(
                    fld, rec.get(fld["col"]),
                    f"edit_{cfg['table']}_{rec_id}",
                )
        save_btn = st.form_submit_button(
            "Save Changes", type="primary", use_container_width=True)

    if save_btn:
        changes = {}
        for c, v in new_values.items():
            old = rec.get(c)
            if isinstance(v, date) and not isinstance(old, date):
                old = _date_or_none(old)
            # Treat empty string and None as equivalent (avoid noise updates)
            if (v in (None, "") and old in (None, "")):
                continue
            if v != old:
                changes[c] = v
        if not changes:
            st.info("No changes detected.")
        else:
            try:
                set_clause = ", ".join(f"{c}=?" for c in changes.keys())
                params = tuple(changes.values()) + (rec_id,)
                execute(
                    f"UPDATE {cfg['table']} SET {set_clause} "
                    f"WHERE {pk}=?", params)
                log_audit("UPDATE", cfg["table"], rec_id,
                          {k: rec.get(k) for k in changes.keys()},
                          changes)
                st.toast(
                    f"Record #{rec_id} updated. "
                    f"{len(changes)} field(s) changed.",
                    icon="✅")
                st.success(
                    f"Record #{rec_id} updated. "
                    f"{len(changes)} field(s) changed: "
                    f"{', '.join(changes.keys())}")
            except Exception as e:
                st.error(f"Update failed: {e}")

    # Delete section
    st.divider()
    st.subheader("Delete a Record")
    st.caption(
        "Deleting a record cannot be undone. If the record is referenced "
        "by other tables (e.g. an animal that has milk records), the "
        "database will refuse the delete to protect data integrity."
    )
    del_col1, del_col2 = st.columns([2, 5])
    del_id = del_col1.number_input(
        f"{pk} to delete", min_value=1, step=1, value=int(rec_id),
        key=f"admin_del_{cfg['table']}",
    )
    confirm = del_col2.text_input(
        "Type DELETE to confirm",
        key=f"admin_del_confirm_{cfg['table']}",
    )
    if st.button(f"Delete {table_label} #{int(del_id)}",
                 type="secondary", key=f"admin_del_btn_{cfg['table']}"):
        if confirm.strip().upper() != "DELETE":
            st.error("Please type DELETE in the confirmation box.")
        else:
            try:
                old = query(
                    f"SELECT * FROM {cfg['table']} WHERE {pk}=?",
                    (int(del_id),))
                if not old:
                    st.error("Record not found.")
                else:
                    execute(
                        f"DELETE FROM {cfg['table']} WHERE {pk}=?",
                        (int(del_id),))
                    log_audit("DELETE", cfg["table"], int(del_id),
                              old[0], None)
                    st.success(f"Record #{int(del_id)} deleted.")
                    st.rerun()
            except Exception as e:
                st.error(
                    f"Delete failed: {e}\n\n"
                    "Tip: this record is probably referenced by another "
                    "table. Edit or delete the dependent rows first."
                )

# ---------------- Audit log ----------------
st.divider()
with st.expander("Audit Log (last 100 admin actions)"):
    audit = pd.DataFrame(query(
        "SELECT id, ts, username, action, table_name, record_id, note "
        "FROM admin_audit_log ORDER BY id DESC LIMIT 100"
    ))
    if audit.empty:
        st.info("No admin actions logged yet.")
    else:
        st.dataframe(audit, use_container_width=True, hide_index=True)
        export_excel_button(audit, "admin_audit_log.xlsx",
                            "Download Audit Log")
