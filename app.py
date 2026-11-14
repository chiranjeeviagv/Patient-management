import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from utils import (
    ALL_TIME_SLOTS, load_clinical_data, apply_custom_ui,
    render_hero, init_db, build_prescription_pdf
)

st.set_page_config(page_title="Patient Portal | Hospital System", page_icon="🏥", layout="wide")
apply_custom_ui()
init_db()

doctors_df, rules_df = load_clinical_data()
specialty_cards = doctors_df.to_dict("records")
specialty_doctors = doctors_df["doctor"].tolist()
symptom_variants = rules_df["symptom"].unique().tolist()
symptom_to_doc = dict(zip(rules_df["symptom"], rules_df["doctor"]))

render_hero("🏥 Patient Health Management System", "Select a medical specialty below, complete a symptom check, or download your prescriptions.")

st.subheader("🏥 Available Clinical Specialties")
if "selected_specialty_doc" not in st.session_state:
    st.session_state["selected_specialty_doc"] = None

row1_cols = st.columns(4, gap="medium")
row2_cols = st.columns(4, gap="medium")
all_cols = row1_cols + row2_cols

for idx, spec in enumerate(specialty_cards):
    if idx < len(all_cols):
        with all_cols[idx]:
            with st.container(border=True):
                st.markdown(f"#### {spec['icon']} {spec['dept']}")
                st.caption(f"**{spec['doctor']}**")
                st.write(f"<small>{spec['desc']}</small>", unsafe_allow_html=True)
                if st.button(f"Select {spec['dept']}", key=f"btn_spec_{idx}", use_container_width=True):
                    st.session_state["selected_specialty_doc"] = spec["doctor"]

st.markdown("---")
col_left, col_right = st.columns((1.15, 1), gap="large")

with col_left:
    st.subheader("🩺 Step 1: Pre-Appointment Symptom Enquiry")
    with st.container(border=True):
        col_age, col_sym = st.columns((1, 2))
        with col_age:
            p_age = st.number_input("Patient Age", min_value=0, max_value=120, value=25)
        with col_sym:
            selected_symptoms = st.multiselect("Current Symptoms", options=symptom_variants, placeholder="Select symptoms...")

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            duration = st.selectbox("Symptom Duration", ["Less than 24 hours", "1 - 3 days", "4 - 7 days", "More than a week"])
        with col_s2:
            severity = st.select_slider("Pain / Discomfort Severity", options=["Mild", "Moderate", "Severe"])

        additional_details = st.text_input("Additional Notes or Allergies (Optional)", placeholder="e.g., Allergic to penicillin...")

        default_doc = next(iter(specialty_doctors))
        if p_age < 16:
            recommended_doc = "Dr. Pradip (Pediatrics)"
            st.info(f"🧸 **Pediatric Routing:** Patients under 16 are automatically routed to **{recommended_doc}**.")
        elif st.session_state["selected_specialty_doc"]:
            recommended_doc = st.session_state["selected_specialty_doc"]
            st.success(f"✅ **Selected Department:** You chose **{recommended_doc}**.")
        elif selected_symptoms:
            recommended_doc = symptom_to_doc.get(next(iter(selected_symptoms)), default_doc)
            st.info(f"💡 **Recommended Specialist:** Based on your symptoms, we suggest **{recommended_doc}**.")
        else:
            recommended_doc = default_doc

    st.markdown("---")
    st.subheader("🗓️ Step 2: Confirm Appointment Details")
    default_idx = specialty_doctors.index(recommended_doc) if recommended_doc in specialty_doctors else 0
    doctor_choice = st.selectbox("Assigned Department Specialist", specialty_doctors, index=default_idx)

    col_date, col_time = st.columns(2)
    with col_date:
        appointment_date = st.date_input("Select Appointment Date", min_value=datetime.today().date())

    conn = sqlite3.connect("hospital_v2.db")
    booked_df = pd.read_sql_query(
        "SELECT appt_time FROM appointments WHERE doctor = ? AND appt_date = ? AND status != 'Cancelled'",
        conn, params=(doctor_choice, str(appointment_date))
    )
    conn.close()
    available_slots = [s for s in ALL_TIME_SLOTS if s not in set(booked_df["appt_time"].tolist())]

    with col_time:
        appointment_time = st.selectbox("Available Time Slot", available_slots) if available_slots else None
        if not available_slots:
            st.warning("No slots left on this date.")

    with st.form("appointment_form", clear_on_submit=True):
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            patient_name = st.text_input("Full Patient Name", placeholder="e.g. Rahul Sharma")
        with col_n2:
            p_gender = st.selectbox("Gender", ["Male", "Female", "Other"])
        p_contact = st.text_input("Registered Contact Number", placeholder="e.g. 9876543210")

        if st.form_submit_button("Confirm Appointment Slot", type="primary"):
            if not patient_name.strip() or not p_contact.strip():
                st.error("Please enter both patient name and contact number.")
            elif not selected_symptoms:
                st.warning("Please select at least one symptom in Step 1.")
            elif not appointment_time:
                st.error("Please pick a date with open time slots.")
            else:
                triage = f"[Severity: {severity} | Duration: {duration} | Age: {p_age}] Symptoms: {', '.join(selected_symptoms)}. Notes: {additional_details or 'None'}"
                conn = sqlite3.connect("hospital_v2.db")
                conn.execute(
                    "INSERT INTO appointments (patient_name, patient_age, patient_gender, patient_contact, patient_problem, doctor, appt_date, appt_time, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (patient_name.strip(), p_age, p_gender, p_contact.strip(), triage, doctor_choice, str(appointment_date), appointment_time, "Pending")
                )
                conn.commit()
                conn.close()
                st.session_state["selected_specialty_doc"] = None
                st.success(f"🎉 Appointment booked with **{doctor_choice}** on {appointment_date} at {appointment_time}!")
                st.rerun()

