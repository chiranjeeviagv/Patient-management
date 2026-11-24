import streamlit as st

def render():
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
