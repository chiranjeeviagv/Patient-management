import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from utils import load_clinical_data, apply_custom_ui, render_hero, require_login

st.set_page_config(page_title="Admin Analytics", page_icon="📊", layout="wide")
apply_custom_ui()

if require_login("Admin Analytics", "admin123"):
    render_hero("📊 Hospital Operational Control Panel", "Real-time booking metrics, revenue, and disease incidence analytics across 20 specialties.")
    
    doctors_df, _ = load_clinical_data()
    doctors_df["doctor"] = doctors_df["doctor"].str.strip()
    doc_to_dept = dict(zip(doctors_df["doctor"], doctors_df["dept"].str.strip()))

    conn = sqlite3.connect("hospital_v2.db")
    df_app = pd.read_sql_query("SELECT * FROM appointments", conn)
    df_cons = pd.read_sql_query("SELECT * FROM consultations", conn)
    df_bill = pd.read_sql_query("SELECT * FROM billing", conn)
    conn.close()

    # Top KPI Strip
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Bookings", len(df_app))
    c2.metric("Pending", len(df_app[df_app["status"] == "Pending"]) if not df_app.empty else 0)
    c3.metric("Completed", len(df_app[df_app["status"] == "Completed"]) if not df_app.empty else 0)
    c4.metric("Total Revenue", f"₹{df_bill['grand_total'].sum():,.2f}" if not df_bill.empty else "₹0.00")

    tab_charts, tab_rev, tab_logs = st.tabs(["📈 Clinical & Specialty Analytics", "💰 Revenue Breakdown", "🗂️ Master Records"])

    with tab_charts:
        col_left, col_right = st.columns(2, gap="large")
        with col_left:
            st.subheader("🩺 Top Diagnosed Conditions")
            if not df_cons.empty:
                chart_data = df_cons["diagnosed_disease"].value_counts().head(15).reset_index()
                chart_data.columns = ["Disease", "Cases"]
                fig_dis = px.bar(
                    chart_data,
                    x="Cases",
                    y="Disease",
                    orientation="h",
                    color="Cases",
                    color_continuous_scale="Tealgrn",
                    text_auto=True
                )
                fig_dis.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False, height=420)
                st.plotly_chart(fig_dis, use_container_width=True)
            else:
                st.info("No finalized consultations logged yet.")

        with col_right:
            st.subheader("🏥 Appointments by Specialty")
            if not df_app.empty:
                df_app["Specialty"] = df_app["doctor"].str.strip().map(doc_to_dept).fillna("Other")
                dept_counts = df_app["Specialty"].value_counts().reset_index()
                dept_counts.columns = ["Specialty", "Bookings"]
                fig_dept = px.pie(
                    dept_counts,
                    names="Specialty",
                    values="Bookings",
                    hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_dept.update_traces(textposition="inside", textinfo="percent+label")
                fig_dept.update_layout(height=420)
                st.plotly_chart(fig_dept, use_container_width=True)
            else:
                st.info("No appointments booked yet.")

    with tab_rev:
        if not df_bill.empty:
            r1, r2, r3 = st.columns(3)
            r1.metric("Consultation Fees", f"₹{df_bill['consultation_fee'].sum():,.2f}")
            r2.metric("Pharmacy Sales", f"₹{df_bill['medicine_fee'].sum():,.2f}")
            r3.metric("GST Collected (18%)", f"₹{df_bill['tax_amount'].sum():,.2f}")

            rev_by_doc = (
                df_bill.groupby("doctor_assigned", as_index=False)["grand_total"]
                .sum()
                .sort_values("grand_total", ascending=False)
            )
            rev_by_doc.columns = ["Specialist", "Revenue (₹)"]
            fig_rev = px.bar(
                rev_by_doc,
                x="Specialist",
                y="Revenue (₹)",
                color="Revenue (₹)",
                color_continuous_scale="Blues",
                text_auto=".2s"
            )
            st.plotly_chart(fig_rev, use_container_width=True)
        else:
            st.info("No invoices generated yet.")

    with tab_logs:
        st.subheader("Appointments Log")
        st.dataframe(df_app, use_container_width=True, hide_index=True)
        st.subheader("Consultations Log")
        st.dataframe(df_cons, use_container_width=True, hide_index=True)
        st.subheader("Billing Ledger")
        st.dataframe(df_bill, use_container_width=True, hide_index=True)
