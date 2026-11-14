import streamlit as st
import pandas as pd
import sqlite3
from utils import apply_custom_ui, render_hero, require_login

st.set_page_config(page_title="Pharmacy Inventory", page_icon="📦", layout="wide")
apply_custom_ui()

if require_login("Pharmacy Inventory", "pharma123"):
    render_hero("📦 Medical Dispensary & Pharmacy Stock", "Monitor stock levels, unit pricing, and reorder alerts.")
    conn = sqlite3.connect("hospital_v2.db")
    df_inv = pd.read_sql_query("SELECT id AS ID, medicine_name AS [Medicine Name], category AS [Category], stock_qty AS [Stock], min_required AS [Min Limit], unit_price AS [Price (₹)] FROM inventory", conn)
    conn.close()

    low_stock = df_inv[df_inv["Stock"] <= df_inv["Min Limit"]]
    c1, c2 = st.columns(2)
    c1.metric("Total Formulas", len(df_inv))
    c2.metric("Low Stock Alerts", len(low_stock), delta=-len(low_stock), delta_color="inverse")

    if not low_stock.empty:
        st.error("⚠️ Low Stock Warning:")
        st.dataframe(low_stock, use_container_width=True, hide_index=True)

    edited_inv = st.data_editor(df_inv, disabled=["ID", "Medicine Name", "Category"], use_container_width=True, hide_index=True)
    if st.button("💾 Save Inventory Updates", type="primary"):
        conn = sqlite3.connect("hospital_v2.db")
        for _, row in edited_inv.iterrows():
            conn.execute("UPDATE inventory SET stock_qty = ?, min_required = ?, unit_price = ? WHERE id = ?", (int(row["Stock"]), int(row["Min Limit"]), float(row["Price (₹)"]), int(row["ID"])))
        conn.commit()
        conn.close()
        st.success("Inventory updated!")
        st.rerun()
