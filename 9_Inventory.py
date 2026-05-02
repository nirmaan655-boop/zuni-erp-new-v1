"""Inventory - 5 stores, item master, stock in/out."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute, add_stock_move
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Inventory", layout="wide")
init_db()

require_role("9_Inventory")
render_user_sidebar()
st.title("Inventory")

stores = query("SELECT * FROM stores")
store_opts = {s["name"]: s["store_id"] for s in stores}

tab_bal, tab_item, tab_move = st.tabs(["Stock Balance", "Item Master", "Stock Move"])

with tab_bal:
    df = pd.DataFrame(query("""
        SELECT s.name store, i.name item, i.uom, i.unit_cost,
            COALESCE(SUM(CASE WHEN m.move_type='IN' THEN m.qty ELSE -m.qty END),0) balance
        FROM items i
        JOIN stores s ON s.store_id=i.store_id
        LEFT JOIN stock_moves m ON m.item_id=i.item_id
        GROUP BY s.name, i.name, i.uom, i.unit_cost
        ORDER BY s.name, i.name
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "stock_balance.xlsx")

with tab_item:
    with st.form("add_item", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        name = c1.text_input("Item Name *")
        store = c2.selectbox("Store", list(store_opts.keys()))
        uom = c3.text_input("UOM", "kg")
        cost = c4.number_input("Unit Cost", min_value=0.0, step=0.5)
        opening = st.number_input("Opening Stock (optional)", min_value=0.0, step=1.0,
                                  help="If you already have stock on hand, enter the quantity here. It will be logged as an opening IN move.")
        if st.form_submit_button("Save Item", type="primary"):
            if not name.strip():
                st.error("Item name is required.")
            else:
                # Case-insensitive duplicate check (across all stores to avoid confusion)
                dup = query("SELECT item_id, name, (SELECT name FROM stores WHERE store_id=items.store_id) store "
                            "FROM items WHERE LOWER(name)=LOWER(?)", (name.strip(),))
                if dup:
                    st.error(f"Item '{dup[0]['name']}' already exists in {dup[0]['store']}.")
                else:
                    try:
                        iid = execute(
                            "INSERT INTO items(name,store_id,uom,unit_cost) VALUES(?,?,?,?)",
                            (name.strip(), store_opts[store], uom, cost))
                        if opening > 0:
                            add_stock_move(iid, date.today(), "IN", opening, cost,
                                           "opening", iid, "Opening stock")
                        st.success(f"Item '{name}' saved." +
                                   (f" Opening stock: {opening} {uom}." if opening > 0 else ""))
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    df = pd.DataFrame(query("""
        SELECT i.item_id, i.name, s.name store, i.uom, i.unit_cost
        FROM items i JOIN stores s ON s.store_id=i.store_id ORDER BY s.name, i.name
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_move:
    items = query("SELECT i.item_id, i.name, s.name store FROM items i JOIN stores s ON s.store_id=i.store_id")
    if not items:
        st.info("Add items first.")
    else:
        with st.form("mv"):
            c1, c2, c3, c4, c5 = st.columns(5)
            sel = c1.selectbox("Item", [f"{i['store']} / {i['name']}" for i in items])
            mt = c2.selectbox("Type", ["IN", "OUT"])
            qty = c3.number_input("Qty", min_value=0.0, step=0.1)
            unit = c4.number_input("Unit Cost", min_value=0.0, step=0.5)
            d = c5.date_input("Date", date.today())
            note = st.text_input("Note")
            if st.form_submit_button("Save"):
                idx = [f"{i['store']} / {i['name']}" for i in items].index(sel)
                add_stock_move(items[idx]["item_id"], d, mt, qty, unit,
                               "manual", None, note)
                st.success("Saved.")

    df = pd.DataFrame(query("""
        SELECT m.move_date, s.name store, i.name item, m.move_type, m.qty, m.unit_cost, m.note
        FROM stock_moves m
        JOIN items i ON i.item_id=m.item_id
        JOIN stores s ON s.store_id=i.store_id
        ORDER BY m.id DESC LIMIT 500
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "stock_moves.xlsx")
