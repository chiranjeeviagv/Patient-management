import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from utils import apply_custom_ui, render_hero, require_login

st.set_page_config(page_title="Admin Analytics", page_icon="📊", layout="wide")
apply_custom_ui()

if require_login("Admin Analytics", "admin123"):
    render_hero("📊 Hospital Operational Control Panel", "Real-time booking metrics, revenue, and disease incidence analytics.")
    conn = sqlite3.connect("hospital_v2.db")
    df_app = pd.read_sql_query("SELECT * FROM appointments", conn)
    df_cons = pd.read_sql_query("SELECT * FROM consultations", conn)
    df_bill = pd.read_sql_query("SELECT * FROM billing", conn)
    conn.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Bookings", len(df_app))
    c2.metric("Pending", len(df_app[df_app["status"] == "Pending"]))
    c3.metric("Completed", len(df_app[df_app["status"] == "Completed"]))
    c4.metric("Total Revenue", f"₹{df_bill['grand_total'].sum():,.2f}" if not df_bill.empty else "₹0.00")

    if not df_cons.empty:
        chart_data = df_cons["diagnosed_disease"].value_counts().reset_index()
        chart_data.columns = ["Disease", "Cases"]
        fig = px.bar(chart_data, x="Disease", y="Cases", color="Cases", color_continuous_scale="Tealgrn", text_auto=True)
        st.plotly_chart(fig, use_container_width=True)
