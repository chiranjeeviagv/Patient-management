import os
import plotly.express as px
import streamlit as st

def render(hospital_title: str, doctors_df):
    st.subheader(f"🏛️ About {hospital_title}")
    if os.path.exists("assets/hospital_campus.png"):
        st.image("assets/hospital_campus.png", caption="Govardhan Multispecialty Hospital — Simhachalam Hills Campus", use_container_width=True)

    ab1, ab2 = st.columns((1.4, 1), gap="large")
    with ab1:
        with st.container(border=True):
            st.markdown("### Integrated Outpatient, Tele-Health & Surgical Excellence")
            st.write(
                "Founded to bridge specialized medical expertise with seamless digital patient access and modern clinical governance, "
                f"**{hospital_title}** delivers comprehensive **Offline OPD Consultations**, **24×7 Tele-Medicine**, "
                "and **In-Hospital Surgical & Critical Care** across **30 specialized clinical departments**."
            )
            st.markdown("#### 🏥 Clinical & Surgical Infrastructure")
            st.markdown(
                "- **Modular Operation Theatres (4 Laminar-Flow OTs):** Equipped for Laparoscopic, Orthopedic, Cardiac, Neuro, and ENT surgeries with HEPA filtration.\n"
                "- **120-Bed Inpatient & Critical Care Wing:** Dedicated Surgical ICU (SICU), Medical ICU (MICU), Neonatal ICU, and private recovery suites.\n"
                "- **Hybrid OPD & Tele-Health:** Morning **09:00 AM – 02:00 PM** | Evening **03:00 PM – 09:00 PM** (In-person & Video)."
            )
    with ab2:
        with st.container(border=True):
            st.markdown("### 📊 Hospital at a Glance")
            m1, m2 = st.columns(2)
            m1.metric("Clinical Specialties", "30 Departments")
            m2.metric("Modular OTs & Beds", "4 OTs • 120 Beds")
            m3, m4 = st.columns(2)
            m3.metric("Nursing & OT Staff", "85+ Care Staff")
            m4.metric("Emergency & Trauma", "24 × 7 Critical Care")
            st.info("📍 **Location:** Simhachalam Hills, Simhachalam North, Visakhapatnam – 530029, AP\n\n📞 **Helpline:** +91 99999 88888 | ✉️ **Email:** care@govardhanmedical.in")

    st.markdown("---")
    st.subheader("📊 Clinical Departments & OPD Consultation Fee Structure")
    fig_depts = px.bar(
        doctors_df.sort_values("fee", ascending=True),
        x="fee",
        y="dept",
        orientation="h",
        color="fee",
        color_continuous_scale="Teal",
        labels={"fee": "Offline OPD Fee (₹) [Online Video: 20% Off]", "dept": "Clinical Specialty"},
        text_auto=True
    )
    fig_depts.update_layout(height=680, showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig_depts, use_container_width=True)
