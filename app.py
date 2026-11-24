import sqlite3
import razorpay
import streamlit as st

HOSPITAL_TITLE = "Govardhan Multispecialty Hospital & E-Health Portal"
HOSPITAL_SUBTITLE = "20+ Clinical Specialties • Online & Offline OPD • Surgical IPD & OT Care"
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
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(appointments)").fetchall()}
    for col, ddl in [
        ("aadhaar_masked", "TEXT DEFAULT 'Unverified'"),
        ("aadhaar_hash", "TEXT DEFAULT ''"),
        ("kyc_verified", "INTEGER DEFAULT 0"),
        ("care_mode", "TEXT DEFAULT 'Offline OPD Consultation'"),
        ("service_package", "TEXT DEFAULT 'Standard OPD'")
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE appointments ADD COLUMN {col} {ddl}")
    conn.commit()
    conn.close()
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

# --- CRYPTOGRAPHICALLY VERIFY RAZORPAY PAYMENT CALLBACK ---
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
            log_audit_event("Payment_Gateway", verify_payload["razorpay_payment_id"], "RAZORPAY_SIGNATURE_VERIFIED", f"Appt #{appt_id}", db_path=DB_PATH)
            st.success(f"🔒 Verified payment ({verify_payload['razorpay_payment_id']})! Booking #{appt_id} is Confirmed.")
    except razorpay.errors.SignatureVerificationError:
        log_audit_event("Security_Alert", "Callback_Spoof_Attempt", "INVALID_RAZORPAY_SIGNATURE", f"Appt #{appt_id}", db_path=DB_PATH)
        st.error("🚨 Security Alert: Invalid Razorpay signature detected.")
    finally:
        st.query_params.clear()

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
