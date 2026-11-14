import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from utils import load_clinical_data, apply_custom_ui, render_hero, require_login, build_invoice_pdf

st.set_page_config(page_title="Billing Dashboard", page_icon="💰", layout="wide")
apply_custom_ui()

if require_login("Billing Dashboard", "billing123"):
    render_hero("💰 Patient Checkouts & Invoice Generator", "Process completed consultations with itemized pharmacy charges and 18% GST.")
    doctors_df, _ = load_clinical_data()
    fee_map = dict(zip(doctors_df["doctor"], doctors_df["fee"]))

    conn = sqlite3.connect("hospital_v2.db")
    unbilled_df = pd.read_sql_query("SELECT DISTINCT patient_name, doctor FROM appointments WHERE status = 'Completed' AND patient_name NOT IN (SELECT patient_name FROM billing)", conn)
    conn.close()

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.subheader("💳 Process Pending Checkout")
        if not unbilled_df.empty:
            unbilled_df["label"] = unbilled_df["patient_name"] + " — " + unbilled_df["doctor"]
            selected = st.selectbox("Select Patient:", unbilled_df["label"].tolist())
            patient, doctor = selected.split(" — ", 1)

            conn = sqlite3.connect("hospital_v2.db")
            med_row = conn.execute("SELECT medicine_dispensed, medicine_cost FROM consultations WHERE patient_name = ? ORDER BY id DESC LIMIT 1", (patient,)).fetchone()
            conn.close()

            med_name, med_fee = (med_row, float(med_row)) if med_row else ("None", 0.0)
            base_fee = float(fee_map.get(doctor, 500.0))
            tax = round((base_fee + med_fee) * 0.18, 2)
            total = round(base_fee + med_fee + tax, 2)

            st.info(f"**Dispensed Medicine:** {med_name}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Consult Fee", f"₹{base_fee:,.2f}")
            m2.metric("Medicine", f"₹{med_fee:,.2f}")
            m3.metric("Total (+18% GST)", f"₹{total:,.2f}")

            pay_method = st.selectbox("Payment Method:", ["Cash", "UPI / QR", "Card", "Insurance"])
            if st.button("🚀 Issue Invoice", type="primary"):
                conn = sqlite3.connect("hospital_v2.db")
                cur = conn.cursor()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                cur.execute("INSERT INTO billing (patient_name, doctor_assigned, consultation_fee, medicine_fee, tax_amount, grand_total, payment_status, billing_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (patient, doctor, base_fee, med_fee, tax, total, f"Paid via {pay_method}", now_str))
                inv_id = cur.lastrowid
                conn.commit()
                conn.close()
                st.session_state["last_inv"] = (inv_id, patient, doctor, base_fee, med_fee, med_name, tax, total, f"Paid via {pay_method}", now_str)
                st.rerun()
        else:
            st.info("✨ No pending unbilled checkouts.")

        if "last_inv" in st.session_state:
            pdf_bytes = build_invoice_pdf(*st.session_state["last_inv"])
            st.download_button("📥 Download Invoice PDF", data=pdf_bytes, file_name=f"Invoice_{st.session_state['last_inv']}.pdf", mime="application/pdf")

    with col2:
        st.subheader("📜 Billing History")
        conn = sqlite3.connect("hospital_v2.db")
        hist = pd.read_sql_query("SELECT id AS ID, patient_name AS Patient, grand_total AS [Total (₹)], payment_status AS Status, billing_date AS Date FROM billing ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(hist, use_container_width=True, hide_index=True)
