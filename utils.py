import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import hashlib
import random
import requests

# --- OFFICIAL UIDAI VERHOEFF CHECKSUM VALIDATION ---
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

def is_valid_aadhaar_format(aadhaar_str: str) -> bool:
    """Validates 12 digits, non-zero/one start, and official UIDAI Verhoeff checksum."""
    digits = "".join(ch for ch in str(aadhaar_str) if ch.isdigit())
    if len(digits) != 12 or digits[0] in ("0", "1"):
        return False
    c = 0
    for idx, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[idx % 8][int(ch)]]
    return c == 0

def mask_and_hash_aadhaar(aadhaar_str: str, salt: str = "HOSPITAL_EHEALTH_2026") -> tuple[str, str]:
    """Returns (masked_display, sha256_reference_hash) so raw Aadhaar is never stored."""
    digits = "".join(ch for ch in str(aadhaar_str) if ch.isdigit())
    masked = f"XXXX-XXXX-{digits[-4:]}"
    ref_hash = hashlib.sha256(f"{salt}:{digits}".encode("utf-8")).hexdigest()
    return masked, ref_hash

def send_aadhaar_otp(aadhaar_digits: str) -> dict:
    """
    Triggers OTP via licensed KYC provider (if configured in st.secrets)
    or runs in Sandbox Demo mode for immediate testing.
    """
    if "KYC_API_KEY" in st.secrets and "KYC_BASE_URL" in st.secrets:
        resp = requests.post(
            f"{st.secrets['KYC_BASE_URL']}/aadhaar/otp",
            headers={"x-api-key": st.secrets["KYC_API_KEY"], "Content-Type": "application/json"},
            json={"aadhaar_number": aadhaar_digits},
            timeout=15,
        )
        return resp.json()
    # Sandbox Demo Fallback
    demo_otp = str(random.randint(100000, 999999))
    return {"status": "sandbox", "ref_id": f"REF-{random.randint(10000,99999)}", "demo_otp": demo_otp}
# Morning (09:00 AM - 02:00 PM) & Afternoon/Evening (03:00 PM - 09:00 PM)
ALL_TIME_SLOTS = (
    "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM",
    "11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM",
    "01:00 PM", "01:30 PM",
    "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM",
    "05:00 PM", "05:30 PM", "06:00 PM", "06:30 PM",
    "07:00 PM", "07:30 PM", "08:00 PM", "08:30 PM"
)

def load_clinical_data():
    for enc in ("utf-8-sig", "cp1252", "latin1"):
        try:
            doctors_df = pd.read_csv("data/doctors.csv", encoding=enc)
            rules_df = pd.read_csv("data/clinical_rules.csv", encoding=enc).fillna("None")
            return doctors_df, rules_df
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, "Unable to decode CSV files with utf-8 or cp1252.")

