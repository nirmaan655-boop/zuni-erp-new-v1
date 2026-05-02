"""RFID Integration (simulated)."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from db import init_db, query, execute
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="RFID", layout="wide")
init_db()

require_role("2_RFID")
render_user_sidebar()
st.title("RFID Integration")

st.subheader("Simulate RFID Scan")
rfid = st.text_input("RFID Tag")
loc = st.text_input("Scan Location", "Gate A")
if st.button("Scan"):
    a = query("SELECT animal_id, tag FROM animals WHERE rfid_tag=?", (rfid,))
    aid = a[0]["animal_id"] if a else None
    execute("INSERT INTO rfid_scans(rfid_tag, animal_id, location) VALUES(?,?,?)",
            (rfid, aid, loc))
    if aid:
        st.success(f"Recognized animal: {a[0]['tag']}")
    else:
        st.warning("Unknown RFID. Logged.")

st.subheader("Bind RFID to Animal")
animals = query("SELECT animal_id, tag, rfid_tag FROM animals ORDER BY tag")
if animals:
    tag = st.selectbox("Animal", [a["tag"] for a in animals])
    new_rfid = st.text_input("RFID for animal")
    if st.button("Bind"):
        execute("UPDATE animals SET rfid_tag=? WHERE tag=?", (new_rfid, tag))
        st.success("Bound.")
        st.rerun()

st.subheader("Scan Log")
df = pd.DataFrame(query("""
    SELECT s.scanned_at, s.rfid_tag, a.tag animal, s.location
    FROM rfid_scans s LEFT JOIN animals a ON a.animal_id=s.animal_id
    ORDER BY s.id DESC LIMIT 500
"""))
st.dataframe(df, use_container_width=True, hide_index=True)
export_excel_button(df, "rfid_scans.xlsx")
