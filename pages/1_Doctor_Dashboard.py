import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from utils import load_clinical_data, apply_custom_ui, render_hero, require_login, build_prescription_pdf
from clinical_interop import build_qr_verified_prescription_pdf, build_fhir_r4_bundle
from security_utils import log_audit_event
st.set_page_config(page_title="Doctor Dashboard", page_icon="🩺", layout="wide")
apply_custom_ui()
from clinical_interop import build_qr_verified_prescription_pdf, build_fhir_r4_bundle
from security_utils import log_audit_event

# Example using the selected/completed consultation variables:
col_pdf, col_fhir = st.columns(2)

with col_pdf:
    pdf_bytes = build_qr_verified_prescription_pdf(
        patient_name=patient_name,
        age_gender=f"{patient_age} Y / {patient_gender}",
        doctor_name=selected_doctor,
        specialty=doctor_specialty,
        diagnosis=diagnosed_disease,
        medications=prescribed_medicines,
        notes=doctor_notes
    )
    if st.download_button(
        label="📄 Download QR-Verified e-Prescription (PDF)",
        data=pdf_bytes,
        file_name=f"eRx_{patient_name.replace(' ', '_')}.pdf",
        mime="application/pdf",
        use_container_width=True
    ):
        log_audit_event("Doctor", selected_doctor, "EXPORT_QR_PDF", patient_name, db_path="hospital_v2.db")

with col_fhir:
    fhir_json = build_fhir_r4_bundle(
        patient_name=patient_name,
        doctor_name=selected_doctor,
        specialty=doctor_specialty,
        diagnosis=diagnosed_disease,
        medications=prescribed_medicines
    )
    if st.download_button(
        label="🔗 Export HL7 FHIR R4 Bundle (JSON)",
        data=fhir_json,
        file_name=f"FHIR_{patient_name.replace(' ', '_')}.json",
        mime="application/json",
        use_container_width=True
    ):
        log_audit_event("Doctor", selected_doctor, "EXPORT_FHIR_JSON", patient_name, db_path="hospital_v2.db")
