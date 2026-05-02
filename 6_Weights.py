"""Weight tracking."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from db import init_db, query, execute
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Weights", layout="wide")
init_db()

require_role("6_Weights")
render_user_sidebar()
st.title("Weight Management")

animals = query("SELECT animal_id, tag FROM animals WHERE status='Active' ORDER BY tag")

with st.form("add_w"):
    c1, c2, c3 = st.columns(3)
    if animals:
        tag = c1.selectbox("Animal", [a["tag"] for a in animals])
        d = c2.date_input("Date", date.today())
        w = c3.number_input("Weight (kg)", min_value=0.0, step=0.5)
        if st.form_submit_button("Save"):
            aid = next(a["animal_id"] for a in animals if a["tag"] == tag)
            execute("INSERT INTO weights(animal_id,weight_date,weight_kg) VALUES(?,?,?)",
                    (aid, str(d), w))
            st.success("Saved.")

st.subheader("Latest Weight per Animal")
df = pd.DataFrame(query("""
    SELECT a.tag, a.breed, w.weight_date latest_date, w.weight_kg latest_weight
    FROM animals a
    LEFT JOIN weights w ON w.id=(
        SELECT id FROM weights w2 WHERE w2.animal_id=a.animal_id
        ORDER BY weight_date DESC, id DESC LIMIT 1)
    WHERE a.status='Active' ORDER BY a.tag
"""))
st.dataframe(df, use_container_width=True, hide_index=True)
export_excel_button(df, "weights_latest.xlsx")

st.subheader("Growth Trend")
if animals:
    sel = st.selectbox("Pick animal", [a["tag"] for a in animals], key="growth")
    aid = next(a["animal_id"] for a in animals if a["tag"] == sel)
    hist = pd.DataFrame(query(
        "SELECT weight_date, weight_kg FROM weights WHERE animal_id=? ORDER BY weight_date",
        (aid,)))
    if not hist.empty:
        fig = px.line(hist, x="weight_date", y="weight_kg", markers=True)
        st.plotly_chart(fig, use_container_width=True)
