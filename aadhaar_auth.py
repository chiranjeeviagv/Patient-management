import os
import random
import smtplib
from email.message import EmailMessage
import streamlit as st

# Verhoeff algorithm tables for official 12-digit ID checksum validation
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

def is_valid_aadhaar_format(aadhaar_str: str, strict_checksum: bool = False) -> tuple[bool, str]:
    """Validates 12-digit numeric structure (and optional Verhoeff check digit)."""
    digits = "".join(filter(str.isdigit, str(aadhaar_str)))
    if len(digits) != 12:
        return False, "Please enter a 12-digit numeric ID."
    if digits[0] in ("0", "1"):
        return False, "ID numbers cannot start with 0 or 1."
    
    if strict_checksum:
        c = 0
        for i, item in enumerate(reversed(digits)):
            c = _D[c][_P[i % 8][int(item)]]
        if c != 0:
            return False, "Invalid Verhoeff check digit."
    return True, "Valid format"

def send_real_email_otp(recipient_email: str) -> tuple[bool, str]:
    """Sends a real 6-digit OTP via Gmail SMTP using Streamlit Secrets (with sandbox fallback)."""
    otp = str(random.randint(100000, 999999))
    st.session_state["active_otp"] = otp
    st.session_state["sandbox_otp"] = otp

    sender_email = st.secrets.get("SMTP_EMAIL", os.environ.get("SMTP_EMAIL"))
    sender_pass = st.secrets.get("SMTP_APP_PASSWORD", os.environ.get("SMTP_APP_PASSWORD"))

    if not sender_email or not sender_pass:
        return False, f"SMTP secrets not configured yet. Demo Fallback OTP: {otp}"

    try:
        msg = EmailMessage()
        msg["Subject"] = "Sunrise Multispecialty Hospital - Patient Verification OTP"
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg.set_content(
            f"Dear Patient,\n\n"
            f"Your 6-digit One-Time Password (OTP) for identity verification at Sunrise Multispecialty Hospital is: {otp}\n\n"
            f"Please do not share this code with anyone.\n\n"
            f"Regards,\nSunrise Hospital Digital Health Desk"
        )

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)
        return True, f"Real OTP dispatched to {recipient_email}!"
    except Exception as e:
        return False, f"Email delivery error ({e}). Demo Fallback OTP: {otp}"

def trigger_sandbox_otp() -> str:
    """Generates and stores a 6-digit sandbox OTP in Streamlit session state."""
    otp = str(random.randint(100000, 999999))
    st.session_state["active_otp"] = otp
    st.session_state["sandbox_otp"] = otp
    return otp

def verify_otp(user_otp: str) -> bool:
    """Verifies user-entered OTP against active session state."""
    expected = st.session_state.get("active_otp") or st.session_state.get("sandbox_otp")
    return bool(expected and str(user_otp).strip() == expected)

# Alias kept for backward compatibility
verify_sandbox_otp = verify_otp
