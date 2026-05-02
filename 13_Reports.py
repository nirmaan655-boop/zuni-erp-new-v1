"""Consolidated reports."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import init_db, query
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Reports", layout="wide")
init_db()

require_role("13_Reports")
render_user_sidebar()
st.title("Reports")

c1, c2 = st.columns(2)
start = c1.date_input("From", date.today() - timedelta(days=30))
end = c2.date_input("To", date.today())

report = st.selectbox("Report", [
    "Animal History", "Milk", "Feed", "Stock", "Treatments",
    "Sales Ledger", "Purchase Ledger", "Vendor Ledger", "Customer Ledger"
])

df = pd.DataFrame()

if report == "Animal History":
    animals = query("SELECT animal_id, tag FROM animals ORDER BY tag")
    if animals:
        tag = st.selectbox("Animal", [a["tag"] for a in animals])
        aid = next(a["animal_id"] for a in animals if a["tag"] == tag)
        sections = []
        sections.append(("Movements", pd.DataFrame(query("""
            SELECT move_date, p1.name from_pen, p2.name to_pen, m.note
            FROM animal_movements m
            LEFT JOIN pens p1 ON p1.pen_id=m.from_pen_id
            LEFT JOIN pens p2 ON p2.pen_id=m.to_pen_id
            WHERE m.animal_id=? AND move_date BETWEEN ? AND ?
            ORDER BY move_date""", (aid, str(start), str(end))))))
        sections.append(("Milk", pd.DataFrame(query("""
            SELECT record_date, shift, litres FROM milk_records
            WHERE animal_id=? AND record_date BETWEEN ? AND ?
            ORDER BY record_date""", (aid, str(start), str(end))))))
        sections.append(("Weights", pd.DataFrame(query("""
            SELECT weight_date, weight_kg FROM weights
            WHERE animal_id=? AND weight_date BETWEEN ? AND ?
            ORDER BY weight_date""", (aid, str(start), str(end))))))
        sections.append(("Treatments", pd.DataFrame(query("""
            SELECT t.treat_date, d.name disease, i.name medicine, t.qty, t.uom, t.cost
            FROM treatments t LEFT JOIN diseases d ON d.disease_id=t.disease_id
            LEFT JOIN items i ON i.item_id=t.medicine_item_id
            WHERE t.animal_id=? AND t.treat_date BETWEEN ? AND ?
            ORDER BY t.treat_date""", (aid, str(start), str(end))))))
        for name, sdf in sections:
            st.subheader(name)
            st.dataframe(sdf, use_container_width=True, hide_index=True)
            export_excel_button(sdf, f"{tag}_{name}.xlsx", f"Download {name}")

elif report == "Milk":
    df = pd.DataFrame(query("""
        SELECT m.record_date, a.tag, m.shift, m.litres
        FROM milk_records m JOIN animals a ON a.animal_id=m.animal_id
        WHERE m.record_date BETWEEN ? AND ?
        ORDER BY m.record_date DESC, a.tag
    """, (str(start), str(end))))

elif report == "Feed":
    df = pd.DataFrame(query("""
        SELECT a.alloc_date, p.name pen, r.name recipe, a.servings
        FROM feed_allocations a
        JOIN pens p ON p.pen_id=a.pen_id
        JOIN feed_recipes r ON r.recipe_id=a.recipe_id
        WHERE a.alloc_date BETWEEN ? AND ?
        ORDER BY a.alloc_date DESC
    """, (str(start), str(end))))

elif report == "Stock":
    df = pd.DataFrame(query("""
        SELECT m.move_date, s.name store, i.name item, m.move_type, m.qty, m.unit_cost
        FROM stock_moves m JOIN items i ON i.item_id=m.item_id
        JOIN stores s ON s.store_id=i.store_id
        WHERE m.move_date BETWEEN ? AND ?
        ORDER BY m.move_date DESC
    """, (str(start), str(end))))

elif report == "Treatments":
    df = pd.DataFrame(query("""
        SELECT t.treat_date, a.tag animal, d.name disease, i.name medicine, t.qty, t.uom, t.cost
        FROM treatments t JOIN animals a ON a.animal_id=t.animal_id
        LEFT JOIN diseases d ON d.disease_id=t.disease_id
        LEFT JOIN items i ON i.item_id=t.medicine_item_id
        WHERE t.treat_date BETWEEN ? AND ?
        ORDER BY t.treat_date DESC
    """, (str(start), str(end))))

elif report == "Sales Ledger":
    df = pd.DataFrame(query("""
        SELECT s.sale_date, s.kind, c.name customer, s.qty, s.unit_price, s.total
        FROM sales s LEFT JOIN parties c ON c.party_id=s.customer_id
        WHERE s.sale_date BETWEEN ? AND ?
        ORDER BY s.sale_date DESC
    """, (str(start), str(end))))

elif report == "Purchase Ledger":
    df = pd.DataFrame(query("""
        SELECT p.purchase_date, p.kind, v.name vendor, p.qty, p.unit_cost, p.total
        FROM purchases p LEFT JOIN parties v ON v.party_id=p.vendor_id
        WHERE p.purchase_date BETWEEN ? AND ?
        ORDER BY p.purchase_date DESC
    """, (str(start), str(end))))

elif report == "Vendor Ledger":
    parties = query("SELECT * FROM parties WHERE party_type='Vendor'")
    if parties:
        v = st.selectbox("Vendor", [p["name"] for p in parties])
        vid = next(p["party_id"] for p in parties if p["name"] == v)
        df = pd.DataFrame(query("""
            SELECT purchase_date, kind, qty, unit_cost, total, note
            FROM purchases WHERE vendor_id=? AND purchase_date BETWEEN ? AND ?
            ORDER BY purchase_date DESC
        """, (vid, str(start), str(end))))
        if not df.empty:
            st.metric("Total Purchases", f"{df['total'].sum():,.2f}")

elif report == "Customer Ledger":
    parties = query("SELECT * FROM parties WHERE party_type='Customer'")
    if parties:
        cu = st.selectbox("Customer", [p["name"] for p in parties])
        cid = next(p["party_id"] for p in parties if p["name"] == cu)
        df = pd.DataFrame(query("""
            SELECT sale_date, kind, qty, unit_price, total, note
            FROM sales WHERE customer_id=? AND sale_date BETWEEN ? AND ?
            ORDER BY sale_date DESC
        """, (cid, str(start), str(end))))
        if not df.empty:
            st.metric("Total Sales", f"{df['total'].sum():,.2f}")

if report != "Animal History":
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, f"{report.replace(' ','_')}.xlsx")
