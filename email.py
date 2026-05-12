import os
import re
import ssl
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage

import streamlit as st
from dotenv import load_dotenv

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Financial Email Sender",
    page_icon="📧",
    layout="centered"
)

# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# =========================================================
# DATABASE
# =========================================================

DB_NAME = "app.db"

conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# ---------------- USERS ----------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    auth_code TEXT NOT NULL
)
""")

# ---------------- INSTITUTIONS ----------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS institutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL
)
""")

# ---------------- EMAIL LOGS ----------------

cursor.execute("""
CREATE TABLE IF NOT EXISTS email_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    institution_name TEXT NOT NULL,
    recipients TEXT NOT NULL,
    ref_no TEXT NOT NULL,
    sent_at TEXT NOT NULL
)
""")

conn.commit()

# =========================================================
# INSERT SAMPLE DATA
# =========================================================
# sample_users = [
#     ("Raj Kumar Tamang", "Auth001"),
#     ("Barun Kumar Jha", "Auth002"),
#     ("Rajendra Kafle", "Auth003"),
#     ("Jasmin Regmi", "Auth004")
# ]

# sample_institutions = [
#     ("Nepal Bank", "info@nepalbank.com"),
#     ("Nabil Bank", "support@nabilbank.com"),
#     ("Global IME", "contact@globalimebank.com")
# ]

# for user in sample_users:
#     cursor.execute("""
#     INSERT OR IGNORE INTO users (name, auth_code)
#     VALUES (?, ?)
#     """, user)

# for inst in sample_institutions:
#     cursor.execute("""
#     INSERT OR IGNORE INTO institutions (name, email)
#     VALUES (?, ?)
#     """, inst)

# conn.commit()

# =========================================================
# CONSTANTS
# =========================================================

ALLOWED_EXTENSIONS = [".pdf", ".docx"]

MAX_FILE_SIZE = 10 * 1024 * 1024       # 10MB
MAX_TOTAL_SIZE = 25 * 1024 * 1024      # 25MB

# =========================================================
# SESSION STATE
# =========================================================

if "show_auth_popup" not in st.session_state:
    st.session_state.show_auth_popup = False

if "form_data" not in st.session_state:
    st.session_state.form_data = {}

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def validate_ref_no(ref_no):
    """
    Rules:
    - Exactly 9 characters
    - Starts with RK
    """

    ref_no = ref_no.upper()

    return (
        len(ref_no) == 9
        and ref_no.startswith("RK")
    )


def validate_email(email):

    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

    return re.match(pattern, email)


def validate_cc_emails(cc_text):

    if not cc_text.strip():
        return True, []

    emails = [
        e.strip()
        for e in cc_text.split(",")
        if e.strip()
    ]

    for email in emails:

        if not validate_email(email):
            return False, []

    return True, emails


def validate_files(uploaded_files):

    total_size = 0

    for file in uploaded_files:

        ext = os.path.splitext(
            file.name
        )[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            return (
                False,
                f"Invalid file type: {file.name}"
            )

        if file.size > MAX_FILE_SIZE:
            return (
                False,
                f"{file.name} exceeds 10MB limit"
            )

        total_size += file.size

    if total_size > MAX_TOTAL_SIZE:
        return (
            False,
            "Total attachment size exceeds 25MB"
        )

    return True, ""


def get_users():

    cursor.execute("""
    SELECT name
    FROM users
    ORDER BY name
    """)

    return [row[0] for row in cursor.fetchall()]


def get_institutions():

    cursor.execute("""
    SELECT name, email
    FROM institutions
    ORDER BY name
    """)

    return cursor.fetchall()


def verify_auth_code(user_name, auth_code):

    cursor.execute("""
    SELECT auth_code
    FROM users
    WHERE name = ?
    """, (user_name,))

    result = cursor.fetchone()

    if not result:
        return False

    return auth_code == result[0]


def send_email(
    to_email,
    cc_list,
    uploaded_files
):

    msg = EmailMessage()

    msg["Subject"] = "रोक्का जानकारी"

    msg["From"] = GMAIL_USER

    msg["To"] = to_email

    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg.set_content("")

    # ---------------- ATTACH FILES ----------------

    for file in uploaded_files:

        file_data = file.read()

        ext = os.path.splitext(
            file.name
        )[1].lower()

        if ext == ".pdf":

            maintype = "application"
            subtype = "pdf"

        elif ext == ".docx":

            maintype = "application"

            subtype = (
                "vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

        else:
            continue

        msg.add_attachment(
            file_data,
            maintype=maintype,
            subtype=subtype,
            filename=file.name
        )

    recipients = [to_email] + cc_list

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        context=context
    ) as server:

        server.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )

        server.send_message(
            msg,
            from_addr=GMAIL_USER,
            to_addrs=recipients
        )


