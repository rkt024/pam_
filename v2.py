import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
import urllib3
import math
import os

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
load_dotenv()

VERIFY_SSL = False

if not VERIFY_SSL:
    urllib3.disable_warnings(
        urllib3.exceptions.InsecureRequestWarning
    )

BASE_URL = "https://public.dolma.gov.np"

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/dolma/",
    "user-type": "3"
}

PAGE_SIZE = 5

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------
st.set_page_config(
    page_title="DOLMA Dashboard",
    page_icon="📄",
    layout="wide"
)

# ---------------------------------------------------
# SESSION INIT
# ---------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "page" not in st.session_state:
    st.session_state["page"] = 1

if "expanded_row" not in st.session_state:
    st.session_state["expanded_row"] = None

if "detail_cache" not in st.session_state:
    st.session_state["detail_cache"] = {}

if "http_session" not in st.session_state:
    st.session_state["http_session"] = requests.Session()

session = st.session_state["http_session"]

# ---------------------------------------------------
# LOGIN API
# ---------------------------------------------------
def login_api(username, password):

    payload = {
        "usernameOrEmail": username,
        "password": password,
        "remember": True
    }

    try:
        with st.spinner("Logging in..."):

            res = session.post(
                f"{BASE_URL}/pam/api/auth/login",
                headers=BASE_HEADERS,
                json=payload,
                timeout=50,
                verify=VERIFY_SSL
            )

        if res.status_code != 200:
            st.error(f"Server Error: {res.status_code}")
            return False

        data = res.json()

        if not data.get("status"):
            st.error("Invalid username or password")
            return False

        user = data["data"]["user"]
        roles = user.get("roles", [])

        role_id = roles[0].get("roleId") if roles else None

        if not role_id:
            st.error("No valid role assigned")
            return False

        st.session_state.update({
            "token": data["data"]["accessToken"],
            "user_id": user.get("userId"),
            "office_id": user.get("officeId"),
            "role_id": role_id,
            "username": username,
            "password": password,  # 👈 Stored for auto-relogin
            "logged_in": True
        })

        return True

    except requests.exceptions.Timeout:
        st.error("Request timeout")

    except Exception as e:
        st.error(f"Login Error: {e}")

    return False


# ---------------------------------------------------
# 🔑 SIMPLE AUTO-RELOGIN WRAPPER
# ---------------------------------------------------
def api_call(url, method="POST", **kwargs):
    """Makes a request. If 401/403, relogs in and retries ONCE."""
    token = st.session_state.get("token")
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers
    kwargs.setdefault("timeout", 50)
    kwargs.setdefault("verify", VERIFY_SSL)

    res = session.request(method, url, **kwargs)

    # If unauthorized, re-login and retry ONCE
    if res.status_code in [401, 403]:
        u = st.session_state.get("username")
        p = st.session_state.get("password")
        if u and p:
            login_res = session.post(
                f"{BASE_URL}/pam/api/auth/login",
                headers=BASE_HEADERS,
                json={"usernameOrEmail": u, "password": p, "remember": True},
                timeout=50, verify=VERIFY_SSL
            )
            if login_res.status_code == 200 and login_res.json().get("status"):
                new_token = login_res.json()["data"]["accessToken"]
                st.session_state["token"] = new_token
                headers["Authorization"] = f"Bearer {new_token}"
                kwargs["headers"] = headers
                res = session.request(method, url, **kwargs)
    return res


# ---------------------------------------------------
# FETCH REGISTRATION DATA
# ---------------------------------------------------
@st.cache_data(ttl=300)
def fetch_registration_data_cached(
    token,
    user_id,
    role_id,
    office_id
):

    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "pid": "8,15",
        "statusid": 1,
        "userid": user_id,
        "roleid": role_id,
        "officeid": office_id,
    }

    res = api_call(
        f"{BASE_URL}/pam/app/allregprocess",
        json=payload,
        headers=headers
    )

    if res.status_code != 200:
        raise Exception(f"API Error: {res.status_code}")

    data = res.json().get("data", [])

    df = pd.DataFrame([
        {
            "reference_no": r.get("referenceno"),
            "username": r.get("username"),
            "date": r.get("dateofapplication"),
            "process": r.get("processname"),
            "agency": r.get("rokkaagency")
        }
        for r in data
    ])

    if df.empty:
        return df

    df["reference_no"] = pd.to_numeric(
        df["reference_no"],
        errors="coerce"
    ).astype("Int64")

    df = df.sort_values(
        by="reference_no",
        ascending=False
    ).reset_index(drop=True)

    return df


