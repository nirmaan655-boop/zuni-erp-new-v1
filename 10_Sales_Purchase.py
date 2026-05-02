"""Sale & Purchase."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import (init_db, query, execute, add_stock_move, post_journal,
                add_milk_move, milk_store_balance, latest_milk_rate)
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Sale & Purchase", layout="wide")
init_db()

require_role("10_Sales_Purchase")
render_user_sidebar()
st.title("Sales & Purchases")

tab_p, tab_s, tab_party = st.tabs(["Purchases", "Sales", "Vendors / Customers"])

with tab_party:
    with st.form("party", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        n = c1.text_input("Name *")
        t = c2.selectbox("Type", ["Vendor", "Customer"])
        ph = c3.text_input("Phone")
        ad = c4.text_input("Address")
        if st.form_submit_button("Save", type="primary"):
            if not n.strip():
                st.error("Name is required.")
            else:
                dup = query("SELECT party_id, name, party_type FROM parties "
                            "WHERE LOWER(name)=LOWER(?) AND party_type=?", (n.strip(), t))
                if dup:
                    st.error(f"{t} '{dup[0]['name']}' already exists.")
                else:
                    execute("INSERT INTO parties(name,party_type,phone,address) VALUES(?,?,?,?)",
                            (n.strip(), t, ph, ad))
                    st.success(f"{t} '{n}' saved.")
                    st.rerun()
    df = pd.DataFrame(query("SELECT * FROM parties ORDER BY party_type, name"))
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab_p:
    stores = query("SELECT store_id, name FROM stores ORDER BY name")
    vendors = query("SELECT * FROM parties WHERE party_type='Vendor' ORDER BY name")
    animals = query("SELECT animal_id, tag FROM animals WHERE status='Active'")

    kind = st.radio("Purchase Kind", ["Item", "Animal"], horizontal=True, key="pk")

    c1, c2, c3 = st.columns(3)
    d = c1.date_input("Date", date.today())
    vendor = c2.selectbox(
        "Vendor (type to search)",
        ["-"] + [v["name"] for v in vendors],
        key="pvend")

    iid = aid = None
    item_unit_cost = 0.0
    item_uom = ""
    if kind == "Item":
        store_name = c3.selectbox("Store", [s["name"] for s in stores], key="pstore")
        store_id = next(s["store_id"] for s in stores if s["name"] == store_name)
        store_items = query(
            "SELECT item_id, name, uom, unit_cost FROM items WHERE store_id=? ORDER BY name",
            (store_id,))
        if not store_items:
            st.warning(f"No items in '{store_name}'. Add some in Inventory first.")
        else:
            sel_name = st.selectbox("Item", [i["name"] for i in store_items], key="pitem")
            sel_item = next(i for i in store_items if i["name"] == sel_name)
            iid = sel_item["item_id"]
            item_unit_cost = sel_item["unit_cost"] or 0
            item_uom = sel_item["uom"]
    else:
        atag_in = c3.text_input("New Animal Tag")
        breed = st.text_input("Breed", "Mixed", key="pbreed")

    with st.form("pur", clear_on_submit=False):
        c4, c5 = st.columns(2)
        qty = c4.number_input(f"Qty {('('+item_uom+')') if item_uom else ''}",
                              min_value=0.0, step=1.0, value=1.0, key="pqty")
        unit = c5.number_input("Unit Cost (auto from item, override if needed)",
                               min_value=0.0, step=1.0, value=float(item_unit_cost), key="pucost")
        note = st.text_input("Note", key="pnote")
        st.metric("Total", f"{qty * unit:,.2f}")
        if st.form_submit_button("Save Purchase", type="primary"):
            vid = next((v["party_id"] for v in vendors if v["name"] == vendor), None)
            total = qty * unit
            new_aid = None
            if kind == "Item" and not iid:
                st.error("Please pick an item.")
            elif kind == "Animal" and not (kind == "Animal" and atag_in.strip()):
                st.error("Please enter the new animal tag.")
            else:
                if kind == "Animal":
                    new_aid = execute(
                        "INSERT INTO animals(tag,breed,dob,sex,status) VALUES(?,?,?,?,?)",
                        (atag_in.strip(), breed, str(d), "F", "Active"))
                pid = execute(
                    "INSERT INTO purchases(purchase_date,vendor_id,item_id,animal_id,qty,unit_cost,total,kind,note) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (str(d), vid, iid, new_aid, qty, unit, total, kind, note))
                if iid:
                    add_stock_move(iid, d, "IN", qty, unit, "purchase", pid)
                    execute("UPDATE items SET unit_cost=? WHERE item_id=?", (unit, iid))
                    post_journal(d, "Purchase item",
                                 [("1200", total, 0), ("2000", 0, total)], "purchase", pid)
                elif new_aid:
                    post_journal(d, f"Purchase animal {atag_in}",
                                 [("1300", total, 0), ("2000", 0, total)], "purchase", pid)
                st.success(f"Saved. Total: {total:,.2f}")

    df = pd.DataFrame(query("""
        SELECT p.purchase_date, p.kind, v.name vendor,
            COALESCE(i.name, a.tag) ref, p.qty, p.unit_cost, p.total
        FROM purchases p
        LEFT JOIN parties v ON v.party_id=p.vendor_id
        LEFT JOIN items i ON i.item_id=p.item_id
        LEFT JOIN animals a ON a.animal_id=p.animal_id
        ORDER BY p.purchase_id DESC
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "purchases.xlsx")

