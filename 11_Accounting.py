"""Accounting - COA, Cash/Bank Payments, Receipts, JV, Journal, Vendor Ledger, P&L."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute, post_journal, account_balance
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Accounting", layout="wide")
init_db()

require_role("11_Accounting")
render_user_sidebar()
st.title("Accounting")

(tab_coa, tab_cash, tab_bank, tab_recv, tab_jv,
 tab_je, tab_vl, tab_tb, tab_pl, tab_bs) = st.tabs(
    ["Chart of Accounts", "Cash Payment", "Bank Payment", "Receipt",
     "JV (Journal Voucher)", "Journal Ledger", "Vendor Ledger",
     "Trial Balance", "P&L", "Balance Sheet"])

# ---------------- helpers ----------------
def accounts_by(filter_sql):
    return query(f"SELECT account_id, code, name, type FROM accounts WHERE {filter_sql} ORDER BY code")

def cash_accounts():
    return accounts_by("type='Asset' AND (code LIKE '10%' AND name LIKE '%Cash%')") or \
           accounts_by("code='1000'")

def bank_accounts():
    return accounts_by("type='Asset' AND code LIKE '11%'") or accounts_by("code='1100'")

def expense_accounts():
    return accounts_by("type='Expense'")

def income_accounts():
    return accounts_by("type='Income'")

def vendors_list():
    return query("SELECT party_id, name FROM parties WHERE party_type='Vendor' ORDER BY name")

def customers_list():
    return query("SELECT party_id, name FROM parties WHERE party_type='Customer' ORDER BY name")

def next_bank_code():
    """Next available 11xx code for new bank account."""
    rows = query("SELECT code FROM accounts WHERE code LIKE '11%' ORDER BY code DESC")
    if not rows:
        return "1100"
    try:
        last = int(rows[0]["code"])
        return str(last + 10)
    except Exception:
        return "1199"


# ---------------- Chart of Accounts ----------------
with tab_coa:
    df = pd.DataFrame(query("""
        SELECT a.code, a.name, a.type,
            COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit),0) net_dr_minus_cr
        FROM accounts a LEFT JOIN journal_lines l ON l.account_id=a.account_id
        GROUP BY a.account_id ORDER BY a.code
    """))
    if not df.empty:
        # Show signed balance per account type
        def _bal(r):
            v = r["net_dr_minus_cr"]
            return v if r["type"] in ("Asset", "Expense") else -v
        df["balance"] = df.apply(_bal, axis=1)
        df = df.drop(columns=["net_dr_minus_cr"])
    st.dataframe(df, use_container_width=True, hide_index=True)
    with st.expander("Add new account"):
        with st.form("acc", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("Code")
            name = c2.text_input("Name")
            t = c3.selectbox("Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
            if st.form_submit_button("Add", type="primary") and code and name:
                try:
                    execute("INSERT INTO accounts(code,name,type) VALUES(?,?,?)", (code, name, t))
                    st.success("Added.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# ---------------- Generic payment builder ----------------
def payment_voucher(kind_label, source_accounts):
    if not source_accounts:
        st.warning(f"No {kind_label.lower()} accounts found in COA.")
        return

    # Show balance of every available source account at top
    st.markdown(f"**Available {kind_label} balances:**")
    bcols = st.columns(min(len(source_accounts), 5) or 1)
    for i, a in enumerate(source_accounts):
        bal = account_balance(a["code"])
        bcols[i % len(bcols)].metric(f"{a['name']} ({a['code']})", f"{bal:,.2f}")

    c1, c2, c3 = st.columns(3)
    src_label = [f"{a['code']} - {a['name']}" for a in source_accounts]
    sel_src = c1.selectbox(f"Pay From ({kind_label})", src_label, key=f"{kind_label}_src")
    src_acc = source_accounts[src_label.index(sel_src)]
    pay_date = c2.date_input("Date", date.today(), key=f"{kind_label}_d")
    voucher_no = c3.text_input("Voucher # / Ref", key=f"{kind_label}_v")
    narration = st.text_input("Narration", key=f"{kind_label}_n")

    src_bal = account_balance(src_acc["code"])
    st.info(f"Selected: **{src_acc['name']}** — Current balance: **{src_bal:,.2f}**")

    vendors = vendors_list()
    exp_accs = expense_accounts()
    vendor_labels = [v["name"] for v in vendors]
    expense_labels = [f"{a['code']} - {a['name']}" for a in exp_accs]

    st.caption("Add multiple payment lines. Type = Vendor pays a supplier (settles AP); "
               "Type = Expense books a direct expense.")

    default_rows = pd.DataFrame([
        {"Type": "Vendor", "Name": (vendor_labels[0] if vendor_labels else ""),
         "Amount": 0.0, "Note": ""},
    ])
    edited = st.data_editor(
        default_rows, num_rows="dynamic", use_container_width=True, hide_index=True,
        key=f"{kind_label}_lines",
        column_config={
            "Type": st.column_config.SelectboxColumn(
                "Type", options=["Vendor", "Expense"], required=True),
            "Name": st.column_config.SelectboxColumn(
                "Pay To (Vendor / Expense Account)",
                options=sorted(set(vendor_labels + expense_labels)), required=True),
            "Amount": st.column_config.NumberColumn(
                "Amount", min_value=0.0, step=100.0, format="%.2f"),
            "Note": st.column_config.TextColumn("Note"),
        },
    )

    valid_rows = []
    for _, r in edited.iterrows():
        nm = (r.get("Name") or "").strip()
        amt = float(r.get("Amount") or 0)
        if not nm or amt <= 0:
            continue
        valid_rows.append((r["Type"], nm, amt, (r.get("Note") or "")))
    total = sum(r[2] for r in valid_rows)
    st.metric(f"Total {kind_label} Payment", f"{total:,.2f}")

    if st.button(f"Post {kind_label} Payment", type="primary",
                 key=f"{kind_label}_post", disabled=(total <= 0)):
        jlines = []
        descs = []
        vendor_id_map = {v["name"]: v["party_id"] for v in vendors}
        for typ, name, amt, note in valid_rows:
            if typ == "Vendor":
                code = "2000"
                pid = vendor_id_map.get(name)
                descs.append(f"Vendor {name}: {amt:,.0f}" + (f" ({note})" if note else ""))
                jlines.append((code, amt, 0, pid))
            else:
                code = name.split(" - ")[0]
                descs.append(f"{name}: {amt:,.0f}" + (f" ({note})" if note else ""))
                jlines.append((code, amt, 0, None))
        jlines.append((src_acc["code"], 0, total, None))
        full_narration = " | ".join(filter(None, [voucher_no, narration, "; ".join(descs)]))
        post_journal(pay_date, f"{kind_label} Payment | {full_narration}",
                     jlines, f"{kind_label.lower()}_pmt")
        st.success(f"{kind_label} payment posted. Total {total:,.2f} from {src_acc['name']}.")
        st.rerun()


with tab_cash:
    payment_voucher("Cash", cash_accounts())

with tab_bank:
    # Quick "Add new bank account" tool, before payment voucher
    with st.expander("Add a new Bank account"):
        with st.form("new_bank", clear_on_submit=True):
            bc1, bc2 = st.columns([1, 3])
            bcode = bc1.text_input("Code", value=next_bank_code())
            bname = bc2.text_input("Bank Name (e.g. HBL Main, Meezan Current)")
            if st.form_submit_button("Create Bank", type="primary"):
                if not bname.strip():
                    st.error("Bank name required.")
                else:
                    try:
                        execute("INSERT INTO accounts(code,name,type) VALUES(?,?,?)",
                                (bcode.strip(), bname.strip(), "Asset"))
                        st.success(f"Bank account {bcode} - {bname} created.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    payment_voucher("Bank", bank_accounts())


# ---------------- Receipt ----------------
with tab_recv:
    st.caption("Money received — into Cash or Bank account, from Customer (settles AR) or Income.")
    deposit_into = cash_accounts() + bank_accounts()
    if not deposit_into:
        st.warning("Add a Cash or Bank account in COA first.")
    else:
        st.markdown("**Available Cash & Bank balances:**")
        rcols = st.columns(min(len(deposit_into), 5) or 1)
        for i, a in enumerate(deposit_into):
            bal = account_balance(a["code"])
            rcols[i % len(rcols)].metric(f"{a['name']} ({a['code']})", f"{bal:,.2f}")

        c1, c2, c3 = st.columns(3)
        di_lbl = [f"{a['code']} - {a['name']}" for a in deposit_into]
        sel_into = c1.selectbox("Deposit Into", di_lbl, key="rcv_in")
        into_acc = deposit_into[di_lbl.index(sel_into)]
        d_rcv = c2.date_input("Date", date.today(), key="rcv_d")
        ref_rcv = c3.text_input("Voucher # / Ref", key="rcv_v")
        narr_rcv = st.text_input("Narration", key="rcv_n")

        custs = customers_list()
        inc_accs = income_accounts()
        cust_labels = [c["name"] for c in custs]
        inc_labels = [f"{a['code']} - {a['name']}" for a in inc_accs]

        rows_rcv = pd.DataFrame([{"Type": "Customer",
                                  "Name": (cust_labels[0] if cust_labels else ""),
                                  "Amount": 0.0, "Note": ""}])
        edited_r = st.data_editor(
            rows_rcv, num_rows="dynamic", use_container_width=True, hide_index=True,
            key="rcv_lines",
            column_config={
                "Type": st.column_config.SelectboxColumn(
                    "Type", options=["Customer", "Income"], required=True),
                "Name": st.column_config.SelectboxColumn(
                    "Receive From (Customer / Income Account)",
                    options=sorted(set(cust_labels + inc_labels)), required=True),
                "Amount": st.column_config.NumberColumn(
                    "Amount", min_value=0.0, step=100.0, format="%.2f"),
                "Note": st.column_config.TextColumn("Note"),
            },
        )
        valid = []
        for _, r in edited_r.iterrows():
            nm = (r.get("Name") or "").strip()
            amt = float(r.get("Amount") or 0)
            if nm and amt > 0:
                valid.append((r["Type"], nm, amt, r.get("Note") or ""))
        total_r = sum(x[2] for x in valid)
        st.metric("Total Receipt", f"{total_r:,.2f}")

        if st.button("Post Receipt", type="primary", disabled=(total_r <= 0), key="rcv_post"):
            cust_id_map = {c["name"]: c["party_id"] for c in custs}
            jlines = [(into_acc["code"], total_r, 0, None)]
            descs = []
            for typ, name, amt, note in valid:
                if typ == "Customer":
                    code = "1400"
                    pid = cust_id_map.get(name)
                    descs.append(f"Customer {name}: {amt:,.0f}" + (f" ({note})" if note else ""))
                    jlines.append((code, 0, amt, pid))
                else:
                    code = name.split(" - ")[0]
                    descs.append(f"{name}: {amt:,.0f}" + (f" ({note})" if note else ""))
                    jlines.append((code, 0, amt, None))
            full = " | ".join(filter(None, [ref_rcv, narr_rcv, "; ".join(descs)]))
            post_journal(d_rcv, f"Receipt | {full}", jlines, "receipt")
            st.success(f"Receipt posted. {total_r:,.2f} into {into_acc['name']}.")
            st.rerun()


# ---------------- JV (full manual journal voucher) ----------------
with tab_jv:
    st.caption("Free-form Journal Voucher — pick any account on either side. "
               "Total Debit must equal total Credit.")
    all_accs = query("SELECT account_id, code, name, type FROM accounts ORDER BY code")
    if not all_accs:
        st.warning("No accounts in COA.")
    else:
        c1, c2 = st.columns(2)
        jv_date = c1.date_input("Date", date.today(), key="jv_d")
        jv_ref = c2.text_input("Voucher # / Ref", key="jv_v")
        jv_narr = st.text_input("Narration", key="jv_n")

        acc_labels = [f"{a['code']} - {a['name']}" for a in all_accs]
        rows_jv = pd.DataFrame([
            {"Account": acc_labels[0], "Debit": 0.0, "Credit": 0.0, "Note": ""},
            {"Account": acc_labels[0], "Debit": 0.0, "Credit": 0.0, "Note": ""},
        ])
        ed_jv = st.data_editor(
            rows_jv, num_rows="dynamic", use_container_width=True, hide_index=True, key="jv_lines",
            column_config={
                "Account": st.column_config.SelectboxColumn(
                    "Account", options=acc_labels, required=True, width="large"),
                "Debit": st.column_config.NumberColumn("Debit", min_value=0.0, step=100.0, format="%.2f"),
                "Credit": st.column_config.NumberColumn("Credit", min_value=0.0, step=100.0, format="%.2f"),
                "Note": st.column_config.TextColumn("Note"),
            },
        )
        tot_dr = float(ed_jv["Debit"].fillna(0).sum())
        tot_cr = float(ed_jv["Credit"].fillna(0).sum())
        c3, c4, c5 = st.columns(3)
        c3.metric("Total Debit", f"{tot_dr:,.2f}")
        c4.metric("Total Credit", f"{tot_cr:,.2f}")
        c5.metric("Difference", f"{(tot_dr - tot_cr):,.2f}",
                  delta_color=("normal" if abs(tot_dr - tot_cr) < 0.01 else "inverse"))

        ok_balanced = abs(tot_dr - tot_cr) < 0.01 and tot_dr > 0
        if st.button("Post JV", type="primary", disabled=not ok_balanced, key="jv_post"):
            jlines = []
            for _, r in ed_jv.iterrows():
                acc_lbl = r.get("Account")
                if not acc_lbl:
                    continue
                code = acc_lbl.split(" - ")[0]
                dr = float(r.get("Debit") or 0)
                cr = float(r.get("Credit") or 0)
                if dr == 0 and cr == 0:
                    continue
                jlines.append((code, dr, cr))
            post_journal(jv_date, f"JV | {jv_ref} | {jv_narr}", jlines, "jv")
            st.success(f"JV posted. Total {tot_dr:,.2f}.")
            st.rerun()
        if not ok_balanced and (tot_dr or tot_cr):
            st.warning("Debit and Credit totals must be equal and greater than zero.")


# ---------------- Journal Ledger ----------------
with tab_je:
    c1, c2, c3 = st.columns(3)
    s = c1.date_input("From", date.today().replace(day=1), key="ls")
    e = c2.date_input("To", date.today(), key="le")
    accs = query("SELECT account_id, code, name FROM accounts ORDER BY code")
    acc_choices = ["All"] + [f"{a['code']} - {a['name']}" for a in accs]
    pick = c3.selectbox("Filter by Account", acc_choices, key="lacc")

    s1, s2 = st.columns([3, 1])
    search_text = s1.text_input(
        "Search (matches Narration / Account code / Account name)", key="lq")
    search_amt = s2.number_input(
        "Search by Amount (Debit or Credit)", min_value=0.0, step=100.0, key="lqa")

    sql = """
        SELECT e.entry_date, e.description, a.code, a.name account,
               l.debit, l.credit, e.ref_type
        FROM journal_lines l
        JOIN journal_entries e ON e.entry_id=l.entry_id
        JOIN accounts a ON a.account_id=l.account_id
        WHERE e.entry_date BETWEEN ? AND ?
    """
    params = [str(s), str(e)]
    if pick != "All":
        sql += " AND a.code=?"
        params.append(pick.split(" - ")[0])
    if search_text.strip():
        sql += " AND (e.description LIKE ? OR a.code LIKE ? OR a.name LIKE ?)"
        like = f"%{search_text.strip()}%"
        params.extend([like, like, like])
    if search_amt and search_amt > 0:
        sql += " AND (ABS(l.debit - ?) < 0.01 OR ABS(l.credit - ?) < 0.01)"
        params.extend([search_amt, search_amt])
    sql += " ORDER BY e.entry_id DESC, l.id ASC LIMIT 2000"
    df = pd.DataFrame(query(sql, tuple(params)))
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        c4, c5, c6 = st.columns(3)
        c4.metric("Total Debit", f"{df['debit'].sum():,.2f}")
        c5.metric("Total Credit", f"{df['credit'].sum():,.2f}")
        c6.metric("Rows", len(df))
    export_excel_button(df, "journal.xlsx")


# ---------------- Vendor Ledger ----------------
with tab_vl:
    st.caption("Per-vendor running ledger: purchase bills (Dr — what we owe), payments (Cr — what we paid). "
               "Closing balance = outstanding payable.")
    vendors = vendors_list()
    if not vendors:
        st.info("No vendors yet. Add one in Sales / Purchase.")
    else:
        vc1, vc2, vc3 = st.columns(3)
        v_pick = vc1.selectbox("Vendor", [v["name"] for v in vendors], key="vl_v")
        v_from = vc2.date_input("From", date.today().replace(month=1, day=1), key="vl_s")
        v_to = vc3.date_input("To", date.today(), key="vl_e")
        v_id = next(v["party_id"] for v in vendors if v["name"] == v_pick)

        # Purchases (Dr — supplier bill)
        df_pur = pd.DataFrame(query("""
            SELECT purchase_date AS date, 'Purchase' AS type,
                   COALESCE(note,'') AS narration, total AS debit, 0.0 AS credit
            FROM purchases WHERE vendor_id=? AND purchase_date BETWEEN ? AND ?
        """, (v_id, str(v_from), str(v_to))))

        # Payments to this vendor (Cr — settles AP). We tagged journal_lines.party_id on Vendor lines.
        df_pmt = pd.DataFrame(query("""
            SELECT je.entry_date AS date, 'Payment' AS type,
                   COALESCE(je.description,'') AS narration,
                   0.0 AS debit, l.debit AS credit
            FROM journal_lines l
            JOIN journal_entries je ON je.entry_id=l.entry_id
            JOIN accounts a ON a.account_id=l.account_id
            WHERE l.party_id=? AND a.code='2000' AND l.debit>0
              AND je.entry_date BETWEEN ? AND ?
        """, (v_id, str(v_from), str(v_to))))

        df_v = pd.concat([df_pur, df_pmt], ignore_index=True)
        if df_v.empty:
            st.info("No transactions for this vendor in the selected range.")
        else:
            df_v = df_v.sort_values("date").reset_index(drop=True)
            df_v["balance"] = (df_v["debit"] - df_v["credit"]).cumsum()

            # Search bar
            sc1, sc2 = st.columns([3, 1])
            search = sc1.text_input(
                "Search (narration / type / date)",
                key="vl_search",
                placeholder="Type to filter rows…")
            type_pick = sc2.selectbox(
                "Type", ["All", "Purchase", "Payment"], key="vl_type")
            df_show = df_v.copy()
            if search.strip():
                t = search.strip().lower()
                mask = (df_show["narration"].astype(str).str.lower().str.contains(t)
                        | df_show["type"].astype(str).str.lower().str.contains(t)
                        | df_show["date"].astype(str).str.contains(t))
                df_show = df_show[mask]
            if type_pick != "All":
                df_show = df_show[df_show["type"] == type_pick]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            tot_dr = df_v["debit"].sum()
            tot_cr = df_v["credit"].sum()
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Total Bills (Dr)", f"{tot_dr:,.2f}")
            mc2.metric("Total Paid (Cr)", f"{tot_cr:,.2f}")
            mc3.metric("Outstanding Payable", f"{(tot_dr - tot_cr):,.2f}")
            export_excel_button(df_v, f"vendor_{v_pick}_ledger.xlsx",
                                "Download Vendor Ledger")


# ---------------- Trial Balance ----------------
with tab_tb:
    st.caption("Trial Balance — every account's net debit or credit balance "
               "as of the chosen date. Total Debit must equal Total Credit.")
    tbc1, tbc2 = st.columns(2)
    tb_from = tbc1.date_input(
        "From (leave as Jan 1 for full year-to-date)",
        date.today().replace(month=1, day=1), key="tb_s")
    tb_to = tbc2.date_input("As of", date.today(), key="tb_e")

    df_tb_raw = pd.DataFrame(query("""
        SELECT a.code, a.name, a.type,
               COALESCE(SUM(l.debit),0)  AS dr,
               COALESCE(SUM(l.credit),0) AS cr
        FROM accounts a
        LEFT JOIN journal_lines l   ON l.account_id=a.account_id
        LEFT JOIN journal_entries je ON je.entry_id=l.entry_id
            AND je.entry_date BETWEEN ? AND ?
        GROUP BY a.account_id
        ORDER BY a.code
    """, (str(tb_from), str(tb_to))))

    if df_tb_raw.empty:
        st.info("No accounts in Chart of Accounts.")
    else:
        # Net = Dr - Cr ; show as Debit balance (if positive) or Credit balance (if negative)
        df_tb_raw["net"] = df_tb_raw["dr"] - df_tb_raw["cr"]
        df_tb_raw["Debit"] = df_tb_raw["net"].apply(lambda v: v if v > 0 else 0.0)
        df_tb_raw["Credit"] = df_tb_raw["net"].apply(lambda v: -v if v < 0 else 0.0)
        # Hide zero-balance accounts toggle
        hide_zero = st.checkbox("Hide accounts with zero balance", value=True, key="tb_hz")
        df_show = df_tb_raw.copy()
        if hide_zero:
            df_show = df_show[(df_show["Debit"].abs() + df_show["Credit"].abs()) > 0.005]
        df_show = df_show[["code", "name", "type", "Debit", "Credit"]].rename(
            columns={"code": "Code", "name": "Account", "type": "Type"})
        st.dataframe(
            df_show, use_container_width=True, hide_index=True,
            column_config={
                "Debit":  st.column_config.NumberColumn(format="%.2f"),
                "Credit": st.column_config.NumberColumn(format="%.2f"),
            })

        tot_dr = float(df_show["Debit"].sum())
        tot_cr = float(df_show["Credit"].sum())
        diff = tot_dr - tot_cr
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Debit", f"{tot_dr:,.2f}")
        m2.metric("Total Credit", f"{tot_cr:,.2f}")
        m3.metric("Difference", f"{diff:,.2f}",
                  delta_color=("normal" if abs(diff) < 0.01 else "inverse"))
        if abs(diff) < 0.01:
            st.success("Books are in balance. ✔")
        else:
            st.warning("Trial Balance is OUT of balance — check journal entries.")
        export_excel_button(df_show, "trial_balance.xlsx")


# ---------------- P&L (Profit & Loss Statement) ----------------
with tab_pl:
    st.caption("Profit & Loss for the selected period. Income (credit balances) "
               "minus Expenses (debit balances) = Net Profit.")
    c1, c2 = st.columns(2)
    s = c1.date_input("From", date.today().replace(day=1), key="pls")
    e = c2.date_input("To", date.today(), key="ple")

    df_pl_raw = pd.DataFrame(query("""
        SELECT a.type, a.code, a.name,
               COALESCE(SUM(l.debit),0)  AS dr,
               COALESCE(SUM(l.credit),0) AS cr
        FROM accounts a
        LEFT JOIN journal_lines l   ON l.account_id=a.account_id
        LEFT JOIN journal_entries je ON je.entry_id=l.entry_id
            AND je.entry_date BETWEEN ? AND ?
        WHERE a.type IN ('Income', 'Expense')
        GROUP BY a.account_id
        ORDER BY a.type DESC, a.code
    """, (str(s), str(e))))

    if df_pl_raw.empty:
        st.info("No Income or Expense accounts in COA.")
    else:
        df_pl_raw["amount"] = df_pl_raw.apply(
            lambda r: (r["cr"] - r["dr"]) if r["type"] == "Income"
                      else (r["dr"] - r["cr"]),
            axis=1)

        # ---- Income section ----
        st.markdown("### Income")
        df_inc = df_pl_raw[df_pl_raw["type"] == "Income"][
            ["code", "name", "amount"]].rename(
            columns={"code": "Code", "name": "Account", "amount": "Amount"})
        df_inc = df_inc[df_inc["Amount"].abs() > 0.005] if not df_inc.empty else df_inc
        if df_inc.empty:
            st.caption("— No income recorded in this period —")
            inc_total = 0.0
        else:
            st.dataframe(
                df_inc, use_container_width=True, hide_index=True,
                column_config={"Amount": st.column_config.NumberColumn(format="%.2f")})
            inc_total = float(df_inc["Amount"].sum())
        st.markdown(f"**Total Income: {inc_total:,.2f}**")

        # ---- Expense section ----
        st.markdown("### Expenses")
        df_exp = df_pl_raw[df_pl_raw["type"] == "Expense"][
            ["code", "name", "amount"]].rename(
            columns={"code": "Code", "name": "Account", "amount": "Amount"})
        df_exp = df_exp[df_exp["Amount"].abs() > 0.005] if not df_exp.empty else df_exp
        if df_exp.empty:
            st.caption("— No expenses recorded in this period —")
            exp_total = 0.0
        else:
            st.dataframe(
                df_exp, use_container_width=True, hide_index=True,
                column_config={"Amount": st.column_config.NumberColumn(format="%.2f")})
            exp_total = float(df_exp["Amount"].sum())
        st.markdown(f"**Total Expenses: {exp_total:,.2f}**")

        net = inc_total - exp_total
        st.markdown("---")
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Income", f"{inc_total:,.2f}")
        k2.metric("Total Expenses", f"{exp_total:,.2f}")
        k3.metric("Net Profit / (Loss)", f"{net:,.2f}",
                  delta=f"{(net/inc_total*100 if inc_total else 0):.1f}% margin")

        df_full = pd.concat([
            df_inc.assign(Section="Income"),
            df_exp.assign(Section="Expense"),
        ], ignore_index=True) if (not df_inc.empty or not df_exp.empty) else pd.DataFrame()
        if not df_full.empty:
            export_excel_button(df_full, "profit_and_loss.xlsx", "Download P&L")


# ---------------- Balance Sheet ----------------
with tab_bs:
    st.caption("Balance Sheet — financial position as of the chosen date. "
               "Assets must equal Liabilities + Equity (incl. retained earnings).")
    bsc1, bsc2 = st.columns(2)
    bs_to = bsc1.date_input("As of", date.today(), key="bs_e")
    fy_start = bsc2.date_input(
        "Financial year start (for current-year P&L)",
        date.today().replace(month=1, day=1), key="bs_fy")

    df_bs_raw = pd.DataFrame(query("""
        SELECT a.type, a.code, a.name,
               COALESCE(SUM(l.debit),0)  AS dr,
               COALESCE(SUM(l.credit),0) AS cr
        FROM accounts a
        LEFT JOIN journal_lines l   ON l.account_id=a.account_id
        LEFT JOIN journal_entries je ON je.entry_id=l.entry_id
            AND je.entry_date <= ?
        GROUP BY a.account_id
        ORDER BY a.code
    """, (str(bs_to),)))

    if df_bs_raw.empty:
        st.info("No accounts in Chart of Accounts.")
    else:
        # Signed balance per type (positive = "natural" side)
        def _bal(r):
            v = r["dr"] - r["cr"]
            return v if r["type"] in ("Asset", "Expense") else -v
        df_bs_raw["balance"] = df_bs_raw.apply(_bal, axis=1)

        # Current-year Net Profit (Income - Expense for FY range up to bs_to)
        cy_inc = query("""
            SELECT COALESCE(SUM(l.credit-l.debit),0) v FROM journal_lines l
            JOIN journal_entries je ON je.entry_id=l.entry_id
            JOIN accounts a ON a.account_id=l.account_id
            WHERE a.type='Income' AND je.entry_date BETWEEN ? AND ?
        """, (str(fy_start), str(bs_to)))[0]["v"] or 0.0
        cy_exp = query("""
            SELECT COALESCE(SUM(l.debit-l.credit),0) v FROM journal_lines l
            JOIN journal_entries je ON je.entry_id=l.entry_id
            JOIN accounts a ON a.account_id=l.account_id
            WHERE a.type='Expense' AND je.entry_date BETWEEN ? AND ?
        """, (str(fy_start), str(bs_to)))[0]["v"] or 0.0
        net_profit = cy_inc - cy_exp

        col_l, col_r = st.columns(2)

        # ---- ASSETS ----
        with col_l:
            st.markdown("### 🟢 Assets")
            df_a = df_bs_raw[df_bs_raw["type"] == "Asset"][
                ["code", "name", "balance"]].rename(
                columns={"code": "Code", "name": "Account", "balance": "Amount"})
            df_a = df_a[df_a["Amount"].abs() > 0.005] if not df_a.empty else df_a
            if df_a.empty:
                st.caption("— No asset balances —")
                tot_assets = 0.0
            else:
                st.dataframe(
                    df_a, use_container_width=True, hide_index=True,
                    column_config={"Amount": st.column_config.NumberColumn(format="%.2f")})
                tot_assets = float(df_a["Amount"].sum())
            st.markdown(f"**Total Assets: {tot_assets:,.2f}**")

        # ---- LIABILITIES + EQUITY ----
        with col_r:
            st.markdown("### 🔴 Liabilities")
            df_l = df_bs_raw[df_bs_raw["type"] == "Liability"][
                ["code", "name", "balance"]].rename(
                columns={"code": "Code", "name": "Account", "balance": "Amount"})
            df_l = df_l[df_l["Amount"].abs() > 0.005] if not df_l.empty else df_l
            if df_l.empty:
                st.caption("— No liability balances —")
                tot_liab = 0.0
            else:
                st.dataframe(
                    df_l, use_container_width=True, hide_index=True,
                    column_config={"Amount": st.column_config.NumberColumn(format="%.2f")})
                tot_liab = float(df_l["Amount"].sum())
            st.markdown(f"**Total Liabilities: {tot_liab:,.2f}**")

            st.markdown("### 🔵 Equity")
            df_eq = df_bs_raw[df_bs_raw["type"] == "Equity"][
                ["code", "name", "balance"]].rename(
                columns={"code": "Code", "name": "Account", "balance": "Amount"})
            df_eq = df_eq[df_eq["Amount"].abs() > 0.005] if not df_eq.empty else df_eq
            tot_eq = float(df_eq["Amount"].sum()) if not df_eq.empty else 0.0
            # Add current year net profit row
            extra = pd.DataFrame([{
                "Code": "—", "Account": "Net Profit (current FY)", "Amount": net_profit
            }])
            df_eq_show = pd.concat([df_eq, extra], ignore_index=True) if not df_eq.empty else extra
            st.dataframe(
                df_eq_show, use_container_width=True, hide_index=True,
                column_config={"Amount": st.column_config.NumberColumn(format="%.2f")})
            tot_equity = tot_eq + net_profit
            st.markdown(f"**Total Equity: {tot_equity:,.2f}**")

        st.markdown("---")
        tot_le = tot_liab + tot_equity
        diff = tot_assets - tot_le
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Assets", f"{tot_assets:,.2f}")
        m2.metric("Total Liab. + Equity", f"{tot_le:,.2f}")
        m3.metric("Difference", f"{diff:,.2f}",
                  delta_color=("normal" if abs(diff) < 0.01 else "inverse"))
        if abs(diff) < 0.01:
            st.success("Balance Sheet balances. ✔")
        else:
            st.warning(
                "Balance Sheet does NOT balance. "
                "Check that opening equity / capital contributions are recorded.")

        # Export combined
        df_bs_export = pd.concat([
            df_bs_raw[df_bs_raw["type"] == "Asset"][["code", "name", "balance"]]
                .assign(Section="Asset"),
            df_bs_raw[df_bs_raw["type"] == "Liability"][["code", "name", "balance"]]
                .assign(Section="Liability"),
            df_bs_raw[df_bs_raw["type"] == "Equity"][["code", "name", "balance"]]
                .assign(Section="Equity"),
            pd.DataFrame([{"code": "—", "name": "Net Profit (current FY)",
                           "balance": net_profit, "Section": "Equity"}]),
        ], ignore_index=True)
        export_excel_button(df_bs_export, "balance_sheet.xlsx",
                            "Download Balance Sheet")
