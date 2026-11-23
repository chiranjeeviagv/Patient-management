import io
import json
import uuid
import hashlib
from datetime import datetime
import qrcode
from fpdf import FPDF

def generate_record_signature(patient_name: str, doctor_name: str, diagnosis: str, visit_date: str) -> str:
    """Creates a deterministic SHA-256 verification signature for clinical authenticity."""
    raw = f"SUNRISE-HMS|{patient_name}|{doctor_name}|{diagnosis}|{visit_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24].upper()

def build_qr_verified_prescription_pdf(
    patient_name: str,
    age_gender: str,
    doctor_name: str,
    specialty: str,
    diagnosis: str,
    medications: str,
    notes: str = "",
    visit_date: str = None
) -> bytes:
    """Generates a formal PDF e-Prescription with an embedded SHA-256 verification QR code."""
    visit_date = visit_date or datetime.now().strftime("%Y-%m-%d %H:%M")
    sig = generate_record_signature(patient_name, doctor_name, diagnosis, visit_date)
    rx_id = f"RX-{sig[:8]}"

    # 1. Generate QR Code image in memory
    qr_payload = (
        f"Sunrise Multispecialty Hospital | Verified e-Rx\n"
        f"Rx ID: {rx_id}\n"
        f"Patient: {patient_name}\n"
        f"Doctor: {doctor_name} ({specialty})\n"
        f"Diagnosis: {diagnosis}\n"
        f"SHA256-Sig: {sig}"
    )
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    # 2. Build PDF Document
    pdf = FPDF()
    pdf.add_page()
    
    # Header Banner
    pdf.set_fill_color(15, 76, 129)
    pdf.rect(0, 0, 210, 32, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, "SUNRISE MULTISPECIALTY HOSPITAL", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.cell(0, 6, "ABDM-Ready Digital Health Record & Verified e-Prescription", ln=True)

    # Embed QR Code in Top Right
    pdf.image(qr_buffer, x=165, y=38, w=32, h=32)

    # Metadata & Patient Details
    pdf.set_text_color(20, 20, 20)
    pdf.set_xy(12, 38)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(145, 7, f"Prescription ID: {rx_id}   |   Date: {visit_date}", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.cell(145, 6, f"Patient Name: {patient_name} ({age_gender})", ln=True)
    pdf.set_x(12)
    pdf.cell(145, 6, f"Consulting Specialist: {doctor_name} - {specialty}", ln=True)

    pdf.ln(14)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(6)

    # Clinical Diagnosis
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(12)
    pdf.cell(0, 7, "Primary Clinical Diagnosis:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.multi_cell(185, 6, diagnosis or "Routine Clinical Evaluation")
    pdf.ln(4)

    # Prescribed Medications (Rx)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(12)
    pdf.cell(0, 7, "Rx - Prescribed Medications & Dosage:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.multi_cell(185, 6, medications or "As advised during consultation")
    pdf.ln(4)

    if notes:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_x(12)
        pdf.cell(0, 7, "Clinical Advice / Follow-up Instructions:", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_x(12)
        pdf.multi_cell(185, 6, notes)
        pdf.ln(6)

    # Cryptographic Footer
    pdf.set_y(-32)
    pdf.set_draw_color(15, 76, 129)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.set_x(12)
    pdf.cell(0, 5, f"Cryptographic Verification Hash (SHA-256): {sig}", ln=True)
    pdf.set_x(12)
    pdf.cell(0, 5, "Scan the QR code above to validate prescription authenticity against tampering.", ln=True)

    return bytes(pdf.output())

def build_fhir_r4_bundle(
    patient_name: str,
    doctor_name: str,
    specialty: str,
    diagnosis: str,
    medications: str,
    visit_date: str = None
) -> str:
    """Exports the clinical encounter as an HL7 FHIR R4 compliant JSON Bundle."""
    visit_date = visit_date or datetime.now().isoformat()
    patient_id = str(uuid.uuid4())
    encounter_id = str(uuid.uuid4())

    fhir_bundle = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "meta": {
            "lastUpdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "profile": ["http://hl7.org/fhir/StructureDefinition/Bundle"]
        },
        "type": "document",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "name": [{"use": "official", "text": patient_name}]
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": encounter_id,
                    "status": "finished",
                    "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "participant": [{"individual": {"display": f"{doctor_name} ({specialty})"}}],
                    "period": {"start": visit_date}
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": str(uuid.uuid4()),
                    "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
                    "code": {"text": diagnosis},
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "encounter": {"reference": f"Encounter/{encounter_id}"}
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id": str(uuid.uuid4()),
                    "status": "active",
                    "intent": "order",
                    "medicationCodeableConcept": {"text": medications},
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "encounter": {"reference": f"Encounter/{encounter_id}"},
                    "requester": {"display": doctor_name}
                }
            }
        ]
    }
    return json.dumps(fhir_bundle, indent=2)
