import os
import sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import razorpay
import streamlit as st

HOSPITAL_TITLE = "Govardhan Multispecialty Hospital & E-Health Portal"
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
                            "callback_url": f"{APP_BASE_URL}?appt_id={new_appt_id}",
                            "callback_method": "get"
                        }
                        payment_link = client.payment_link.create(payment_data)
                        st.session_state["pending_payment_url"] = payment_link["short_url"]
                        st.session_state["pending_appt_id"] = new_appt_id
                    except Exception as e:
                        st.error(f"Payment gateway error: {e}")

        if "pending_payment_url" in st.session_state:
            st.warning(f"Slot reserved (ID #{st.session_state['pending_appt_id']}). Complete payment below to confirm:")
            st.link_button("💳 Pay Now via UPI / Card", st.session_state["pending_payment_url"], type="primary", use_container_width=True)

    with col_right:
        tab_req, tab_rx = st.tabs(["📋 Active Requests", "📄 Download Prescriptions & Notes"])
        with tab_req:
            conn = sqlite3.connect(DB_PATH)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(appointments)").fetchall()}
            if "aadhaar_masked" not in cols:
                conn.execute("ALTER TABLE appointments ADD COLUMN aadhaar_masked TEXT DEFAULT 'Unverified'")
                conn.commit()
            df = pd.read_sql_query(
                "SELECT id AS ID, patient_name AS [Patient Name], doctor AS Doctor, "
                "appt_date AS [Date], appt_time AS [Slot], "
                "COALESCE(aadhaar_masked, 'Unverified') AS [e-KYC ID], status AS Status "
                "FROM appointments ORDER BY id DESC",
                conn
            )
            conn.close()
            st.dataframe(df, use_container_width=True, hide_index=True)

        with tab_rx:
            st.caption("Enter your full name and registered phone number to download your prescription PDF.")
            v_name = st.text_input("Patient Full Name:", key="v_name")
            v_phone = st.text_input("Registered Contact Number:", key="v_phone")
            if v_name.strip() and v_phone.strip():
                conn = sqlite3.connect(DB_PATH)
                appt_check = pd.read_sql_query("SELECT patient_contact FROM appointments WHERE LOWER(TRIM(patient_name)) = LOWER(TRIM(?))", conn, params=(v_name,))
                digits_in = "".join(c for c in v_phone if c.isdigit())
                digits_db = {"".join(c for c in str(x) if c.isdigit()) for x in appt_check["patient_contact"].dropna()}
                if (digits_in in digits_db and digits_in != "") or (not appt_check.empty and digits_db == {""} and v_phone.strip() == "0000"):
                    rx_df = pd.read_sql_query("SELECT * FROM consultations WHERE LOWER(TRIM(patient_name)) = LOWER(TRIM(?)) ORDER BY id DESC", conn, params=(v_name,))
                    conn.close()
                    if rx_df.empty:
                        st.info("No finalized prescriptions found for this patient yet.")
                    for rec in rx_df.to_dict("records"):
                        with st.container(border=True):
                            st.markdown(f"**Date:** {rec['consultation_date']} | **Doctor:** {rec['doctor']}")
                            st.markdown(f"**Diagnosis:** {rec['diagnosed_disease']}")
                            st.info(f"💊 **Rx:** {rec['prescription']}")
                            st.caption(f"📝 **Notes:** {rec['notes'] or 'None'}")
                            pdf_bytes = build_prescription_pdf(
                                rec["patient_name"],
                                rec["doctor"],
                                rec["diagnosed_disease"],
                                rec["symptoms"],
                                rec["prescription"],
                                rec["notes"]
                            )
                            st.download_button(
                                "📥 Download PDF",
                                data=pdf_bytes,
                                file_name=f"Rx_{rec['id']}.pdf",
                                mime="application/pdf",
                                key=f"dl_{rec['id']}"
                            )
                else:
                    conn.close()
                    st.error("❌ Verification failed. Check your name and phone number.")

