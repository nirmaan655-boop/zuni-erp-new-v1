"""Vaccinations - record, schedule, alerts, history."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import (init_db, query, execute, post_journal,
                add_stock_move)
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Vaccinations", layout="wide")
init_db()

require_role("17_Vaccinations")
render_user_sidebar()
st.title("Vaccinations & Vaccine Alerts")
st.caption("Record vaccinations, auto-deduct from Vaccine Store inventory, "
           "track upcoming due dates per animal.")

today = date.today()

# ----- Top KPIs -----
overdue = query("""
    SELECT COUNT(*) c FROM (
        SELECT animal_id, MAX(vacc_date) last_dt, MAX(next_due) nxt
        FROM vaccinations GROUP BY animal_id, vaccine_name
    ) WHERE nxt IS NOT NULL AND nxt < DATE('now')
""")[0]["c"]
due7 = query("""
    SELECT COUNT(*) c FROM (
        SELECT animal_id, MAX(next_due) nxt
        FROM vaccinations GROUP BY animal_id, vaccine_name
    ) WHERE nxt BETWEEN DATE('now') AND DATE('now','+7 days')
""")[0]["c"]
total_30 = query("SELECT COUNT(*) c FROM vaccinations WHERE vacc_date >= DATE('now','-30 days')")[0]["c"]
cost_30 = query("SELECT COALESCE(SUM(cost),0) v FROM vaccinations WHERE vacc_date >= DATE('now','-30 days')")[0]["v"]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Overdue Vaccinations", overdue)
k2.metric("Due in next 7 days", due7)
k3.metric("Done (last 30 days)", total_30)
k4.metric("Cost (30 days)", f"{cost_30:,.0f}")

tab_record, tab_alerts, tab_hist, tab_master = st.tabs(
    ["Record Vaccination", "Alerts (Due / Overdue)", "History", "Schedules / Master"])

# ---------------- Record ----------------
with tab_record:
    animals = query("SELECT animal_id, tag FROM animals "
                    "WHERE status='Active' ORDER BY tag")
    schedules = query("SELECT sched_id, name, interval_days FROM vaccine_schedules ORDER BY name")
    vacc_items = query("""
        SELECT i.item_id, i.name, i.unit_cost,
               COALESCE((SELECT SUM(CASE WHEN m.move_type='IN' THEN m.qty ELSE -m.qty END)
                         FROM stock_moves m WHERE m.item_id=i.item_id),0) AS bal
        FROM items i JOIN stores s ON s.store_id=i.store_id
        WHERE s.name='Vaccine Store' ORDER BY i.name
    """)

    if not animals:
        st.info("Add active animals first.")
    elif not schedules:
        st.info("Add vaccine schedules in 'Schedules / Master' tab.")
    else:
        st.markdown("### New Vaccination")
        c1, c2, c3 = st.columns(3)
        scope = c1.radio("Apply to", ["Single Animal", "Whole Pen / All Active"],
                         horizontal=True)
        sched_pick = c2.selectbox("Vaccine Schedule",
                                   [s["name"] for s in schedules])
        sched = next(s for s in schedules if s["name"] == sched_pick)
        v_date = c3.date_input("Vaccination Date", today)

        c4, c5, c6 = st.columns(3)
        if scope == "Single Animal":
            tag = c4.selectbox("Animal", [a["tag"] for a in animals])
            target_ids = [next(a["animal_id"] for a in animals if a["tag"] == tag)]
        else:
            target_ids = [a["animal_id"] for a in animals]
            c4.metric("Will vaccinate", f"{len(target_ids)} animals")

        item_pick = "(none)"
        unit_cost_per = 0.0
        item_id = None
        item_obj = None
        if vacc_items:
            labels = [f"{i['name']} (stock {i['bal']:.0f}, {i['unit_cost']:.0f}/dose)"
                      for i in vacc_items]
            item_pick = c5.selectbox("Vaccine item (Vaccine Store)",
                                      ["(no item — manual)"] + labels)
            if item_pick != "(no item — manual)":
                item_obj = vacc_items[labels.index(item_pick)]
                item_id = item_obj["item_id"]
                unit_cost_per = float(item_obj["unit_cost"] or 0)
                c6.info(f"Available stock: **{item_obj['bal']:.0f}** doses")

        c7, c8 = st.columns(2)
        qty = c7.number_input("Doses per animal", min_value=1.0, step=1.0, value=1.0)
        cost_per = c8.number_input("Cost per dose (auto)",
                                    min_value=0.0, step=10.0, value=unit_cost_per)
        note = st.text_input("Note", "")

        total_cost = qty * cost_per * len(target_ids)
        total_doses = qty * len(target_ids)
        st.info(f"**Total**: {total_doses:.0f} doses × {cost_per:.0f} "
                f"= **{total_cost:,.2f}** for {len(target_ids)} animal(s)")

        ok = True
        if item_obj and item_obj["bal"] < total_doses:
            st.error(f"Not enough stock — need {total_doses:.0f}, have {item_obj['bal']:.0f}.")
            ok = False

        if st.button("Save Vaccination", type="primary", disabled=not ok):
            next_due = v_date + timedelta(days=int(sched["interval_days"]))
            for aid in target_ids:
                execute(
                    "INSERT INTO vaccinations(animal_id,vacc_date,sched_id,"
                    "vaccine_name,item_id,qty,cost,next_due,note) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (aid, str(v_date), sched["sched_id"], sched_pick,
                     item_id, qty, qty * cost_per, str(next_due), note))
            # Single inventory move + journal for all
            if item_id and total_doses > 0:
                add_stock_move(item_id, v_date, "OUT", total_doses, cost_per,
                               "vaccination", None,
                               f"Vaccination: {sched_pick} ({len(target_ids)} animals)")
                if total_cost > 0:
                    post_journal(v_date,
                                 f"Vaccination: {sched_pick} — {len(target_ids)} animals",
                                 [("5100", total_cost, 0), ("1200", 0, total_cost)],
                                 "vaccination", None)
            st.success(f"Vaccination saved for {len(target_ids)} animal(s). "
                       f"Next due: {next_due}")
            st.rerun()

# ---------------- Alerts ----------------
with tab_alerts:
    st.subheader("Upcoming & Overdue")
    df_alerts = pd.DataFrame(query("""
        WITH last_vac AS (
            SELECT v.animal_id, v.vaccine_name, MAX(v.vacc_date) last_date,
                   MAX(v.next_due) next_due
            FROM vaccinations v GROUP BY v.animal_id, v.vaccine_name
        )
        SELECT a.tag, lv.vaccine_name, lv.last_date, lv.next_due,
               CAST(julianday(lv.next_due) - julianday('now') AS INTEGER) days_left,
               CASE
                 WHEN lv.next_due < DATE('now') THEN 'OVERDUE'
                 WHEN lv.next_due <= DATE('now','+7 days') THEN 'Due This Week'
                 WHEN lv.next_due <= DATE('now','+30 days') THEN 'Due in 30 days'
                 ELSE 'OK'
               END AS status
        FROM last_vac lv
        JOIN animals a ON a.animal_id=lv.animal_id
        WHERE a.status='Active' AND lv.next_due IS NOT NULL
          AND lv.next_due <= DATE('now','+60 days')
        ORDER BY lv.next_due
    """))
    if df_alerts.empty:
        st.success("No upcoming vaccination alerts.")
    else:
        st.dataframe(df_alerts, use_container_width=True, hide_index=True)
        export_excel_button(df_alerts, "vaccination_alerts.xlsx")

# ---------------- History ----------------
with tab_hist:
    c1, c2 = st.columns(2)
    s = c1.date_input("From", today - timedelta(days=180), key="vh_s")
    e = c2.date_input("To", today, key="vh_e")
    df = pd.DataFrame(query("""
        SELECT v.vacc_date, a.tag, v.vaccine_name, v.qty, v.cost,
               COALESCE(i.name,'') vaccine_item, v.next_due, v.note
        FROM vaccinations v
        JOIN animals a ON a.animal_id=v.animal_id
        LEFT JOIN items i ON i.item_id=v.item_id
        WHERE v.vacc_date BETWEEN ? AND ?
        ORDER BY v.vacc_date DESC
    """, (str(s), str(e))))
    sterm = st.text_input("Search (animal / vaccine / note)", key="vh_search")
    df_show = df.copy()
    if not df.empty and sterm.strip():
        t = sterm.strip().lower()
        m = (df_show["tag"].astype(str).str.lower().str.contains(t)
             | df_show["vaccine_name"].astype(str).str.lower().str.contains(t)
             | df_show["note"].fillna("").astype(str).str.lower().str.contains(t))
        df_show = df_show[m]
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    if not df.empty:
        m1, m2 = st.columns(2)
        m1.metric("Total doses", f"{df['qty'].sum():.0f}")
        m2.metric("Total cost", f"{df['cost'].sum():,.2f}")
    export_excel_button(df, "vaccinations_history.xlsx")

# ---------------- Master ----------------
with tab_master:
    st.subheader("Vaccine Schedules")
    df_s = pd.DataFrame(query(
        "SELECT sched_id, name, interval_days, note FROM vaccine_schedules ORDER BY name"))
    st.dataframe(df_s, use_container_width=True, hide_index=True)
    with st.form("sch_add", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 2])
        n = c1.text_input("Vaccine name *")
        i = c2.number_input("Interval (days)", min_value=1, value=180)
        note = c3.text_input("Note")
        if st.form_submit_button("Add Schedule", type="primary"):
            if n.strip():
                try:
                    execute("INSERT INTO vaccine_schedules(name,interval_days,note) "
                            "VALUES(?,?,?)", (n.strip(), int(i), note))
                    st.success("Schedule added.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
