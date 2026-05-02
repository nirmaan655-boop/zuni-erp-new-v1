"""Employee Management."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute, post_journal
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Employees", layout="wide")
init_db()

require_role("12_Employees")
render_user_sidebar()
st.title("Employee Management")

farms = query("SELECT * FROM farms")
farm_opts = {f["name"]: f["farm_id"] for f in farms}

tab_list, tab_add, tab_pay = st.tabs(["Employees", "Add Employee", "Salary Payments"])

with tab_list:
    df = pd.DataFrame(query("""
        SELECT e.emp_id, e.name, e.role, e.phone, e.salary, f.name farm
        FROM employees e LEFT JOIN farms f ON f.farm_id=e.farm_id
        ORDER BY e.name
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "employees.xlsx")

with tab_add:
    with st.form("emp"):
        c1, c2, c3, c4, c5 = st.columns(5)
        n = c1.text_input("Name *")
        r = c2.text_input("Role")
        p = c3.text_input("Phone")
        s = c4.number_input("Salary", min_value=0.0, step=100.0)
        f = c5.selectbox("Farm", list(farm_opts.keys()) if farm_opts else ["-"])
        if st.form_submit_button("Save") and n:
            execute("INSERT INTO employees(name,role,phone,salary,farm_id) VALUES(?,?,?,?,?)",
                    (n, r, p, s, farm_opts.get(f)))
            st.success("Saved.")
            st.rerun()

with tab_pay:
    emps = query("SELECT * FROM employees")
    if emps:
        with st.form("pay"):
            c1, c2, c3 = st.columns(3)
            who = c1.selectbox("Employee", [e["name"] for e in emps])
            d = c2.date_input("Date", date.today())
            amt = c3.number_input("Amount", min_value=0.0, step=100.0)
            note = st.text_input("Note")
            if st.form_submit_button("Pay"):
                eid = next(e["emp_id"] for e in emps if e["name"] == who)
                pid = execute(
                    "INSERT INTO salary_payments(emp_id,pay_date,amount,note) VALUES(?,?,?,?)",
                    (eid, str(d), amt, note))
                post_journal(d, f"Salary {who}",
                             [("5200", amt, 0), ("1000", 0, amt)], "salary", pid)
                st.success("Paid.")

    df = pd.DataFrame(query("""
        SELECT s.pay_date, e.name employee, s.amount, s.note
        FROM salary_payments s JOIN employees e ON e.emp_id=s.emp_id
        ORDER BY s.id DESC
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "salary_payments.xlsx")
