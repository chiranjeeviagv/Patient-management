import pandas as pd
import plotly.express as px
import streamlit as st

def render():
    st.subheader("👔 Hospital Organizational Hierarchy & Supporting Staff Directory")
    st.caption("Structured clinical, nursing, surgical OT, and general administrative governance ensuring seamless patient care.")

    org_data = pd.DataFrame([
        {"Division": "1. Executive & Clinical Leadership", "Unit": "Medical Director", "Role": "Mr. K. Aravind, MD (Chief of Clinical Services)", "Headcount": 1},
        {"Division": "1. Executive & Clinical Leadership", "Unit": "Hospital Operations", "Role": "Mrs. K. Geetha Madhavi, MBA (Chief Administrative Officer)", "Headcount": 1},
        {"Division": "1. Executive & Clinical Leadership", "Unit": "Academics & Audit", "Role": "Dr. A. Pradeep Kumar, MS (Dean of Clinical Audit)", "Headcount": 1},
        {"Division": "1. Executive & Clinical Leadership", "Unit": "Pharmacy & Supply", "Role": "Mr. K. Ramana, M.Pharm (Chief Pharmacist)", "Headcount": 4},
        {"Division": "2. Nursing Directorate", "Unit": "Nursing Leadership", "Role": "Mrs. S. Hymavathi, M.Sc (N) — Chief Nursing Officer (CNO)", "Headcount": 1},
        {"Division": "2. Nursing Directorate", "Unit": "ICU & Surgical Wards", "Role": "Senior Nursing Superintendents & Ward Matrons (3 Shifts)", "Headcount": 28},
        {"Division": "2. Nursing Directorate", "Unit": "OPD & Triage Nursing", "Role": "OPD Triage & Immunization Staff Nurses", "Headcount": 18},
        {"Division": "3. Operation Theatre (OT) & Surgical Support", "Unit": "OT Coordination", "Role": "Mr. B. Srinivas Rao — Chief OT & Anesthesia Coordinator", "Headcount": 2},
        {"Division": "3. Operation Theatre (OT) & Surgical Support", "Unit": "Scrub & Circulating Nurses", "Role": "Certified OT Scrub & Recovery Room Nurses", "Headcount": 14},
        {"Division": "3. Operation Theatre (OT) & Surgical Support", "Unit": "Anesthesia & CSSD", "Role": "Anesthesia Technicians & Central Sterile Supply (CSSD) Staff", "Headcount": 10},
        {"Division": "4. General Administration & Support", "Unit": "Front Office & Tele-Desk", "Role": "Mr. P. Vamsi Krishna — Patient Relations & Tele-Health Manager", "Headcount": 8},
        {"Division": "4. General Administration & Support", "Unit": "Billing & Insurance TPA", "Role": "Cashless Insurance Desk, Medical Records (MRD) & Billing Officers", "Headcount": 6},
        {"Division": "4. General Administration & Support", "Unit": "Biomedical & Facility Ops", "Role": "Biomedical Engineers, Ambulance Crew & Housekeeping Supervisors", "Headcount": 12},
    ])

    fig_org = px.treemap(
        org_data,
        path=[px.Constant("Govardhan Multispecialty Hospital"), "Division", "Unit", "Role"],
        values="Headcount",
        color="Division",
        title="Interactive Hospital Staffing & Reporting Hierarchy (Click any division to drill down)"
    )
    fig_org.update_layout(height=400, margin=dict(t=45, b=10, l=10, r=10))
    st.plotly_chart(fig_org, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🏛️ Tier 1: Executive Leadership & Clinical Governance")
    t1_leaders = [
        ("Mr. K. Aravind, MD", "Medical Director & Chief of Clinical Services", "25+ years in Internal Medicine & NABH Quality Accreditation. Directs clinical protocols across all 20 specialties and surgical boards."),
        ("Mrs. K. Geetha Madhavi, MBA (Hosp. Admin)", "Chief Administrative Officer (CAO)", "Heads hospital operations, outpatient/tele-health scheduling efficiency, statutory compliance, and general administration."),
        ("Dr. A. Pradeep Kumar, MS", "Dean of Medical Academics & Surgical Audit", "Oversees surgical morbidity/mortality reviews, continuing medical education (CME), and diagnostic quality assurance."),
        ("Mr. K. Ramana, M.Pharm", "Chief Pharmacist & Supply Chain Head", "Manages inpatient/outpatient dispensary inventory, surgical consumables, and cold-chain storage.")
    ]
    t1_cols = st.columns(2, gap="medium")
    for idx, (name, role, bio) in enumerate(t1_leaders):
        with t1_cols[idx % 2]:
            with st.container(border=True):
                st.markdown(f"#### {name}")
                st.caption(f"**{role}**")
                st.write(bio)

    st.markdown("### 🩺 Tier 2: Nursing Directorate & Patient Care Units")
    n_cols = st.columns(3, gap="medium")
    nursing_units = [
        ("Mrs. S. Hymavathi, M.Sc (Nursing)", "Chief Nursing Officer (CNO)", "Reports to Medical Director. Leads 47+ registered nurses across OPD, IPD wards, and critical care units; enforces infection-control protocols."),
        ("Mrs. D. Padmaja, B.Sc (Nursing)", "Senior Matron — Surgical & Post-Op ICU", "Supervises 28 ICU and inpatient ward nurses managing pre-operative preparation, post-anesthesia monitoring, and medication administration."),
        ("Ms. R. Kavitha, GNM / B.Sc (N)", "OPD & Triage Nursing Supervisor", "Coordinates 18 outpatient triage nurses handling vitals recording, pediatric care routing, and tele-consultation clinical documentation.")
    ]
    for col, (name, role, desc) in zip(n_cols, nursing_units):
        with col:
            with st.container(border=True):
                st.markdown(f"#### {name}")
                st.caption(f"**{role}**")
                st.write(desc)

    st.markdown("### 🔬 Tier 3: Operation Theatre (OT) & Surgical Support Team")
    ot_cols = st.columns(3, gap="medium")
    ot_units = [
        ("Mr. B. Srinivas Rao, B.Sc (OT Tech)", "Chief OT & Anesthesia Coordinator", "Reports to Medical Director & Dean of Surgical Audit. Manages scheduling across 4 modular OTs, laparoscopic towers, and emergency surgical readiness."),
        ("Mrs. M. Sailaja & Surgical Nursing Team", "Senior OT Scrub & Recovery Nurses (14 Staff)", "Specialized instrument scrub nurses and Post-Anesthesia Care Unit (PACU) nurses supporting General, Ortho, Cardiac, and Neuro surgeries."),
        ("Mr. G. Naresh & CSSD Technical Wing", "Anesthesia Techs & Sterilization (CSSD) (10 Staff)", "Operates Boyle's anesthesia workstations, ventilator calibration, and autoclave/ETO surgical instrument sterilization.")
    ]
    for col, (name, role, desc) in zip(ot_cols, ot_units):
        with col:
            with st.container(border=True):
                st.markdown(f"#### {name}")
                st.caption(f"**{role}**")
                st.write(desc)

    st.markdown("### 🗂️ Tier 4: General Administration, Front-Office & Facility Support")
    ga_cols = st.columns(3, gap="medium")
    ga_units = [
        ("Mr. P. Vamsi Krishna, MHA", "Manager — Patient Relations & Tele-Health Desk", "Reports to CAO. Leads 8 front-office executives managing OPD registration, video consultation coordination, and patient helpdesk."),
        ("Mrs. T. Bhavani, M.Com", "Head — Billing, Insurance TPA & Medical Records", "Supervises 6 billing and MRD officers handling cashless insurance approvals, GST invoicing, and HL7 FHIR digital record archiving."),
        ("Mr. V. Satyanarayana, B.Tech (Biomed)", "Biomedical Engineering & Facility Operations", "Leads 12 technicians, 24×7 ambulance drivers, medical gas manifold operators, and hospital sanitation supervisors.")
    ]
    for col, (name, role, desc) in zip(ga_cols, ga_units):
        with col:
            with st.container(border=True):
                st.markdown(f"#### {name}")
                st.caption(f"**{role}**")
                st.write(desc)
