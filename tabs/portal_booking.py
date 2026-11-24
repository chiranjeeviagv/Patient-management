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
        rec = conn.execute(
            "SELECT id, patient_name, patient_contact, patient_email, doctor, appt_date, appt_time, preferred_tele_time