with col_right:
    tab_req, tab_rx = st.tabs(["📋 Active Requests", "📄 Download Prescriptions & Notes"])
    with tab_req:
        conn = sqlite3.connect("hospital_v2.db")
        df = pd.read_sql_query("SELECT id AS ID, patient_name AS [Patient Name], doctor AS Doctor, appt_date AS [Date], appt_time AS [Slot], status AS Status FROM appointments ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_rx:
        st.caption("Enter your full name and registered phone number to download your prescription PDF.")
        v_name = st.text_input("Patient Full Name:", key="v_name")
        v_phone = st.text_input("Registered Contact Number:", key="v_phone")
        if v_name.strip() and v_phone.strip():
            conn = sqlite3.connect("hospital_v2.db")
            appt_check = pd.read_sql_query("SELECT patient_contact FROM appointments WHERE LOWER(TRIM(patient_name)) = LOWER(TRIM(?))", conn, params=(v_name,))
            digits_in = "".join(c for c in v_phone if c.isdigit())
            digits_db = {"".join(c for c in str(x) if c.isdigit()) for x in appt_check["patient_contact"].dropna()}
            if (digits_in in digits_db and digits_in != "") or (not appt_check.empty and digits_db == {""} and v_phone.strip() == "0000"):
                rx_df = pd.read_sql_query("SELECT * FROM consultations WHERE LOWER(TRIM(patient_name)) = LOWER(TRIM(?)) ORDER BY id DESC", conn, params=(v_name,))
                conn.close()
                for rec in rx_df.to_dict("records"):
                    with st.container(border=True):
                        st.markdown(f"**Date:** {rec['consultation_date']} | **Doctor:** {rec['doctor']}")
                        st.markdown(f"**Diagnosis:** {rec['diagnosed_disease']}")
                        st.info(f"💊 **Rx:** {rec['prescription']}")
                        st.caption(f"📝 **Notes:** {rec['notes'] or 'None'}")
                        pdf_bytes = build_prescription_pdf(rec["patient_name"], rec["doctor"], rec["diagnosed_disease"], rec["symptoms"], rec["prescription"], rec["notes"])
                        st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"Rx_{rec['id']}.pdf", mime="application/pdf", key=f"dl_{rec['id']}")
            else:
                conn.close()
                st.error("❌ Verification failed. Check your name and phone number.")
