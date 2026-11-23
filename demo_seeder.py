import sqlite3
from datetime import datetime, timedelta
from utils import load_clinical_data
from security_utils import init_audit_table, log_audit_event

def seed_portfolio_demo_data(db_path="hospital_v2.db"):
    """Populates realistic clinical records on cold start so recruiters see live analytics immediately."""
    init_audit_table(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        count = cursor.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    except sqlite3.Error:
        conn.close()
        return

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

    doc_list = doctors_df["doctor"].tolist()
    if not doc_list:
        conn.close()
        return

    # Inspect actual billing table columns so all NOT NULL constraints are satisfied
    billing_cols_info = cursor.execute("PRAGMA table_info(billing)").fetchall()
    billing_cols = [col[1] for col in billing_cols_info if col[1] != "id"]

    for idx, (p_name, p_age, problem, status, appt_date, slot) in enumerate(sample_patients):
        doc = doc_list[idx % len(doc_list)]
        cursor.execute(
            "INSERT INTO appointments (patient_name, patient_age, doctor, patient_problem, appt_date, appt_time, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p_name, p_age, doc, problem, appt_date, slot, status)
        )

        if status == "Completed":
            doc_rule = rules_df[rules_df["doctor"] == doc]
            if not doc_rule.empty:
                r = doc_rule.iloc[0]
                symp, diag, rx, med = r["symptom"], r["disease"], r["prescription"], str(r["medicine"]).strip()
            else:
                symp, diag, rx, med = problem, "Clinical Evaluation Completed", "Tab. Paracetamol 500mg SOS", "Paracetamol"

            med_cost = 180.0
            consult_fee = 500.0
            sub_total = consult_fee + med_cost
            tax = round(sub_total * 0.18, 2)
            grand_total = round(sub_total + tax, 2)

            cursor.execute(
                "INSERT INTO consultations (patient_name, patient_age, doctor, symptoms, diagnosed_disease, prescription, medicine_dispensed, medicine_cost, notes, consultation_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p_name, p_age, doc, symp, diag, rx, med, med_cost, "Follow-up in 7 days; vitals stable.", f"{appt_date} {slot}")
            )

            if billing_cols:
                default_values = {
                    "invoice_no": f"INV-2026-{1001 + idx}",
                    "patient_name": p_name,
                    "doctor_assigned": doc,
                    "doctor": doc,
                    "consultation_fee": consult_fee,
                    "medicine_fee": med_cost,
                    "sub_total": sub_total,
                    "tax_amount": tax,
                    "grand_total": grand_total,
                    "payment_status": "Paid",
                    "payment_method": "Razorpay UPI",
                    "bill_date": appt_date,
                    "created_at": f"{appt_date} {slot}",
                }
                row_vals = [default_values.get(c, "N/A") for c in billing_cols]
                placeholders = ", ".join(["?"] * len(billing_cols))
                col_names = ", ".join(billing_cols)
                try:
                    cursor.execute(f"INSERT INTO billing ({col_names}) VALUES ({placeholders})", row_vals)
                except sqlite3.Error:
                    pass

    conn.commit()
    conn.close()

    log_audit_event("System_Seeder", "Sunrise_HMS_Init", "SEED_DEMO_RECORDS", "6 Clinical Encounters", db_path=db_path)
    log_audit_event("Doctor", doc_list[0], "FINALIZE_CONSULTATION", "Ramesh Naidu", db_path=db_path)
