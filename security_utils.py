import os
import sqlite3
import hashlib
from datetime import datetime
from cryptography.fernet import Fernet

# 1. Key Management: Loads from environment/Streamlit secrets or generates a local key
KEY_FILE = "secret.key"

def load_or_create_key():
    # In production (Streamlit Cloud), store FERNET_KEY in st.secrets
    env_key = os.environ.get("FERNET_KEY")
    if env_key:
        return env_key.encode()
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    return key

CIPHER = Fernet(load_or_create_key())

# 2. Field-Level PII Encryption & Masking
def encrypt_pii(plain_text: str) -> str:
    """Encrypts sensitive fields (Aadhar, diagnosis, phone) before SQLite storage."""
    if not plain_text:
        return ""
    return CIPHER.encrypt(plain_text.encode()).decode()

def decrypt_pii(cipher_text: str) -> str:
    """Decrypts sensitive fields only for authorized roles."""
    if not cipher_text:
        return ""
    try:
        return CIPHER.decrypt(cipher_text.encode()).decode()
    except Exception:
        return "[Encrypted / Invalid Key]"

def mask_aadhar(aadhar_number: str) -> str:
    """Returns masked Aadhar (XXXX-XXXX-1234) for reception/billing UI."""
    clean = "".join(filter(str.isdigit, str(aadhar_number)))
    if len(clean) == 12:
        return f"XXXX-XXXX-{clean[-4:]}"
    return "XXXX-XXXX-XXXX"

# 3. Tamper-Evident SHA-256 Hash-Chained Audit Log
def init_audit_table(db_path="hospital.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS security_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_record TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            record_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def log_audit_event(actor_role: str, actor_id: str, action: str, target_record: str, db_path="hospital.db"):
    """Appends an immutable, hash-chained entry to the audit log."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Fetch the hash of the immediately preceding log entry
    cursor.execute("SELECT record_hash FROM security_audit_logs ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    prev_hash = row[0] if row else "0" * 64  # Genesis hash

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = f"{timestamp}|{actor_role}|{actor_id}|{action}|{target_record}|{prev_hash}"
    record_hash = hashlib.sha256(payload.encode()).hexdigest()

    cursor.execute("""
        INSERT INTO security_audit_logs (timestamp, actor_role, actor_id, action, target_record, prev_hash, record_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, actor_role, actor_id, action, target_record, prev_hash, record_hash))
    
    conn.commit()
    conn.close()

def verify_audit_chain(db_path="hospital.db") -> tuple[bool, str]:
    """Verifies that no database rows were altered or deleted outside the app."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, actor_role, actor_id, action, target_record, prev_hash, record_hash FROM security_audit_logs ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    expected_prev_hash = "0" * 64
    for row in rows:
        log_id, ts, role, aid, action, target, prev_hash, stored_hash = row
        if prev_hash != expected_prev_hash:
            return False, f"Chain broken at Log ID #{log_id}: Previous hash mismatch."
        
        recomputed = hashlib.sha256(f"{ts}|{role}|{aid}|{action}|{target}|{prev_hash}".encode()).hexdigest()
        if recomputed != stored_hash:
            return False, f"Tampering detected at Log ID #{log_id}: Record hash invalid."
        
        expected_prev_hash = stored_hash

    return True, f"Verified {len(rows)} audit records. Integrity intact."
