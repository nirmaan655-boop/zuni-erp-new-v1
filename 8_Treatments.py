"""Treatment system."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute, add_stock_move, post_journal
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Treatments", layout="wide")
init_db()

require_role("8_Treatments")
render_user_sidebar()
st.title("Treatment System")

tab_new, tab_pen, tab_dis, tab_hist = st.tabs(
    ["Single Animal", "Pen-wise (whole pen)", "Diseases", "History"])

with tab_new:
    animals = query("SELECT animal_id, tag FROM animals WHERE status='Active'")
    diseases = query("SELECT * FROM diseases")
    # Show medicines + vaccines from inventory
    meds = query("""
        SELECT i.item_id, i.name, i.unit_cost, i.uom, s.name store
        FROM items i JOIN stores s ON s.store_id=i.store_id
        WHERE s.name IN ('Medicine Store','Vaccine Store')
        ORDER BY s.name, i.name
    """)
    if not meds:
        st.info("No medicines/vaccines yet. Add them in Inventory under 'Medicine Store' or 'Vaccine Store'.")
    if not animals:
        st.info("Add animals first.")
    else:
        with st.form("treat"):
            c1, c2, c3 = st.columns(3)
            tag = c1.selectbox("Animal", [a["tag"] for a in animals])
            d = c2.date_input("Date", date.today())
            disease = c3.selectbox("Disease", ["-"] + [x["name"] for x in diseases])
            c4, c5, c6 = st.columns(3)
            med_labels = ["-"] + [f"{m['store']} / {m['name']}" for m in meds]
            med = c4.selectbox("Medicine / Vaccine", med_labels)
            qty = c5.number_input("Quantity", min_value=0.0, step=0.1)
            uom = c6.selectbox("UOM", ["ml", "mg", "g", "tablet"])
            cost = st.number_input("Cost (auto if medicine selected)", min_value=0.0, step=1.0)
            note = st.text_input("Note")
            if st.form_submit_button("Save"):
                aid = next(a["animal_id"] for a in animals if a["tag"] == tag)
                did = next((x["disease_id"] for x in diseases if x["name"] == disease), None)
                mid = None
                if med != "-":
                    idx = med_labels.index(med) - 1
                    mid = meds[idx]["item_id"]
                final_cost = cost
                if mid and not cost:
                    m = next(m for m in meds if m["item_id"] == mid)
                    final_cost = (m["unit_cost"] or 0) * qty
                tid = execute(
                    "INSERT INTO treatments(animal_id,treat_date,disease_id,medicine_item_id,qty,uom,cost,note) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (aid, str(d), did, mid, qty, uom, final_cost, note))
                if mid:
                    add_stock_move(mid, d, "OUT", qty, final_cost / qty if qty else 0,
                                   "treatment", tid)
                if final_cost:
                    post_journal(d, f"Treatment for {tag}",
                                 [("5100", final_cost, 0), ("1200", 0, final_cost)],
                                 "treatment", tid)
                st.success(f"Saved. Cost: {final_cost:.2f}")

with tab_pen:
    pens = query("SELECT pen_id, name FROM pens ORDER BY name")
    pen_meds = query("""
        SELECT i.item_id, i.name, i.unit_cost, i.uom, s.name store
        FROM items i JOIN stores s ON s.store_id=i.store_id
        WHERE s.name IN ('Medicine Store','Vaccine Store')
        ORDER BY s.name, i.name
    """)
    if not pens:
        st.info("Create pens first.")
    elif not pen_meds:
        st.info("Add medicines / vaccines in Inventory first.")
    else:
        st.caption("Apply a medicine/vaccine to every active animal in a pen. "
                   "Stock OUT = qty per animal × number of animals; cost is split per animal.")
        c1, c2, c3 = st.columns(3)
        pen_name = c1.selectbox("Pen", [p["name"] for p in pens])
        pid = next(p["pen_id"] for p in pens if p["name"] == pen_name)
        d_pen = c2.date_input("Date", date.today(), key="pdt")
        med_labels = [f"{m['store']} / {m['name']}" for m in pen_meds]
        med_lbl = c3.selectbox("Medicine / Vaccine", med_labels, key="pmed")
        sel_med = pen_meds[med_labels.index(med_lbl)]

        c4, c5 = st.columns(2)
        qty_per = c4.number_input(f"Qty per animal ({sel_med['uom']})",
                                   min_value=0.0, step=0.1, key="pqp")
        animals_in_pen = query(
            "SELECT animal_id, tag FROM animals WHERE pen_id=? AND status='Active'", (pid,))
        c5.metric("Active animals in pen", len(animals_in_pen))

        cost_per = qty_per * (sel_med["unit_cost"] or 0)
        total_qty = qty_per * len(animals_in_pen)
        total_cost = cost_per * len(animals_in_pen)
        st.write(f"**Will issue:** {total_qty:.2f} {sel_med['uom']} • "
                 f"**Cost per animal:** {cost_per:,.2f} • **Total cost:** {total_cost:,.2f}")

        disease_pen = st.selectbox(
            "Disease (optional)", ["-"] + [x["name"] for x in query("SELECT * FROM diseases")],
            key="pdis")
        note_pen = st.text_input("Note", key="pnote2")

        if st.button("Apply to whole pen", type="primary",
                     disabled=(qty_per <= 0 or not animals_in_pen)):
            did = next((x["disease_id"] for x in query("SELECT * FROM diseases")
                       if x["name"] == disease_pen), None)
            unit_c = sel_med["unit_cost"] or 0
            # One stock OUT total, then per-animal treatment rows for traceability
            add_stock_move(sel_med["item_id"], d_pen, "OUT", total_qty, unit_c,
                           "treatment_pen", pid, f"Pen {pen_name} treatment")
            for a in animals_in_pen:
                execute(
                    "INSERT INTO treatments(animal_id,treat_date,disease_id,medicine_item_id,"
                    "qty,uom,cost,note) VALUES(?,?,?,?,?,?,?,?)",
                    (a["animal_id"], str(d_pen), did, sel_med["item_id"],
                     qty_per, sel_med["uom"], cost_per,
                     (note_pen + " (pen-wise)").strip()))
            if total_cost:
                post_journal(d_pen, f"Pen-wise treatment {pen_name}",
                             [("5100", total_cost, 0), ("1200", 0, total_cost)],
                             "treatment_pen", pid)
            st.success(f"Applied to {len(animals_in_pen)} animals. Total cost: {total_cost:,.2f}")

with tab_dis:
    with st.form("dis"):
        n = st.text_input("Disease Name")
        if st.form_submit_button("Add") and n:
            try:
                execute("INSERT INTO diseases(name) VALUES(?)", (n,))
                st.success("Added.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
    df = pd.DataFrame(query("SELECT * FROM diseases"))
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_hist:
    df = pd.DataFrame(query("""
        SELECT t.treat_date, a.tag animal, d.name disease, i.name medicine,
               t.qty, t.uom, t.cost, t.note
        FROM treatments t
        JOIN animals a ON a.animal_id=t.animal_id
        LEFT JOIN diseases d ON d.disease_id=t.disease_id
        LEFT JOIN items i ON i.item_id=t.medicine_item_id
        ORDER BY t.id DESC
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "treatments.xlsx")
