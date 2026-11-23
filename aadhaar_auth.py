import random
import streamlit as st

# Verhoeff algorithm tables for official 12-digit Aadhaar checksum validation
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
        return False, "Aadhaar numbers cannot start with 0 or 1."
    
    if strict_checksum:
        c = 0
        for i, item in enumerate(reversed(digits)):
            c = _D[c][_P[i % 8][int(item)]]
        if c != 0:
            return False, "Invalid Verhoeff check digit."
    return True, "Valid format"

def trigger_sandbox_otp() -> str:
    """Generates and stores a 6-digit sandbox OTP in Streamlit session state."""
    otp = str(random.randint(100000, 999999))
    st.session_state["sandbox_otp"] = otp
    return otp

def verify_sandbox_otp(user_otp: str) -> bool:
    """Verifies user-entered OTP against session state."""
    expected = st.session_state.get("sandbox_otp")
    return bool(expected and str(user_otp).strip() == expected)
