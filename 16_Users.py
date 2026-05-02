"""User & Access Management — Admin only."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from db import init_db, query, execute, hash_password, ROLE_PAGES
from auth import require_role, render_user_sidebar

st.set_page_config(page_title="Users", layout="wide")
init_db()

# Only Admin can manage users
user = require_role("16_Users") if False else None
# Custom guard: only Admin allowed
from auth import require_login
me = require_login()
render_user_sidebar()
if me["role"] != "Admin":
    st.error("Access denied — only Admin can manage users.")
    st.stop()

st.title("User & Access Management")
st.caption("Add new users, change roles, reset passwords, deactivate.")

tab_list, tab_add, tab_perms = st.tabs(["All Users", "Add / Edit User", "Role Permissions"])

# ---------- All Users ----------
with tab_list:
    df = pd.DataFrame(query(
        "SELECT user_id, username, full_name, role, "
        "CASE WHEN active=1 THEN 'Active' ELSE 'Disabled' END status, "
        "created_at FROM users ORDER BY user_id"))
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Quick actions")
    users = query("SELECT user_id, username, role, active FROM users ORDER BY username")
    if users:
        c1, c2, c3 = st.columns(3)
        ulabel = c1.selectbox("Pick user",
                              [f"{u['username']} ({u['role']})" for u in users])
        sel = users[[f"{u['username']} ({u['role']})" for u in users].index(ulabel)]
        new_role = c2.selectbox("Change role", ["Admin", "Vet", "Accountant"],
                                index=["Admin", "Vet", "Accountant"].index(sel["role"])
                                if sel["role"] in ["Admin", "Vet", "Accountant"] else 0)
        new_status = c3.selectbox("Status", ["Active", "Disabled"],
                                  index=0 if sel["active"] else 1)
        c4, c5 = st.columns(2)
        if c4.button("Save Changes", type="primary"):
            execute("UPDATE users SET role=?, active=? WHERE user_id=?",
                    (new_role, 1 if new_status == "Active" else 0, sel["user_id"]))
            st.success("Updated.")
            st.rerun()
        new_pw = c5.text_input("Reset Password (leave blank to keep)", type="password")
        if c5.button("Reset Password") and new_pw:
            execute("UPDATE users SET password_hash=? WHERE user_id=?",
                    (hash_password(new_pw), sel["user_id"]))
            st.success("Password reset.")

# ---------- Add User ----------
with tab_add:
    with st.form("new_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        un = c1.text_input("Username *")
        fn = c2.text_input("Full Name")
        c3, c4 = st.columns(2)
        pw = c3.text_input("Password *", type="password")
        role = c4.selectbox("Role *", ["Admin", "Vet", "Accountant"])
        if st.form_submit_button("Create User", type="primary"):
            if not un.strip() or not pw:
                st.error("Username & password required.")
            else:
                try:
                    execute(
                        "INSERT INTO users(username,password_hash,full_name,role) "
                        "VALUES(?,?,?,?)",
                        (un.strip(), hash_password(pw), fn, role))
                    st.success(f"User '{un}' created with role {role}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ---------- Role permissions ----------
with tab_perms:
    st.subheader("Module access by role")
    PAGE_NAMES = {
        "1_Livestock": "Livestock", "2_RFID": "RFID", "3_Milk": "Milk",
        "4_Calving": "Calving", "5_Pens": "Pens", "6_Weights": "Weights",
        "7_Feed": "Feed", "8_Treatments": "Treatments", "9_Inventory": "Inventory",
        "10_Sales_Purchase": "Sales / Purchase", "11_Accounting": "Accounting",
        "12_Employees": "Employees", "13_Reports": "Reports",
        "14_Animal_PL": "Animal P&L", "15_Breeding": "Breeding",
        "16_Users": "Users (Admin)", "17_Vaccinations": "Vaccinations",
    }
    rows = []
    for k, name in PAGE_NAMES.items():
        row = {"Module": name}
        for r in ["Admin", "Vet", "Accountant"]:
            perms = ROLE_PAGES.get(r)
            if perms == "ALL":
                row[r] = "✓"
            elif k == "16_Users":
                row[r] = "✓" if r == "Admin" else "✗"
            else:
                row[r] = "✓" if k in (perms or set()) else "✗"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.info(
        "**Admin** — Full access (all modules + user management).\n\n"
        "**Vet** — Animal & health side: Livestock, RFID, Pens, Calving, Weights, "
        "Treatments, Breeding.\n\n"
        "**Accountant** — Money & operations side: Milk, Feed, Inventory, "
        "Sales/Purchase, Accounting, Employees, Reports, Animal P&L."
    )