def fetch_registration_data():

    token = st.session_state.get("token")

    if not token:
        st.error("Session expired")
        return pd.DataFrame()

    if not st.session_state.get("role_id"):
        st.error("Invalid role")
        return pd.DataFrame()

    try:
        with st.spinner("Loading registration data..."):

            df = fetch_registration_data_cached(
                token,
                st.session_state["user_id"],
                st.session_state["role_id"],
                st.session_state["office_id"]
            )

        return df

    except Exception as e:
        st.error(f"Fetch Error: {e}")

    return pd.DataFrame()


# ---------------------------------------------------
# FETCH DETAIL WITH CACHE
# ---------------------------------------------------
@st.cache_data(ttl=600)
def fetch_detail_cached(ref, token):

    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token}"
    }

    url = f"{BASE_URL}/pam/app/rokka/application/detail/{ref}"

    res = api_call(url, headers=headers)

    if res.status_code != 200:
        raise Exception(f"Detail API Error: {res.status_code}")

    return res.json().get("data")


def fetch_detail(ref):

    token = st.session_state.get("token")

    if not token:
        st.error("Session expired")
        return None

    try:
        with st.spinner(f"Loading detail for {ref}..."):

            data = fetch_detail_cached(ref, token)

        return data

    except Exception as e:
        st.error(f"Detail Fetch Error: {e}")

    return None


# ---------------------------------------------------
# DASHBOARD
# ---------------------------------------------------
def dashboard_home():

    st.title("📊 Dashboard")

    df = st.session_state.get("table_data")

    if df is None or df.empty:
        st.info("Load data from sidebar")
        return

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Records", len(df))
    col2.metric("Unique Users", df["username"].nunique())
    col3.metric("Processes", df["process"].nunique())

    st.subheader("Process Distribution")

    st.bar_chart(df["process"].value_counts())


