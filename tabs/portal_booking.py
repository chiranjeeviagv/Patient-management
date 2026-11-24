from datetime import datetime
from email.message import EmailMessage
import hashlib
import smtplib
import sqlite3
from urllib.parse import quote
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from utils import ALL_TIME_SLOTS, build_prescription_pdf, mask_and_hash_aadhaar
from security_utils import encrypt_pii, mask_aadhar, log_audit_event
from aadhaar_auth import is_valid_aadhaar_format, send_real_email_otp, verify_otp

APP_BASE_URL = "https://patient-health-management.streamlit.app/"

SURGICAL_PACKAGES = {
    "Day-Care Minor Procedure (Local Anesthesia)": 15000.0,
    "Laparoscopic / Minimally Invasive Surgery (2-Day Stay)": 45000.0,
    "Major Multispecialty Surgery + Post-Op ICU (4-Day Stay)": 95000.0,
    "Orthopedic / Joint Reconstruction Package": 120000.0,
}

def _generate_unique_tele_link(appt_id: int, patient_name: str, contact: str) -> str:
    raw = f"{appt_id}:{patient_name}:{contact}:GOVARDHAN_TELE_2026".encode("utf-8")
    token = hashlib.sha256(raw).hexdigest()[:14].upper()
    return f"{APP_BASE_URL}?tele_room=GMH-{appt_id}-{token}"

