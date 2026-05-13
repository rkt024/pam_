import os
import re
import ssl
import sqlite3
import smtplib
from datetime import datetime
from email.message import EmailMessage

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Financial Email Sender",
    page_icon="📧",
    layout="wide"
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
# CONSTANTS
# =========================================================

ALLOWED_EXTENSIONS = [".pdf", ".docx"]

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 25 * 1024 * 1024

# =========================================================
# SESSION STATE
# =========================================================

if "show_auth_popup" not in st.session_state:
    st.session_state.show_auth_popup = False

if "form_data" not in st.session_state:
    st.session_state.form_data = {}

if "sending_email" not in st.session_state:
    st.session_state.sending_email = False

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def validate_ref_no(ref_no):

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

        ext = os.path.splitext(file.name)[1].lower()

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

    # ATTACH FILES

    for file in uploaded_files:

        file_name = file["name"]
        file_data = file["data"]

        ext = os.path.splitext(file_name)[1].lower()

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
            filename=file_name
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


def get_email_logs():

    query = """
    SELECT
        id,
        user_name,
        institution_name,
        recipients,
        ref_no,
        sent_at
    FROM email_logs
    ORDER BY datetime(sent_at) DESC
    """

    return pd.read_sql_query(query, conn)

# =========================================================
# UI
# =========================================================

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

# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title("📂 Navigation")

menu = st.sidebar.radio(
    "Go To",
    [
        "Send Email",
        "Email Logs Dashboard"
    ]
)

st.sidebar.divider()

st.sidebar.title("👤 User")

selected_user = st.sidebar.selectbox(
    "Select User",
    users
)

# =========================================================
# SEND EMAIL PAGE
# =========================================================

if menu == "Send Email":

    st.title("📧 Daily Email Sender")

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

    # =====================================================
    # FORM VALIDATION
    # =====================================================

    if submitted:

        if not GMAIL_USER or not GMAIL_APP_PASSWORD:

            st.error(
                "Email credentials missing in .env"
            )

            st.stop()

        if not validate_ref_no(ref_no):

            st.error(
                "Reference Number must:\n"
                "- Start with RK\n"
                "- Be exactly 9 characters"
            )

            st.stop()

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

        cc_valid, cc_list = validate_cc_emails(
            cc_emails
        )

        if not cc_valid:

            st.error(
                "Invalid CC email format."
            )

            st.stop()

        # SAVE FILES

        saved_files = []

        for file in uploaded_files:

            saved_files.append({
                "name": file.name,
                "type": file.type,
                "data": file.getvalue()
            })

        st.session_state.form_data = {

            "selected_user": selected_user,

            "uploaded_files": saved_files,

            "selected_institution": selected_institution,

            "cc_list": cc_list,

            "ref_no": ref_no
        }

        st.session_state.show_auth_popup = True

        st.rerun()

    # =====================================================
    # AUTH POPUP
    # =====================================================

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

        # CANCEL

        if cancel_btn:

            st.session_state.show_auth_popup = False

            st.rerun()

        # SEND

        if send_btn:

            data = st.session_state.form_data

            selected_user = data["selected_user"]

            if not verify_auth_code(
                selected_user,
                auth_code
            ):

                st.error(
                    "Invalid authorization code."
                )

                return

            st.session_state.show_auth_popup = False

            st.session_state.sending_email = True

            st.rerun()

    # =====================================================
    # SHOW POPUP
    # =====================================================

    if st.session_state.show_auth_popup:

        auth_popup()

    # =====================================================
    # SEND EMAIL PROCESS
    # =====================================================

    if st.session_state.sending_email:

        data = st.session_state.form_data

        selected_user = data["selected_user"]

        uploaded_files = data["uploaded_files"]

        selected_institution = data[
            "selected_institution"
        ]

        cc_list = data["cc_list"]

        ref_no = data["ref_no"]

        to_email = institution_email_map[
            selected_institution
        ]

        with st.spinner("Sending email..."):

            try:

                send_email(
                    to_email=to_email,
                    cc_list=cc_list,
                    uploaded_files=uploaded_files
                )

                all_recipients = (
                    [to_email] + cc_list
                )

                recipients_str = ", ".join(
                    all_recipients
                )

                log_email(
                    user_name=selected_user,
                    institution_name=selected_institution,
                    recipients=recipients_str,
                    ref_no=ref_no
                )

                st.success(
                    "✅ Email sent successfully."
                )

                st.toast(
                    "Email delivered successfully."
                )

                st.balloons()

            except smtplib.SMTPAuthenticationError:

                st.error(
                    "SMTP Authentication failed."
                )

            except smtplib.SMTPException as e:

                st.error(
                    f"SMTP Error: {str(e)}"
                )

            except Exception as e:

                st.exception(e)

        # RESET STATES

        st.session_state.sending_email = False

        st.session_state.form_data = {}

