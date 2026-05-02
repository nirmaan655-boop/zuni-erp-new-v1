"""Shared helpers."""
import io
import pandas as pd
import streamlit as st


def export_excel_button(df: pd.DataFrame, filename: str, label: str = "Download Excel"):
    if df is None or df.empty:
        st.info("No data to export.")
        return
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Report", index=False)
    st.download_button(label, buf.getvalue(),
                       file_name=filename,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def kpi_card(col, label, value, help_text=None):
    col.metric(label, value, help=help_text)