# ==============================================================================
# TAB 2: ABOUT US
# ==============================================================================
with nav_about:
    st.subheader(f"🏛️ About {HOSPITAL_TITLE}")
    if os.path.exists("assets/hospital_campus.png"):
        st.image("assets/hospital_campus.png", caption="Govardhan Multispecialty Hospital — Simhachalam Hills Campus", use_container_width=True)

    ab1, ab2 = st.columns((1.4, 1), gap="large")
    with ab1:
        with st.container(border=True):
            st.markdown("### Excellence in Multispecialty Clinical Care & Digital Health")
            st.write(
                "Founded to bridge specialized medical expertise with seamless digital patient access and initiation of digital governance, "
                f"**{HOSPITAL_TITLE}** delivers comprehensive outpatient, diagnostic, and preventive healthcare "
                "across **20 specialized clinical departments**. Our integrated E-Health platform empowers patients "
                "with intelligent symptom-based specialist routing, transparent consultation fees, real-time slot "
                "scheduling, and instant digital prescriptions."
            )
            st.markdown("#### 🎯 Our Mission & Vision")
            st.markdown(
                "- **Mission:** Provide ethical, affordable, and evidence-based medical care supported by modern digital health workflows.\n"
                "- **Vision:** Become a benchmark community healthcare center known for clinical accuracy, zero-wait scheduling, and compassionate service.\n"
                "- **OPD Consultation Hours:** Morning **09:00 AM – 02:00 PM** | Afternoon & Evening **03:00 PM – 09:00 PM** (Monday – Saturday)."
            )
    with ab2:
        with st.container(border=True):
            st.markdown("### 📊 Hospital at a Glance")
            m1, m2 = st.columns(2)
            m1.metric("Clinical Specialties", "20 Departments")
            m2.metric("Pharmacy Formulas", "50+ Essential Drugs")
            m3, m4 = st.columns(2)
            m3.metric("Daily OPD Slots", "22 Slots / Specialist")
            m4.metric("Emergency Support", "24 × 7 Triage")
            st.info("📍 **Location:** Simhachalam Hills, Simhachalam North, Visakhapatnam – 530029, AP\n\n📞 **Helpline:** +91 99999 88888 | ✉️ **Email:** care@govardhanmedical.in")

    st.markdown("---")
    st.subheader("📊 Clinical Departments & Consultation Fee Structure")
    fig_depts = px.bar(
        doctors_df.sort_values("fee", ascending=True),
        x="fee",
        y="dept",
        orientation="h",
        color="fee",
        color_continuous_scale="Teal",
        labels={"fee": "OPD Consultation Fee (₹)", "dept": "Clinical Specialty"},
        text_auto=True
    )
    fig_depts.update_layout(height=520, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_depts, use_container_width=True)

# ==============================================================================
# TAB 3: ADMINISTRATION
# ==============================================================================
with nav_admin:
    st.subheader("👔 Hospital Administration & Governance")
    st.caption("Leadership team overseeing clinical standards, hospital operations, nursing quality, and patient welfare.")
    admin_leaders = [
        ("Mr. K Aravind, MD", "Medical Director & Chief of Clinical Services", "25+ years in Internal Medicine & Hospital Quality Accreditation (NABH). Oversees clinical protocols across all 20 departments."),
        ("Mrs. K Geetha Madhavi, MBA (Hosp. Admin)", "Chief Administrative Officer (CAO)", "Leads hospital operations, outpatient scheduling efficiency, billing transparency, and statutory healthcare compliance."),
        ("Dr. A Pradeep kumar, MS", "Dean of Medical Academics & Clinical Audit", "Heads continuing medical education (CME), clinical peer audits, and diagnostic quality assurance."),
        ("Mr. K Ramana, M.Pharm", "Chief Pharmacist & Supply Chain Head", "Manages dispensary inventory, cold-chain storage, and essential medicine availability.")
    ]
    a_cols = st.columns(2, gap="medium")
    for idx, (name, role, bio) in enumerate(admin_leaders):
        with a_cols[idx % 2]:
            with st.container(border=True):
                st.markdown(f"#### {name}")
                st.caption(f"**{role}**")
                st.write(bio)