# =========================================================
# EMAIL LOGS DASHBOARD
# =========================================================

if menu == "Email Logs Dashboard":

    st.title("📊 Email Logs Dashboard")

    df = get_email_logs()

    if df.empty:

        st.warning("No email logs found.")

        st.stop()

    # =====================================================
    # DATE CONVERSION
    # =====================================================

    df["sent_at"] = pd.to_datetime(df["sent_at"])

    df["date"] = df["sent_at"].dt.date

    # =====================================================
    # FILTERS
    # =====================================================

    st.sidebar.subheader("🔍 Filters")

    bank_filter = st.sidebar.selectbox(
        "Bank Name",
        ["All"] + sorted(
            df["institution_name"].unique().tolist()
        )
    )

    user_filter = st.sidebar.selectbox(
        "User",
        ["All"] + sorted(
            df["user_name"].unique().tolist()
        )
    )

    ref_filter = st.sidebar.text_input(
        "Reference Number",
        placeholder="RK1234567"
    )

    date_range = st.sidebar.date_input(
        "Date Range",
        []
    )

    filtered_df = df.copy()

    # =====================================================
    # APPLY FILTERS
    # =====================================================

    if bank_filter != "All":

        filtered_df = filtered_df[
            filtered_df["institution_name"]
            == bank_filter
        ]

    if user_filter != "All":

        filtered_df = filtered_df[
            filtered_df["user_name"]
            == user_filter
        ]

    if ref_filter.strip():

        filtered_df = filtered_df[
            filtered_df["ref_no"]
            .str.contains(
                ref_filter.strip(),
                case=False,
                na=False
            )
        ]

    if len(date_range) == 2:

        start_date, end_date = date_range

        filtered_df = filtered_df[
            (filtered_df["date"] >= start_date)
            &
            (filtered_df["date"] <= end_date)
        ]

    # =====================================================
    # METRICS
    # =====================================================

    total_emails = len(filtered_df)

    total_banks = filtered_df[
        "institution_name"
    ].nunique()

    total_users = filtered_df[
        "user_name"
    ].nunique()

    latest_email = filtered_df[
        "sent_at"
    ].max()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Emails",
            total_emails
        )

    with col2:
        st.metric(
            "Banks",
            total_banks
        )

    with col3:
        st.metric(
            "Users",
            total_users
        )

    with col4:
        st.metric(
            "Latest Email",
            latest_email.strftime("%Y-%m-%d")
            if pd.notnull(latest_email)
            else "N/A"
        )

    st.divider()

    # =====================================================
    # CHARTS
    # =====================================================

    st.subheader("📈 Emails by Bank")

    bank_chart = filtered_df[
        "institution_name"
    ].value_counts()

    st.bar_chart(bank_chart)

    st.subheader("📈 Emails by User")

    user_chart = filtered_df[
        "user_name"
    ].value_counts()

    st.bar_chart(user_chart)

    st.subheader("📈 Emails Per Day")

    daily_chart = filtered_df.groupby(
        filtered_df["sent_at"].dt.date
    ).size()

    st.line_chart(daily_chart)

    st.divider()

    # =====================================================
    # LOG TABLE
    # =====================================================

    st.subheader("📋 Email Logs")

    display_df = filtered_df.copy()

    display_df["sent_at"] = display_df[
        "sent_at"
    ].dt.strftime("%Y-%m-%d %H:%M:%S")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # =====================================================
    # DOWNLOAD CSV
    # =====================================================

    csv = display_df.to_csv(index=False)

    st.download_button(
        label="⬇ Download CSV",
        data=csv,
        file_name="email_logs.csv",
        mime="text/csv"
    )