with tab_s:
    customers = query("SELECT * FROM parties WHERE party_type='Customer' ORDER BY name")
    animals_active = query("SELECT animal_id, tag FROM animals WHERE status='Active' ORDER BY tag")
    stores_s = query("SELECT store_id, name FROM stores ORDER BY name")

    kind = st.radio("Sale Kind", ["Milk", "Animal", "Item"], horizontal=True, key="sk")

    c1, c2, c3 = st.columns(3)
    d = c1.date_input("Date", date.today(), key="sd")
    customer = c2.selectbox(
        "Customer (type to search)",
        ["-"] + [c["name"] for c in customers], key="scust")

    sel_aid = None
    sel_item_id = None
    sel_uom = ""
    auto_price = 0.0

    if kind == "Animal":
        if not animals_active:
            c3.info("No active animals.")
        else:
            atag = c3.selectbox("Animal", [a["tag"] for a in animals_active], key="sani")
            sel_aid = next(a["animal_id"] for a in animals_active if a["tag"] == atag)
    elif kind == "Item":
        store_name = c3.selectbox("Store", [s["name"] for s in stores_s], key="sstore")
        store_id = next(s["store_id"] for s in stores_s if s["name"] == store_name)
        store_items = query(
            "SELECT item_id, name, uom, unit_cost FROM items WHERE store_id=? ORDER BY name",
            (store_id,))
        if not store_items:
            st.warning(f"No items in '{store_name}'.")
        else:
            sel_name = st.selectbox("Item", [i["name"] for i in store_items], key="sitem")
            sel = next(i for i in store_items if i["name"] == sel_name)
            sel_item_id = sel["item_id"]
            sel_uom = sel["uom"]
            auto_price = sel["unit_cost"] or 0
            bal = query("SELECT COALESCE(SUM(CASE WHEN move_type='IN' THEN qty ELSE -qty END),0) b "
                        "FROM stock_moves WHERE item_id=?", (sel_item_id,))[0]["b"]
            st.caption(f"Available stock: **{bal} {sel_uom}**")
    elif kind == "Milk":
        c3.metric("Milk Store balance (L)", f"{milk_store_balance():,.1f}")
        auto_price = latest_milk_rate()

    with st.form("sale", clear_on_submit=False):
        c4, c5 = st.columns(2)
        qty = c4.number_input(f"Qty {('('+sel_uom+')') if sel_uom else ''}",
                              min_value=0.0, step=1.0, value=1.0, key="sq")
        unit = c5.number_input("Unit Price (auto from item / last milk rate)",
                               min_value=0.0, step=1.0, value=float(auto_price), key="su")
        note = st.text_input("Note", key="snote")
        st.metric("Total", f"{qty * unit:,.2f}")

        if st.form_submit_button("Save Sale", type="primary"):
            cid = next((c["party_id"] for c in customers if c["name"] == customer), None)
            total = qty * unit
            ok = True
            if kind == "Milk":
                if qty > milk_store_balance():
                    st.error(f"Not enough milk in store. Available {milk_store_balance():.1f} L.")
                    ok = False
            if kind == "Item" and not sel_item_id:
                st.error("Pick an item.")
                ok = False
            if kind == "Animal" and not sel_aid:
                st.error("Pick an animal.")
                ok = False

            if ok:
                sid = execute(
                    "INSERT INTO sales(sale_date,customer_id,kind,animal_id,qty,unit_price,total,note) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (str(d), cid, kind, sel_aid, qty, unit, total, note))
                if kind == "Milk":
                    add_milk_move(d, "OUT", qty, "Sale", unit, "sale", sid, "Milk sale")
                    post_journal(d, "Milk sale",
                                 [("1400", total, 0), ("4000", 0, total)], "sale", sid)
                elif kind == "Animal":
                    post_journal(d, "Animal sale",
                                 [("1400", total, 0), ("4100", 0, total)], "sale", sid)
                    execute("UPDATE animals SET status='Sold' WHERE animal_id=?", (sel_aid,))
                elif kind == "Item":
                    add_stock_move(sel_item_id, d, "OUT", qty, unit, "sale", sid, "Item sale")
                    post_journal(d, "Item sale",
                                 [("1400", total, 0), ("4000", 0, total)], "sale", sid)
                st.success(f"Sale recorded. Total: {total:,.2f}")

    df = pd.DataFrame(query("""
        SELECT s.sale_date, s.kind, c.name customer, a.tag animal, s.qty, s.unit_price, s.total
        FROM sales s
        LEFT JOIN parties c ON c.party_id=s.customer_id
        LEFT JOIN animals a ON a.animal_id=s.animal_id
        ORDER BY s.sale_id DESC
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "sales.xlsx")
