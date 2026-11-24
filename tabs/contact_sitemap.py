import streamlit as st

def render():
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
                "**☎️ OPD & Surgical Admission Desk:** `+91 99999 88888`\n\n"
                "**✉️ Clinical & Admin Support:** `care@govardhanmedical.in`\n\n"
                "**🕒 Consultation & IPD Hours:**\n"
                "- OPD & Tele-Health Morning: `09:00 AM – 02:00 PM`\n"
                "- OPD & Tele-Health Evening: `03:00 PM – 09:00 PM` (Mon – Sat)\n"
                "- In-Hospital Surgical IPD, OT & ICU: `24 × 7 × 365`"
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
            st.markdown("#### 🩺 Patient & Surgical Care Services")
            st.markdown(
                "- **3 Care Modes:** Offline OPD, Online Video Tele-Consultation & In-Hospital Surgical IPD/OT Packages\n"
                "- **Patient Identity e-KYC (2FA):** 12-digit ID validation + Real Email OTP & Fernet PII encryption\n"
                "- **AI Symptom Triage Assistant:** NLP symptom-to-specialty routing across 20+ clinical departments\n"
                "- **Razorpay Payment Gateway:** Instant OPD/Tele-Consult fee & Surgical IPD deposit settlement\n"
                "- **e-Prescription & Discharge PDFs:** Cryptographically verified PDF downloads"
            )

    with sm2:
        with st.container(border=True):
            st.markdown("#### 🔐 Role-Based Clinical & Ops Dashboards")
            st.markdown(
                "- **Doctor Dashboard (`/Doctor_Dashboard`):** Specialist schedules, surgical notes, QR-verified PDF e-Rx & HL7 FHIR R4 JSON export\n"
                "- **Pharmacy Inventory (`/Pharmacy_Inventory`):** Live stock ledger, burn-rate runway forecasting & automated CSV Purchase Orders\n"
                "- **Billing Dashboard (`/Billing_Dashboard`):** GST-compliant invoicing, OPD + Surgical + Pharmacy ledger\n"
                "- **Admin Analytics (`/Admin_Analytics`):** KPI control panel, specialty disease analytics & SHA-256 hash-chained audit logs"
            )

    with sm3:
        with st.container(border=True):
            st.markdown("#### 🏛️ Institutional & Staff Governance")
            st.markdown(
                "- **About Us & Surgical Wing:** 4 Modular OTs, 120 IPD/ICU beds & specialty fee chart\n"
                "- **Hospital Staff & Hierarchy:** Interactive Treemap & 4-Tier directory (Executive, Nursing Directorate, OT Support & General Admin)\n"
                "- **Corporate Social Responsibility (CSR):** Free rural health camps, maternal wellness & school programs\n"
                "- **Patient Feedback:** Live satisfaction donut chart & verified patient testimonials\n"
                "- **Contact & Location:** Emergency helpline, 24×7 IPD/OT hours & interactive Google Maps"
            )
