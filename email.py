# app.py
"""
Minimal Streamlit app for sending daily emails to financial institutions.
- No login system: uses static pre-assigned authorization codes in SQLite
- Email credentials isolated in .env file (never exposed to frontend)
- Single-file structure with strict validation and audit logging
"""

import streamlit as st
import sqlite3
import smtplib
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import COMMASPACE
from email import encoders
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file (credentials isolated)
load_dotenv()

# Database path (SQLite file created in working directory)
DB_PATH = "app.db"

# Email regex pattern for CC validation (simple but effective for internal use)
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

# File validation constants (enforce Gmail limits)
MAX_FILE_SIZE_MB = 10
MAX_TOTAL_SIZE_MB = 25
ALLOWED_EXTENSIONS = {'.pdf', '.docx'}


def init_db():
    """Initialize SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table: stores staff users with static auth codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            auth_code TEXT NOT NULL
        )
    ''')
    
    # Create institutions table: stores financial institution contacts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            contact TEXT
        )
    ''')
    
    # Create email_logs table: audit trail for successful sends ONLY
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            institution_id INTEGER NOT NULL,
            ref_no TEXT NOT NULL,
            recipients TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (institution_id) REFERENCES institutions(id)
        )
    ''')
    
    # Insert 3 sample users with static auth codes (if not exists)
    sample_users = [
        ('Barun Kumar Jha', 'AUTH001'),
        ('Jasmin Regmi', 'AUTH002'),
        ('Rajendra Kafle', 'AUTH003'),
        ('Raj Kumar Tamang', 'AUTH004'),
    ]
    for name, auth_code in sample_users:
        cursor.execute(
            'INSERT OR IGNORE INTO users (name, auth_code) VALUES (?, ?)',
            (name, auth_code)
        )
    
    # Insert 3 sample institutions (if not exists)
    sample_institutions = [
        ('Nepal Rastra Bank', 'info@nrb.org.np', "9851421542"),
        ('Everest Bank', 'contact@everestbank.com', "9851421542"),
        ('Himalayan Bank', 'support@himalayanbank.com', "9851421542"),
    ]
    for name, email, contact in sample_institutions:
        cursor.execute(
            'INSERT OR IGNORE INTO institutions (name, email, contact) VALUES (?, ?, ?)',
            (name, email, contact)
        )
    
    conn.commit()
    conn.close()


def get_users_with_auth(conn):
    """Fetch all users with auth codes for server-side validation (never exposed to UI)."""
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, auth_code FROM users ORDER BY name')
    return cursor.fetchall()


def get_institutions(conn):
    """Fetch all institutions for dropdown population."""
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, email, contact FROM institutions ORDER BY name')
    return cursor.fetchall()


def validate_ref_no(ref_no):
    """
    Validate reference number: exactly 9 chars, starts with 'RK' (case-insensitive).
    Returns: (is_valid: bool, result: str)
    - result is uppercase validated ref_no if valid, else error message
    """
    if not ref_no or not ref_no.strip():
        return False, "Reference number is required"
    
    ref_clean = ref_no.strip().upper()
    
    if len(ref_clean) != 9:
        return False, f"Must be exactly 9 characters (got {len(ref_clean)})"
    
    if not ref_clean.startswith("RK"):
        return False, "Must start with 'RK'"
    
    return True, ref_clean


def validate_single_email(email):
    """Validate a single email address using regex."""
    email = email.strip()
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email))


def validate_cc_emails(cc_input):
    """
    Validate comma-separated CC emails. Optional field.
    Returns: (is_valid: bool, result: list or str)
    - result is list of validated emails if valid, else error message
    """
    if not cc_input or not cc_input.strip():
        return True, []  # Optional: empty is valid
    
    emails = []
    for raw in cc_input.split(','):
        email = raw.strip()
        if email:  # Skip empty from trailing commas
            if not validate_single_email(email):
                return False, f"Invalid format: '{email}'"
            emails.append(email)
    
    return True, emails


def validate_file(uploaded_file):
    """Validate single file: extension and size."""
    _, ext = os.path.splitext(uploaded_file.name)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        return False, f"Type not allowed: '{uploaded_file.name}' (only .pdf, .docx)"
    
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if uploaded_file.size > max_bytes:
        return False, f"Too large: '{uploaded_file.name}' (max {MAX_FILE_SIZE_MB}MB)"
    
    return True, None


def validate_files(files):
    """Validate file list: individual checks + total size limit."""
    if not files:
        return False, "At least one file required"
    
    total_bytes = 0
    for f in files:
        valid, err = validate_file(f)
        if not valid:
            return False, err
        total_bytes += f.size
    
    max_total = MAX_TOTAL_SIZE_MB * 1024 * 1024
    if total_bytes > max_total:
        return False, f"Total size ({total_bytes/1024/1024:.1f}MB) exceeds {MAX_TOTAL_SIZE_MB}MB limit"
    
    return True, None


def send_email_via_gmail(institution_email, cc_emails, files, ref_no):
    """
    Send email via Gmail SMTP (SSL, port 465).
    - Credentials loaded from .env via os.getenv (never printed/exposed)
    - Fixed subject: "रोक्का जानकारी", empty body
    - msg['To']/msg['Cc'] as strings; sendmail() recipients as list
    """
    gmail_user = os.getenv('GMAIL_USER')
    gmail_pass = os.getenv('GMAIL_APP_PASSWORD')
    
    if not gmail_user or not gmail_pass:
        raise RuntimeError("Email credentials missing. Check .env file.")
    
    # Build MIME message
    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = institution_email  # String for header
    msg['Subject'] = "रोक्का जानकारी"
    
    if cc_emails:
        msg['Cc'] = COMMASPACE.join(cc_emails)  # String for header
    
    msg.attach(MIMEText('', 'plain'))  # Empty body per spec
    
    # Attach files (preserve original filenames)
    for f in files:
        f.seek(0)  # Reset pointer
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{f.name}"')
        msg.attach(part)
    
    # sendmail() requires list of ALL recipients (To + CC)
    recipients_list = [institution_email] + cc_emails
    
    # Send via SMTP SSL
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, recipients_list, msg.as_string())


def log_success(conn, user_id, inst_id, ref_no, recipients_str, sent_at):
    """Log successful send to email_logs (only successes logged per requirements)."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO email_logs (user_id, institution_id, ref_no, recipients, sent_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, inst_id, ref_no, recipients_str, sent_at, 'sent'))
    conn.commit()


