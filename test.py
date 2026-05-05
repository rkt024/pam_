import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
import os

# -------------------------
# CONFIG
# -------------------------
load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://public.dolma.gov.np")
session = requests.Session()

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/dolma/",
    "user-type": "3"
}

# -------------------------
# LOGIN
# -------------------------
def login_api(username, password):
    payload = {
        "usernameOrEmail": username,
        "password": password,
        "remember": True
    }

    res = session.post(
        f"{BASE_URL}/pam/api/auth/login",
        headers=BASE_HEADERS,
        json=payload,
        timeout=10,
        verify=False
    )

    if res.status_code == 200:
        data = res.json()

        if data.get("status"):
            user = data["data"]["user"]
            roles = user.get("roles", [])

            st.session_state.update({
                "token": data["data"]["accessToken"],
                "user_id": user.get("userId"),
                "office_id": user.get("officeId"),
                "role_id": roles[0].get("roleId") if roles else None,
                "username": username,
                "logged_in": True
            })
            return True

    return False


# -------------------------
# FETCH LIST
# -------------------------
def fetch_registration_data():
    token = st.session_state["token"]

    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "pid": "8,15",
        "statusid": 1,
        "userid": st.session_state["user_id"],
        "roleid": st.session_state["role_id"],
        "officeid": st.session_state["office_id"],
    }

    res = session.post(
        f"{BASE_URL}/pam/app/allregprocess",
        json=payload,
        headers=headers,
        verify=False
    )

    data = res.json().get("data", [])

    df = pd.DataFrame([
        {
            "reference_no": r.get("referenceno"),
            "username": r.get("username"),
            "date": r.get("dateofapplication"),
            "process": r.get("processname"),
        }
        for r in data
    ])

    # 🔥 IMPORTANT: numeric + descending sort
    df["reference_no"] = pd.to_numeric(df["reference_no"], errors="coerce")
    df = df.sort_values(by="reference_no", ascending=False).reset_index(drop=True)

    st.session_state["table_data"] = df


# -------------------------
# DETAIL API (CACHE SAFE)
# -------------------------
def fetch_detail(ref):
    if "detail_cache" not in st.session_state:
        st.session_state["detail_cache"] = {}

    cache = st.session_state["detail_cache"]

    if ref in cache:
        return cache[ref]

    MAX_CACHE = 100
    if len(cache) > MAX_CACHE:
        cache.pop(next(iter(cache)))

    token = st.session_state["token"]

    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token}"
    }

    url = f"{BASE_URL}/pam/app/rokka/application/detail/{ref}"

    res = session.post(url, headers=headers, verify=False)

    if res.status_code != 200:
        return None

    data = res.json().get("data")

    cache[ref] = data
    return data


# -------------------------
# DASHBOARD
# -------------------------
def dashboard_home():
    st.title("📊 Admin Dashboard")

    df = st.session_state.get("table_data")

    if df is None or df.empty:
        st.info("Load data from sidebar")
        return

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Records", len(df))
    col2.metric("Unique Users", df["username"].nunique())
    col3.metric("Processes", df["process"].nunique())

    st.bar_chart(df["process"].value_counts())


# -------------------------
# TABLE PAGE
# -------------------------
def table_page():
    st.title("📋 Registration Records")

    df = st.session_state.get("table_data")

    if df is None or df.empty:
        st.warning("Load data first")
        return

    # -------------------------
    # SEARCH
    # -------------------------
    search = st.text_input("🔍 Search")

    if search:
        st.session_state["page"] = 1

        df = df[
            df["reference_no"].astype(str).str.contains(search, case=False, na=False) |
            df["username"].astype(str).str.contains(search, case=False, na=False) |
            df["process"].astype(str).str.contains(search, case=False, na=False)
        ]

    # -------------------------
    # EXPORT
    # -------------------------
    st.download_button(
        "📥 Export CSV",
        df.to_csv(index=False),
        "data.csv"
    )

    # -------------------------
    # PAGINATION (DESCENDING STYLE)
    # -------------------------
    PAGE_SIZE = 10
    total_pages = (len(df) // PAGE_SIZE) + (1 if len(df) % PAGE_SIZE else 0)

    if "page" not in st.session_state:
        st.session_state["page"] = 1

    st.session_state["page"] = max(1, min(st.session_state["page"], total_pages))

    col1, col2, col3 = st.columns([1, 2, 1])

    if col1.button("⬅ Prev"):
        st.session_state["page"] = min(total_pages, st.session_state["page"] + 1)

    if col3.button("Next ➡"):
        st.session_state["page"] = max(1, st.session_state["page"] - 1)

    display_page = total_pages - st.session_state["page"] + 1
    col2.write(f"Page {display_page} / {total_pages}")

    start = (st.session_state["page"] - 1) * PAGE_SIZE
    page_df = df.iloc[start:start + PAGE_SIZE]

    # -------------------------
    # TABLE
    # -------------------------
    for _, row in page_df.iterrows():
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])

        c1.write(row["reference_no"])
        c2.write(row["username"])
        c3.write(row["date"])
        c4.write(row["process"])

        if c5.button("View", key=f"view_{row['reference_no']}"):
            st.session_state["selected_ref"] = row["reference_no"]

    # -------------------------
    # DETAIL VIEW
    # -------------------------
    if "selected_ref" in st.session_state:
        ref = st.session_state["selected_ref"]

        st.divider()

        col1, col2 = st.columns([6, 1])
        col1.subheader(f"📄 Detail for {ref}")

        if col2.button("❌ Close"):
            del st.session_state["selected_ref"]
            st.rerun()

        data = fetch_detail(ref)

        if not data:
            st.error("Failed to fetch detail")
        else:
            process = data.get("PROCESSREGISTRATION", {})
            prop = data.get("PROPERTYDETAIL", [])
            rokka = data.get("ROKKAINFORMATION", [])

            munc = ""
            if isinstance(prop, list) and len(prop) > 0:
                munc = prop[0].get("MUNCNAME", "")

            agency = ""
            if isinstance(rokka, list) and len(rokka) > 0:
                agency = rokka[0].get("AGENCYNAME", "")

            df_detail = pd.DataFrame([{
                "REFERENCENO": data.get("REFERENCENO"),
                "dateofapplication": process.get("dateofapplication"),
                "processname": process.get("processname"),
                "MUNCNAME": munc,
                "agencyname": agency
            }])

            st.dataframe(df_detail, use_container_width=True)


# -------------------------
# DETAIL PAGE
# -------------------------
def detail_page():
    st.title("📄 Detail View")

    ref = st.session_state.get("selected_ref")

    if not ref:
        st.info("Select a record")
        return

    data = fetch_detail(ref)

    if not data:
        st.error("Failed to fetch")
        return

    st.json(data)


# -------------------------
# SIDEBAR
# -------------------------
def sidebar():
    st.sidebar.title("🏛 Admin Panel")

    if st.sidebar.button("📥 Load Data"):
        fetch_registration_data()

    page = st.sidebar.radio("Navigate", ["Dashboard", "Records", "Detail View"])

    if st.sidebar.button("🧹 Clear Cache"):
        st.session_state["detail_cache"] = {}

    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    return page


# -------------------------
# LOGIN PAGE
# -------------------------
def login_page():
    st.title("🔐 Login")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        if login_api(u, p):
            st.rerun()
        else:
            st.error("Invalid credentials")


# -------------------------
# MAIN
# -------------------------
def main():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        login_page()
        return

    page = sidebar()

    if page == "Dashboard":
        dashboard_home()
    elif page == "Records":
        table_page()
    elif page == "Detail View":
        detail_page()


if __name__ == "__main__":
    main()