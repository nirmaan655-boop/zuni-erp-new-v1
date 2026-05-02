"""Animal-wise Profit & Loss."""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import init_db, query, latest_milk_rate
from auth import require_role, render_user_sidebar
from utils import export_excel_button

st.set_page_config(page_title="Animal P&L", layout="wide")
init_db()

require_role("14_Animal_PL")
render_user_sidebar()
st.title("Animal-wise Profit & Loss")
st.caption("Revenue from milk + animal sale, less purchase + treatment + share of pen feed cost. "
           "Milk rate is auto-picked from the latest milk sale.")

auto_rate = latest_milk_rate() or 80.0
c1, c2, c3 = st.columns(3)
start = c1.date_input("From", date.today() - timedelta(days=90))
end = c2.date_input("To", date.today())
milk_price = c3.number_input("Milk price per Litre (auto from last sale)",
                              min_value=0.0, step=1.0, value=float(auto_rate),
                              help="Auto-picked from the most recent Milk sale; override if needed.")

animals = query("""
    SELECT a.animal_id, a.tag, a.breed, a.status, a.pen_id, p.name pen
    FROM animals a LEFT JOIN pens p ON p.pen_id=a.pen_id
""")

if not animals:
    st.info("Add animals to see the report.")
    st.stop()

rows = []
for a in animals:
    aid = a["animal_id"]

    milk_l = query(
        "SELECT COALESCE(SUM(litres),0) v FROM milk_records "
        "WHERE animal_id=? AND record_date BETWEEN ? AND ?",
        (aid, str(start), str(end)))[0]["v"]
    milk_revenue = milk_l * milk_price

    animal_sale = query(
        "SELECT COALESCE(SUM(total),0) v FROM sales "
        "WHERE animal_id=? AND sale_date BETWEEN ? AND ?",
        (aid, str(start), str(end)))[0]["v"]

    animal_cost = query(
        "SELECT COALESCE(SUM(total),0) v FROM purchases "
        "WHERE animal_id=? AND purchase_date BETWEEN ? AND ?",
        (aid, str(start), str(end)))[0]["v"]

    treat_cost = query(
        "SELECT COALESCE(SUM(cost),0) v FROM treatments "
        "WHERE animal_id=? AND treat_date BETWEEN ? AND ?",
        (aid, str(start), str(end)))[0]["v"]

    breed_cost = query(
        "SELECT COALESCE(SUM(cost),0) v, COALESCE(SUM(straws_used),0) s "
        "FROM breeding_events WHERE animal_id=? AND event_date BETWEEN ? AND ?",
        (aid, str(start), str(end)))[0]
    breeding_cost = breed_cost["v"]
    straws = breed_cost["s"]

    # Share of pen feed cost & feed kg
    feed_share = 0
    feed_kg = 0
    if a["pen_id"]:
        pen_feed = query("""
            SELECT
              COALESCE(SUM(
                a.servings * (
                    SELECT COALESCE(SUM(ri.qty * COALESCE(i.unit_cost,0)),0)
                    FROM feed_recipe_items ri JOIN items i ON i.item_id=ri.item_id
                    WHERE ri.recipe_id=a.recipe_id
                )
              ),0) cost,
              COALESCE(SUM(
                a.servings * (
                    SELECT COALESCE(SUM(ri.qty),0)
                    FROM feed_recipe_items ri WHERE ri.recipe_id=a.recipe_id
                )
              ),0) kg
            FROM feed_allocations a
            WHERE a.pen_id=? AND a.alloc_date BETWEEN ? AND ?
        """, (a["pen_id"], str(start), str(end)))[0]
        pen_animals = query(
            "SELECT COUNT(*) c FROM animals WHERE pen_id=? AND status='Active'",
            (a["pen_id"],))[0]["c"] or 1
        feed_share = pen_feed["cost"] / pen_animals
        feed_kg = pen_feed["kg"] / pen_animals

    revenue = milk_revenue + animal_sale
    cost = animal_cost + treat_cost + feed_share + breeding_cost
    profit = revenue - cost
    rows.append({
        "Tag": a["tag"], "Breed": a["breed"], "Pen": a["pen"], "Status": a["status"],
        "Milk (L)": round(milk_l, 1),
        "Feed (kg)": round(feed_kg, 2),
        "Straws": int(straws),
        "Milk Revenue": round(milk_revenue, 2),
        "Animal Sale": round(animal_sale, 2),
        "Total Revenue": round(revenue, 2),
        "Animal Cost": round(animal_cost, 2),
        "Treatment Cost": round(treat_cost, 2),
        "Feed Cost": round(feed_share, 2),
        "Breeding Cost": round(breeding_cost, 2),
        "Total Cost": round(cost, 2),
        "Profit / (Loss)": round(profit, 2),
    })

df = pd.DataFrame(rows)

k1, k2, k3 = st.columns(3)
k1.metric("Total Revenue", f"{df['Total Revenue'].sum():,.0f}")
k2.metric("Total Cost", f"{df['Total Cost'].sum():,.0f}")
k3.metric("Total Profit", f"{df['Profit / (Loss)'].sum():,.0f}")

st.dataframe(df.sort_values("Profit / (Loss)", ascending=False),
             use_container_width=True, hide_index=True)
export_excel_button(df, "animal_profit_loss.xlsx")
