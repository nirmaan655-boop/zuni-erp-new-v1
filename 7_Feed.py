"""Feed Management - TMR recipes (build once, consume date-wise)."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date
from db import init_db, query, execute, add_stock_move, post_journal
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Feed", layout="wide")
init_db()

require_role("7_Feed")
render_user_sidebar()
st.title("Feed Management (TMR)")
st.caption("Build a TMR recipe once — then just consume it date-wise. Stock and accounting update automatically.")

tab_recipe, tab_alloc, tab_rep = st.tabs(["TMR Recipes", "Daily Consumption", "Reports"])

feed_store = query("SELECT store_id FROM stores WHERE name='Feed Store'")[0]["store_id"]
feed_items = query("SELECT * FROM items WHERE store_id=?", (feed_store,))

# ---------- Recipes ----------
with tab_recipe:
    st.subheader("Create New TMR Recipe")
    with st.form("rec_new", clear_on_submit=True):
        c1, c2 = st.columns([1, 2])
        rname = c1.text_input("Recipe Name *")
        rdesc = c2.text_input("Description")
        if st.form_submit_button("Create Recipe", type="primary"):
            if not rname.strip():
                st.error("Recipe name is required.")
            else:
                try:
                    execute("INSERT INTO feed_recipes(name,description) VALUES(?,?)",
                            (rname.strip(), rdesc))
                    st.success(f"Recipe '{rname}' created. Now add items below.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    st.divider()
    recipes = query("SELECT * FROM feed_recipes ORDER BY name")

    if not recipes:
        st.info("No recipes yet. Create one above to start.")
    elif not feed_items:
        st.warning("No feed items found. Add items in Inventory → Feed Store first.")
    else:
        st.subheader("Manage Recipe Ingredients")
        rec_names = [r["name"] for r in recipes]
        sel_name = st.selectbox("Select Recipe", rec_names)
        sel_recipe = next(r for r in recipes if r["name"] == sel_name)
        rid = sel_recipe["recipe_id"]

        # Build option labels and lookup maps for feed items
        item_labels = [f"{i['name']} ({i['uom']})" for i in feed_items]
        label_to_id = {f"{i['name']} ({i['uom']})": i["item_id"] for i in feed_items}
        id_to_label = {i["item_id"]: f"{i['name']} ({i['uom']})" for i in feed_items}
        id_to_cost = {i["item_id"]: (i["unit_cost"] or 0) for i in feed_items}

        # Current ingredients
        items_in = query(
            "SELECT id, item_id, qty FROM feed_recipe_items WHERE recipe_id=? ORDER BY id",
            (rid,))
        rows = []
        for idx, it in enumerate(items_in, 1):
            label = id_to_label.get(it["item_id"], "")
            cost = round(it["qty"] * id_to_cost.get(it["item_id"], 0), 2)
            rows.append({"Sr": idx, "Item": label, "Qty / animal": it["qty"], "Line Cost": cost})
        if not rows:
            rows = [{"Sr": 1, "Item": "", "Qty / animal": 0.0, "Line Cost": 0.0}]
        df_edit = pd.DataFrame(rows)

        st.caption("Add, edit or remove rows below — then click Save Changes. Use the + button to add a row, or check a row and press Delete to remove.")
        edited = st.data_editor(
            df_edit,
            key=f"rec_editor_{rid}",
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Sr": st.column_config.NumberColumn("Sr No", disabled=True, width="small"),
                "Item": st.column_config.SelectboxColumn(
                    "Item", options=item_labels, required=True, width="large"),
                "Qty / animal": st.column_config.NumberColumn(
                    "Qty / animal", min_value=0.0, step=0.1, format="%.3f"),
                "Line Cost": st.column_config.NumberColumn(
                    "Line Cost", disabled=True, format="%.2f"),
            },
        )

        # Live total
        live_total = 0.0
        for _, r in edited.iterrows():
            iid = label_to_id.get(r["Item"])
            if iid:
                live_total += float(r["Qty / animal"] or 0) * id_to_cost.get(iid, 0)
        st.metric("Cost per animal / day", f"{live_total:,.2f}")

        cA, cB, cC = st.columns([1, 1, 2])
        if cA.button("Save Changes", type="primary", key=f"save_{rid}"):
            # Validate: drop rows with no item; aggregate duplicates by summing qty
            agg = {}
            for _, r in edited.iterrows():
                lbl = r["Item"]
                if not lbl or lbl not in label_to_id:
                    continue
                iid = label_to_id[lbl]
                qty = float(r["Qty / animal"] or 0)
                if qty <= 0:
                    continue
                agg[iid] = agg.get(iid, 0) + qty
            execute("DELETE FROM feed_recipe_items WHERE recipe_id=?", (rid,))
            for iid, qty in agg.items():
                execute("INSERT INTO feed_recipe_items(recipe_id,item_id,qty) VALUES(?,?,?)",
                        (rid, iid, qty))
            st.success(f"Saved {len(agg)} ingredient(s) for '{sel_name}'.")
            st.rerun()

        if cB.button("Reset", key=f"reset_{rid}"):
            st.rerun()

        with cC:
            if st.button(f"Delete recipe '{sel_name}'", type="secondary", key=f"del_{rid}"):
                execute("DELETE FROM feed_recipe_items WHERE recipe_id=?", (rid,))
                execute("DELETE FROM feed_recipes WHERE recipe_id=?", (rid,))
                st.rerun()

# ---------- Daily Consumption ----------
with tab_alloc:
    pens = query("SELECT * FROM pens")
    recipes = query("SELECT * FROM feed_recipes")
    if not (pens and recipes):
        st.info("Create at least one pen and one TMR recipe first.")
    else:
        st.subheader("Consume TMR pen-wise (auto x animal count)")
        st.caption("Recipe quantities are per animal. The system multiplies by the number of active animals in the chosen pen automatically.")

        c1, c2, c3 = st.columns(3)
        pen = c1.selectbox("Pen", [p["name"] for p in pens])
        rec = c2.selectbox("TMR Recipe", [r["name"] for r in recipes])
        d = c3.date_input("Date", date.today())

        pid = next(p["pen_id"] for p in pens if p["name"] == pen)
        rid = next(r["recipe_id"] for r in recipes if r["name"] == rec)
        pen_animals = query(
            "SELECT COUNT(*) c FROM animals WHERE pen_id=? AND status='Active'",
            (pid,))[0]["c"]

        c4, c5 = st.columns(2)
        c4.metric("Active animals in pen", pen_animals)
        servings = c5.number_input(
            "Servings (defaults to animal count, override if needed)",
            min_value=0.0, step=1.0, value=float(pen_animals))

        # Live preview
        items = query(
            "SELECT i.name, ri.qty, i.uom, i.unit_cost, ri.item_id "
            "FROM feed_recipe_items ri JOIN items i ON i.item_id=ri.item_id "
            "WHERE ri.recipe_id=?", (rid,))
        if items and servings > 0:
            prev = pd.DataFrame([{
                "Item": it["name"],
                "Total Qty": round(it["qty"] * servings, 2),
                "UOM": it["uom"],
                "Cost": round(it["qty"] * servings * (it["unit_cost"] or 0), 2),
            } for it in items])
            st.write("**Will consume:**")
            st.dataframe(prev, use_container_width=True, hide_index=True)
            st.metric("Total cost", f"{prev['Cost'].sum():,.2f}")

        if st.button("Confirm Consumption", type="primary", disabled=(servings <= 0 or not items)):
            alloc_id = execute(
                "INSERT INTO feed_allocations(pen_id,recipe_id,alloc_date,servings) VALUES(?,?,?,?)",
                (pid, rid, str(d), servings))
            total_cost = 0
            for it in items:
                use_qty = it["qty"] * servings
                add_stock_move(it["item_id"], d, "OUT", use_qty, it["unit_cost"],
                               "feed_alloc", alloc_id, "Feed allocation")
                total_cost += use_qty * (it["unit_cost"] or 0)
            if total_cost:
                post_journal(d, f"Feed allocation pen {pen}",
                             [("5000", total_cost, 0), ("1200", 0, total_cost)],
                             "feed_alloc", alloc_id)
            st.success(f"Consumed for {servings} animals. Total cost: {total_cost:,.2f}")

# ---------- Reports ----------
with tab_rep:
    df = pd.DataFrame(query("""
        SELECT a.alloc_date, p.name pen, r.name recipe, a.servings,
               ROUND(((SELECT SUM(ri.qty*COALESCE(i.unit_cost,0))
                       FROM feed_recipe_items ri JOIN items i ON i.item_id=ri.item_id
                       WHERE ri.recipe_id=a.recipe_id) * a.servings)::numeric, 2) cost
        FROM feed_allocations a
        JOIN pens p ON p.pen_id=a.pen_id
        JOIN feed_recipes r ON r.recipe_id=a.recipe_id
        ORDER BY a.id DESC
    """))
    st.dataframe(df, use_container_width=True, hide_index=True)
    export_excel_button(df, "feed_allocations.xlsx")
