import streamlit as st
import pandas as pd
import sqlite3
import razorpay
from datetime import datetime

HOSPITAL_TITLE = "Sunrise Multispecialty Hospital & E-Health Portal"
HOSPITAL_SUBTITLE = "20+ Clinical Specialties • Digital Triage • Instant Slot Booking & E-Prescriptions"
DB_PATH = "hospital_v2.db"

st.set_page_config(page_title=HOSPITAL_TITLE, page_icon="🏥", layout="wide")

from utils import (
    ALL_TIME_SLOTS, load_clinical_data, apply_custom_ui,
    render_hero, init_db, build_prescription_pdf, mask_and_hash_aadhaar
)
from security_utils import init_audit_table, encrypt_pii, mask_aadhar, log_audit_event
from aadhaar_auth import is_valid_aadhaar_format, send_real_email_otp, verify_otp
from ai_triage_engine import ClinicalAIEngine
from demo_seeder import seed_portfolio_demo_data

apply_custom_ui()

@st.cache_resource
def initialize_system(db_path: str):
    """Runs once per server boot instead of on every button click."""
    init_db()
    init_audit_table(db_path)
    seed_portfolio_demo_data(db_path)

    conn_init = sqlite3.connect(db_path)
    existing_cols = {row[1] for row in conn_init.execute("PRAGMA table_info(appointments)").fetchall()}
    if "aadhaar_masked" not in existing_cols:
        conn_init.execute("ALTER TABLE appointments ADD COLUMN aadhaar_masked TEXT DEFAULT 'Unverified'")
    if "aadhaar_hash" not in existing_cols:
        conn_init.execute("ALTER TABLE appointments ADD COLUMN aadhaar_hash TEXT DEFAULT ''")
    if "kyc_verified" not in existing_cols:
        conn_init.execute("ALTER TABLE appointments ADD COLUMN kyc_verified INTEGER DEFAULT 0")

    conn_init.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            department TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comments TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        )
    ''')
    conn_init.commit()
    conn_init.close()
    return True

@st.cache_data(ttl=3600)
def get_cached_clinical_data():
    """Caches the 20-specialty doctors and symptom rules DataFrames in memory."""
    d_df, r_df = load_clinical_data()
    d_df["doctor"] = d_df["doctor"].str.strip()
    d_df["dept"] = d_df["dept"].str.strip()
    r_df["doctor"] = r_df["doctor"].str.strip()
    return d_df, r_df

@st.cache_resource
def load_ai_engine():
    return ClinicalAIEngine()

initialize_system(DB_PATH)
doctors_df, rules_df = get_cached_clinical_data()
ai_engine = load_ai_engine()

# Initialize Razorpay Client using Streamlit Secrets
client = razorpay.Client(auth=(st.secrets["RAZORPAY_KEY_ID"], st.secrets["RAZORPAY_KEY_SECRET"]))

specialty_cards = doctors_df.to_dict("records")
specialty_doctors = doctors_df["doctor"].tolist()
dept_list = doctors_df["dept"].tolist()
fee_map = dict(zip(doctors_df["doctor"], doctors_df["fee"]))
symptom_variants = rules_df["symptom"].unique().tolist()
symptom_to_doc = dict(zip(rules_df["symptom"], rules_df["doctor"]))

APP_BASE_URL = "https://patient-health-management.streamlit.app/"

# --- HANDLE & CRYPTOGRAPHICALLY VERIFY RAZORPAY PAYMENT CALLBACK ---
query_params = st.query_params
if "razorpay_payment_id" in query_params and "razorpay_signature" in query_params:
    appt_id = query_params.get("appt_id")
    verify_payload = {
        "payment_link_id": query_params.get("razorpay_payment_link_id", ""),
        "payment_link_reference_id": query_params.get("razorpay_payment_link_reference_id", ""),
        "payment_link_status": query_params.get("razorpay_payment_link_status", ""),
        "razorpay_payment_id": query_params.get("razorpay_payment_id", ""),
        "razorpay_signature": query_params.get("razorpay_signature", ""),
    }
    try:
        client.utility.verify_payment_link_signature(verify_payload)
        if appt_id and verify_payload["payment_link_status"] == "paid":
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE appointments SET status = 'Confirmed (Paid)' WHERE id = ?", (appt_id,))
            conn.commit()
            conn.close()
            log_audit_event(
                "Payment_Gateway",
                verify_payload["razorpay_payment_id"],
                "RAZORPAY_SIGNATURE_VERIFIED",
                f"Appt #{appt_id}",
                db_path=DB_PATH
            )
            st.success(f"🔒 Cryptographically verified payment ({verify_payload['razorpay_payment_id']})! Appointment #{appt_id} is Confirmed.")
    except razorpay.errors.SignatureVerificationError:
        log_audit_event("Security_Alert", "Callback_Spoof_Attempt", "INVALID_RAZORPAY_SIGNATURE", f"Appt #{appt_id}", db_path=DB_PATH)
        st.error("🚨 Security Alert: Invalid Razorpay payment signature detected. Appointment status was not updated.")
    finally:
        st.query_params.clear()

# --- HERO TITLE BANNER ---
render_hero(f"🏥 {HOSPITAL_TITLE}", HOSPITAL_SUBTITLE)

# --- TOP INSTITUTIONAL NAVIGATION TABS ---
nav_portal, nav_about, nav_admin, nav_csr, nav_feedback, nav_contact = st.tabs([
    "🩺 Book Appointment & Patient Portal",
    "🏛️ About Us",
    "👔 Administration",
    "🤝 Corporate Social Responsibility (CSR)",
    "💬 Patient Feedback",
    "📍 Contact & Site Map"
])

# ==============================================================================
# TAB 1: MAIN PATIENT PORTAL (20 SPECIALTIES, E-KYC 2FA, AI TRIAGE & BOOKING)
# ==============================================================================
with nav_portal:
    st.markdown("#### 🪪 Patient Identity Verification (2FA e-KYC & PII Encryption)")
    with st.container(border=True):
        k1, k2, k3 = st.columns([1.4, 1.4, 0.8])
        gov_id_input = k1.text_input(
            "12-Digit Government / Health ID",
            max_chars=14,
            placeholder="e.g. 2345 6789 0123",
            key="kyc_id_input"
        )
        kyc_email_input = k2.text_input(
            "Registered Email (for Real OTP)",
            placeholder="patient@example.com",
            key="kyc_email_input"
        )
        k3.markdown("<br>", unsafe_allow_html=True)
        if k3.button("📩 Send Real OTP", use_container_width=True):
            clean_num = "".join(c for c in gov_id_input if c.isdigit())
            valid, msg = is_valid_aadhaar_format(clean_num, strict_checksum=False)
            if not valid:
                st.error(f"❌ {msg}")
            elif "@" not in kyc_email_input:
                st.error("❌ Please enter a valid email address to receive the OTP.")
            else:
                sent, status_msg = send_real_email_otp(kyc_email_input.strip())
                st.session_state["kyc_pending_num"] = clean_num
                st.session_state["kyc_verified"] = False
                if sent:
                    st.success(f"✅ {status_msg}")
                else:
                    st.info(f"ℹ️ {status_msg}")
                log_audit_event("Patient_Portal", mask_aadhar(clean_num), "REAL_OTP_SENT", kyc_email_input.strip(), db_path=DB_PATH)

        if "active_otp" in st.session_state and not st.session_state.get("kyc_verified"):
            o1, o2 = st.columns([2, 1])
            entered_otp = o1.text_input("Enter 6-Digit OTP received in your email:", max_chars=6, key="kyc_otp_box")
            o2.markdown("<br>", unsafe_allow_html=True)
            if o2.button("✅ Verify & Encrypt ID", use_container_width=True):
                if verify_otp(entered_otp):
                    pending_digits = st.session_state.get("kyc_pending_num", "")
                    masked, ref_hash = mask_and_hash_aadhaar(pending_digits)
                    encrypted_val = encrypt_pii(pending_digits)
                    st.session_state["kyc_verified"] = True
                    st.session_state["kyc_masked"] = masked
                    st.session_state["kyc_hash"] = ref_hash
                    st.session_state["kyc_encrypted"] = encrypted_val
                    st.session_state.pop("kyc_pending_num", None)
                    log_audit_event("Patient_Portal", masked, "2FA_EKYC_VERIFIED", "Fernet_Encrypted", db_path=DB_PATH)
                    st.success(f"🛡️ Identity Verified & Encrypted: `{masked}`")
                else:
                    st.error("❌ Incorrect OTP. Please check your inbox and try again.")

        if st.session_state.get("kyc_verified"):
            st.success(f"🔒 **Active Verified Session:** `{st.session_state['kyc_masked']}` (AES-128 Fernet Protected)")

    st.markdown("---")
    st.subheader(f"🏥 Available Clinical Specialties ({len(specialty_cards)} Departments)")
    if "selected_specialty_doc" not in st.session_state:
        st.session_state["selected_specialty_doc"] = None

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
        st.subheader("🩺 Step 1: AI Triage & Pre-Appointment Symptom Enquiry")
        with st.expander("🤖 AI Symptom-to-Specialty NLP Triage Assistant", expanded=True):
            free_text_symptoms = st.text_input(
                "Describe symptoms in plain English (e.g., 'chest pain and shortness of breath' or 'knee joint swelling'):",
                key="ai_free_text"
            )
            if free_text_symptoms:
                recommendations = ai_engine.recommend_specialty(free_text_symptoms)
                top_spec, confidence, urgency = recommendations[0]
                ac1, ac2, ac3 = st.columns(3)
                ac1.metric("AI Recommended Dept", top_spec)
                ac2.metric("TF-IDF Match Score", f"{confidence}%")
                ac3.metric("Triage Priority", urgency)
                if len(recommendations) > 1:
                    alt_list = ", ".join([f"{s} ({c}%)" for s, c, _ in recommendations[1:]])
                    st.caption(f"Differential departments: {alt_list}")
                log_audit_event("AI_Triage", "Patient_Portal", "AI_SYMPTOM_TRIAGE", f"Dept:{top_spec}", db_path=DB_PATH)

        with st.container(border=True):
            col_age, col_sym = st.columns((1, 2))
            with col_age:
                p_age = st.number_input("Patient Age", min_value=0, max_value=120, value=25)
            with col_sym:
                if st.session_state["selected_specialty_doc"]:
                    dept_syms = rules_df[rules_df["doctor"] == st.session_state["selected_specialty_doc"]]["symptom"].unique().tolist()
                    sym_options = dept_syms + [s for s in symptom_variants if s not in dept_syms]
                else:
                    sym_options = symptom_variants
                selected_symptoms = st.multiselect("Current Symptoms", options=sym_options, placeholder="Select symptoms...")

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
                r_col1, r_col2 = st.columns([3, 1])
                r_col1.success(f"✅ **Selected Department:** **{recommended_doc}**")
                if r_col2.button("Reset", use_container_width=True):
                    st.session_state["selected_specialty_doc"] = None
                    st.rerun()
            elif selected_symptoms:
                recommended_doc = symptom_to_doc.get(next(iter(selected_symptoms)), default_doc)
                st.info(f"💡 **Recommended Specialist:** Based on your symptoms, we suggest **{recommended_doc}**.")
            else:
                recommended_doc = default_doc

        st.markdown("---")
        st.subheader("🗓️ Step 2: Confirm Appointment & Pay Consultation Fee")
        default_idx = specialty_doctors.index(recommended_doc) if recommended_doc in specialty_doctors else 0
        doctor_choice = st.selectbox("Assigned Department Specialist", specialty_doctors, index=default_idx)

        consult_fee = float(fee_map.get(doctor_choice, 500.0))
        st.info(f"💳 **Consultation Fee for {doctor_choice}:** ₹{consult_fee:,.2f}")

        col_date, col_time = st.columns(2)
        with col_date:
            appointment_date = st.date_input("Select Appointment Date", min_value=datetime.today().date())

        conn = sqlite3.connect(DB_PATH)
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

        if appointment_time:
            lead_days = max(0, (appointment_date - datetime.today().date()).days)
            noshow_prob, noshow_label = ai_engine.predict_noshow_risk(p_age, lead_days, appointment_time)
            st.caption(f"📊 **ML Attendance Forecast (Random Forest):** No-Show Probability `{noshow_prob}%` — *{noshow_label}*")

        with st.form("appointment_form", clear_on_submit=True):
            col_n1, col_n2 = st.columns(2)
            with col_n1:
                patient_name = st.text_input("Full Patient Name", placeholder="e.g. Rahul Sharma")
            with col_n2:
                p_gender = st.selectbox("Gender", ["Male", "Female", "Other"])
            p_contact = st.text_input("Registered Contact Number", placeholder="e.g. 9876543210")

            if st.form_submit_button(f"Proceed to Pay ₹{consult_fee:,.0f} & Book", type="primary"):
                if not patient_name.strip() or not p_contact.strip():
                    st.error("Please enter both patient name and contact number.")
                elif not selected_symptoms:
                    st.warning("Please select at least one symptom in Step 1.")
                elif not appointment_time:
                    st.error("Please pick a date with open time slots.")
                else:
                    kyc_verified_flag = 1 if st.session_state.get("kyc_verified") else 0
                    kyc_masked_val = st.session_state.get("kyc_masked", "Unverified")
                    kyc_hash_val = st.session_state.get("kyc_hash", "")

                    triage = f"[Severity: {severity} | Duration: {duration} | Age: {p_age}] Symptoms: {', '.join(selected_symptoms)}. Notes: {additional_details or 'None'}"
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO appointments (patient_name, patient_age, patient_gender, patient_contact, patient_problem, doctor, appt_date, appt_time, status, aadhaar_masked, aadhaar_hash, kyc_verified) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (patient_name.strip(), p_age, p_gender, p_contact.strip(), triage, doctor_choice, str(appointment_date), appointment_time, "Awaiting Payment", kyc_masked_val, kyc_hash_val, kyc_verified_flag)
                    )
                    new_appt_id = cur.lastrowid
                    conn.commit()
                    conn.close()

                    log_audit_event("Patient_Portal", patient_name.strip(), "BOOK_APPOINTMENT", f"Appt#{new_appt_id} ({kyc_masked_val})", db_path=DB_PATH)

                    try:
                        payment_data = {
                            "amount": int(consult_fee * 100),
                            "currency": "INR",
                            "description": f"Consultation with {doctor_choice}",
                            "customer": {
                                "name": patient_name.strip(),
                                "contact": p_contact.strip()
                            },
                            "notify": {"sms": False, "email": False},

                            
