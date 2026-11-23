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
init_db()
init_audit_table(DB_PATH)
seed_portfolio_demo_data(DB_PATH)

@st.cache_resource
def load_ai_engine():
    return ClinicalAIEngine()

ai_engine = load_ai_engine()

# Ensure schema extensions and feedback table exist on hospital_v2.db
conn_init = sqlite3.connect(DB_PATH)
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

# Initialize Razorpay Client using Streamlit Secrets
client = razorpay.Client(auth=(st.secrets["RAZORPAY_KEY_ID"], st.secrets["RAZORPAY_KEY_SECRET"]))

doctors_df, rules_df = load_clinical_data()
doctors_df["doctor"] = doctors_df["doctor"].str.strip()
doctors_df["dept"] = doctors_df["dept"].str.strip()
rules_df["doctor"] = rules_df["doctor"].str.strip()

specialty_cards = doctors_df.to_dict("records")
specialty_doctors = doctors_df["doctor"].tolist()
dept_list = doctors_df["dept"].tolist()
fee_map = dict(zip(doctors_df["doctor"], doctors_df["fee"]))
symptom_variants = rules_df["symptom"].unique().tolist()
symptom_to_doc = dict(zip(rules_df["symptom"], rules_df["doctor"]))

APP_BASE_URL = "https://patient-health-management.streamlit.app/"

# --- HANDLE PAYMENT REDIRECT FROM RAZORPAY ---
query_params = st.query_params
if query_params.get("razorpay_payment_link_status") == "paid":
    appt_id = query_params.get("appt_id")
    if appt_id:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE appointments SET status = 'Confirmed (Paid)' WHERE id = ?", (appt_id,))
        conn.commit()
        conn.close()
        log_audit_event("Payment_Gateway", "Razorpay", "PAYMENT_CONFIRMED", f"Appt #{appt_id}", db_path=DB_PATH)
        st.success(f"🎉 Payment successful! Appointment #{appt_id} is now Confirmed.")
        st.query_params.clear()

# --- HERO TITLE BANNER ---
render_hero(f"🏥 {HOSPITAL_TITLE}", HOSPITAL_SUBTITLE)

# --- TOP INSTITUTIONAL NAVIGATION TABS ---
nav_portal, nav_about, nav_admin, nav_csr, nav_feedback = st.tabs([
    "🩺 Book Appointment & Patient Portal",
    "🏛️ About Us",
    "👔 Administration",
    "🤝 Corporate Social Responsibility (CSR)",
    "💬 Patient Feedback"
])

# ==============================================================================
# TAB 1: MAIN PATIENT PORTAL (20 SPECIALTIES, E-KYC 2FA, AI TRIAGE & BOOKING)
# ==============================================================================
with nav_portal:
    # 1. Unified Real-Time 2FA Identity Verification (Email OTP + Fernet Encryption)
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
                    sym_options = dept_syms + [s for s in symptom_variants if s not in dept_syms
