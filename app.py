import streamlit as st
import pandas as pd
import sqlite3
import razorpay
from datetime import datetime
from utils import (
    ALL_TIME_SLOTS, load_clinical_data, apply_custom_ui,
    render_hero, init_db, build_prescription_pdf
)

st.set_page_config(page_title="Patient Portal | Hospital System", page_icon="🏥", layout="wide")
apply_custom_ui()
init_db()

# Initialize Razorpay Client using Streamlit Secrets
client = razorpay.Client(auth=(st.secrets["RAZORPAY_KEY_ID"], st.secrets["RAZORPAY_KEY_SECRET"]))

doctors_df, rules_df = load_clinical_data()
doctors_df["doctor"] = doctors_df["doctor"].str.strip()
doctors_df["dept"] = doctors_df["dept"].str.strip()
rules_df["doctor"] = rules_df["doctor"].str.strip()

specialty_cards = doctors_df.to_dict("records")
specialty_doctors = doctors_df["doctor"].tolist()
fee_map = dict(zip(doctors_df["doctor"], doctors_df["fee"]))
symptom_variants = rules_df["symptom"].unique().tolist()
symptom_to_doc = dict(zip(rules_df["symptom"], rules_df["doctor"]))

APP_BASE_URL = "https://patient-health-management.streamlit.app/"

# --- HANDLE PAYMENT REDIRECT FROM RAZORPAY ---
query_params = st.query_params
if query_params.get("razorpay_payment_link_status") == "paid":
    appt_id = query_params.get("appt_id")
    if appt_id:
        conn = sqlite3.connect("hospital_v2.db")
        conn.execute("UPDATE appointments SET status = 'Confirmed (Paid)' WHERE id = ?", (appt_id,))
        conn.commit()
        conn.close()
        st.success(f"🎉 Payment successful! Appointment #{appt_id} is now Confirmed.")
        st.query_params.clear()

render_hero("🏥 Patient Health Management System", "Select a medical specialty below, complete a symptom check, or download your prescriptions.")

st.subheader(f"🏥 Available Clinical Specialties ({len(specialty_cards)} Departments)")
if "selected_specialty_doc" not in st.session_state:
    st.session_state["selected_specialty_doc"] = None

# FIXED: Dynamically render all 20 specialties in rows of 4 columns
for row_start in range(0, len(specialty_cards), 4):
    cols = st.columns(4, gap="medium")
    for col_idx, spec in enumerate(specialty_cards[row_start:row_start + 4]):
        global_idx = row_start + col_idx
        with cols[col_idx]:
            with st.container(border=True):
                st.markdown(f"#### {spec['icon']} {spec['dept']}")
                st.caption(f"**{spec['doctor']}** • Fee: ₹{spec.get('fee', 500)}")
                st.write(f"<small>{spec['desc']}</small>", unsafe_allow_html=True)
                if st.button(f"Select {spec['dept']}", key=f"btn_spec_{global_idx}", use_container_width=True):
                    st.session_state["selected_specialty_doc"] = spec["doctor"]

st.markdown("---")
col_left, col_right = st.columns((1.15, 1), gap="large")

with col_left:
    st.subheader("🩺 Step 1: Pre-Appointment Symptom Enquiry")
    with st.container(border=True):
        col_age, col_sym = st.columns((1, 2))
        with col_age:
            p_age = st.number_input("Patient Age", min_value=0, max_value=120, value=25)
        with
