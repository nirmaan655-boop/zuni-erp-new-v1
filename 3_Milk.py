"""Milk system - 3 shifts, milk store, and milk usage."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import (init_db, query, execute, post_journal,
                add_milk_move, milk_store_balance, latest_milk_rate)
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Milk", layout="wide")
init_db()

require_role("3_Milk")
render_user_sidebar()
st.title("Milk Production & Store")

# Top KPI: milk store balance + latest rate
k1, k2 = st.columns(2)
k1.metric("Milk Store balance (L)", f"{milk_store_balance():,.1f}")
k2.metric("Latest sale rate (Rs/L)", f"{latest_milk_rate():,.2f}")

tab_in, tab_use, tab_store, tab_rep = st.tabs(
    ["Record Milk", "Milk Usage", "Store Ledger", "Reports"])

# ---------- Record per-animal milk ----------
with tab_in:
    animals = query("SELECT animal_id, tag FROM animals WHERE status='Active' AND sex='F' ORDER BY tag")
    if not animals:
        st.info("Add active female animals first.")
    else:
        with st.form("milk_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            tag = c1.selectbox("Animal", [a["tag"] for a in animals])
            d = c2.date_input("Date", date.today())
            shift = c3.selectbox("Shift", ["Morning", "Evening", "Night"])
            litres = c4.number_input("Litres", min_value=0.0, step=0.1)
            if st.form_submit_button("Save", type="primary"):
                aid = next(a["animal_id"] for a in animals if a["tag"] == tag)
                # Compute delta vs existing record so milk-store stays accurate
                existing = query(
                    "SELECT litres FROM milk_records WHERE animal_id=? AND record_date=? AND shift=?",
                    (aid, str(d), shift))
                old_l = existing[0]["litres"] if existing else 0
                delta = litres - old_l
                try:
                    execute(
                        "INSERT OR REPLACE INTO milk_records(animal_id,record_date,shift,litres) "
                        "VALUES(?,?,?,?)", (aid, str(d), shift, litres))
                    if delta > 0:
                        add_milk_move(d, "IN", delta, "Production",
                                      0, "milk_record", aid, f"{tag} {shift}")
                    elif delta < 0:
                        add_milk_move(d, "OUT", -delta, "Adjustment",
                                      0, "milk_record", aid, f"{tag} {shift} correction")
                    st.success(f"Saved. Delta added to milk store: {delta:+.1f} L.")
                except Exception as e:
                    st.error(str(e))

# ---------- Milk Usage (4 options) ----------
with tab_use:
    st.subheader("Use milk from store")
    st.caption("Pick where the milk goes — Sale, Calf, Mess, or Farm Use. "
               "Stock auto-deducts. For internal uses, milk value is booked to the chosen expense account.")

    use_type = st.radio("Use Type",
                        ["Sale", "Calf use", "Mess use", "Farm use"],
                        horizontal=True, key="ut")
    customers = query("SELECT party_id, name FROM parties WHERE party_type='Customer' ORDER BY name")
    pens = query("SELECT pen_id, name FROM pens ORDER BY name")
    expense_accs = query("SELECT code, name FROM accounts WHERE type='Expense' ORDER BY code")

    # Default expense account by use type
    default_exp = {"Calf use": "5500", "Mess use": "5510", "Farm use": "5520"}.get(use_type, None)

    with st.form("use_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Date", date.today(), key="ud")
        litres = c2.number_input("Litres", min_value=0.0, step=1.0, key="ul")
        rate = c3.number_input(
            "Rate per L (auto-fill from latest sale rate)",
            min_value=0.0, step=1.0,
            value=float(latest_milk_rate()),
            key="ur")

        cust = None
        pen_pick = None
        exp_pick = None

        if use_type == "Sale":
            cust = st.selectbox("Customer",
                                ["-"] + [c["name"] for c in customers], key="uc")
        else:
            colA, colB = st.columns(2)
            exp_labels = [f"{a['code']} - {a['name']}" for a in expense_accs]
            default_idx = next(
                (i for i, a in enumerate(expense_accs) if a["code"] == default_exp), 0)
            exp_pick = colA.selectbox("Expense Account",
                                      exp_labels, index=default_idx, key="uexp")
            if use_type == "Calf use":
                pen_pick = colB.selectbox(
                    "Pen (whose calves got this milk)",
                    ["-"] + [p["name"] for p in pens], key="upen")

        note = st.text_input("Note", key="un")
        st.metric("Total Value", f"{litres * rate:,.2f}")

        if st.form_submit_button(f"Record {use_type}", type="primary"):
            bal = milk_store_balance()
            if litres <= 0:
                st.error("Litres must be > 0.")
            elif litres > bal:
                st.error(f"Not enough milk in store. Available {bal:.1f} L.")
            else:
                if use_type == "Sale":
                    cid = next((c["party_id"] for c in customers if c["name"] == cust), None)
                    total = litres * rate
                    sid = execute(
                        "INSERT INTO sales(sale_date,customer_id,kind,qty,unit_price,total,note) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (str(d), cid, "Milk", litres, rate, total, note))
                    add_milk_move(d, "OUT", litres, "Sale", rate, "sale", sid, "Milk sale")
                    if total:
                        post_journal(d, "Milk sale",
                                     [("1400", total, 0), ("4000", 0, total)], "sale", sid)
                    st.success(f"Milk sale saved. Total {total:,.2f}.")
                else:
                    # Internal use: Calf / Mess / Farm
                    use_label = use_type.replace(" use", "")  # Calf / Mess / Farm
                    pen_id = next(
                        (p["pen_id"] for p in pens if p["name"] == pen_pick), None) if pen_pick and pen_pick != "-" else None
                    exp_code = exp_pick.split(" - ")[0] if exp_pick else None
                    total = litres * rate

                    add_milk_move(d, "OUT", litres, use_label, rate,
                                  "use", None, note or f"{use_type} allocation",
                                  pen_id=pen_id, expense_code=exp_code)

                    if total > 0 and exp_code:
                        # Book the cost: Dr <expense> / Cr Milk Sales (notional internal allocation)
                        post_journal(
                            d,
                            f"{use_type}: {litres} L @ {rate} "
                            + (f"(Pen: {pen_pick})" if pen_pick and pen_pick != '-' else ""),
                            [(exp_code, total, 0), ("4000", 0, total)],
                            "milk_internal", None)
                    st.success(f"{litres} L issued to {use_type}. "
                               f"Booked {total:,.2f} to {exp_pick or '—'}.")

# ---------- Store ledger ----------
with tab_store:
    df = pd.DataFrame(query("""
        SELECT m.move_date, m.move_type, m.use_type, m.litres, m.rate,
               (m.litres * m.rate) AS value,
               p.name AS pen, m.expense_code, m.note
        FROM milk_store_moves m
        LEFT JOIN pens p ON p.pen_id = m.pen_id
        ORDER BY m.id DESC LIMIT 500
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "milk_store_ledger.xlsx")

    st.divider()
    df_sum = pd.DataFrame(query("""
        SELECT use_type,
               SUM(CASE WHEN move_type='IN' THEN litres ELSE 0 END) IN_L,
               SUM(CASE WHEN move_type='OUT' THEN litres ELSE 0 END) OUT_L,
               SUM(CASE WHEN move_type='OUT' THEN litres*rate ELSE 0 END) OUT_Value
        FROM milk_store_moves GROUP BY use_type
    """))
    st.write("**Summary by use:**")
    st.dataframe(df_sum, use_container_width=True, hide_index=True)