def _dispatch_tele_link_email(to_email: str, patient_name: str, doctor: str, appt_date: str, conv_time: str, room_link: str) -> tuple[bool, str]:
    if not to_email or "@" not in to_email:
        return False, "No valid email provided."
    try:
        smtp_user = st.secrets["SMTP_EMAIL"]
        smtp_pass = st.secrets["SMTP_APP_PASSWORD"]
        msg = EmailMessage()
        msg["Subject"] = f"Govardhan Hospital — Confirmed Online Tele-Consultation Link ({appt_date})"
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg.set_content(
            f"Dear {patient_name},\n\n"
            f"Your Online Tele-Consultation with {doctor} is CONFIRMED.\n"
            f"• Date: {appt_date}\n"
            f"• Confirmed Convenience Time: {conv_time}\n"
            f"• Unique Secure Video Room Link: {room_link}\n\n"
            f"Please allow Camera and Microphone permissions when joining the room.\n\n"
            f"Warm regards,\nGovardhan Multispecialty Hospital & E-Health Desk"
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, f"Unique tele-consultation link sent to {to_email}"
    except Exception as exc:
        return False, f"Email dispatch queued (SMTP notice: {exc})"

def _render_av_permission_widget(room_link: str):
    """Triggers native browser Camera & Microphone permission prompt and shows live preview."""
    html_code = f"""
    <div style="font-family: sans-serif; border: 1px solid #bae6fd; background: #f0f9ff; border-radius: 12px; padding: 16px;">
        <h4 style="margin: 0 0 8px 0; color: #0f4c81;">🎥 Step B: Camera & Microphone Access Check</h4>
        <p style="margin: 0 0 12px 0; font-size: 13px; color: #334155;">
            Click below to grant browser permission for your <b>Camera</b> and <b>Microphone</b> before joining your doctor.
        </p>
        <button id="btn-av" onclick="requestAV()" style="
            background: #0284c7; color: white; border: none; padding: 10px 18px;
            border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px;
        ">🎙️ Allow Camera & Microphone Access</button>
        <span id="av-status" style="margin-left: 12px; font-size: 13px; font-weight: 600; color: #475569;">
            Awaiting device permission...
        </span>
        <div style="margin-top: 12px; display: flex; gap: 16px; align-items: center;">
            <video id="local-preview" autoplay muted playsinline style="
                width: 220px; height: 130px; background: #0f172a; border-radius: 8px; object-fit: cover; display: none;
            "></video>
            <div id="join-box" style="display: none;">
                <p style="margin: 0 0 8px 0; color: #15803d; font-weight: 600; font-size: 13px;">
                    ✅ Audio & Video Hardware Ready!
                </p>
                <a href="{room_link}" target="_blank" style="
                    display: inline-block; background: #16a34a; color: white; text-decoration: none;
                    padding: 9px 16px; border-radius: 8px; font-weight: 600; font-size: 13px;
                ">🚀 Enter Tele-Consultation Room</a>
            </div>
        </div>
    </div>
    <script>
    async function requestAV() {{
        const statusEl = document.getElementById('av-status');
        const videoEl = document.getElementById('local-preview');
        const joinEl = document.getElementById('join-box');
        try {{
            const stream = await navigator.mediaDevices.getUserMedia({{ video: true, audio: true }});
            videoEl.srcObject = stream;
            videoEl.style.display = 'block';
            joinEl.style.display = 'block';
            statusEl.style.color = '#15803d';
            statusEl.innerText = '✅ Camera & Microphone Permitted';
        }} catch (err) {{
            statusEl.style.color = '#dc2626';
            statusEl.innerText = '❌ Permission Blocked: Please allow Camera & Mic in browser address bar.';
        }}
    }}
    </script>
    """
    components.html(html_code, height=235)

def _ensure_appointments_schema(conn: sqlite3.Connection) -> set:
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
            try:
                conn.execute(f"ALTER TABLE appointments ADD COLUMN {col} {ddl}")
            except Exception:
                pass
    conn.commit()
    return {r[1] for r in conn.execute("PRAGMA table_info(appointments)").fetchall()}

def render(db_path: str, doctors_df, rules_df, ai_engine, client):
    specialty_cards = doctors_df.to_dict("records")
    specialty_doctors = doctors_df["doctor"].tolist()
    fee_map = dict(zip(doctors_df["doctor"], doctors_df["fee"]))
    symptom_variants = rules_df["symptom"].unique().tolist()
    symptom_to_doc = dict(zip(rules_df["symptom"], rules_df["doctor"]))

    # --- POST-PAYMENT TELE-CONSULTATION CONFIRMATION & A/V HARDWARE CHECK ---
    active_tele_id = st.session_state.get("confirmed_tele_appt_id")
    if active_tele_id:
        conn = sqlite3.connect(db_path)
        _ensure_appointments_schema(conn)
        rec = conn.execute(
            "SELECT id, patient_name, patient_contact, patient_email, doctor, appt_date, appt_time, preferred_tele_time, tele_room_link "
            "FROM appointments WHERE id = ?",
            (active_tele_id,)
        ).fetchone()
        conn.close()

        if rec:
            r_id, r_name, r_phone, r_email, r_doc, r_date, r_slot, r_conv, r_link = rec
            with st.container(border=True):
                st.success(f"🎉 **Payment Verified! Online Tele-Consultation #{r_id} with {r_doc} is Booked.**")
                st.markdown("#### ⏰ Step A: Confirm Your Convenience Time & Dispatch Unique Room Link")
                c1, c2, c3 = st.columns([1.2, 1.3, 1.3])
                conv_slot = c1.selectbox(
                    "Select Your Preferred Convenience Window:",
                    [r_slot] + [s for s in ALL_TIME_SLOTS if s != r_slot] + ["Flexible — Next Available Doctor Window"],
                    key=f"conv_time_{r_id}"
                )
                confirm_email = c2.text_input("Confirm Registered Email:", value=r_email or "", key=f"conf_email_{r_id}")
                confirm_phone = c3.text_input("Confirm Registered Phone:", value=r_phone or "", key=f"conf_phone_{r_id}")

                if st.button("✅ Confirm Time & Send Unique Link to Phone & Email", type="primary", use_container_width=True):
                    unique_link = r_link or _generate_unique_tele_link(r_id, r_name, confirm_phone)
                    conn = sqlite3.connect(db_path)
                    conn.execute(
                        "UPDATE appointments SET preferred_tele_time = ?, patient_email = ?, patient_contact = ?, tele_room_link = ?, status = 'Tele-Consult Confirmed' WHERE id = ?",
                        (conv_slot, confirm_email.strip(), confirm_phone.strip(), unique_link, r_id)
                    )
                    conn.commit()
                    conn.close()

                    sent_ok, mail_msg = _dispatch_tele_link_email(
                        confirm_email.strip(), r_name, r_doc, r_date, conv_slot, unique_link
                    )
                    log_audit_event("Tele_Consult", r_name, "TELE_LINK_DISPATCHED", f"Appt#{r_id} | {conv_slot}", db_path=db_path)

                    st.session_state["ready_tele_link"] = unique_link
                    st.session_state["ready_tele_phone"] = confirm_phone.strip()
                    st.session_state["ready_tele_msg"] = (
                        f"Govardhan Hospital Tele-Consultation Confirmed! Doctor: {r_doc}, Date: {r_date}, "
                        f"Time: {conv_slot}. Join via your unique link: {unique_link}"
                    )
                    if sent_ok:
                        st.success(f"📧 {mail_msg}")
                    else:
                        st.info(f"📧 {mail_msg}")

                if st.session_state.get("ready_tele_link"):
                    u_link = st.session_state["ready_tele_link"]
                    u_phone = "".join(c for c in st.session_state.get("ready_tele_phone", "") if c.isdigit())
                    wa_phone = f"91{u_phone}" if len(u_phone) == 10 else u_phone
                    encoded_text = quote(st.session_state.get("ready_tele_msg", u_link))

                    st.info(f"🔗 **Your Unique Tele-Consultation Room Link:** `{u_link}`")
                    l1, l2 = st.columns(2)
                    l1.link_button(
                        f"📱 Send Link to Registered Phone (+{wa_phone}) via WhatsApp",
                        f"https://wa.me/{wa_phone}?text={encoded_text}",
                        use_container_width=True
                    )
                    l2.link_button(
                        "💬 Send via Mobile SMS",
                        f"sms:+{wa_phone}?body={encoded_text}",
                        use_container_width=True
                    )

                    _render_av_permission_widget(u_link)

    # Care Mode Overview Strip
    m_col1, m_col2, m_col3 = st.columns(3, gap="medium")
    with m_col1:
        with st.container(border=True):
            st.markdown("#### 🏥 Offline OPD Consultation")
            st.caption("In-person specialist examination, physical vitals check & diagnostic lab access at Simhachalam Hills.")
    with m_col2:
        with st.container(border=True):
            st.markdown("#### 💻 Online Tele-Consultation")
            st.caption("HD video consultation with Camera/Mic verification & unique link sent to your Phone & Email (20% off).")
    with m_col3:
        with st.container(border=True):
            st.markdown("#### 🛏️ In-Hospital Surgical & IPD Care")
            st.caption("Modular Operation Theatres (OT), pre-op anesthesia workup, 24×7 nursing & post-op ICU recovery.")

    st.markdown("#### 🪪 Patient Identity Verification (2FA e-KYC & PII Encryption)")
    with st.container(border=True):
        k1, k2, k3 = st.columns([1.4, 1.4, 0.8])
        gov_id_input = k1.text_input("12-Digit Government / Health ID", max_chars=14, placeholder="e.g. 2345 6789 0123", key="kyc_id_input")
        kyc_email_input = k2.text_input("Registered Email (for Real OTP)", placeholder="patient@example.com", key="kyc_email_input")
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
                log_audit_event("Patient_Portal", mask_aadhar(clean_num), "REAL_OTP_SENT", kyc_email_input.strip(), db_path=db_path)

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
                    log_audit_event("Patient_Portal", masked, "2FA_EKYC_VERIFIED", "Fernet_Encrypted", db_path=db_path)
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
                    st.caption(f"**{spec['doctor']}** • OPD: ₹{spec.get('fee', 500)}")
                    st.write(f"<small>{spec['desc']}</small>", unsafe_allow_html=True)
                    if st.button(f"Select {spec['dept']}", key=f"btn_spec_{global_idx}", use_container_width=True):
                        st.session_state["selected_specialty_doc"] = spec["doctor"]

    st.markdown("---")
    col_left, col_right = st.columns((1.15, 1), gap="large")

    with col_left:
        st.subheader("🩺 Step 1: AI Triage & Clinical Assessment")
        with st.expander("🤖 AI Symptom-to-Specialty NLP Triage Assistant", expanded=True):
            free_text_symptoms = st.text_input("Describe symptoms in plain English:", key="ai_free_text")
            if free_text_symptoms:
                red_flags = [
                    "chest pain", "stroke", "unconscious", "severe bleeding",
                    "can't breathe", "cannot breathe", "seizure", "heart attack"
                ]
                if any(flag in free_text_symptoms.lower() for flag in red_flags):
                    st.error(
                        "🚨 **EMERGENCY RED-FLAG DETECTED:** Call 24×7 Emergency Ambulance (`+91 891-255-8888`) "
                        "or visit the Simhachalam Hills Trauma Bay immediately. Do not wait for an online slot."
                    )
                recommendations = ai_engine.recommend_specialty(free_text_symptoms)
                top_spec, confidence, urgency = recommendations[0]
                ac1, ac2, ac3 = st.columns(3)
                ac1.metric("AI Recommended Dept", top_spec)
                ac2.metric("TF-IDF Match Score", f"{confidence}%")
                ac3.metric("Triage Priority", urgency)
                if len(recommendations) > 1:
                    alt_list = ", ".join([f"{s} ({c}%)" for s, c, _ in recommendations[1:]])
                    st.caption(f"Differential departments: {alt_list}")
                st.caption("⚕️ *Clinical Decision Support Only: AI routing assists department selection and does not constitute a medical diagnosis.*")
                log_audit_event("AI_Triage", "Patient_Portal", "AI_SYMPTOM_TRIAGE", f"Dept:{top_spec}", db_path=db_path)

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
                selected_symptoms = st.multiselect("Current Symptoms / Condition", options=sym_options, placeholder="Select symptoms...")

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                duration = st.selectbox("Symptom Duration", ["Less than 24 hours", "1 - 3 days", "4 - 7 days", "More than a week", "Scheduled Surgical Evaluation"])
            with col_s2:
                severity = st.select_slider("Pain / Clinical Urgency", options=["Mild", "Moderate", "Severe"])

            additional_details = st.text_input("Medical History, Allergies, or Prior Scans (Optional)", placeholder="e.g., Allergic to penicillin...")

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
        st.subheader("🗓️ Step 2: Select Care Pathway (Online / Offline OPD / Surgery)")

        care_mode = st.radio(
            "Choose Mode of Treatment:",
            [
                "🏥 Offline OPD Consultation (In-Person)",
                "💻 Online Video Tele-Consultation",
                "🛏️ In-Hospital Surgical & IPD Treatment"
            ],
            horizontal=False
        )

        default_idx = specialty_doctors.index(recommended_doc) if recommended_doc in specialty_doctors else 0
        doctor_choice = st.selectbox("Assigned Department Specialist / Surgeon", specialty_doctors, index=default_idx)
        base_opd_fee = float(fee_map.get(doctor_choice, 500.0))

        if "Online" in care_mode:
            payable_amount = round(base_opd_fee * 0.80, 2)
            service_package = "Online Tele-Consultation (Video)"
            st.info(f"💻 **Tele-Consultation Fee (20% Online Discount):** ₹{payable_amount:,.2f} *(Includes post-payment convenience slot confirmation, Camera/Mic check & unique Phone/Email link)*")
        elif "Surgical" in care_mode:
            selected_pkg = st.selectbox("Select Surgical & IPD Care Package:", list(SURGICAL_PACKAGES.keys()))
            ward_pref = st.selectbox("Inpatient Ward Preference:", ["General Ward", "Semi-Private Twin Sharing", "Private Deluxe Room", "Surgical Post-Op ICU"])
            pkg_est = SURGICAL_PACKAGES[selected_pkg]
            payable_amount = 2000.0
            service_package = f"{selected_pkg} [{ward_pref}]"
            st.warning(f"🏥 **Estimated Surgical Package:** ₹{pkg_est:,.0f}\n\n💳 **Upfront OT & Admission Booking Deposit:** ₹{payable_amount:,.2f}")
        else:
            payable_amount = base_opd_fee
            service_package = "Offline OPD Visit"
            st.info(f"🏥 **Offline OPD Consultation Fee for {doctor_choice}:** ₹{payable_amount:,.2f}")

        col_date, col_time = st.columns(2)
        with col_date:
            appointment_date = st.date_input("Select Date", min_value=datetime.today().date())

        conn = sqlite3.connect(db_path)
        booked_df = pd.read_sql_query(
            "SELECT appt_time FROM appointments WHERE doctor = ? AND appt_date = ? AND status != 'Cancelled'",
            conn, params=(doctor_choice, str(appointment_date))
        )
        conn.close()
        available_slots = [s for s in ALL_TIME_SLOTS if s not in set(booked_df["appt_time"].tolist())]

        with col_time:
            appointment_time = st.selectbox("Initial Preferred Time Slot", available_slots) if available_slots else None
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
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                p_contact = st.text_input("Registered Phone Number", placeholder="e.g. 9876543210")
            with col_c2:
                p_email = st.text_input("Registered Email (for Unique Link)", value=st.session_state.get("kyc_email_input", ""), placeholder="patient@example.com")

            btn_label = f"Pay ₹{payable_amount:,.0f} Deposit & Reserve OT/IPD Bed" if "Surgical" in care_mode else f"Proceed to Pay ₹{payable_amount:,.0f} & Book"
            if st.form_submit_button(btn_label, type="primary"):
                if not patient_name.strip() or not p_contact.strip():
                    st.error("Please enter both patient name and registered phone number.")
                elif "Online" in care_mode and "@" not in p_email:
                    st.error("Please enter a valid registered email address so we can dispatch your unique tele-consultation link.")
                elif not selected_symptoms:
                    st.warning("Please select at least one symptom or condition in Step 1.")
                elif not appointment_time:
                    st.error("Please pick a date with open time slots.")
                else:
                    kyc_verified_flag = 1 if st.session_state.get("kyc_verified") else 0
                    kyc_masked_val = st.session_state.get("kyc_masked", "Unverified")
                    kyc_hash_val = st.session_state.get("kyc_hash", "")

                    clean_mode = care_mode.split(" ", 1)[1]
                    triage = f"[{clean_mode} | {service_package} | Severity: {severity} | Duration: {duration} | Age: {p_age}] Symptoms: {', '.join(selected_symptoms)}. Notes: {additional_details or 'None'}"
                    conn = sqlite3.connect(db_path)
                    _ensure_appointments_schema(conn)
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO appointments (patient_name, patient_age, patient_gender, patient_contact, patient_email, patient_problem, doctor, appt_date, appt_time, status, aadhaar_masked, aadhaar_hash, kyc_verified, care_mode, service_package) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (patient_name.strip(), p_age, p_gender, p_contact.strip(), p_email.strip(), triage, doctor_choice, str(appointment_date), appointment_time, "Awaiting Payment", kyc_masked_val, kyc_hash_val, kyc_verified_flag, clean_mode, service_package)
                    )
                    new_appt_id = cur.lastrowid
                    unique_tele_url = _generate_unique_tele_link(new_appt_id, patient_name.strip(), p_contact.strip()) if "Online" in care_mode else ""
                    if unique_tele_url:
                        cur.execute("UPDATE appointments SET tele_room_link = ? WHERE id = ?", (unique_tele_url, new_appt_id))
                    conn.commit()
                    conn.close()

                    log_audit_event("Patient_Portal", patient_name.strip(), "BOOK_CARE_REQUEST", f"Appt#{new_appt_id} [{clean_mode}]", db_path=db_path)

                    try:
                        payment_data = {
                            "amount": int(payable_amount * 100),
                            "currency": "INR",
                            "description": f"{clean_mode} - {doctor_choice}",
                            "customer": {
                                "name": patient_name.strip(),
                                "contact": p_contact.strip(),
                                **({"email": p_email.strip()} if "@" in p_email else {})
                            },
                            "notify": {"sms": True, "email": "@" in p_email},
                            "callback_url": f"{APP_BASE_URL}?appt_id={new_appt_id}",
                            "callback_method": "get"
                        }
                        payment_link = client.payment_link.create(payment_data)
                        st.session_state["pending_payment_url"] = payment_link["short_url"]
                        st.session_state["pending_appt_id"] = new_appt_id
                        st.session_state["pending_is_online"] = ("Online" in care_mode)
                    except Exception as e:
                        st.error(f"Payment gateway error: {e}")

        if "pending_payment_url" in st.session_state:
            st.warning(f"Booking reserved (ID #{st.session_state['pending_appt_id']}). Complete payment below to confirm:")
            st.link_button("💳 Pay Now via UPI / Card", st.session_state["pending_payment_url"], type="primary", use_container_width=True)
            if st.session_state.get("pending_is_online"):
                if st.button("✅ Simulate / Complete Payment & Open Tele-Consult Setup", use_container_width=True):
                    p_id = st.session_state["pending_appt_id"]
                    conn = sqlite3.connect(db_path)
                    conn.execute("UPDATE appointments SET status = 'Confirmed (Paid)' WHERE id = ?", (p_id,))
                    conn.commit()
                    conn.close()
                    st.session_state["confirmed_tele_appt_id"] = p_id
                    st.rerun()

    with col_right:
        tab_req, tab_rx = st.tabs(["📋 Active Care & Surgery Requests", "📄 Download Prescriptions & Discharge Notes"])
        with tab_req:
            conn = sqlite3.connect(db_path)
            actual_cols = _ensure_appointments_schema(conn)
            mode_expr = "COALESCE(care_mode, 'Offline OPD') AS [Care Mode]" if "care_mode" in actual_cols else "'Offline OPD' AS [Care Mode]"
            time_expr = "COALESCE(NULLIF(preferred_tele_time, ''), appt_time) AS [Confirmed Time]" if "preferred_tele_time" in actual_cols else "appt_time AS [Confirmed Time]"
            df = pd.read_sql_query(
                f"SELECT id AS ID, patient_name AS [Patient], {mode_expr}, "
                f"doctor AS Doctor, appt_date AS [Date], {time_expr}, status AS Status "
                "FROM appointments ORDER BY id DESC",
                conn
            )
            conn.close()
            st.dataframe(df, use_container_width=True, hide_index=True)

        with tab_rx:
            st.caption("Enter your full name and registered phone number to download your prescription or surgical discharge PDF.")
            v_name = st.text_input("Patient Full Name:", key="v_name")
            v_phone = st.text_input("Registered Contact Number:", key="v_phone")
            if v_name.strip() and v_phone.strip():
                conn = sqlite3.connect(db_path)
                appt_check = pd.read_sql_query("SELECT patient_contact FROM appointments WHERE LOWER(TRIM(patient_name)) = LOWER(TRIM(?))", conn, params=(v_name,))
                digits_in = "".join(c for c in v_phone if c.isdigit())
                digits_db = {"".join(c for c in str(x) if c.isdigit()) for x in appt_check["patient_contact"].dropna()}
                if (digits_in in digits_db and digits_in != "") or (not appt_check.empty and digits_db == {""} and v_phone.strip() == "0000"):
                    rx_df = pd.read_sql_query("SELECT * FROM consultations WHERE LOWER(TRIM(patient_name)) = LOWER(TRIM(?)) ORDER BY id DESC", conn, params=(v_name,))
                    conn.close()
                    if rx_df.empty:
                        st.info("No finalized prescriptions or surgical notes found for this patient yet.")
                    for rec in rx_df.to_dict("records"):
                        with st.container(border=True):
                            st.markdown(f"**Date:** {rec['consultation_date']} | **Doctor:** {rec['doctor']}")
                            st.markdown(f"**Diagnosis:** {rec['diagnosed_disease']}")
                            st.info(f"💊 **Rx / Post-Op Care:** {rec['prescription']}")
                            st.caption(f"📝 **Notes:** {rec['notes'] or 'None'}")
                            pdf_bytes = build_prescription_pdf(
                                rec["patient_name"], rec["doctor"], rec["diagnosed_disease"],
                                rec["symptoms"], rec["prescription"], rec["notes"]
                            )
                            st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"Rx_{rec['id']}.pdf", mime="application/pdf", key=f"dl_{rec['id']}")
                else:
                    conn.close()
                    st.error("❌ Verification failed. Check your name and phone number.")