def log_email(
    user_name,
    institution_name,
    recipients,
    ref_no
):

    cursor.execute("""
    INSERT INTO email_logs (
        user_name,
        institution_name,
        recipients,
        ref_no,
        sent_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        user_name,
        institution_name,
        recipients,
        ref_no,
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    ))

    conn.commit()

# =========================================================
# UI
# =========================================================

st.title("📧 Daily Email Sender")

users = get_users()

institutions = get_institutions()

institution_names = [
    inst[0]
    for inst in institutions
]

institution_email_map = {
    name: email
    for name, email in institutions
}


st.sidebar.title("User")

selected_user = st.sidebar.selectbox(
    "Select User",
    users
)

# =========================================================
# MAIN FORM
# =========================================================

with st.form("email_form"):

    uploaded_files = st.file_uploader(
        "Upload Documents (.pdf, .docx)",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )

    selected_institution = st.selectbox(
        "Select Institution",
        institution_names
    )

    cc_emails = st.text_input(
        "CC Emails (optional)",
        placeholder="manager@bank.com, auditor@firm.org"
    )

    ref_no = st.text_input(
        "Reference Number",
        placeholder="RK1234567"
    ).upper()

    submitted = st.form_submit_button(
        "Send Email"
    )

# =========================================================
# FORM VALIDATION
# =========================================================

if submitted:

    # ---------------- ENV CHECK ----------------

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:

        st.error(
            "Email credentials missing in .env"
        )

        st.stop()

    # ---------------- REF VALIDATION ----------------

    if not validate_ref_no(ref_no):

        st.error(
            "Reference Number must:\n"
            "- Start with RK\n"
            "- Be exactly 9 characters"
        )

        st.stop()

    # ---------------- FILE CHECK ----------------

    if not uploaded_files:

        st.error(
            "Please upload at least one file."
        )

        st.stop()

    files_valid, file_error = validate_files(
        uploaded_files
    )

    if not files_valid:

        st.error(file_error)

        st.stop()

    # ---------------- CC VALIDATION ----------------

    cc_valid, cc_list = validate_cc_emails(
        cc_emails
    )

    if not cc_valid:

        st.error(
            "Invalid CC email format."
        )

        st.stop()

    # ---------------- SAVE FORM DATA ----------------

    st.session_state.form_data = {

        "selected_user": selected_user,

        "uploaded_files": uploaded_files,

        "selected_institution": selected_institution,

        "cc_list": cc_list,

        "ref_no": ref_no
    }

    # OPEN POPUP

    st.session_state.show_auth_popup = True

    st.rerun()

# =========================================================
# AUTH POPUP
# =========================================================

@st.dialog("Authorization Required")
def auth_popup():

    st.write(
        "Enter authorization code to send email."
    )

    auth_code = st.text_input(
        "Authorization Code",
        type="password"
    )

    col1, col2 = st.columns(2)

    with col1:

        send_btn = st.button(
            "Confirm & Send",
            use_container_width=True
        )

    with col2:

        cancel_btn = st.button(
            "Cancel",
            use_container_width=True
        )

    # ---------------- CANCEL ----------------

    if cancel_btn:

        st.session_state.show_auth_popup = False

        st.rerun()

    # ---------------- SEND ----------------

    if send_btn:

        data = st.session_state.form_data

        selected_user = data["selected_user"]

        uploaded_files = data["uploaded_files"]

        selected_institution = data[
            "selected_institution"
        ]

        cc_list = data["cc_list"]

        ref_no = data["ref_no"]

        # ------------ VERIFY AUTH ------------

        if not verify_auth_code(
            selected_user,
            auth_code
        ):

            st.error(
                "Invalid authorization code."
            )

            return

        try:

            to_email = institution_email_map[
                selected_institution
            ]

            send_email(
                to_email=to_email,
                cc_list=cc_list,
                uploaded_files=uploaded_files
            )

            # RECIPIENTS

            all_recipients = (
                [to_email] + cc_list
            )

            recipients_str = ", ".join(
                all_recipients
            )

            # LOG SUCCESS

            log_email(
                user_name=selected_user,
                institution_name=selected_institution,
                recipients=recipients_str,
                ref_no=ref_no
            )

            # RESET STATE

            st.session_state.show_auth_popup = False

            st.session_state.form_data = {}

            st.success(
                "✅ Email sent successfully."
            )

            st.rerun()

        except smtplib.SMTPAuthenticationError:

            st.error(
                "SMTP Authentication failed. "
                "Check Gmail App Password."
            )

        except smtplib.SMTPException as e:

            st.error(
                f"SMTP Error: {str(e)}"
            )

        except Exception as e:

            st.error(
                f"Unexpected Error: {str(e)}"
            )

# =========================================================
# SHOW POPUP
# =========================================================

if st.session_state.show_auth_popup:

    auth_popup()