# ---------------------------------------------------
# RECORDS PAGE
# ---------------------------------------------------
def table_page():

    st.title("📋 Registration Records")
    
    st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlock"] > div {
        padding-top: 0rem !important;
        padding-bottom: 0rem !important;
        margin-top: 0rem !important;
        margin-bottom: 0rem !important;
    }

    div[data-testid="element-container"] {
        margin-bottom: 0rem !important;
    }

    hr {
        margin-top: 0.2rem !important;
        margin-bottom: 0.2rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True
    )

    df = st.session_state.get("table_data")

    if df is None or df.empty:
        st.warning("No data loaded")
        return

    search = st.text_input("🔍 Search")

    if search:
        df = df[
            df["reference_no"].astype(str).str.contains(search, case=False, na=False)
            |
            df["username"].astype(str).str.contains(search, case=False, na=False)
            |
            df["process"].astype(str).str.contains(search, case=False, na=False)
            |
            df["agency"].astype(str).str.contains(search, case=False, na=False)
        ]

    if df.empty:
        st.warning("No matching records")
        return

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "📥 Export CSV",
        csv,
        "registration_data.csv",
        "text/csv"
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    total_pages = max(1, math.ceil(len(df) / PAGE_SIZE))
    current_page = st.session_state["page"]
    current_page = max(1, min(current_page, total_pages))
    st.session_state["page"] = current_page

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("⬅ Prev"):
            if current_page > 1:
                st.session_state["page"] -= 1
                st.session_state["expanded_row"] = None
                st.rerun()

    with col3:
        if st.button("Next ➡"):
            if current_page < total_pages:
                st.session_state["page"] += 1
                st.session_state["expanded_row"] = None
                st.rerun()

    col2.markdown(
        f"<center><b>Page {current_page} / {total_pages}</b></center>",
        unsafe_allow_html=True
    )

    start = (current_page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_df = df.iloc[start:end]

    st.divider()

    h1, h2, h3, h4, h5, h6 = st.columns([2, 2, 2, 2, 2, 1])
    h1.markdown("**Ref No**")
    h2.markdown("**User**")
    h3.markdown("**Date**")
    h4.markdown("**Process**")
    h5.markdown("**Agency**")
    h6.markdown("")
    st.divider()

    for _, row in page_df.iterrows():
        ref = row["reference_no"]
        c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 2, 1])

        c1.write(ref)
        c2.write(row["username"])
        c3.write(row["date"])
        c4.write(row["process"])
        c5.write(row["agency"])

        expanded = st.session_state.get("expanded_row") == ref
        button_text = "Hide" if expanded else "View"

        if c6.button(button_text, key=f"view_{ref}"):
            if expanded:
                st.session_state["expanded_row"] = None
            else:
                st.session_state["expanded_row"] = ref
            st.rerun()

        if expanded:
            detail = fetch_detail(ref)
            if detail:
                process = detail.get("PROCESSREGISTRATION", {})
                prop = detail.get("PROPERTYDETAIL", [])

                munc = "-"
                if isinstance(prop, list) and len(prop) > 0: 
                    munc = prop[0].get("MUNCNAME_NP", "-")
                agency = "-"

                process_name = process.get("processname", "").lower()

                if "rokka" in process_name:
                    rokka_info = detail.get("ROKKAINFORMATION", [])
                    if isinstance(rokka_info, list) and len(rokka_info) > 0:
                        agency = rokka_info[0].get("AGENCYNAME_NP", "-")
                else:
                    fukuwa = detail.get("data", {}).get("fukuwaDetails", [])
                    if isinstance(fukuwa, list) and len(fukuwa) > 0:
                        agency = fukuwa[0].get("tblrokkaagency", {}).get("agencyname_np", "-")

                st.markdown(
                    """
                    <style>
                    .mini-detail {
                        background-color: #f8f9fa;
                        padding: 10px 15px;
                        border-radius: 6px;
                        margin-top: 5px;
                        margin-bottom: 10px;
                        border: 1px solid #e6e6e6;
                        font-size: 14px;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )

                d1, d2, d3, d4, d5 = st.columns([2, 2, 2, 2, 2])
                with d1:
                    st.caption("Reference")
                    st.write(process.get("referenceno", ref))
                with d2:
                    st.caption("Municipality")
                    st.write(munc)
                with d3:
                    st.caption("Agency")
                    st.write(agency)
                with d4:
                    st.caption("Process")
                    st.write(process.get("processname", "-"))
                with d5:
                    st.caption("Application Date")
                    st.write(process.get("dateofapplication", "-"))
            else:
                st.error("Failed to load detail")

        st.divider()


# ---------------------------------------------------
# SIDEBAR (With Compact Transactions)
# ---------------------------------------------------
def sidebar():

    st.sidebar.title("🏛 Admin Panel")
    st.sidebar.write(f"👤 {st.session_state.get('username', '')}")
    st.sidebar.divider()

    if st.sidebar.button("📥 Load Data"):
        df = fetch_registration_data()
        st.session_state["table_data"] = df
        st.session_state["page"] = 1
        st.session_state["expanded_row"] = None
        if not df.empty:
            st.sidebar.success(f"{len(df)} records loaded")

    st.sidebar.divider()

    # Navigation (Transactions removed)
    pages = ["Dashboard", "Records"]
    default_page = st.session_state.get("page_name", "Dashboard")
    selected_page = st.sidebar.radio(
        "Navigate",
        pages,
        index=pages.index(default_page)
    )
    st.session_state["page_name"] = selected_page

    st.sidebar.divider()

    # 💰 COMPACT TRANSACTION FORM IN SIDEBAR
    with st.sidebar.expander("💰 Quick Response", expanded=False):
        t_id = st.text_input("Ref No.", max_chars=7, placeholder="Enter Reference No.", key="t_id_sb")
        t_type = st.selectbox("Type", ["Rokka", "Fukuwa", "Others"], key="t_type_sb", index=2)
        remarks = st.text_area(
            "Remarks", 
            value="भू सेवाबाट माग भए बमोजिम फिर्ता ।", 
            height=60, 
            key="t_remarks_sb"
        )

        col_t1, col_t2 = st.sidebar.columns(2)
        t_transfer = col_t1.button("Transfer", use_container_width=True, key="btn_transfer_sb")
        t_return = col_t2.button("Return", use_container_width=True, key="btn_return_sb")

        is_valid = t_id.isdigit() and len(t_id) == 7
        if t_id and not is_valid:
            st.sidebar.error("⚠️ Enter exactly 7 digits")

        if t_transfer:
            if not is_valid:
                st.sidebar.warning("Enter valid 7-digit ID")
            else:
                try:
                    url_map = {
                        "Rokka": f"{BASE_URL}/pam/app/rokka/data/send/{t_id}",
                        "Fukuwa": f"{BASE_URL}/pam/app/fukuwa/data/send/{t_id}",
                        "Others": f"{BASE_URL}/pam/app/all/data/send/{t_id}"
                    }

                    url = url_map[t_type]

                    # Fukuwa does not require payload
                    if t_type == "Fukuwa":
                        res = api_call(url)
                    else:
                        res = api_call(url, json={})

                    if res and res.ok:
                        response_data = res.json()

                        if response_data.get("status"):
                            message = response_data.get("message", "Success")
                            reference_no = response_data.get("data", {}).get("referenceNo", "N/A")

                            st.sidebar.success(
                                f"✅ {t_type} transferred successfully\n"
                                f"📌 Ref No: {reference_no}"
                            )

                            st.sidebar.info(f"ℹ️ {message}")

                        else:
                            st.sidebar.error(
                                f"❌ Transfer failed: {response_data.get('message', 'Unknown error')}"
                            )

                    else:
                        st.sidebar.error(
                            f"❌ Failed: {res.status_code if res else 'No response'}"
                        )

                        if res:
                            st.sidebar.code(res.text)

                except Exception as e:
                    st.sidebar.error(f"❌ Error: {e}")
                    
            if not is_valid:
                st.sidebar.warning("Enter valid 7-digit ID")
            else:
                try:
                    url_map = {
                        "Rokka": f"{BASE_URL}/pam/app/rokka/data/send/{t_id}",
                        "Fukuwa": f"{BASE_URL}/pam/app/fukuwa/data/send/{t_id}",
                        "Others": f"{BASE_URL}/pam/app/all/data/send/{t_id}"
                    }
                    
                    res = api_call(url_map[t_type], json={})

                    if res and res.ok:
                        response_data = res.json()

                        if response_data.get("status"):
                            message = response_data.get("message", "Success")
                            reference_no = response_data.get("data", {}).get("referenceNo", "N/A")

                            st.sidebar.success(
                                f"✅ {t_type} transferred successfully\n"
                                f"📌 Ref No: {reference_no}"
                            )

                            st.sidebar.info(f"ℹ️ {message}")

                        else:
                            st.sidebar.error(
                                f"❌ Transfer failed: {response_data.get('message', 'Unknown error')}"
                            )

                    else:
                        st.sidebar.error(
                            f"❌ Failed: {res.status_code if res else 'No response'}"
                        )

                except Exception as e:
                    st.sidebar.error(f"❌ Error: {e}")

        if t_return:
            if not is_valid:
                st.sidebar.warning("Enter valid 7-digit ID")
            elif not remarks.strip():
                st.sidebar.warning("Remarks cannot be empty")
            else:
                try:
                    url = f"{BASE_URL}/pam/app/submit/deed/application/{t_id}/6"
                     
                    res = api_call(url, json={"remarks": remarks})
                    if res and res.ok:
                        response_data = res.json()

                        if response_data.get("status"):
                            message = response_data.get("message", "Success")
                            submitted_id = response_data.get("data")

                            st.sidebar.success(
                                f"✅ Returned successfully\n"
                                f"📌 Submission ID: {submitted_id}"
                            )

                            st.sidebar.info(f"ℹ️ {message}")

                        else:
                            st.sidebar.error(
                                f"❌ Failed: {response_data.get('message', 'Unknown error')}"
                            )

                    else:
                        st.sidebar.error(
                            f"❌ Failed: {res.status_code if res else 'No response'}"
                        )

                except Exception as e:
                    st.sidebar.error(f"❌ Error: {e}")

    st.sidebar.divider()

    if st.sidebar.button("🧹 Clear Cache"):
        st.cache_data.clear()
        st.sidebar.success("Cache cleared")

    if st.sidebar.button("🚪 Logout"):
        st.session_state.pop("password", None)
        st.session_state.clear()
        st.rerun()

    return selected_page


# ---------------------------------------------------
# LOGIN PAGE
# ---------------------------------------------------
def login_page():

    _, center, _ = st.columns([3, 1.2, 3])

    with center:

        st.subheader("🔐 Login")

        username = st.text_input(
            "Username",
            placeholder="Enter username"
        )

        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter password"
        )

        if st.button("Login", use_container_width=True):

            if not username or not password:
                st.warning("Enter username and password")
                return

            if login_api(username, password):
                st.success("Login successful")
                st.rerun()

# ---------------------------------------------------
# MAIN
# ---------------------------------------------------
def main():

    if not st.session_state["logged_in"]:
        login_page()
        return

    page = sidebar()

    if page == "Dashboard":
        dashboard_home()
    elif page == "Records":
        table_page()


# ---------------------------------------------------
# ENTRY
# ---------------------------------------------------
if __name__ == "__main__":
    main()
