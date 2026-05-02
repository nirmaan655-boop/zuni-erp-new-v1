"""Livestock Management - Animal master, status, movement history."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Livestock", layout="wide")
init_db()

require_role("1_Livestock")
render_user_sidebar()
st.title("Livestock Management")

tab_master, tab_add, tab_move = st.tabs(["Animal Master", "Add Animal", "Movement History"])

farms = query("SELECT * FROM farms")
pens = query("SELECT * FROM pens")
farm_opts = {f["name"]: f["farm_id"] for f in farms}
pen_opts = {p["name"]: p["pen_id"] for p in pens}

with tab_master:
    df = pd.DataFrame(query("""
        SELECT a.animal_id, a.tag, a.rfid_tag, a.breed, a.category, a.sex,
               a.dob, a.purchase_value AS value, a.status,
               CASE WHEN a.is_pregnant=1 THEN 'Pregnant' ELSE '' END preg,
               a.expected_calving_date AS expected_calving,
               f.name AS farm, p.name AS pen, m.tag AS mother
        FROM animals a
        LEFT JOIN farms f ON f.farm_id=a.farm_id
        LEFT JOIN pens p ON p.pen_id=a.pen_id
        LEFT JOIN animals m ON m.animal_id=a.mother_id
        ORDER BY a.animal_id DESC
    """))
    # search bar
    sc1, sc2, sc3 = st.columns([3, 1, 1])
    sterm = sc1.text_input("Search (tag / breed / category)", key="ls_search")
    cat_filt = sc2.selectbox("Category",
        ["All", "Milking Cow", "Dry Cow", "Pregnant Heifer", "Heifer",
         "Calf", "Bull"], key="ls_cat")
    stat_filt = sc3.selectbox("Status", ["All", "Active", "Sold", "Dead"],
                              key="ls_stat")
    df_show = df.copy()
    if not df.empty:
        if sterm.strip():
            t = sterm.strip().lower()
            mask = (df_show["tag"].astype(str).str.lower().str.contains(t)
                    | df_show["breed"].fillna("").astype(str).str.lower().str.contains(t)
                    | df_show["category"].fillna("").astype(str).str.lower().str.contains(t))
            df_show = df_show[mask]
        if cat_filt != "All":
            df_show = df_show[df_show["category"] == cat_filt]
        if stat_filt != "All":
            df_show = df_show[df_show["status"] == stat_filt]
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    export_excel_button(df, "animals.xlsx")

    st.subheader("Update Status")
    if not df.empty:
        target = st.selectbox("Animal", df["tag"])
        new_status = st.selectbox("New Status", ["Active", "Sold", "Dead"])
        if st.button("Update"):
            execute("UPDATE animals SET status=? WHERE tag=?", (new_status, target))
            st.success("Updated.")
            st.rerun()

with tab_add:
    from datetime import timedelta
    with st.form("add_animal", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tag = c1.text_input("Tag *")
        rfid = c2.text_input("RFID Tag")
        breed = c3.selectbox("Breed",
            ["Holstein Friesian", "Jersey", "Sahiwal", "Cholistani",
             "Sahiwal Cross", "HF Cross", "Australian", "Brown Swiss",
             "Buffalo (Nili Ravi)", "Buffalo (Kundi)", "Other"])
        c4, c5, c6 = st.columns(3)
        sex = c4.selectbox("Gender", ["F (Female)", "M (Male)"])
        category = c5.selectbox("Category / Type *",
            ["Milking Cow", "Dry Cow", "Pregnant Heifer", "Heifer",
             "Calf", "Bull"])
        status = c6.selectbox("Status", ["Active", "Sold", "Dead"])

        c7, c8, c9 = st.columns(3)
        dob = c7.date_input("Date of Birth", value=date.today() - timedelta(days=365))
        purchase_value = c8.number_input("Animal Value (purchase price)",
                                          min_value=0.0, step=500.0, value=0.0)
        farm = c9.selectbox("Farm", list(farm_opts.keys()) if farm_opts else ["-"])

        c10, c11, c12 = st.columns(3)
        pen = c10.selectbox("Pen", ["-"] + list(pen_opts.keys()))
        is_preg = c11.checkbox("Currently Pregnant?", value=False)
        preg_days = c12.number_input(
            "If pregnant — days into pregnancy",
            min_value=0, max_value=300, step=1, value=0,
            help="0–280 days. ECD will be auto-calculated (calving ~ 280 days from conception).")

        if st.form_submit_button("Save Animal", type="primary"):
            if not tag:
                st.error("Tag required.")
            else:
                try:
                    sex_v = "F" if sex.startswith("F") else "M"
                    preg_start = None
                    ecd = None
                    if is_preg and preg_days > 0:
                        preg_start = date.today() - timedelta(days=int(preg_days))
                        ecd = preg_start + timedelta(days=280)
                    execute(
                        "INSERT INTO animals(tag,rfid_tag,breed,category,dob,sex,"
                        "status,farm_id,pen_id,purchase_value,is_pregnant,"
                        "preg_start_date,expected_calving_date) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (tag.strip(), rfid or None, breed, category, str(dob),
                         sex_v, status,
                         farm_opts.get(farm), pen_opts.get(pen),
                         purchase_value, 1 if is_preg else 0,
                         str(preg_start) if preg_start else None,
                         str(ecd) if ecd else None))
                    msg = f"Animal {tag} added ({category}, {breed})"
                    if is_preg:
                        msg += f" — pregnant {preg_days}d, ECD {ecd}"
                    st.success(msg)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

with tab_move:
    st.subheader("Move Animal Between Pens")
    animals = query("SELECT animal_id, tag, pen_id FROM animals WHERE status='Active'")
    if animals and pens:
        atag = st.selectbox("Animal", [a["tag"] for a in animals])
        new_pen = st.selectbox("Move to Pen", list(pen_opts.keys()))
        note = st.text_input("Note")
        if st.button("Move"):
            a = next(a for a in animals if a["tag"] == atag)
            execute(
                "INSERT INTO animal_movements(animal_id,from_pen_id,to_pen_id,move_date,note) "
                "VALUES(?,?,?,?,?)",
                (a["animal_id"], a["pen_id"], pen_opts[new_pen], str(date.today()), note))
            execute("UPDATE animals SET pen_id=? WHERE animal_id=?",
                    (pen_opts[new_pen], a["animal_id"]))
            st.success("Moved.")
            st.rerun()

    st.subheader("Movement Log")
    df_mv = pd.DataFrame(query("""
        SELECT m.move_date, a.tag animal, p1.name from_pen, p2.name to_pen, m.note
        FROM animal_movements m
        JOIN animals a ON a.animal_id=m.animal_id
        LEFT JOIN pens p1 ON p1.pen_id=m.from_pen_id
        LEFT JOIN pens p2 ON p2.pen_id=m.to_pen_id
        ORDER BY m.id DESC
    """))
    st.dataframe(df_mv, use_container_width=True, hide_index=True)
    export_excel_button(df_mv, "movements.xlsx")
