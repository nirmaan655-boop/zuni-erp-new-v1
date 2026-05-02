"""Calving system - single/twins."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Calving", layout="wide")
init_db()

require_role("4_Calving")
render_user_sidebar()
st.title("Calving Records")

mothers = query("SELECT animal_id, tag, farm_id, pen_id FROM animals WHERE sex='F' AND status='Active'")

if not mothers:
    st.info("Add active female animals first.")
else:
    with st.form("calve", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        mtag = c1.selectbox("Mother", [m["tag"] for m in mothers])
        cdate = c2.date_input("Calving Date", date.today())
        ctype = c3.selectbox("Type", ["Single", "Twins"])
        sire_tag = c4.text_input("Sire (Father) Tag")

        c1b, c2b = st.columns(2)
        delivery_status = c1b.selectbox(
            "Delivery Status",
            ["Normal", "Dystocia (difficult)", "Caesarean", "Assisted",
             "Stillbirth", "Abortion (late)", "Retained Placenta"])
        complications = c2b.text_input("Complications / Notes (optional)")

        st.markdown("**Calf 1**")
        c5, c6, c7 = st.columns(3)
        calf1_tag = c5.text_input("Calf 1 Tag *")
        calf1_sex = c6.selectbox("Calf 1 Sex", ["F", "M"], key="s1")
        calf1_wt = c7.number_input("Calf 1 Birth Weight (kg)", min_value=0.0, step=0.1, key="w1")

        st.markdown("**Calf 2 (twins only)**")
        c8, c9, c10 = st.columns(3)
        calf2_tag = c8.text_input("Calf 2 Tag")
        calf2_sex = c9.selectbox("Calf 2 Sex", ["F", "M"], key="s2")
        calf2_wt = c10.number_input("Calf 2 Birth Weight (kg)", min_value=0.0, step=0.1, key="w2")

        note = st.text_input("Note")
        submitted = st.form_submit_button("Record Calving", type="primary")
        if submitted:
            mother = next(m for m in mothers if m["tag"] == mtag)
            if not calf1_tag.strip():
                st.error("Calf 1 tag is required.")
            else:
                try:
                    c1id = execute(
                        "INSERT INTO animals(tag,breed,dob,sex,status,farm_id,pen_id,mother_id) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (calf1_tag.strip(), "Calf", str(cdate), calf1_sex, "Active",
                         mother["farm_id"], mother["pen_id"], mother["animal_id"]))
                    if calf1_wt > 0:
                        execute("INSERT INTO weights(animal_id,weight_date,weight_kg) VALUES(?,?,?)",
                                (c1id, str(cdate), calf1_wt))
                    c2id = None
                    if ctype == "Twins" and calf2_tag.strip():
                        c2id = execute(
                            "INSERT INTO animals(tag,breed,dob,sex,status,farm_id,pen_id,mother_id) "
                            "VALUES(?,?,?,?,?,?,?,?)",
                            (calf2_tag.strip(), "Calf", str(cdate), calf2_sex, "Active",
                             mother["farm_id"], mother["pen_id"], mother["animal_id"]))
                        if calf2_wt > 0:
                            execute("INSERT INTO weights(animal_id,weight_date,weight_kg) VALUES(?,?,?)",
                                    (c2id, str(cdate), calf2_wt))
                    execute(
                        "INSERT INTO calvings(mother_id,calving_date,calving_type,calf1_id,calf2_id,"
                        "sire_tag,calf1_weight,calf2_weight,delivery_status,complications,note) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (mother["animal_id"], str(cdate), ctype, c1id, c2id,
                         sire_tag.strip() or None, calf1_wt, calf2_wt,
                         delivery_status, complications, note))
                    # Reset pregnancy status & save last calving date
                    execute("UPDATE animals SET is_pregnant=0, is_dry=0, "
                            "last_calving_date=?, preg_start_date=NULL, "
                            "expected_calving_date=NULL "
                            "WHERE animal_id=?", (str(cdate), mother["animal_id"]))
                    st.success(f"Calving recorded ({delivery_status}). Mother set to lactating.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

st.divider()
st.subheader("Pregnancy Status (used for dry-off alerts)")
preg_animals = query("SELECT animal_id, tag, is_pregnant FROM animals WHERE sex='F' AND status='Active' ORDER BY tag")
if preg_animals:
    pc1, pc2, pc3 = st.columns([2, 1, 1])
    sel_tag = pc1.selectbox("Animal", [a["tag"] for a in preg_animals], key="preg_sel")
    cur_state = next(a["is_pregnant"] for a in preg_animals if a["tag"] == sel_tag)
    pc2.metric("Current", "Pregnant" if cur_state else "Not pregnant")
    new_state = pc3.radio("Mark as", ["Pregnant", "Not pregnant"],
                          index=0 if not cur_state else 1, horizontal=True, key="preg_radio")
    if st.button("Update Pregnancy", type="primary", key="preg_btn"):
        aid = next(a["animal_id"] for a in preg_animals if a["tag"] == sel_tag)
        execute("UPDATE animals SET is_pregnant=? WHERE animal_id=?",
                (1 if new_state == "Pregnant" else 0, aid))
        st.success(f"{sel_tag} marked as {new_state}.")
        st.rerun()

    df_preg = pd.DataFrame(query("""
        SELECT a.tag, ROUND(COALESCE(AVG(m.litres)*3, 0)::numeric, 2) avg_daily_l
        FROM animals a
        LEFT JOIN milk_records m ON m.animal_id=a.animal_id
            AND m.record_date >= DATE('now', '-7 days')
        WHERE a.is_pregnant=1 AND a.status='Active'
        GROUP BY a.animal_id, a.tag ORDER BY avg_daily_l ASC
    """))
    if not df_preg.empty:
        st.write("**Currently pregnant animals (with 7-day avg daily milk):**")
        st.dataframe(df_preg, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Calving History")
df = pd.DataFrame(query("""
    SELECT c.calving_date, m.tag mother, c.sire_tag sire, c.calving_type,
           c.delivery_status status, c.complications,
           c1.tag calf1, c.calf1_weight "calf1_kg",
           c2.tag calf2, c.calf2_weight "calf2_kg", c.note
    FROM calvings c
    JOIN animals m ON m.animal_id=c.mother_id
    LEFT JOIN animals c1 ON c1.animal_id=c.calf1_id
    LEFT JOIN animals c2 ON c2.animal_id=c.calf2_id
    ORDER BY c.id DESC
"""))
# Search bar
sc1, sc2 = st.columns([3, 1])
sterm = sc1.text_input("Search calving (mother / sire / status / note)", key="cal_search")
sfilter = sc2.selectbox("Status filter",
    ["All", "Normal", "Dystocia (difficult)", "Caesarean", "Assisted",
     "Stillbirth", "Abortion (late)", "Retained Placenta"], key="cal_filt")
df_show = df.copy() if not df.empty else df
if not df.empty:
    if sterm.strip():
        t = sterm.strip().lower()
        m = (df_show["mother"].astype(str).str.lower().str.contains(t)
             | df_show["sire"].astype(str).fillna("").str.lower().str.contains(t)
             | df_show["status"].astype(str).str.lower().str.contains(t)
             | df_show["note"].astype(str).fillna("").str.lower().str.contains(t)
             | df_show["complications"].astype(str).fillna("").str.lower().str.contains(t))
        df_show = df_show[m]
    if sfilter != "All":
        df_show = df_show[df_show["status"] == sfilter]
st.dataframe(df_show, use_container_width=True, hide_index=True)
export_excel_button(df, "calvings.xlsx")
