"""Breeding & Reproduction - AI, Bull Service, Heat, Preg Check, Abortion, Dry Off."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import (init_db, query, execute, post_journal,
                add_stock_move, stock_balance)
from auth import require_role, render_user_sidebar
from utils import export_excel_button

GESTATION_DAYS = 280
DRY_OFF_DAYS_BEFORE = 60   # start of dry-off period
CLOSEUP_DAYS_BEFORE = 21   # close-up before calving

st.set_page_config(page_title="Breeding", layout="wide")
init_db()

require_role("15_Breeding")
render_user_sidebar()
st.title("Breeding & Reproduction")
st.caption("AI, Bull Service, Heat detection, Pregnancy check, Abortion, Dry Off — "
           "with semen straw inventory & per-animal cost tracking.")

# ----- Top KPIs -----
today = date.today()
preg_count = query("SELECT COUNT(*) c FROM animals WHERE is_pregnant=1 AND status='Active'")[0]["c"]
dry_count = query("SELECT COUNT(*) c FROM animals WHERE is_dry=1 AND status='Active'")[0]["c"]
ai_30 = query("SELECT COUNT(*) c FROM breeding_events WHERE event_type='AI' "
              "AND event_date >= DATE('now','-30 days')")[0]["c"]
straws_30 = query("SELECT COALESCE(SUM(straws_used),0) s FROM breeding_events "
                  "WHERE event_type='AI' AND event_date >= DATE('now','-30 days')")[0]["s"]
cost_30 = query("SELECT COALESCE(SUM(cost),0) v FROM breeding_events "
                "WHERE event_date >= DATE('now','-30 days')")[0]["v"]

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Pregnant Animals", preg_count)
k2.metric("Dry Animals", dry_count)
k3.metric("AI (last 30 days)", ai_30)
k4.metric("Straws used (30d)", f"{straws_30:.0f}")
k5.metric("Breeding cost (30d)", f"{cost_30:,.0f}")

(tab_heat, tab_ai, tab_bull, tab_preg, tab_ab, tab_dry,
 tab_master, tab_hist, tab_cost) = st.tabs(
    ["Heat", "AI (Insemination)", "Bull Service", "Pregnancy Check",
     "Abortion", "Dry Off", "Bulls / Protocols",
     "Breeding History", "Cost per Animal"])


def active_females():
    return query("SELECT animal_id, tag FROM animals "
                 "WHERE status='Active' AND sex='F' ORDER BY tag")


def insert_event(animal_id, event_date, event_type, bull_id=None,
                 semen_item_id=None, straws_used=0, cost=0,
                 protocol_id=None, result=None, note=None):
    return execute(
        "INSERT INTO breeding_events(animal_id,event_date,event_type,bull_id,"
        "semen_item_id,straws_used,cost,protocol_id,result,note) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (animal_id, str(event_date), event_type, bull_id,
         semen_item_id, straws_used, cost, protocol_id, result, note))


# ---------------- Heat ----------------
with tab_heat:
    st.subheader("Record Heat (Estrus)")
    fems = active_females()
    if not fems:
        st.info("No active females.")
    else:
        with st.form("heat_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            tag = c1.selectbox("Animal", [a["tag"] for a in fems])
            d = c2.date_input("Heat Date", today)
            sign = c3.selectbox("Sign", ["Standing heat", "Mounting", "Mucus discharge",
                                          "Restless", "Bellowing", "Other"])
            note = st.text_input("Note")
            if st.form_submit_button("Save Heat", type="primary"):
                aid = next(a["animal_id"] for a in fems if a["tag"] == tag)
                insert_event(aid, d, "Heat", note=f"{sign} | {note}")
                st.success(f"Heat recorded for {tag}.")
                st.rerun()


# ---------------- AI ----------------
with tab_ai:
    st.subheader("Artificial Insemination")
    fems = active_females()
    bulls = query("SELECT bull_id, name FROM bulls ORDER BY name")
    semen_items = query("""
        SELECT i.item_id, i.name, i.unit_cost,
               COALESCE((SELECT SUM(CASE WHEN m.move_type='IN' THEN m.qty ELSE -m.qty END)
                         FROM stock_moves m WHERE m.item_id=i.item_id),0) AS bal
        FROM items i JOIN stores s ON s.store_id=i.store_id
        WHERE s.name='Semen Store' ORDER BY i.name
    """)
    protocols = query("SELECT protocol_id, name FROM ai_protocols ORDER BY name")

    if not fems:
        st.info("No active females.")
    elif not bulls:
        st.warning("Add a bull first in **Bulls / Protocols** tab.")
    elif not semen_items:
        st.warning("Add semen items in **Inventory → Semen Store** first (so straws can be deducted).")
    else:
        c1, c2, c3 = st.columns(3)
        tag = c1.selectbox("Cow", [a["tag"] for a in fems], key="ai_tag")
        d = c2.date_input("AI Date", today, key="ai_d")
        bull_pick = c3.selectbox("Bull", [b["name"] for b in bulls], key="ai_bull")

        c4, c5, c6 = st.columns(3)
        sem_labels = [f"{s['name']} (stock {s['bal']:.0f}, {s['unit_cost']:.0f}/straw)"
                      for s in semen_items]
        sem_pick = c4.selectbox("Semen (auto from Semen Store)", sem_labels, key="ai_sem")
        sem_obj = semen_items[sem_labels.index(sem_pick)]
        straws = c5.number_input("Straws used", min_value=1, step=1, value=1, key="ai_straws")
        proto = c6.selectbox("AI Protocol", ["-"] + [p["name"] for p in protocols], key="ai_proto")

        c7, c8 = st.columns(2)
        unit_cost = c7.number_input("Cost per Straw (auto)",
                                    min_value=0.0, step=10.0,
                                    value=float(sem_obj["unit_cost"] or 0),
                                    key="ai_uc")
        total_cost = straws * unit_cost
        c8.metric("Total AI Cost", f"{total_cost:,.2f}")
        note = st.text_input("Note", key="ai_note")

        st.info(f"Available straws of {sem_obj['name']}: **{sem_obj['bal']:.0f}**")
        ok = straws <= sem_obj["bal"]
        if not ok and sem_obj["bal"] >= 0:
            st.error("Not enough straws in Semen Store.")

        if st.button("Record AI", type="primary", disabled=not ok, key="ai_post"):
            aid = next(a["animal_id"] for a in fems if a["tag"] == tag)
            bid = next(b["bull_id"] for b in bulls if b["name"] == bull_pick)
            pid = next((p["protocol_id"] for p in protocols if p["name"] == proto), None)

            eid = insert_event(aid, d, "AI", bull_id=bid,
                               semen_item_id=sem_obj["item_id"],
                               straws_used=straws, cost=total_cost,
                               protocol_id=pid,
                               result="Pending",
                               note=note)
            # Save last AI date on the cow
            execute("UPDATE animals SET last_ai_date=? WHERE animal_id=?",
                    (str(d), aid))
            # Deduct semen straws from inventory
            add_stock_move(sem_obj["item_id"], d, "OUT", straws,
                           unit_cost, "ai", eid, f"AI {tag} by {bull_pick}")
            # Post journal: Dr Breeding Expense / Cr Inventory
            if total_cost > 0:
                post_journal(d, f"AI: {tag} by {bull_pick} ({straws} straws)",
                             [("5600", total_cost, 0), ("1200", 0, total_cost)],
                             "ai", eid)
            st.success(f"AI recorded for {tag}. Cost {total_cost:,.2f} booked. "
                       f"{straws} straw(s) deducted from semen store.")
            st.rerun()


# ---------------- Bull Service (Natural) ----------------
with tab_bull:
    st.subheader("Natural Bull Service (Bull Meet)")
    fems = active_females()
    bulls = query("SELECT bull_id, name FROM bulls ORDER BY name")
    if not fems or not bulls:
        st.info("Need active females and at least one bull.")
    else:
        with st.form("bs_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            tag = c1.selectbox("Cow", [a["tag"] for a in fems])
            d = c2.date_input("Service Date", today)
            bull_pick = c3.selectbox("Bull", [b["name"] for b in bulls])
            cost = c4.number_input("Service Fee (optional)", min_value=0.0, step=10.0)
            note = st.text_input("Note")
            if st.form_submit_button("Save Service", type="primary"):
                aid = next(a["animal_id"] for a in fems if a["tag"] == tag)
                bid = next(b["bull_id"] for b in bulls if b["name"] == bull_pick)
                eid = insert_event(aid, d, "Bull Service", bull_id=bid,
                                   cost=cost, result="Pending", note=note)
                if cost > 0:
                    post_journal(d, f"Bull service: {tag} by {bull_pick}",
                                 [("5600", cost, 0), ("1000", 0, cost)],
                                 "bullsvc", eid)
                st.success(f"Service recorded for {tag}.")
                st.rerun()


# ---------------- Pregnancy Check (PD1 / PD2) ----------------
with tab_preg:
    st.subheader("Pregnancy Check — PD1 (1st check) & PD2 (confirmation)")
    st.caption(
        "**PD1** is done ~30–45 days after AI/service. "
        "**PD2** is the confirmation check ~60–90 days after AI/service. "
        "On a positive **PD2**, Expected Calving Date (ECD) is auto-set "
        f"= AI date + {GESTATION_DAYS} days, and the cow is officially "
        "marked pregnant.")

    # ----- Pending PD1 -----
    pd1_due = pd.DataFrame(query("""
        SELECT a.animal_id, a.tag, a.last_ai_date,
               CAST(julianday('now') - julianday(a.last_ai_date) AS INTEGER) days_post_ai
        FROM animals a
        WHERE a.status='Active' AND a.sex='F'
          AND a.last_ai_date IS NOT NULL
          AND a.is_pregnant=0
          AND julianday('now') - julianday(a.last_ai_date) BETWEEN 30 AND 60
          AND NOT EXISTS (SELECT 1 FROM breeding_events b
                          WHERE b.animal_id=a.animal_id AND b.event_type='PD1'
                            AND b.event_date >= a.last_ai_date)
    """))
    if not pd1_due.empty:
        st.warning(f"**PD1 due — {len(pd1_due)} cow(s) ready for first pregnancy check:**")
        st.dataframe(pd1_due, use_container_width=True, hide_index=True)

    # ----- Pending PD2 -----
    pd2_due = pd.DataFrame(query("""
        SELECT a.animal_id, a.tag, a.last_ai_date,
               CAST(julianday('now') - julianday(a.last_ai_date) AS INTEGER) days_post_ai
        FROM animals a
        WHERE a.status='Active' AND a.sex='F'
          AND a.last_ai_date IS NOT NULL
          AND julianday('now') - julianday(a.last_ai_date) BETWEEN 60 AND 100
          AND EXISTS (SELECT 1 FROM breeding_events b
                      WHERE b.animal_id=a.animal_id AND b.event_type='PD1'
                        AND b.result='Positive'
                        AND b.event_date >= a.last_ai_date)
          AND NOT EXISTS (SELECT 1 FROM breeding_events b
                          WHERE b.animal_id=a.animal_id AND b.event_type='PD2'
                            AND b.event_date >= a.last_ai_date)
    """))
    if not pd2_due.empty:
        st.warning(f"**PD2 confirmation due — {len(pd2_due)} cow(s):**")
        st.dataframe(pd2_due, use_container_width=True, hide_index=True)

    if pd1_due.empty and pd2_due.empty:
        st.success("No pending pregnancy checks at this moment.")

    st.divider()
    st.markdown("### Record Pregnancy Check")
    fems = active_females()
    if fems:
        with st.form("pd_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            tag = c1.selectbox("Animal", [a["tag"] for a in fems])
            stage = c2.selectbox("Stage", ["PD1 (1st check)", "PD2 (confirmation)"])
            d = c3.date_input("Check Date", today)
            result = c4.selectbox("Result", ["Positive", "Negative", "Re-check"])
            note = st.text_input("Note")
            if st.form_submit_button("Save Pregnancy Check", type="primary"):
                aid = next(a["animal_id"] for a in fems if a["tag"] == tag)
                stage_code = "PD1" if stage.startswith("PD1") else "PD2"
                # Get cow info
                cow = query("SELECT last_ai_date, last_calving_date FROM animals "
                            "WHERE animal_id=?", (aid,))[0]
                last_ai = cow["last_ai_date"]
                ecd = None
                if stage_code == "PD2" and result == "Positive" and last_ai:
                    ecd = (date.fromisoformat(last_ai) + timedelta(days=GESTATION_DAYS))
                insert_event(aid, d, stage_code, result=result, note=note)
                # Update animal — only PD2 positive officially confirms pregnancy
                if result == "Positive" and stage_code == "PD2" and ecd:
                    execute(
                        "UPDATE animals SET is_pregnant=1, is_dry=0, "
                        "preg_start_date=?, expected_calving_date=? "
                        "WHERE animal_id=?",
                        (last_ai, str(ecd), aid))
                elif result == "Negative":
                    execute("UPDATE animals SET is_pregnant=0, "
                            "preg_start_date=NULL, expected_calving_date=NULL "
                            "WHERE animal_id=?", (aid,))
                # Update underlying AI/Service result
                execute("""UPDATE breeding_events SET result=?
                           WHERE animal_id=? AND result='Pending'
                             AND event_type IN ('AI','Bull Service')""",
                        (result, aid))
                msg = f"{stage_code} ({result}) recorded for {tag}."
                if ecd:
                    msg += f" Expected calving date set to **{ecd}**."
                st.success(msg)
                st.rerun()


# ---------------- Abortion ----------------
with tab_ab:
    st.subheader("Record Abortion")
    fems = active_females()
    if fems:
        with st.form("ab_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            tag = c1.selectbox("Animal", [a["tag"] for a in fems])
            d = c2.date_input("Abortion Date", today)
            stage = c3.text_input("Gestation Stage / Cause", "Unknown")
            note = st.text_input("Note")
            if st.form_submit_button("Save Abortion", type="primary"):
                aid = next(a["animal_id"] for a in fems if a["tag"] == tag)
                insert_event(aid, d, "Abortion", note=f"{stage} | {note}")
                # Reset pregnancy
                execute("UPDATE animals SET is_pregnant=0 WHERE animal_id=?", (aid,))
                st.success(f"Abortion recorded for {tag}. Pregnancy reset.")
                st.rerun()


# ---------------- Dry Off ----------------
with tab_dry:
    st.subheader("Dry Off")
    fems = active_females()
    if fems:
        with st.form("dry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            tag = c1.selectbox("Animal", [a["tag"] for a in fems])
            d = c2.date_input("Dry-off Date", today)
            note = st.text_input("Note", "Dried off ahead of next calving")
            if st.form_submit_button("Mark as Dry", type="primary"):
                aid = next(a["animal_id"] for a in fems if a["tag"] == tag)
                insert_event(aid, d, "Dry Off", note=note)
                execute("UPDATE animals SET is_dry=1 WHERE animal_id=?", (aid,))
                st.success(f"{tag} marked as dry.")
                st.rerun()

        st.divider()
        df_dry = pd.DataFrame(query("""
            SELECT a.tag, a.is_pregnant, a.is_dry
            FROM animals a WHERE a.status='Active' AND a.sex='F'
            ORDER BY a.is_dry DESC, a.is_pregnant DESC, a.tag
        """))
        st.write("**Status overview:**")
        st.dataframe(df_dry, use_container_width=True, hide_index=True)


# ---------------- Bulls / Protocols ----------------
with tab_master:
    st.subheader("Bulls Master")
    df_b = pd.DataFrame(query("SELECT bull_id, name, breed, bull_type, note FROM bulls ORDER BY name"))
    st.dataframe(df_b, use_container_width=True, hide_index=True)
    with st.form("bull_add", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        bn = c1.text_input("Bull Name *")
        bb = c2.text_input("Breed", "Holstein")
        bt = c3.selectbox("Type", ["AI", "Natural"])
        bnote = c4.text_input("Note")
        if st.form_submit_button("Add Bull", type="primary"):
            if not bn.strip():
                st.error("Name required.")
            else:
                try:
                    execute("INSERT INTO bulls(name,breed,bull_type,note) VALUES(?,?,?,?)",
                            (bn.strip(), bb, bt, bnote))
                    st.success("Bull added.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    st.divider()
    st.subheader("AI Protocols")
    df_p = pd.DataFrame(query("SELECT protocol_id, name, description FROM ai_protocols ORDER BY name"))
    st.dataframe(df_p, use_container_width=True, hide_index=True)
    with st.form("proto_add", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        pn = c1.text_input("Protocol Name *")
        pd_ = c2.text_input("Description")
        if st.form_submit_button("Add Protocol", type="primary"):
            if pn.strip():
                try:
                    execute("INSERT INTO ai_protocols(name, description) VALUES(?,?)",
                            (pn.strip(), pd_))
                    st.success("Protocol added.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# ---------------- History ----------------
with tab_hist:
    c1, c2, c3 = st.columns(3)
    s = c1.date_input("From", date.today() - timedelta(days=180), key="bh_s")
    e = c2.date_input("To", date.today(), key="bh_e")
    type_filter = c3.selectbox("Event Type",
                                ["All", "Heat", "AI", "Bull Service",
                                 "Preg Check", "Abortion", "Dry Off"], key="bh_t")
    sql = """
      SELECT b.event_date, b.event_type, a.tag,
             COALESCE(bl.name,'') bull,
             COALESCE(i.name,'') semen,
             b.straws_used, b.cost,
             COALESCE(p.name,'') protocol, b.result, b.note
      FROM breeding_events b
      JOIN animals a ON a.animal_id=b.animal_id
      LEFT JOIN bulls bl ON bl.bull_id=b.bull_id
      LEFT JOIN items i ON i.item_id=b.semen_item_id
      LEFT JOIN ai_protocols p ON p.protocol_id=b.protocol_id
      WHERE b.event_date BETWEEN ? AND ?
    """
    params = [str(s), str(e)]
    if type_filter != "All":
        sql += " AND b.event_type=?"
        params.append(type_filter)
    sql += " ORDER BY b.event_date DESC, b.event_id DESC"
    df = pd.DataFrame(query(sql, tuple(params)))
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Events", len(df))
        m2.metric("Total Straws", f"{df['straws_used'].sum():.0f}")
        m3.metric("Total Cost", f"{df['cost'].sum():,.2f}")
    export_excel_button(df, "breeding_history.xlsx")


# ---------------- Cost per Animal ----------------
with tab_cost:
    st.subheader("Per-Animal Breeding Cost")
    c1, c2 = st.columns(2)
    s = c1.date_input("From", date.today() - timedelta(days=180), key="bc_s")
    e = c2.date_input("To", date.today(), key="bc_e")
    df = pd.DataFrame(query("""
      SELECT a.tag,
             COUNT(CASE WHEN b.event_type='AI' THEN 1 END) AS ai_count,
             COUNT(CASE WHEN b.event_type='Bull Service' THEN 1 END) AS service_count,
             COALESCE(SUM(b.straws_used),0) straws,
             COALESCE(SUM(b.cost),0) total_cost
      FROM animals a
      LEFT JOIN breeding_events b ON b.animal_id=a.animal_id
            AND b.event_date BETWEEN ? AND ?
      WHERE a.status='Active' AND a.sex='F'
      GROUP BY a.animal_id, a.tag
      HAVING COUNT(CASE WHEN b.event_type='AI' THEN 1 END)
           + COUNT(CASE WHEN b.event_type='Bull Service' THEN 1 END) > 0
      ORDER BY total_cost DESC
    """, (str(s), str(e))))
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        st.metric("Grand Total Breeding Cost", f"{df['total_cost'].sum():,.2f}")
    export_excel_button(df, "breeding_cost_per_animal.xlsx")
