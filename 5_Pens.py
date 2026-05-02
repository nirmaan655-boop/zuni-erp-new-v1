"""Pen Management."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from db import init_db, query, execute
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Pens", layout="wide")
init_db()

require_role("5_Pens")
render_user_sidebar()
st.title("Pen Management")

farms = query("SELECT * FROM farms")
farm_opts = {f["name"]: f["farm_id"] for f in farms}

tab_list, tab_add, tab_weight = st.tabs(["Pens", "Add Pen", "Pen-wise Weights"])

with tab_list:
    df = pd.DataFrame(query("""
        SELECT p.pen_id, p.name pen, f.name farm, p.capacity,
            (SELECT COUNT(*) FROM animals a WHERE a.pen_id=p.pen_id AND a.status='Active') animals
        FROM pens p JOIN farms f ON f.farm_id=p.farm_id ORDER BY p.pen_id
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "pens.xlsx")

with tab_add:
    st.subheader("Create Pen")
    if not farm_opts:
        st.warning("No farms exist yet. Please add a farm below first.")
    else:
        with st.form("add_pen", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Pen Name *")
            farm = c2.selectbox("Farm *", list(farm_opts.keys()))
            cap = c3.number_input("Capacity", min_value=0, step=1)
            create = st.form_submit_button("Create Pen", type="primary")
            if create:
                if not name.strip():
                    st.error("Pen Name is required.")
                else:
                    try:
                        execute("INSERT INTO pens(farm_id,name,capacity) VALUES(?,?,?)",
                                (farm_opts[farm], name.strip(), cap))
                        st.success(f"Pen '{name}' created in farm '{farm}'.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not create pen: {e}")

    st.divider()
    st.subheader("Add Farm")
    with st.form("add_farm", clear_on_submit=True):
        c1, c2 = st.columns(2)
        fname = c1.text_input("Farm Name *")
        floc = c2.text_input("Location")
        save_farm = st.form_submit_button("Add Farm", type="primary")
        if save_farm:
            if not fname.strip():
                st.error("Farm Name is required.")
            else:
                execute("INSERT INTO farms(name,location) VALUES(?,?)", (fname.strip(), floc))
                st.success(f"Farm '{fname}' added.")
                st.rerun()

with tab_weight:
    df = pd.DataFrame(query("""
        SELECT p.name pen,
            COUNT(a.animal_id) animals,
            ROUND(AVG(w.latest_w)::numeric,2) avg_weight,
            ROUND(SUM(w.latest_w)::numeric,2) total_weight
        FROM pens p
        LEFT JOIN animals a ON a.pen_id=p.pen_id AND a.status='Active'
        LEFT JOIN (
            SELECT animal_id, weight_kg AS latest_w FROM weights w1
            WHERE weight_date=(SELECT MAX(weight_date) FROM weights w2 WHERE w2.animal_id=w1.animal_id)
        ) w ON w.animal_id=a.animal_id
        GROUP BY p.pen_id
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "pen_weights.xlsx")