def apply_custom_ui():
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #f0f4f8;
            background-image: 
                radial-gradient(at 0% 0%, rgba(23, 185, 120, 0.14) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(30, 61, 89, 0.14) 0px, transparent 50%);
            background-attachment: fixed;
        }
        [data-testid="stForm"], [data-testid="stDataFrame"], [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.90);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 18px;
            border: 1px solid rgba(30, 61, 89, 0.12);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
        }
        [data-testid="stSidebar"] [data-testid="stAlert"] {
            background-color: #e8f8f2 !important;
        }
        [data-testid="stSidebar"] [data-testid="stAlert"] * {
            color: #162e44 !important;
        }
        [data-testid="stSidebar"] input {
            color: #1e3d59 !important;
        }
        .hero-banner {
            background: linear-gradient(135deg, #1e3d59 0%, #17b978 100%);
            padding: 24px 30px;
            border-radius: 14px;
            color: white;
            margin-bottom: 24px;
            box-shadow: 0 8px 20px rgba(30, 61, 89, 0.15);
        }
        .hero-banner h1 { color: white !important; margin: 0; font-size: 1.9rem; }
        .hero-banner p { color: rgba(255, 255, 255, 0.92); margin: 6px 0 0 0; font-size: 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_hero(title, subtitle):
    st.markdown(f'<div class="hero-banner"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)

def require_login(role_name, expected_password):
    st.sidebar.markdown(f"#### 🔐 {role_name} Login")
    pwd = st.sidebar.text_input("Enter Access Password:", type="password", key=f"auth_{role_name}")
    if pwd == expected_password:
        st.sidebar.success("🔒 Access Granted")
        return True
    if pwd != "":
        st.sidebar.error("❌ Invalid Access Token")
    render_hero("🔒 Restricted Clinical Access Area", "Authorized medical personnel only. Enter your access token in the sidebar.")
    st.warning("Please provide the correct credentials in the sidebar to unlock this dashboard.")
    return False

def init_db():
    conn = sqlite3.connect("hospital_v2.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            patient_age INTEGER,
            patient_gender TEXT,
            patient_contact TEXT,
            patient_problem TEXT,
            doctor TEXT NOT NULL,
            appt_date TEXT NOT NULL DEFAULT '',
            appt_time TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            patient_age INTEGER,
            doctor TEXT NOT NULL DEFAULT 'Attending Specialist',
            symptoms TEXT NOT NULL,
            diagnosed_disease TEXT NOT NULL,
            prescription TEXT NOT NULL,
            medicine_dispensed TEXT NOT NULL DEFAULT 'None',
            medicine_cost REAL NOT NULL DEFAULT 0.0,
            notes TEXT,
            consultation_date TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            stock_qty INTEGER NOT NULL,
            min_required INTEGER NOT NULL,
            unit_price REAL NOT NULL DEFAULT 150.0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            doctor_assigned TEXT NOT NULL,
            consultation_fee REAL NOT NULL,
            medicine_fee REAL NOT NULL DEFAULT 0.0,
            tax_amount REAL NOT NULL,
            grand_total REAL NOT NULL,
            payment_status TEXT NOT NULL,
            billing_date TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            department TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comments TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        )
    ''')
    medicines = [
        ('Paracetamol 650mg', 'Analgesic / Antipyretic', 120, 30, 45.0),
        ('Artemether-Lumefantrine', 'Antimalarial', 15, 10, 240.0),
        ('Dextromethorphan Syr.', 'Antitussive Cough Syrup', 45, 15, 110.0),
        ('Budesonide Inhaler', 'Bronchodilator', 8, 10, 380.0),
        ('Pantoprazole 40mg', 'Antacid / PPI', 350, 100, 95.0),
        ('Rabeprazole Combo', 'Antacid / GERD Support', 180, 40, 140.0),
        ('Naproxen 500mg', 'NSAID / Anti-inflammatory', 90, 30, 125.0),
        ('Febuxostat 40mg', 'Uric Acid Lowering Therapy', 60, 20, 190.0),
        ('Fluticasone Nasal Spray', 'ENT Nasal Corticosteroid', 55, 15, 310.0),
        ('Amoxicillin-Clavulanate 625mg', 'Broad-Spectrum Antibiotic', 85, 25, 220.0),
        ('Betahistine 16mg', 'Antivertigo Agent', 70, 20, 165.0),
        ('Ciprofloxacin Ear Drops', 'Otic Antibiotic', 40, 15, 85.0),
        ('Sumatriptan 50mg', 'Antimigraine / Triptan', 75, 20, 260.0),
        ('Levetiracetam 500mg', 'Anticonvulsant', 110, 30, 290.0),
        ('Pregabalin 75mg', 'Neuropathic Pain Agent', 95, 25, 210.0),
        ('Moxifloxacin Eye Drops', 'Ophthalmic Antibiotic', 40, 15, 145.0),
        ('Carboxymethylcellulose Drops', 'Ocular Lubricant', 65, 20, 130.0),
        ('Timolol 0.5% Eye Drops', 'Antiglaucoma Agent', 30, 10, 175.0),
        ('Sertraline 50mg', 'SSRI Antidepressant', 140, 40, 185.0),
        ('Escitalopram 10mg', 'SSRI Anxiolytic', 160, 40, 195.0),
        ('Melatonin 5mg', 'Sleep Regulator', 85, 25, 150.0),
        ('Myo-Inositol + Folic Acid', 'PCOS Metabolic Support', 90, 25, 340.0),
        ('Mefenamic Acid 250mg', 'Antispasmodic Analgesic', 110, 30, 75.0),
        ('Folic Acid 5mg', 'Prenatal Supplement', 200, 50, 60.0),
        ('Calcium + Vitamin D3', 'Bone & Hormonal Support', 150, 40, 180.0),
        ('Paracetamol Pediatric Drops', 'Pediatric Antipyretic', 80, 15, 65.0),
        ('Saline Nasal Drops', 'Pediatric Respiratory', 90, 15, 45.0),
        ('Ketorolac 10mg', 'Dental Analgesic', 100, 20, 75.0),
        ('Chlorhexidine Mouthwash', 'Dental Antiseptic', 75, 15, 110.0),
        ('Telmisartan 40mg', 'Antihypertensive', 100, 20, 145.0),
        ('Torsemide 10mg', 'Cardiac Diuretic', 85, 15, 95.0),
        ('Cetirizine 10mg', 'Antihistamine / Allergy', 150, 25, 35.0),
        ('Clotrimazole Cream', 'Topical Antifungal', 90, 15, 85.0),
        ('Aceclofenac Combo', 'Orthopedic Analgesic', 110, 20, 110.0),
        ('Etoricoxib 90mg', 'COX-2 Inhibitor / NSAID', 95, 15, 160.0),
        ('Mebeverine 135mg', 'Antispasmodic / GI', 80, 15, 180.0),
        ('Esomeprazole 40mg', 'Antacid / PPI', 120, 20, 130.0),
        ('Tiotropium Rotacaps', 'COPD Bronchodilator', 65, 10, 320.0),
        ('Fluticasone Spray', 'Respiratory Corticosteroid', 70, 12, 290.0),
        ('Metformin 500mg', 'Antidiabetic / Glycemic', 160, 30, 65.0),
        ('Levothyroxine 50mcg', 'Thyroid Hormone', 130, 25, 115.0),
        ('Renal Diet Protocol', 'Nephrology Nutrition Pack', 50, 10, 250.0),
        ('Potassium Citrate Syr.', 'Urinary Alkalizer', 75, 15, 140.0),
        ('Tamsulosin 0.4mg', 'Alpha-Blocker / Urology', 85, 15, 210.0),
        ('Nitrofurantoin 100mg', 'Urinary Antibiotic', 95, 15, 125.0),
        ('Ondansetron 8mg', 'Antiemetic / Oncology', 110, 20, 90.0),
        ('Hydroxychloroquine 200mg', 'DMARD / Immunomodulator', 80, 15, 175.0),
        ('Indomethacin 75mg', 'Rheumatology NSAID', 90, 15, 120.0),
        ('IFT Rehab Protocol', 'Physiotherapy Session', 100, 10, 400.0),
        ('Ultrasound & Exercise', 'Physiotherapy Session', 100, 10, 350.0)
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO inventory (medicine_name, category, stock_qty, min_required, unit_price) VALUES (?, ?, ?, ?, ?)",
        medicines
    )
    conn.commit()
    conn.close()

def build_prescription_pdf(name, doctor, disease, symptoms, rx, notes):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], alignment=TA_CENTER, textColor='#1e3d59', fontSize=24, spaceAfter=6)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], alignment=TA_CENTER, textColor='#17b978', fontSize=10, spaceAfter=20)
    meta_style = ParagraphStyle('DocMeta', parent=styles['Normal'], fontSize=11, leading=16, spaceAfter=8)
    section_title = ParagraphStyle('SecTitle', parent=styles['Heading3'], textColor='#1e3d59', fontSize=14, spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'], fontSize=11, leading=16, leftIndent=10)
    story = [
        Paragraph("🏥 PATIENT HEALTH MANAGEMENT SYSTEM", title_style),
        Paragraph("E-Health Portal Automated Prescription Record System", sub_style),
        Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", meta_style),
        Paragraph(f"<b>Patient Name:</b> {name}", meta_style),
        Paragraph(f"<b>Attending Doctor:</b> {doctor}", meta_style),
        Spacer(1, 10),
        Paragraph("Clinical Diagnostics Summary", section_title),
        Paragraph(f"<b>Presenting Symptoms:</b> {symptoms}", body_style),
        Paragraph(f"<b>Inferred Final Diagnosis:</b> {disease}", body_style),
        Spacer(1, 10),
        Paragraph("💊 Prescribed Medications (Rx Options)", section_title),
        Paragraph(rx.replace('\n', '<br/>'), body_style),
        Spacer(1, 10),
        Paragraph("📝 Lifestyle Advice & Clinical Notes", section_title),
        Paragraph(notes if notes else "No additional restrictions specified.", body_style),
        Spacer(1, 40),
        Paragraph(f"Authorized Signature: <b>{doctor}</b> (Digitally Validated)", ParagraphStyle('Sign', parent=styles['Normal'], alignment=TA_LEFT, fontSize=9))
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def build_invoice_pdf(invoice_id, name, doctor, base_fee, med_fee, med_name, tax, total, status, date_str):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    brand_title = ParagraphStyle('InvBrand', parent=styles['Heading1'], alignment=TA_CENTER, textColor='#1e3d59', fontSize=22, spaceAfter=4)
    brand_sub = ParagraphStyle('InvSub', parent=styles['Normal'], alignment=TA_CENTER, textColor='#777777', fontSize=9, spaceAfter=25)
    inv_title = ParagraphStyle('InvTitle', parent=styles['Heading2'], textColor='#1e3d59', fontSize=14, spaceAfter=15)
    meta_style = ParagraphStyle('InvMeta', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6)
    table_label = ParagraphStyle('TblLabel', parent=styles['Normal'], fontSize=11, leading=16)
    total_style = ParagraphStyle('TblTotal', parent=styles['Heading3'], textColor='#17b978', fontSize=12, leading=16)
    footer_style = ParagraphStyle('InvFoot', parent=styles['Normal'], alignment=TA_CENTER, textColor='#888888', fontSize=8, spaceBefore=40)
    story = [
        Paragraph("🏥 PATIENT HEALTH MANAGEMENT SYSTEM", brand_title),
        Paragraph("123 Health Boulevard, Wellness District | Support: +91 99999 88888", brand_sub),
        Paragraph("<b>PATIENT INVOICE RECEIPT</b>", inv_title),
        Paragraph(f"<b>Invoice ID:</b> #LL-2026-{invoice_id}", meta_style),
        Paragraph(f"<b>Date/Time:</b> {date_str}", meta_style),
        Paragraph(f"<b>Patient Name:</b> {name}", meta_style),
        Paragraph(f"<b>Attending Clinician:</b> {doctor}", meta_style),
        Spacer(1, 15),
        Paragraph("<hr/>", meta_style),
        Spacer(1, 10),
        Paragraph("<b>Itemised Description Charges:</b>", meta_style),
        Spacer(1, 5),
        Paragraph(f"• Clinical Consultation Services Base Fee: <b>₹{base_fee:,.2f}</b>", table_label),
        Paragraph(f"• Pharmacy Dispensed Medication ({med_name}): <b>₹{med_fee:,.2f}</b>", table_label),
        Paragraph(f"• Central Medical Tax Services (18% GST): <b>₹{tax:,.2f}</b>", table_label),
        Spacer(1, 10),
        Paragraph(f"<b>Grand Total Amount Settled: ₹{total:,.2f}</b>", total_style),
        Paragraph(f"<b>Transaction Status:</b> <font color='#17b978'><b>{status}</b></font>", table_label),
        Spacer(1, 30),
        Paragraph("<i>This is a computer-generated transaction record voucher. No physical signature is required.</i>", footer_style)
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