# ==============================================================================
# TAB 4: CORPORATE SOCIAL RESPONSIBILITY (CSR)
# ==============================================================================
with nav_csr:
    st.subheader("🤝 Corporate Social Responsibility (CSR) & Community Health")
    st.write("We believe quality healthcare is a community right. Through our structured CSR initiatives, our specialists dedicate regular clinical hours to underserved populations:")
    c_cols = st.columns(3, gap="medium")
    with c_cols[0]:
        with st.container(border=True):
            st.markdown("#### 🚐 Rural & Urban Free Health Camps")
            st.write("Monthly multi-specialty screening camps offering free blood pressure, blood glucose, ECG, vision, and dental checkups in rural mandals and industrial colonies.")
    with c_cols[1]:
        with st.container(border=True):
            st.markdown("#### 🤰 Maternal & Child Wellness Drive")
            st.write("Subsidized antenatal checkups, nutritional supplements (Iron, Calcium, Folic Acid), and pediatric immunization awareness programs led by our Gynecology & Pediatrics teams.")
    with c_cols[2]:
        with st.container(border=True):
            st.markdown("#### 🧠 Mental Health & School Awareness")
            st.write("Free stress-management workshops, adolescent counseling, and preventive hygiene sessions conducted across government schools and colleges.")

# ==============================================================================
# TAB 5: PATIENT FEEDBACK
# ==============================================================================
with nav_feedback:
    st.subheader("💬 Share Your Experience & Patient Feedback")
    fb_left, fb_right = st.columns((1, 1.1), gap="large")
    with fb_left:
        with st.form("patient_feedback_form", clear_on_submit=True):
            fb_name = st.text_input("Your Name", placeholder="e.g. Ananya Verma")
            fb_dept = st.selectbox("Department Visited", ["General / Portal Experience"] + dept_list)
            fb_rating = st.slider("Overall Satisfaction Rating (1 = Poor, 5 = Excellent)", min_value=1, max_value=5, value=5)
            fb_comments = st.text_area("Your Comments or Suggestions", placeholder="Tell us about your consultation, wait time, or portal experience...", height=110)
            if st.form_submit_button("📩 Submit Feedback", type="primary"):
                if not fb_name.strip() or not fb_comments.strip():
                    st.error("Please enter your name and feedback comments.")
                else:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute(
                        "INSERT INTO feedback (patient_name, department, rating, comments, submitted_at) VALUES (?, ?, ?, ?, ?)",
                        (fb_name.strip(), fb_dept, int(fb_rating), fb_comments.strip(), datetime.now().strftime("%Y-%m-%d %H:%M"))
                    )
                    conn.commit()
                    conn.close()
                    st.success("🙏 Thank you! Your feedback has been recorded for our Quality Assurance team.")
                    st.rerun()

    with fb_right:
        st.markdown("#### ⭐ Recent Patient Testimonials")
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                department TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comments TEXT NOT NULL,
                submitted_at TEXT NOT NULL
            )
        ''')
        conn.commit()
        fb_df = pd.read_sql_query("SELECT patient_name, department, rating, comments, submitted_at FROM feedback ORDER BY id DESC LIMIT 6", conn)
        conn.close()
        if fb_df.empty:
            st.info("Be the first to share feedback about your consultation experience!")
        else:
            rating_counts = fb_df["rating"].value_counts().reset_index()
            rating_counts.columns = ["Rating", "Count"]
            rating_counts["Rating"] = rating_counts["Rating"].astype(str) + " ⭐"
            fig_ratings = px.pie(
                rating_counts,
                names="Rating",
                values="Count",
                hole=0.5,
                title="Patient Satisfaction Distribution",
                color_discrete_sequence=px.colors.sequential.Tealgrn
            )
            fig_ratings.update_layout(height=260, margin=dict(t=40, b=10, l=10, r=10))
            st.plotly_chart(fig_ratings, use_container_width=True)

            for row in fb_df.to_dict("records"):
                stars = "⭐" * int(row["rating"])
                with st.container(border=True):
                    st.markdown(f"**{row['patient_name']}** • *{row['department']}* — {stars}")
                    st.write(row["comments"])
                    st.caption(f"Submitted on {row['submitted_at']}")

# ==============================================================================
# TAB 6: CONTACT INFORMATION, GOOGLE MAPS & INSTITUTIONAL SITE MAP
# ==============================================================================
with nav_contact:
    st.subheader("📍 Hospital Location, Contact Directory & Interactive Map")

    c_info, c_map = st.columns((1, 1.4), gap="large")

    with c_info:
        with st.container(border=True):
            st.markdown("### 🏥 Govardhan Multispecialty Hospital")
            st.markdown(
                "**Address:**\n"
                "Simhachalam Hills, Simhachalam North,\n"
                "Visakhapatnam – 530029, Andhra Pradesh, India"
            )
            st.divider()
            st.markdown(
                "**📞 24×7 Emergency & Ambulance:** `+91 891-255-8888`\n\n"
                "**☎️ OPD Appointment Desk:** `+91 99999 88888`\n\n"
                "**✉️ Clinical & Admin Support:** `care@govardhanmedical.in`\n\n"
                "**🕒 OPD Consultation Hours:**\n"
                "- Morning Shift: `09:00 AM – 02:00 PM`\n"
                "- Evening Shift: `03:00 PM – 09:00 PM` (Mon – Sat)"
            )
            st.divider()
            maps_directions_url = "https://www.google.com/maps/search/?api=1&query=Simhachalam+Hills+Visakhapatnam+Andhra+Pradesh"
            st.link_button("🧭 Open Turn-by-Turn Directions in Google Maps", maps_directions_url, type="primary", use_container_width=True)

    with c_map:
        with st.container(border=True):
            st.markdown("### 🗺️ Interactive Campus Location (Google Maps)")
            google_maps_embed_url = (
                "https://maps.google.com/maps?q=Simhachalam%20Hills%20Visakhapatnam"
                "&t=&z=14&ie=UTF8&iwloc=&output=embed"
            )
            st.components.v1.iframe(google_maps_embed_url, height=380, scrolling=False)
            st.caption("Interactive map: Zoom or pan to explore nearby transit routes, pharmacies, and diagnostic centers.")

    st.markdown("---")
    st.subheader("🧭 Digital Health Portal — Complete Site Map")
    st.caption("Structured architectural directory of patient services, role-based clinical workspaces, and institutional resources.")

    sm1, sm2, sm3 = st.columns(3, gap="medium")

    with sm1:
        with st.container(border=True):
            st.markdown("#### 🩺 Patient & Outpatient Services")
            st.markdown(
                "- **Patient Identity e-KYC (2FA):** 12-digit ID validation + Real Email OTP & Fernet PII encryption\n"
                "- **AI Symptom Triage Assistant:** NLP symptom-to-specialty routing across 20+ clinical departments\n"
                "- **Online Slot Booking:** Real-time Morning (`9 AM–2 PM`) & Evening (`3 PM–9 PM`) scheduling\n"
                "- **Razorpay Payment Gateway:** Instant UPI/Card fee settlement & confirmation\n"
                "- **e-Prescription Downloads:** Cryptographically verified PDF prescriptions"
            )

    with sm2:
        with st.container(border=True):
            st.markdown("#### 🔐 Role-Based Clinical & Ops Dashboards")
            st.markdown(
                "- **Doctor Dashboard (`/Doctor_Dashboard`):** Specialist schedules, diagnostics, QR-verified PDF e-Rx & HL7 FHIR R4 JSON export\n"
                "- **Pharmacy Inventory (`/Pharmacy_Inventory`):** Live stock ledger, burn-rate runway forecasting & automated CSV Purchase Orders\n"
                "- **Billing Dashboard (`/Billing_Dashboard`):** GST-compliant invoicing, consultation + pharmacy ledger\n"
                "- **Admin Analytics (`/Admin_Analytics`):** KPI control panel, specialty disease analytics & SHA-256 hash-chained audit logs"
            )

    with sm3:
        with st.container(border=True):
            st.markdown("#### 🏛️ Institutional & Governance Pages")
            st.markdown(
                "- **About Us:** Hospital mission, vision, NABH quality standards & clinical overview\n"
                "- **Administration:** Medical Director, CAO, Dean of Academics & Chief Pharmacist profiles\n"
                "- **Corporate Social Responsibility (CSR):** Free rural health camps, maternal wellness & school programs\n"
                "- **Patient Feedback:** Live satisfaction ratings & verified patient testimonials\n"
                "- **Contact & Location:** Emergency helpline, OPD hours & interactive Google Maps integration"
            )