if require_login("Doctor Dashboard", "doctor123"):
    render_hero("🩺 Medical Practitioner Workspace", "Manage daily patient schedules, review E-health logs, and issue digital prescriptions.")
    doctors_df, rules_df = load_clinical_data()
    
    # Strip accidental whitespace in CSV columns to ensure exact matching
    doctors_df["doctor"] = doctors_df["doctor"].str.strip()
    rules_df["doctor"] = rules_df["doctor"].str.strip()
    
    specialty_doctors = doctors_df["doctor"].tolist()

    selected_dept = st.selectbox("Filter Schedule by Specialist:", ["All Departments"] + specialty_doctors)
    conn = sqlite3.connect("hospital_v2.db")
    df = pd.read_sql_query(
        "SELECT id AS ID, patient_name AS [Patient Name], patient_age AS [Age], doctor AS Doctor, "
        "patient_problem AS [Triage Report], appt_date AS [Date], appt_time AS [Slot], status AS Status "
        "FROM appointments",
        conn
    )
    conn.close()

    if selected_dept != "All Departments":
        df = df[df["Doctor"].str.strip() == selected_dept]

    if not df.empty:
        tab1, tab2 = st.tabs(["📅 Operational Schedule", "🩺 Patient Diagnostics & Rx"])
        with tab1:
            edited_df = st.data_editor(
                df,
                column_config={"Status": st.column_config.SelectboxColumn("Status", options=["Pending", "Confirmed", "Completed", "Cancelled"], required=True)},
                disabled=["ID", "Patient Name", "Age", "Doctor", "Triage Report", "Date", "Slot"],
                use_container_width=True, hide_index=True
            )
            if st.button("💾 Save Status Updates", type="primary"):
                conn = sqlite3.connect("hospital_v2.db")
                for _, row in edited_df.iterrows():
                    conn.execute("UPDATE appointments SET status = ? WHERE id = ?", (row["Status"], int(row["ID"])))
                conn.commit()
                conn.close()
                st.success("Schedules updated!")
                st.rerun()

        with tab2:
            selected_patient = st.selectbox("Select Patient:", df["Patient Name"].unique().tolist())
            conn = sqlite3.connect("hospital_v2.db")
            p_info = conn.execute(
                "SELECT patient_age, doctor, patient_problem FROM appointments WHERE patient_name = ? ORDER BY id DESC LIMIT 1",
                (selected_patient,)
            ).fetchone()
            p_age_val, assigned_doc, triage_note = p_info if p_info else (25, selected_dept, "None")
            assigned_doc = str(assigned_doc).strip()
            
            history_df = pd.read_sql_query(
                "SELECT id AS ID, consultation_date AS [Date], doctor AS [Doctor], symptoms AS [Symptoms], "
                "diagnosed_disease AS [Diagnosis], prescription AS [Rx], notes AS [Notes] "
                "FROM consultations WHERE patient_name = ? ORDER BY id DESC",
                conn, params=(selected_patient,)
            )
            conn.close()

            st.info(f"📋 **Assigned Specialist:** {assigned_doc}  |  **Patient Age:** {p_age_val}  |  **Triage Report:** {triage_note}")
            if not history_df.empty:
                st.dataframe(history_df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

            # Filter symptoms for the assigned doctor first (fallback to all if none match)
            doc_rules = rules_df[rules_df["doctor"] == assigned_doc]
            active_rules = doc_rules if not doc_rules.empty else rules_df
            symptom_variants = active_rules["symptom"].unique().tolist()

            col_d, col_p = st.columns(2)
            with col_d:
                chosen_symptom = st.selectbox("Presenting Symptom:", symptom_variants)
                matched_rules = active_rules[active_rules["symptom"] == chosen_symptom]
                chosen_disease = st.selectbox("Diagnosed Condition:", matched_rules["disease"].tolist())
            with col_p:
                # FIXED: Added [0] index to extract dictionary from to_dict("records") list
                rule_records = matched_rules[matched_rules["disease"] == chosen_disease].to_dict("records")
                rule_row = rule_records[0] if rule_records else {"prescription": "", "medicine": "None"}
                suggested_rx = rule_row["prescription"]
                target_med = str(rule_row["medicine"]).strip()
                st.info(f"**Recommended Protocol:** {suggested_rx}\n\n**Primary Medicine:** `{target_med}`")
                final_rx = st.text_area("Finalized Prescription:", value=suggested_rx, height=70)
                notes = st.text_input("Clinical Notes:")

            if st.button("🚀 Log & Finalize Case", type="primary"):
                conn = sqlite3.connect("hospital_v2.db")
                cursor = conn.cursor()
                med_price = 0.0
                if target_med and target_med != "None":
                    price_row = cursor.execute("SELECT unit_price FROM inventory WHERE medicine_name = ?", (target_med,)).fetchone()
                    if price_row:
                        med_price = float(price_row[0])
                        cursor.execute("UPDATE inventory SET stock_qty = MAX(0, stock_qty - 1) WHERE medicine_name = ?", (target_med,))
                
                consult_time = datetime.now().strftime("%Y-%m-%d %H:%M")
                cursor.execute(
                    "INSERT INTO consultations (patient_name, patient_age, doctor, symptoms, diagnosed_disease, prescription, medicine_dispensed, medicine_cost, notes, consultation_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (selected_patient, p_age_val, assigned_doc, chosen_symptom, chosen_disease, final_rx, target_med, med_price, notes, consult_time)
                )
                cursor.execute("UPDATE appointments SET status = 'Completed' WHERE patient_name = ?", (selected_patient,))
                conn.commit()
                conn.close()
                st.success("✅ Case finalized and pharmacy inventory updated!")
                st.rerun()
    else:
        st.warning(f"📭 No scheduled appointments found for **{selected_dept}**.")