def main():
    """Main Streamlit app entry point."""
    st.set_page_config(page_title="Daily Email Sender", page_icon="📧", layout="centered")
    st.title("📧 Daily Email Sender")
    st.caption("Internal tool for financial institution communications")
    
    # Initialize DB with tables + sample data
    init_db()
    conn = sqlite3.connect(DB_PATH)
    
    # Fetch data for dropdowns
    users_data = get_users_with_auth(conn)  # [(id, name, auth_code), ...]
    inst_data = get_institutions(conn)       # [(id, name, email, contact), ...]
    
    # Build lookup dicts (auth_code used server-side only, never exposed)
    user_lookup = {name: {'id': uid, 'auth': auth} for uid, name, auth in users_data}
    inst_lookup = {name: {'id': iid, 'email': email} for iid, name, email, _ in inst_data}
    
    # Use st.form to prevent duplicate sends on Streamlit reruns
    with st.form("email_form", clear_on_submit=False):
        st.subheader("Compose Email")
        
        # Field 1: Select User
        sel_user = st.selectbox("Select User", [n for _, n, _ in users_data], 
                               index=None, placeholder="👤 Choose your name...")
        
        # Field 2: Select Institution
        sel_inst = st.selectbox("Select Institution", [n for _, n, _, _ in inst_data],
                               index=None, placeholder="🏦 Choose recipient...")
        
        # Field 3: CC Emails (optional)
        cc_input = st.text_input("CC Emails (optional)", 
                                placeholder="manager@bank.com, auditor@firm.org",
                                help="Comma-separated; each validated individually")
        
        # Field 4: Reference Number (strict: 9 chars, starts with RK)
        ref_input = st.text_input("Reference Number", placeholder="RK1234567",
                                 help="Exactly 9 characters, must start with 'RK'")
        
        # Field 5: Authorization Code (static, per-user, masked input)
        auth_input = st.text_input("Authorization Code", type="password",
                                  placeholder="Enter your pre-assigned code",
                                  help="Static code assigned to your account")
        
        # Field 6: File Upload (multiple, type/size validated)
        files = st.file_uploader("Attach Documents", type=['pdf', 'docx'],
                                accept_multiple_files=True,
                                help=f"Max {MAX_FILE_SIZE_MB}MB/file, total <{MAX_TOTAL_SIZE_MB}MB")
        
        # Submit Button
        submitted = st.form_submit_button("📤 Send Email")
        
        if submitted:
            # === VALIDATION PIPELINE ===
            
            # 1. Required selections
            if not sel_user or not sel_inst:
                st.error("❌ Select both user and institution")
            elif not files:
                st.error("❌ Attach at least one document")
            else:
                # 2. Validate ref_no
                ref_ok, ref_res = validate_ref_no(ref_input)
                if not ref_ok:
                    st.error(f"❌ Reference: {ref_res}")
                else:
                    ref_val = ref_res  # Uppercase validated
                    
                    # 3. Validate CC emails
                    cc_ok, cc_res = validate_cc_emails(cc_input)
                    if not cc_ok:
                        st.error(f"❌ CC Emails: {cc_res}")
                    else:
                        cc_val = cc_res  # List of validated emails
                        
                        # 4. Verify auth code (server-side, never exposed)
                        user_info = user_lookup.get(sel_user)
                        if not user_info or auth_input != user_info['auth']:
                            st.error("❌ Authorization code mismatch")
                        else:
                            # 5. Validate files
                            files_ok, files_err = validate_files(files)
                            if not files_ok:
                                st.error(f"❌ Attachments: {files_err}")
                            else:
                                # === ALL VALIDATIONS PASSED: SEND EMAIL ===
                                try:
                                    inst_info = inst_lookup[sel_inst]
                                    to_email = inst_info['email']
                                    
                                    # Send via Gmail SMTP
                                    send_email_via_gmail(
                                        institution_email=to_email,
                                        cc_emails=cc_val,
                                        files=files,
                                        ref_no=ref_val
                                    )
                                    
                                    # Log success (only successful sends logged)
                                    sent_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    all_recipients = [to_email] + cc_val
                                    recipients_log = COMMASPACE.join(all_recipients)
                                    
                                    log_success(
                                        conn=conn,
                                        user_id=user_info['id'],
                                        inst_id=inst_info['id'],
                                        ref_no=ref_val,
                                        recipients_str=recipients_log,
                                        sent_at=sent_ts
                                    )
                                    
                                    st.success(f"✅ Sent! Ref: {ref_val}")
                                    st.info(f"📬 To: {to_email}" + 
                                           (f" | CC: {', '.join(cc_val)}" if cc_val else ""))
                                    
                                except RuntimeError as e:
                                    st.error(f"❌ Config Error: {e}")
                                except smtplib.SMTPAuthenticationError:
                                    st.error("❌ Auth failed. Check GMAIL_APP_PASSWORD in .env")
                                except smtplib.SMTPException as e:
                                    st.error(f"❌ SMTP Error: {e}")
                                except ConnectionError:
                                    st.error("❌ Network error. Check internet connection")
                                except Exception:
                                    st.error("❌ Unexpected error. Please retry or contact support")
    
    conn.close()
    
    # Footer security note
    st.markdown("---")
    st.caption("🔐 Credentials from .env only. Never logged or exposed. Gmail App Password required.")


if __name__ == "__main__":
    main()
