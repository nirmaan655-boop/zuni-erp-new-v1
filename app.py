"""Zuni Dairy ERP - Main dashboard."""
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

from db import (init_db, query, milk_store_balance, latest_milk_rate,
                account_balance)
from auth import require_login, render_user_sidebar

ORANGE_BLUE = ["#1ABC9C", "#3498DB", "#F39C12", "#E74C3C", "#2ECC71", "#9B59B6"]

st.set_page_config(page_title="Zuni Dairy ERP", layout="wide", page_icon="🐄")
init_db()

# ---- Login gate ----
user = require_login()
render_user_sidebar()

# ----- Custom styling: Professional Corporate ERP -----
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    :root {
        --bg:           #ECF0F2;
        --surface:      #FFFFFF;
        --surface-2:    #F8FAFC;
        --border:       #E1E5EB;
        --border-soft:  #EEF2F6;
        --text:         #2C3E50;
        --text-muted:   #7B8A9C;
        --text-light:   #BDC3C7;
        --primary:      #1ABC9C;
        --primary-dark: #16A085;
        --primary-soft: #E8F8F5;
        --sidebar-bg:   #2C3E50;
        --sidebar-2:    #34495E;
        --sidebar-txt:  #ECF0F1;
        --sidebar-mute: #95A5A6;
        --sidebar-act:  #1ABC9C;
        --success:      #2ECC71;
        --warning:      #F39C12;
        --danger:       #E74C3C;
        --info:         #3498DB;
    }

    /* Global font */
    html, body, [class*="css"], .stApp, .stMarkdown,
    button, input, select, textarea {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont,
                     'Segoe UI', sans-serif !important;
        -webkit-font-smoothing: antialiased;
        color: var(--text);
    }

    /* Page background */
    .stApp { background: var(--bg); }

    /* Block container */
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2.5rem;
        max-width: 100%;
    }

    /* ---------- Metric cards (st.metric) ---------- */
    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
        transition: all 0.18s ease;
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: 0 4px 14px rgba(15,23,42,0.08);
        transform: translateY(-1px);
        border-color: #CBD5E1;
    }
    div[data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
        font-weight: 600 !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.7px;
    }
    div[data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-weight: 700 !important;
        font-size: 26px !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ---------- App background (subtle gradient) ---------- */
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(at 12% 0%, rgba(26,188,156,0.06) 0%, transparent 45%),
            radial-gradient(at 90% 5%, rgba(52,152,219,0.05) 0%, transparent 50%),
            linear-gradient(180deg, #F4F7FA 0%, #ECF0F2 100%) !important;
    }
    [data-testid="stMain"] { background: transparent !important; }
    .block-container { padding-top: 1.4rem !important; }

    /* ---------- Colored KPI cards ---------- */
    .kpi-card {
        border-radius: 14px;
        padding: 20px 22px;
        color: #FFFFFF !important;
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 110px;
        margin-bottom: 14px;
        position: relative;
        overflow: hidden;
        box-shadow:
            0 10px 24px rgba(15,23,42,0.10),
            0 2px 6px rgba(15,23,42,0.06);
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        backdrop-filter: blur(4px);
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow:
            0 16px 32px rgba(15,23,42,0.14),
            0 4px 10px rgba(15,23,42,0.08);
    }
    .kpi-card * { color: #FFFFFF !important; }
    .kpi-card::before {
        content: ""; position: absolute; left: 0; top: 0; bottom: 0;
        width: 5px; background: rgba(255,255,255,0.45);
        border-radius: 14px 0 0 14px;
    }
    .kpi-card::after {
        content: ""; position: absolute; right: -40px; top: -40px;
        width: 150px; height: 150px; border-radius: 50%;
        background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0) 70%);
    }
    .kpi-card .num {
        font-size: 34px; font-weight: 800; line-height: 1;
        letter-spacing: -0.8px;
        text-shadow: 0 2px 4px rgba(0,0,0,0.12);
    }
    .kpi-card .lbl {
        font-size: 11px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 1.2px;
        opacity: 0.95; margin-top: 8px;
    }
    .kpi-card .ico {
        font-size: 50px; opacity: 0.40; z-index: 1;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.15));
    }
    .kpi-red    { background: linear-gradient(135deg,#FF6B6B 0%,#C0392B 100%); }
    .kpi-orange { background: linear-gradient(135deg,#FFB74D 0%,#E67E22 100%); }
    .kpi-blue   { background: linear-gradient(135deg,#5DADE2 0%,#2471A3 100%); }
    .kpi-green  { background: linear-gradient(135deg,#7DCEA0 0%,#229954 100%); }
    .kpi-teal   { background: linear-gradient(135deg,#48D1CC 0%,#117A65 100%); }
    .kpi-purple { background: linear-gradient(135deg,#BB8FCE 0%,#7D3C98 100%); }

    /* ---------- Headings ---------- */
    h1 {
        color: var(--text) !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    h2, h3 {
        color: var(--text) !important;
        font-weight: 600 !important;
        border: none !important;
        padding: 0 !important;
        margin-top: 20px !important;
        margin-bottom: 10px !important;
        position: relative;
        padding-left: 14px !important;
    }
    h2::before, h3::before {
        content: ""; position: absolute; left: 0; top: 8px; bottom: 8px;
        width: 4px; border-radius: 2px;
        background: linear-gradient(180deg, #1ABC9C 0%, #26C6DA 100%);
    }
    h2 { font-size: 22px !important; }
    h3 { font-size: 17px !important; }

    /* ---------- Panel / chart card ---------- */
    .panel-card {
        background: var(--surface);
        border-radius: 10px;
        padding: 18px 20px;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
        border: 1px solid var(--border);
        margin-bottom: 14px;
    }

    /* ---------- Tabs ---------- */
    [data-baseweb="tab-list"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 4px;
        gap: 2px !important;
    }
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border-radius: 6px !important;
        color: var(--text-muted) !important;
        font-weight: 500 !important;
        font-size: 13px !important;
        padding: 8px 14px !important;
        border: none !important;
        transition: all 0.15s ease;
    }
    button[data-baseweb="tab"]:hover {
        background-color: var(--surface-2) !important;
        color: var(--text) !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #1ABC9C 0%, #26C6DA 100%) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 6px rgba(26,188,156,0.30);
    }
    [data-baseweb="tab-highlight"] { display: none !important; }
    [data-baseweb="tab-border"] { display: none !important; }

    /* ---------- Tables / Dataframes (force readable text) ---------- */
    [data-testid="stDataFrame"], [data-testid="stTable"],
    [data-testid="stDataFrame"] *, [data-testid="stTable"] * {
        color: #2C3E50 !important;
    }
    [data-testid="stDataFrame"] th, [data-testid="stTable"] th {
        background: #F8FAFC !important;
        color: #2C3E50 !important;
        font-weight: 600 !important;
    }
    [data-testid="stDataFrame"] td, [data-testid="stTable"] td {
        background: #FFFFFF !important;
        color: #2C3E50 !important;
    }
    .stDataFrame [role="gridcell"], .stDataFrame [role="columnheader"] {
        color: #2C3E50 !important;
    }
    /* ---------- Generic markdown text in main area ---------- */
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] span,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] .stMarkdown {
        color: #2C3E50;
    }
    /* Re-override sidebar to white */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] li,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stMarkdown * {
        color: #FFFFFF !important;
    }

    /* ---------- Dataframes ---------- */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid var(--border);
        background: var(--surface);
        box-shadow: 0 1px 2px rgba(15,23,42,0.03);
    }

    /* ---------- Buttons ---------- */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        font-size: 13px;
        padding: 6px 14px;
        border: 1px solid var(--border);
        background: var(--surface);
        color: var(--text);
        transition: all 0.15s ease;
        box-shadow: 0 1px 2px rgba(15,23,42,0.03);
    }
    .stButton > button:hover {
        background: var(--surface-2);
        border-color: #94A3B8;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1ABC9C 0%, #26C6DA 100%);
        border: none;
        color: #FFFFFF;
        font-weight: 600;
        box-shadow: 0 2px 6px rgba(26,188,156,0.30);
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #16A085 0%, #1ABC9C 100%);
        box-shadow: 0 4px 12px rgba(26,188,156,0.40);
        transform: translateY(-1px);
    }
    .stDownloadButton > button {
        background: var(--surface);
        border: 1px solid var(--border);
        color: var(--text);
        border-radius: 6px;
        font-weight: 500;
    }

    /* ---------- Sidebar (deep purple) ---------- */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--sidebar-bg) 0%, var(--sidebar-2) 100%) !important;
        border-right: 1px solid #4C1D95;
    }
    /* Hide Streamlit's default flat page navigation — we use grouped custom nav */
    [data-testid="stSidebarNav"] { display: none !important; }

    /* ---------- Sidebar grouped nav (expanders + page links) ---------- */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.10) !important;
        border-radius: 8px !important;
        margin-bottom: 8px !important;
        box-shadow: none !important;
        overflow: hidden;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary,
    [data-testid="stSidebar"] [data-testid="stExpander"] details > summary {
        background: rgba(26,188,156,0.12) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        padding: 10px 12px !important;
        border-left: 3px solid #1ABC9C !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        background: rgba(26,188,156,0.22) !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding: 6px 4px !important;
        background: transparent !important;
    }
    /* Page link items inside grouped nav */
    [data-testid="stSidebar"] [data-testid="stPageLink"] a,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
        background: transparent !important;
        color: #ECF0F1 !important;
        font-weight: 500 !important;
        font-size: 13.5px !important;
        padding: 7px 10px !important;
        border-radius: 6px !important;
        margin: 1px 4px !important;
        display: flex !important;
        align-items: center !important;
        text-decoration: none !important;
        transition: all 0.15s ease;
        border-left: 2px solid transparent;
    }
    [data-testid="stSidebar"] [data-testid="stPageLink"] a *,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] * {
        color: #ECF0F1 !important;
    }
    [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
        background: rgba(26,188,156,0.20) !important;
        border-left: 2px solid #1ABC9C !important;
        padding-left: 12px !important;
    }
    [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] {
        background: linear-gradient(90deg, rgba(26,188,156,0.30) 0%, rgba(26,188,156,0.05) 100%) !important;
        border-left: 3px solid #1ABC9C !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    /* ALL text in sidebar = pure white */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] *,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] a,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] li,
    [data-testid="stSidebar"] strong,
    [data-testid="stSidebar"] em,
    [data-testid="stSidebar"] small {
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stSidebarNav"] a,
    [data-testid="stSidebarNavItems"] a,
    [data-testid="stSidebarNavLink"] {
        color: #FFFFFF !important;
        font-weight: 500 !important;
        font-size: 14px !important;
        border-radius: 6px !important;
        padding: 8px 12px !important;
        margin: 2px 6px !important;
        transition: all 0.15s ease;
    }
    [data-testid="stSidebarNav"] a span,
    [data-testid="stSidebarNav"] a p,
    [data-testid="stSidebarNavItems"] a span,
    [data-testid="stSidebarNavItems"] a p,
    [data-testid="stSidebarNavLink"] span,
    [data-testid="stSidebarNavLink"] p {
        color: #FFFFFF !important;
        font-weight: 500 !important;
        font-size: 14px !important;
    }
    [data-testid="stSidebarNav"] a:hover,
    [data-testid="stSidebarNavItems"] a:hover,
    [data-testid="stSidebarNavLink"]:hover {
        background: rgba(26,188,156,0.20) !important;
        color: #FFFFFF !important;
    }
    [data-testid="stSidebarHeader"] *,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4 {
        color: #FFFFFF !important;
        border: none !important;
        padding: 0 !important;
    }
    [data-testid="stSidebar"] h2::before,
    [data-testid="stSidebar"] h3::before { display: none !important; }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.20) !important;
        margin: 12px 0 !important;
    }
    /* Sidebar inputs - white text on translucent bg */
    [data-testid="stSidebar"] .stTextInput input,
    [data-testid="stSidebar"] .stNumberInput input,
    [data-testid="stSidebar"] .stDateInput input,
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"],
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] *,
    [data-testid="stSidebar"] .stTextArea textarea {
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.30) !important;
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] .stTextInput input::placeholder,
    [data-testid="stSidebar"] .stTextArea textarea::placeholder {
        color: rgba(255,255,255,0.55) !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        background: rgba(255,255,255,0.10) !important;
        border: 1px solid rgba(255,255,255,0.30) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(26,188,156,0.25) !important;
        border-color: #1ABC9C !important;
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(135deg,#1ABC9C 0%,#16A085 100%) !important;
        border: none !important;
        color: #FFFFFF !important;
    }
    /* Sidebar markdown links / icons */
    [data-testid="stSidebar"] svg { fill: #FFFFFF !important; color: #FFFFFF !important; }
    /* Sidebar collapse button */
    [data-testid="stSidebarCollapseButton"] svg,
    [data-testid="stSidebarCollapsedControl"] svg { color: #FFFFFF !important; }

    /* ---------- Inputs (MAIN AREA: white bg + dark visible text) ---------- */
    /* Outer BaseWeb input wrapper - force white bg globally */
    div[data-baseweb="input"],
    div[data-baseweb="input"] > div,
    div[data-baseweb="base-input"],
    div[data-baseweb="textarea"],
    div[data-baseweb="textarea"] > div {
        background-color: #FFFFFF !important;
        background: #FFFFFF !important;
        border-color: var(--border) !important;
        color: #2C3E50 !important;
    }
    /* Re-override sidebar input wrappers to translucent white-text */
    [data-testid="stSidebar"] div[data-baseweb="input"],
    [data-testid="stSidebar"] div[data-baseweb="input"] > div,
    [data-testid="stSidebar"] div[data-baseweb="base-input"],
    [data-testid="stSidebar"] div[data-baseweb="textarea"],
    [data-testid="stSidebar"] div[data-baseweb="textarea"] > div {
        background-color: rgba(255,255,255,0.08) !important;
        background: rgba(255,255,255,0.08) !important;
        border-color: rgba(255,255,255,0.30) !important;
        color: #FFFFFF !important;
    }
    /* Inner <input> / <textarea> */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    .stTextArea textarea, .stPasswordInput input,
    input[type="text"], input[type="number"], input[type="password"],
    input[type="date"], input[type="email"], textarea {
        background: #FFFFFF !important;
        background-color: #FFFFFF !important;
        border: 1px solid var(--border) !important;
        border-radius: 6px !important;
        color: #2C3E50 !important;
        -webkit-text-fill-color: #2C3E50 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        caret-color: #1ABC9C !important;
    }
    .stTextInput input::placeholder,
    .stNumberInput input::placeholder,
    .stTextArea textarea::placeholder,
    input::placeholder, textarea::placeholder {
        color: #9CA3AF !important;
        opacity: 1 !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus,
    .stDateInput input:focus, .stTextArea textarea:focus,
    input:focus, textarea:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(26,188,156,0.18) !important;
        background: #FFFFFF !important;
        color: #2C3E50 !important;
    }
    /* Selectbox - main area */
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {
        background: #FFFFFF !important;
        border-radius: 6px !important;
        border: 1px solid var(--border) !important;
    }
    .stSelectbox div[data-baseweb="select"] > div *,
    .stMultiSelect div[data-baseweb="select"] > div * {
        color: #2C3E50 !important;
    }
    /* Selectbox dropdown menu (popover) */
    div[data-baseweb="popover"] li,
    div[data-baseweb="popover"] [role="option"],
    div[data-baseweb="menu"] li,
    div[data-baseweb="menu"] [role="option"] {
        background: #FFFFFF !important;
        color: #2C3E50 !important;
    }
    div[data-baseweb="popover"] [role="option"]:hover,
    div[data-baseweb="menu"] [role="option"]:hover {
        background: #E8F8F5 !important;
        color: #16A085 !important;
    }
    /* Date picker calendar */
    div[data-baseweb="calendar"], div[data-baseweb="calendar"] * {
        color: #2C3E50 !important;
    }

    /* ---------- Alerts (info/success/warning/error) ---------- */
    div[data-testid="stAlert"] {
        border-radius: 8px;
        border: 1px solid var(--border);
        font-size: 13px;
        padding: 12px 14px;
    }

    /* ---------- Expander ---------- */
    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        box-shadow: 0 1px 2px rgba(15,23,42,0.03);
    }
    [data-testid="stExpander"] summary {
        font-weight: 600;
        color: var(--text);
    }

    /* ---------- Form (legacy rule, polished version below) ---------- */

    /* ---------- Divider ---------- */
    hr {
        border-color: var(--border) !important;
        margin: 18px 0 !important;
    }

    /* ---------- Top header bar (hero) ---------- */
    .top-bar {
        position: relative;
        background:
            linear-gradient(135deg, #2C3E50 0%, #34495E 60%, #1ABC9C 130%);
        padding: 22px 28px;
        border-radius: 16px;
        box-shadow:
            0 14px 32px rgba(15,23,42,0.18),
            0 4px 10px rgba(15,23,42,0.10);
        margin-bottom: 22px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .top-bar::before {
        content: ""; position: absolute; right: -60px; top: -60px;
        width: 220px; height: 220px; border-radius: 50%;
        background: radial-gradient(circle, rgba(26,188,156,0.30) 0%, rgba(26,188,156,0) 70%);
    }
    .top-bar::after {
        content: ""; position: absolute; left: 35%; bottom: -80px;
        width: 260px; height: 160px; border-radius: 50%;
        background: radial-gradient(circle, rgba(52,152,219,0.20) 0%, rgba(52,152,219,0) 70%);
    }
    .top-bar > div { position: relative; z-index: 1; }
    .top-bar .erp-title {
        font-size: 28px; font-weight: 800; color: #FFFFFF;
        letter-spacing: -0.6px; line-height: 1.1;
        text-shadow: 0 2px 6px rgba(0,0,0,0.20);
    }
    .top-bar .erp-sub {
        color: rgba(255,255,255,0.78); margin-top: 6px;
        font-size: 13px; font-weight: 500; letter-spacing: 0.2px;
    }
    .top-bar .erp-pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        background: rgba(26,188,156,0.25); color: #FFFFFF;
        font-size: 10px; font-weight: 700; letter-spacing: 0.6px;
        text-transform: uppercase; margin-left: 8px;
        border: 1px solid rgba(26,188,156,0.40);
    }
    .top-bar .erp-date-lbl {
        color: #4FE0C9; font-size: 10px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 1.2px;
    }
    .top-bar .erp-date-val {
        color: #FFFFFF; font-size: 19px; font-weight: 700;
        margin-top: 3px; letter-spacing: -0.3px;
    }

    /* ---------- Streamlit native st.metric polish ---------- */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px 16px;
        box-shadow: 0 2px 6px rgba(15,23,42,0.04);
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
    }
    [data-testid="stMetric"]:hover {
        box-shadow: 0 6px 16px rgba(15,23,42,0.10);
        transform: translateY(-1px);
        border-color: rgba(26,188,156,0.40);
    }
    [data-testid="stMetric"]::before {
        content: ""; position: absolute; left: 0; top: 0; bottom: 0;
        width: 3px;
        background: linear-gradient(180deg, #1ABC9C 0%, #3498DB 100%);
    }
    [data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-weight: 800 !important;
        font-size: 22px !important;
        letter-spacing: -0.5px;
    }

    /* ---------- Expander polish ---------- */
    [data-testid="stExpander"] {
        background: #FFFFFF !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 6px rgba(15,23,42,0.04) !important;
        overflow: hidden;
        transition: box-shadow 0.2s ease;
    }
    [data-testid="stExpander"]:hover {
        box-shadow: 0 6px 14px rgba(15,23,42,0.08) !important;
    }
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] details > summary {
        font-weight: 600 !important;
        color: var(--text) !important;
        padding: 12px 16px !important;
        background: linear-gradient(90deg, #F8FAFC 0%, #FFFFFF 100%);
        border-left: 3px solid #1ABC9C;
    }

    /* ---------- Plotly chart container polish ---------- */
    [data-testid="stPlotlyChart"] {
        background: #FFFFFF;
        border-radius: 12px;
        padding: 12px;
        border: 1px solid var(--border);
        box-shadow: 0 2px 8px rgba(15,23,42,0.05);
    }

    /* ---------- Form polish ---------- */
    [data-testid="stForm"] {
        background: #FFFFFF !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
        padding: 22px !important;
        box-shadow: 0 4px 14px rgba(15,23,42,0.05) !important;
    }

    /* ---------- Hide Streamlit branding ---------- */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stDecoration"] { display: none; }

    /* ---------- Radio / Checkbox ---------- */
    [data-testid="stRadio"] label, [data-testid="stCheckbox"] label {
        font-size: 14px;
    }

    /* ---------- Captions ---------- */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: var(--text-muted) !important;
        font-size: 12px !important;
    }
</style>
""", unsafe_allow_html=True)

# ----- Top header bar -----
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "zuni_logo.jpeg")
st.markdown("<div class='top-bar'>", unsafe_allow_html=True)
hcol1, hcol2, hcol3 = st.columns([1, 5, 2])
with hcol1:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=120)
with hcol2:
    farm_name = os.environ.get("FARM_NAME", "").strip()
    farm_suffix = (
        f" &mdash; <span style='color:#4FE0C9'>{farm_name}</span>"
        if farm_name else ""
    )
    st.markdown(
        "<div style='padding-top:6px;'>"
        f"<div class='erp-title'>Zuni Dairy ERP{farm_suffix} "
        "<span class='erp-pill'>● Live</span></div>"
        "<div class='erp-sub'>"
        "Corporate Dairy Management &nbsp;·&nbsp; Operations · Herd · Finance"
        "</div></div>",
        unsafe_allow_html=True)
with hcol3:
    st.markdown(
        f"<div style='text-align:right;padding-top:12px;'>"
        f"<div class='erp-date-lbl'>Today</div>"
        f"<div class='erp-date-val'>"
        f"{date.today().strftime('%a, %d %b %Y')}</div>"
        f"</div>",
        unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# ----- Date filter -----
today = date.today()
c1, c2 = st.columns(2)
start = c1.date_input("From", today - timedelta(days=30))
end = c2.date_input("To", today)

# ----- Cash & Bank summary (top of dashboard) -----
st.subheader("Cash & Bank Position")
cash_bank_accs = query(
    "SELECT code, name, type FROM accounts "
    "WHERE (type='Asset' AND code LIKE '10%' AND name LIKE '%Cash%') "
    "   OR (type='Asset' AND code LIKE '11%') ORDER BY code")
if cash_bank_accs:
    cb_cols = st.columns(min(len(cash_bank_accs), 6) or 1)
    for i, a in enumerate(cash_bank_accs):
        bal = account_balance(a["code"])
        cb_cols[i % len(cb_cols)].metric(
            f"{a['name']} ({a['code']})", f"{bal:,.2f}")
else:
    st.info("Add Cash / Bank accounts in Accounting → Chart of Accounts.")

# ----- KPI rows -----
animals = query("SELECT status, COUNT(*) c FROM animals GROUP BY status")
status_map = {r["status"]: r["c"] for r in animals}
total = sum(status_map.values())
active = status_map.get("Active", 0)
sold = status_map.get("Sold", 0)
dead = status_map.get("Dead", 0)

milk_today = query(
    "SELECT shift, COALESCE(SUM(litres),0) l FROM milk_records WHERE record_date=? GROUP BY shift",
    (str(today),))
milk_map = {r["shift"]: r["l"] for r in milk_today}
total_today_milk = sum(milk_map.values())
store_bal = milk_store_balance()


def kpi_card(color, num, label, icon):
    return (
        f"<div class='kpi-card kpi-{color}'>"
        f"  <div><div class='num'>{num}</div><div class='lbl'>{label}</div></div>"
        f"  <div class='ico'>{icon}</div>"
        f"</div>"
    )


# 4 colored KPI cards (red / orange / blue / green) — like reference
k1, k2, k3, k4 = st.columns(4)
k1.markdown(kpi_card("red", active, "Active Animals", "🐄"), unsafe_allow_html=True)
k2.markdown(kpi_card("orange", f"{total_today_milk:.0f}",
                     "Today's Milk (L)", "🥛"), unsafe_allow_html=True)
k3.markdown(kpi_card("blue", f"{store_bal:,.0f}",
                     "Milk Store (L)", "🏪"), unsafe_allow_html=True)
k4.markdown(kpi_card("green", total, "Total Animals", "📊"), unsafe_allow_html=True)

# Secondary stat row
st.subheader("Today's Milk Production")
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Morning (L)", f"{milk_map.get('Morning',0):.1f}")
m2.metric("Evening (L)", f"{milk_map.get('Evening',0):.1f}")
m3.metric("Night (L)", f"{milk_map.get('Night',0):.1f}")
m4.metric("Sold", sold)
m5.metric("Dead", dead)
m6.metric("Last Sale Rate", f"{latest_milk_rate():,.2f}")

# ----- Comprehensive Alerts Center -----
st.subheader("Alerts Center")

# Closeup (≤21 days to calving) & Dry-off (60-21 days to calving) alerts via ECD
df_closeup = pd.DataFrame(query("""
    SELECT a.tag, a.expected_calving_date AS ecd,
           CAST(julianday(a.expected_calving_date) - julianday('now') AS INTEGER) days_left
    FROM animals a
    WHERE a.status='Active' AND a.is_pregnant=1
      AND a.expected_calving_date IS NOT NULL
      AND julianday(a.expected_calving_date) - julianday('now') BETWEEN 0 AND 21
    ORDER BY a.expected_calving_date
"""))
df_dryoff = pd.DataFrame(query("""
    SELECT a.tag, a.expected_calving_date AS ecd,
           CAST(julianday(a.expected_calving_date) - julianday('now') AS INTEGER) days_left,
           CASE WHEN a.is_dry=1 THEN 'Already dry' ELSE 'Needs dry-off' END status
    FROM animals a
    WHERE a.status='Active' AND a.is_pregnant=1
      AND a.expected_calving_date IS NOT NULL
      AND julianday(a.expected_calving_date) - julianday('now') BETWEEN 22 AND 60
    ORDER BY a.expected_calving_date
"""))

# Vaccination alerts
df_vacc_due = pd.DataFrame(query("""
    WITH last_vac AS (
        SELECT v.animal_id, v.vaccine_name, MAX(v.next_due) next_due
        FROM vaccinations v GROUP BY v.animal_id, v.vaccine_name
    )
    SELECT a.tag, lv.vaccine_name, lv.next_due,
           CAST(julianday(lv.next_due) - julianday('now') AS INTEGER) days_left
    FROM last_vac lv
    JOIN animals a ON a.animal_id=lv.animal_id
    WHERE a.status='Active' AND lv.next_due IS NOT NULL
      AND lv.next_due <= DATE('now','+14 days')
    ORDER BY lv.next_due
"""))

# PD due alerts
df_pd_due = pd.DataFrame(query("""
    SELECT a.tag, a.last_ai_date,
           CAST(julianday('now') - julianday(a.last_ai_date) AS INTEGER) days_post_ai,
           CASE
             WHEN julianday('now') - julianday(a.last_ai_date) BETWEEN 30 AND 60
                  AND NOT EXISTS (SELECT 1 FROM breeding_events b
                                  WHERE b.animal_id=a.animal_id AND b.event_type='PD1'
                                    AND b.event_date >= a.last_ai_date)
             THEN 'PD1 due'
             WHEN julianday('now') - julianday(a.last_ai_date) BETWEEN 60 AND 100
                  AND NOT EXISTS (SELECT 1 FROM breeding_events b
                                  WHERE b.animal_id=a.animal_id AND b.event_type='PD2'
                                    AND b.event_date >= a.last_ai_date)
                  AND EXISTS (SELECT 1 FROM breeding_events b
                              WHERE b.animal_id=a.animal_id AND b.event_type='PD1'
                                AND b.result='Positive'
                                AND b.event_date >= a.last_ai_date)
             THEN 'PD2 due'
             ELSE NULL
           END AS pd_status
    FROM animals a
    WHERE a.status='Active' AND a.sex='F'
      AND a.last_ai_date IS NOT NULL
      AND a.is_pregnant=0
"""))
df_pd_due = df_pd_due[df_pd_due["pd_status"].notna()] if not df_pd_due.empty else df_pd_due

# Low-milk alerts (lactating only)
alert_window_start = today - timedelta(days=7)
df_alerts = pd.DataFrame(query("""
    SELECT a.animal_id, a.tag, a.is_pregnant,
           ROUND((COALESCE(SUM(m.litres),0) / 7.0)::numeric, 2) AS avg_7d,
           COUNT(DISTINCT m.record_date) AS days_recorded
    FROM animals a
    LEFT JOIN milk_records m ON m.animal_id=a.animal_id
        AND m.record_date BETWEEN ? AND ?
    WHERE a.status='Active' AND a.sex='F'
    GROUP BY a.animal_id, a.tag, a.is_pregnant
    HAVING COUNT(DISTINCT m.record_date) > 0
    ORDER BY avg_7d ASC
""", (str(alert_window_start), str(today))))
low_alerts = df_alerts[df_alerts["avg_7d"] < 8] if not df_alerts.empty else pd.DataFrame()

# Summary tally
ac1, ac2, ac3, ac4, ac5 = st.columns(5)
ac1.metric("Closeup (≤21 d)", len(df_closeup))
ac2.metric("Dry-off due", len(df_dryoff))
ac3.metric("Vaccine due/overdue", len(df_vacc_due))
ac4.metric("PD checks due", len(df_pd_due))
ac5.metric("Low milk (<8 L/d)", len(low_alerts))

# Detail expanders
if not df_closeup.empty:
    with st.expander(f"⚠ Close-up ({len(df_closeup)}) — calving within 21 days", expanded=True):
        st.dataframe(df_closeup, use_container_width=True, hide_index=True)
if not df_dryoff.empty:
    with st.expander(f"💧 Dry-off ({len(df_dryoff)}) — calving in 22–60 days"):
        st.dataframe(df_dryoff, use_container_width=True, hide_index=True)
if not df_vacc_due.empty:
    with st.expander(f"💉 Vaccinations due/overdue ({len(df_vacc_due)})"):
        st.dataframe(df_vacc_due, use_container_width=True, hide_index=True)
if not df_pd_due.empty:
    with st.expander(f"🔬 Pregnancy checks due ({len(df_pd_due)})"):
        st.dataframe(df_pd_due, use_container_width=True, hide_index=True)
if not low_alerts.empty:
    with st.expander(f"⬇ Low-milk cows ({len(low_alerts)}) — under 8 L/day"):
        st.dataframe(low_alerts[["tag", "avg_7d"]].rename(
            columns={"tag": "Tag", "avg_7d": "7-day Avg (L/d)"}),
            use_container_width=True, hide_index=True)

if (df_closeup.empty and df_dryoff.empty and df_vacc_due.empty
        and df_pd_due.empty and low_alerts.empty):
    st.success("All clear — no active alerts.")

# ----- Financial summary -----
sales_total = query(
    "SELECT COALESCE(SUM(total),0) t FROM sales WHERE sale_date BETWEEN ? AND ?",
    (str(start), str(end)))[0]["t"]
purchase_total = query(
    "SELECT COALESCE(SUM(total),0) t FROM purchases WHERE purchase_date BETWEEN ? AND ?",
    (str(start), str(end)))[0]["t"]
expense_total = query(
    "SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE exp_date BETWEEN ? AND ?",
    (str(start), str(end)))[0]["t"]
salary_total = query(
    "SELECT COALESCE(SUM(amount),0) t FROM salary_payments WHERE pay_date BETWEEN ? AND ?",
    (str(start), str(end)))[0]["t"]
treat_cost = query(
    "SELECT COALESCE(SUM(cost),0) t FROM treatments WHERE treat_date BETWEEN ? AND ?",
    (str(start), str(end)))[0]["t"]

profit = sales_total - (purchase_total + expense_total + salary_total + treat_cost)

st.subheader("Financial Summary (selected range)")
f1, f2, f3, f4 = st.columns(4)
f1.metric("Sales", f"{sales_total:,.0f}")
f2.metric("Purchases", f"{purchase_total:,.0f}")
f3.metric("Expenses + Salary", f"{(expense_total + salary_total):,.0f}")
f4.metric("Profit / (Loss)", f"{profit:,.0f}")

# ----- Charts -----
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Daily Milk Production Trend")
    df_milk = pd.DataFrame(query(
        "SELECT record_date, shift, SUM(litres) litres FROM milk_records "
        "WHERE record_date BETWEEN ? AND ? GROUP BY record_date, shift ORDER BY record_date",
        (str(start), str(end))))
    if not df_milk.empty:
        fig = px.bar(df_milk, x="record_date", y="litres", color="shift",
                     barmode="stack", color_discrete_sequence=ORANGE_BLUE)
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                          paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                          font=dict(color="#2C3E50"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No milk records in range.")

with col_b:
    st.subheader("Pen-wise Animal Count")
    df_pen = pd.DataFrame(query(
        "SELECT p.name pen, COUNT(a.animal_id) animals FROM pens p "
        "LEFT JOIN animals a ON a.pen_id=p.pen_id AND a.status='Active' "
        "GROUP BY p.pen_id, p.name ORDER BY animals DESC"))
    if not df_pen.empty:
        fig = px.bar(df_pen, x="pen", y="animals",
                     color_discrete_sequence=ORANGE_BLUE)
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                          paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                          font=dict(color="#2C3E50"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No pens yet.")

# ----- Stock summary -----
st.subheader("Inventory Snapshot (per Store)")
df_stock = pd.DataFrame(query("""
    SELECT s.name store, i.name item, i.uom,
        COALESCE(SUM(CASE WHEN m.move_type='IN' THEN m.qty ELSE -m.qty END),0) balance
    FROM items i
    JOIN stores s ON s.store_id=i.store_id
    LEFT JOIN stock_moves m ON m.item_id=i.item_id
    GROUP BY s.name, i.name, i.uom ORDER BY s.name, i.name
"""))
if not df_stock.empty:
    st.dataframe(df_stock, use_container_width=True, hide_index=True)
else:
    st.info("No items yet — add some in the Inventory page.")

st.divider()
st.caption("Use the left sidebar to navigate modules.")