# ---------- Reports ----------
with tab_rep:
    c1, c2 = st.columns(2)
    start = c1.date_input("From", date.today().replace(day=1), key="rs")
    end = c2.date_input("To", date.today(), key="re")

    st.subheader("Daily Total (3 Shifts)")
    df_day = pd.DataFrame(query("""
        SELECT record_date,
            SUM(CASE WHEN shift='Morning' THEN litres ELSE 0 END) Morning,
            SUM(CASE WHEN shift='Evening' THEN litres ELSE 0 END) Evening,
            SUM(CASE WHEN shift='Night' THEN litres ELSE 0 END) Night,
            SUM(litres) Total
        FROM milk_records WHERE record_date BETWEEN ? AND ?
        GROUP BY record_date ORDER BY record_date DESC
    """, (str(start), str(end))))
    st.dataframe(df_day, use_container_width=True, hide_index=True)
    export_excel_button(df_day, "milk_daily.xlsx", "Download Daily Excel")

    st.subheader("Animal-wise Milk Report")
    df_anim = pd.DataFrame(query("""
        SELECT a.tag, SUM(m.litres) total_litres,
               ROUND(AVG(m.litres)::numeric,2) avg_litres, COUNT(*) records
        FROM milk_records m JOIN animals a ON a.animal_id=m.animal_id
        WHERE m.record_date BETWEEN ? AND ?
        GROUP BY a.animal_id, a.tag ORDER BY total_litres DESC
    """, (str(start), str(end))))
    st.dataframe(df_anim, use_container_width=True, hide_index=True)
    export_excel_button(df_anim, "milk_animal.xlsx", "Download Animal Excel")
