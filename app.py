import sqlite3
import razorpay
import streamlit as st

HOSPITAL_TITLE = "Govardhan Multispecialty Hospital & E-Health Portal"
HOSPITAL_SUBTITLE = "30 Clinical Specialties • Online & Offline OPD • Surgical IPD & OT Care"
DB_PATH = "hospital_v2.db"

st.set_page_config(page_title=HOSPITAL_TITLE, page_icon="🏥", layout="wide")

from utils import load_clinical_data, apply_custom_ui, render_hero, init_db
from security_utils import init_audit_table, log_audit_event
from ai_triage_engine import ClinicalAIEngine
from demo_seeder import seed_portfolio_demo_data
from tabs import (
    portal_booking, about_hospital, staff_hierarchy,
    csr_community, patient_feedback, contact_sitemap
)

apply_custom_ui()

@st.cache_resource
def initialize_system(db_path: str):
    init_db()
    init_audit_table(db_path)
    seed_portfolio_demo_data(db_path)
    with sqlite3.connect(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(appointments)").fetchall()}
        for col, ddl in [
            ("aadhaar_masked", "TEXT DEFAULT 'Unverified'"),
            ("aadhaar_hash", "TEXT DEFAULT ''"),
            ("kyc_verified", "INTEGER DEFAULT 0"),
            ("care_mode", "TEXT DEFAULT 'Offline OPD Consultation'"),
            ("service_package", "TEXT DEFAULT 'Standard OPD'"),
            ("patient_email", "TEXT DEFAULT ''"),
            ("preferred_tele_time", "TEXT DEFAULT ''"),
            ("tele_room_link", "TEXT DEFAULT ''"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE appointments ADD COLUMN {col} {ddl}")
        conn.commit()
    return True

@st.cache_data(ttl=3600)
def get_cached_clinical_data():
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
client = razorpay.Client(auth=(st.secrets["RAZORPAY_KEY_ID"], st.secrets["RAZORPAY_KEY_SECRET"]))

query_params = st.query_params

# --- HANDLE UNIQUE TELE-CONSULTATION ROOM LINK (?tele_room=GMH-...) ---
if "tele_room" in query_params:
    room_code = query_params.get("tele_room")
    st.info(f"📹 **Welcome to Govardhan Tele-Health Room (`{room_code}`)** — Please allow Camera and Microphone permissions below to connect with your specialist.")
    portal_booking._render_av_permission_widget(f"https://meet.govardhanmedical.in/{room_code}")

# --- CRYPTOGRAPHICALLY VERIFY RAZORPAY PAYMENT CALLBACK ---
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
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE appointments SET status = 'Confirmed (Paid)' WHERE id = ?", (appt_id,))
                row = conn.execute("SELECT care_mode FROM appointments WHERE id = ?", (appt_id,)).fetchone()
                conn.commit()
            log_audit_event("Payment_Gateway", verify_payload["razorpay_payment_id"], "RAZORPAY_SIGNATURE_VERIFIED", f"Appt #{appt_id}", db_path=DB_PATH)
            if row and "Online" in row[0]:
                st.session_state["confirmed_tele_appt_id"] = int(appt_id)
            else:
                st.session_state["payment_flash_msg"] = ("success", f"🔒 Verified payment ({verify_payload['razorpay_payment_id']})! Booking #{appt_id} is Confirmed.")
    except razorpay.errors.SignatureVerificationError:
        log_audit_event("Security_Alert", "Callback_Spoof_Attempt", "INVALID_RAZORPAY_SIGNATURE", f"Appt #{appt_id}", db_path=DB_PATH)
        st.session_state["payment_flash_msg"] = ("error", "🚨 Security Alert: Invalid Razorpay signature detected.")
    finally:
        st.query_params.clear()

# Render persisted payment confirmation message after query_params rerun
if "payment_flash_msg" in st.session_state:
    level, msg_text = st.session_state.pop("payment_flash_msg")
    if level == "success":
        st.success(msg_text)
    else:
        st.error(msg_text)

render_hero(f"🏥 {HOSPITAL_TITLE}", HOSPITAL_SUBTITLE)

nav_portal, nav_about, nav_admin, nav_csr, nav_feedback, nav_contact = st.tabs([
    "🩺 Book Care (Online / OPD / Surgery)",
    "🏛️ About Us & Surgical Facilities",
    "👔 Hospital Staff & Hierarchy",
    "🤝 Corporate Social Responsibility (CSR)",
    "💬 Patient Feedback",
    "📍 Contact & Site Map"
])

with nav_portal:
    portal_booking.render(DB_PATH, doctors_df, rules_df, ai_engine, client)
with nav_about:
    about_hospital.render(HOSPITAL_TITLE, doctors_df)
with nav_admin:
    staff_hierarchy.render()
with nav_csr:
    csr_community.render()
with nav_feedback:
    patient_feedback.render(DB_PATH, doctors_df["dept"].tolist())
with nav_contact:
    contact_sitemap.render()
