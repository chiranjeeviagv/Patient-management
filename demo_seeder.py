import sqlite3
from datetime import datetime, timedelta
from utils import load_clinical_data
from security_utils import init_audit_table, log_audit_event

def seed_portfolio_demo_data(db_path="hospital_v2.db"):
    """Populates realistic clinical records on cold start so recruiters see live analytics immediately."""
    init_audit_table(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if tables exist and whether appointments already have data
    try:
        count = cursor.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    except sqlite3.OperationalError:
        conn.close()
        return  # Let app.py create tables first if not yet initialized

    if count > 0:
        conn.close()
        return

    doctors_df, rules_df = load_clinical_data()
    doctors_df["doctor"] = doctors_df["doctor"].str.strip()
    rules_df["doctor"] = rules_df["doctor"].str.strip()

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    sample_patients = [
        ("Ramesh Naidu", 54, "Chest tightness and mild palpitations", "Completed", yesterday, "10:30 AM"),
        ("Ananya Sharma", 32, "Recurring migraine and visual aura", "Completed", yesterday, "11:15 AM"),
        ("Karthik Varma", 41, "Lower back stiffness after lifting", "Completed", today, "09:45 AM"),
        ("Meenakshi Iyer", 28, "Persistent dry cough and wheezing", "Completed", today, "11:00 AM"),
        ("Suresh Babu", 61, "Elevated fasting blood sugar and fatigue", "Confirmed", today, "04:30 PM"),
        ("Divya Krishnan", 36, "Acute sinus congestion and earache", "Pending", today, "06:00 PM"),
    ]

    # Pick up to 6 distinct doctors from your CSV dataset
    doc_list = doctors_df["doctor"].tolist()
    if not doc_list:
        conn.close()
        return

    for idx, (p_name, p_age, problem, status, appt_date, slot) in enumerate(sample_patients):
        doc = doc_list[idx % len(doc_list)]
        cursor.execute(
            "INSERT INTO appointments (patient_name, patient_age, doctor, patient_problem, appt_date, appt_time, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p_name, p_age, doc, problem, appt_date, slot, status)
        )

        # For Completed cases, also seed consultations & billing ledgers
        if status == "Completed":
            doc_rule = rules_df[rules_df["doctor"] == doc]
            if not doc_rule.empty:
                r = doc_rule.iloc[0]
                symp, diag, rx, med = r["symptom"], r["disease"], r["prescription"], str(r["medicine"]).strip()
            else:
                symp, diag, rx, med = problem, "Clinical Evaluation Completed", "Tab. Paracetamol 500mg SOS", "Paracetamol"

            med_cost = 180.0
            consult_fee = 500.0
            tax = round((consult_fee + med_cost) * 0.18, 2)
            grand_total = round(consult_fee + med_cost + tax, 2)

            cursor.execute(
                "INSERT INTO consultations (patient_name, patient_age, doctor, symptoms, diagnosed_disease, prescription, medicine_dispensed, medicine_cost, notes, consultation_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p_name, p_age, doc, symp, diag, rx, med, med_cost, "Follow-up in 7 days; vitals stable.", f"{appt_date} {slot}")
            )

            # Seed billing record (wrapped in try/except in case column names vary slightly)
            try:
                cursor.execute(
                    "INSERT INTO billing (patient_name, doctor_assigned, consultation_fee, medicine_fee, tax_amount, grand_total, payment_status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (p_name, doc, consult_fee, med_cost, tax, grand_total, "Paid")
                )
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()

    # Log cryptographic audit entries for the seeded clinical actions
    log_audit_event("System_Seeder", "Sunrise_HMS_Init", "SEED_DEMO_RECORDS", "6 Clinical Encounters", db_path=db_path)
    log_audit_event("Doctor", doc_list[0], "FINALIZE_CONSULTATION", "Ramesh Naidu", db_path=db_path)
