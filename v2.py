import streamlit as st
import requests
import pandas as pd
import urllib3
import math
from dotenv import load_dotenv

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
load_dotenv()
VERIFY_SSL = False
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://public.dolma.gov.np"
BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/dolma/",
    "user-type": "3"
}

PAGES = [
    "Likhat Parit", "Jagga Darta", "Namsari", "Dakhil Kharej",
    "Samsodan", "Halsabik", "Rokka/Fukuwa", "Apartment",
    "Pratilipi", "Guthi Adhinastha"
]

PROCESS_IDS = {
    "Likhat Parit": "1", "Jagga Darta": "2", "Namsari": "3", "Dakhil Kharej": "4",
    "Samsodan": "5", "Halsabik": "7", "Rokka/Fukuwa": "8,15", "Apartment": "16",
    "Pratilipi": "21", "Guthi Adhinastha": "22"
}

ROWS_PER_PAGE = 7
st.set_page_config(page_title="DOLMA Office Portal", page_icon="🏛️", layout="wide")

# ---------------------------------------------------
# SESSION STATE INIT
# ---------------------------------------------------
defaults = {
    "logged_in": False, "token": None, "user_id": None, "role_id": None,
    "office_id": None, "username": None, "password": None,
    "selected_page": PAGES[0], "table_data": None,
    "page_num": 1, "search_query": "", "expanded_row": None,
    "return_mode_ref": None, "http_session": requests.Session()
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

session = st.session_state["http_session"]

# ---------------------------------------------------
# API CLIENT
# ---------------------------------------------------
def api_call(url, method="POST", **kwargs):
    """Makes a request. If 401/403, relogs in and retries ONCE."""
    token = st.session_state.get("token")
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers
    kwargs.setdefault("timeout", 30)
    kwargs.setdefault("verify", VERIFY_SSL)
    
    try:
        res = session.request(method, url, **kwargs)
        if res.status_code in (401, 403):
            u, p = st.session_state.get("username"), st.session_state.get("password")
            if u and p:
                login_res = session.post(
                    f"{BASE_URL}/pam/api/auth/login",
                    headers=BASE_HEADERS,
                    json={"usernameOrEmail": u, "password": p, "remember": True},
                    timeout=30, verify=VERIFY_SSL
                )
                if login_res.ok and login_res.json().get("status"):
                    new_token = login_res.json()["data"]["accessToken"]
                    st.session_state["token"] = new_token
                    headers["Authorization"] = f"Bearer {new_token}"
                    kwargs["headers"] = headers
                    res = session.request(method, url, **kwargs)
        return res
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

def login_api(username, password):
    try:
        with st.spinner("Logging in..."):
            res = api_call(f"{BASE_URL}/pam/api/auth/login", headers=BASE_HEADERS, 
                           json={"usernameOrEmail": username, "password": password, "remember": True})
        if not res or res.status_code != 200:
            st.error(f"Server Error: {res.status_code if res else 'No Response'}")
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
            "username": username, "password": password, "logged_in": True
        })
        return True
    except Exception as e:
        st.error(f"Login Error: {e}")
        return False

@st.cache_data(ttl=300)
def fetch_registration_data_cached(token, user_id, role_id, office_id, pid):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"pid": pid, "statusid": 1, "userid": user_id, "roleid": role_id, "officeid": office_id}
    
    res = api_call(f"{BASE_URL}/pam/app/allregprocess", json=payload, headers=headers)
    if not res or res.status_code != 200:
        return pd.DataFrame()
        
    data = res.json().get("data", [])
    if not data:
        return pd.DataFrame()
        
    df = pd.DataFrame([{
        "reference_no": r.get("referenceno"),
        "username": r.get("username"),
        "date": r.get("dateofapplication"),
        "process": r.get("processname"),
        "agency": r.get("rokkaagency")
    } for r in data])
    
    df["reference_no"] = pd.to_numeric(df["reference_no"], errors="coerce").astype("Int64")
    return df.sort_values("reference_no", ascending=False).reset_index(drop=True)

@st.cache_data(ttl=600)
def fetch_detail_cached(ref, token):
    headers = {"Authorization": f"Bearer {token}"}
    res = api_call(f"{BASE_URL}/pam/app/rokka/application/detail/{ref}", headers=headers)
    if res and res.status_code == 200:
        return res.json().get("data")
    return None

# ---------------------------------------------------
# ROW ACTIONS
# ---------------------------------------------------
def do_transfer(ref, process_name):
    pn = (process_name or "").lower()
    if "rokka" in pn:
        url, method = f"{BASE_URL}/pam/app/rokka/data/send/{ref}", "POST"
    elif "fukuwa" in pn:
        url, method = f"{BASE_URL}/pam/app/fukuwa/data/send/{ref}", "GET"
    else:
        url, method = f"{BASE_URL}/pam/app/all/data/send/{ref}", "POST"
        
    res = api_call(url, method=method, json={} if method == "POST" else None)
    if res and res.ok:
        d = res.json()
        if d.get("status"):
            st.success(f"✅ Transferred: {d.get('data', {}).get('referenceNo', 'N/A')}")
        else:
            st.error(f"❌ Failed: {d.get('message', 'Unknown')}")
    else:
        st.error(f"❌ Transfer Error: {res.status_code if res else 'No Response'}")

def do_return(ref, remarks):
    res = api_call(f"{BASE_URL}/pam/app/submit/deed/application/{ref}/6", json={"remarks": remarks})
    if res and res.ok:
        d = res.json()
        if d.get("status"):
            st.success(f"✅ Returned successfully (ID: {d.get('data')})")
        else:
            st.error(f"❌ Failed: {d.get('message', 'Unknown')}")
    else:
        st.error(f"❌ Return Error: {res.status_code if res else 'No Response'}")

# ---------------------------------------------------
# UI COMPONENTS
# ---------------------------------------------------
def render_table(page_name):
    pid = PROCESS_IDS[page_name]
    is_rokka = (page_name == "Rokka/Fukuwa")
    
    # Lazy Load Data
    if st.session_state["table_data"] is None or st.session_state.get("_last_pid") != pid:
        with st.spinner(f"Loading {page_name}..."):
            df = fetch_registration_data_cached(
                st.session_state["token"],
                st.session_state["user_id"],
                st.session_state["role_id"],
                st.session_state["office_id"],
                pid
            )
            st.session_state["table_data"] = df
            st.session_state["_last_pid"] = pid
            st.session_state["page_num"] = 1
            st.session_state["search_query"] = ""
            st.session_state["expanded_row"] = None
            st.session_state["return_mode_ref"] = None

    df = st.session_state["table_data"]
    if df.empty:
        st.info("No records found.")
        return

    # Search
    search = st.text_input("🔍 Search", value=st.session_state["search_query"], key="search_input")
    if search:
        mask = df.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        df = df[mask]
    st.session_state["search_query"] = search
    
    total = len(df)
    total_pages = max(1, math.ceil(total / ROWS_PER_PAGE))
    st.session_state["page_num"] = max(1, min(st.session_state["page_num"], total_pages))
    
    # Pagination
    c1, _, _, c2 = st.columns([1, 2, 2, 1])
    if c1.button("⬅ Prev", disabled=st.session_state["page_num"]==1, key="btn_prev"):
        st.session_state["page_num"] -= 1; st.session_state["expanded_row"] = None; st.session_state["return_mode_ref"] = None; st.rerun()
    c2.text(f"Page {st.session_state['page_num']}/{total_pages} ({total} records)")
    if c2.button("Next ➡", disabled=st.session_state["page_num"]==total_pages, key="btn_next"):
        st.session_state["page_num"] += 1; st.session_state["expanded_row"] = None; st.session_state["return_mode_ref"] = None; st.rerun()
        
    st.download_button("📥 Export CSV", df.to_csv(index=False).encode("utf-8"), f"{page_name}.csv", "text/csv", key="btn_csv")
    st.divider()

    # Table Header
    col_defs = st.columns([1.5, 1.5, 1.5, 1.5, 1.5, 0.6, 0.8, 0.8]) if is_rokka else st.columns([1.5, 1.5, 1.5, 1.5, 0.6, 0.8, 0.8])
    headers = ["Ref No", "User", "Date", "Process", "Agency", "", "", ""] if is_rokka else ["Ref No", "User", "Date", "Process", "", "", ""]
    for i, h in enumerate(headers):
        col_defs[i].markdown(f"**{h}**")
    st.divider()

    # Table Rows
    start = (st.session_state["page_num"] - 1) * ROWS_PER_PAGE
    page_df = df.iloc[start:start+ROWS_PER_PAGE]
    
    for _, row in page_df.iterrows():
        ref = str(row["reference_no"])
        cols = st.columns([1.5, 1.5, 1.5, 1.5, 1.5, 0.6, 0.8, 0.8]) if is_rokka else st.columns([1.5, 1.5, 1.5, 1.5, 0.6, 0.8, 0.8])
        
        idx_offset = 5 if is_rokka else 4
        cols[0].write(ref)
        cols[1].write(row["username"])
        cols[2].write(row["date"])
        cols[3].write(row["process"])
        if is_rokka:
            cols[4].write(row.get("agency", "-") or "-")

        # View Button (Rokka/Fukuwa Only)
        expanded = st.session_state.get("expanded_row") == ref
        if is_rokka:
            if cols[idx_offset].button("👁️ View" if not expanded else "Hide", key=f"view_{ref}", type="primary" if not expanded else "secondary", use_container_width=True):
                if expanded: st.session_state["expanded_row"] = None
                else: st.session_state["expanded_row"] = ref
                st.session_state["return_mode_ref"] = None
                st.rerun()

        # Transfer Button
        if cols[idx_offset+1].button("🔄 Transfer", key=f"tr_{ref}", use_container_width=True):
            do_transfer(ref, row["process"])
            st.rerun()
            
        # Return Button
        return_mode = st.session_state.get("return_mode_ref") == ref
        if cols[idx_offset+2].button("↩️ Return", key=f"ret_{ref}", use_container_width=True):
            if not return_mode:
                st.session_state["return_mode_ref"] = ref
                st.session_state["expanded_row"] = None
                st.rerun()

        # Inline Return Form
        if return_mode:
            with st.container(border=True):
                remarks = st.text_input("Remarks", value="भू सेवाबाट माग भए बमोजिम फिर्ता ।", key=f"remarks_{ref}")
                c_c, c_x = st.columns(2)
                if c_c.button("✅ Confirm Return", key=f"conf_ret_{ref}", type="primary", use_container_width=True):
                    do_return(ref, remarks)
                    st.session_state["return_mode_ref"] = None
                    st.rerun()
                if c_x.button("❌ Cancel", key=f"cancel_ret_{ref}", use_container_width=True):
                    st.session_state["return_mode_ref"] = None
                    st.rerun()
            st.divider()

        # Expanded Detail (Rokka/Fukuwa Only)
        if expanded and is_rokka:
            with st.container(border=True):
                detail = fetch_detail_cached(ref, st.session_state["token"])
                if detail:
                    # Exact logic from original app.py
                    process = detail.get("PROCESSREGISTRATION", {})
                    prop = detail.get("PROPERTYDETAIL", [])

                    munc = "-"
                    if isinstance(prop, list) and len(prop) > 0: 
                        munc = prop[0].get("MUNCNAME_NP", "-")
                    agency_detail = "-"

                    process_name = process.get("processname", " ").lower()

                    if "rokka" in process_name:
                        rokka_info = detail.get("ROKKAINFORMATION", [])
                        if isinstance(rokka_info, list) and len(rokka_info) > 0:
                            agency_detail = rokka_info[0].get("AGENCYNAME_NP", "-")
                    else:
                        fukuwa = detail.get("data", {}).get("fukuwaDetails", [])
                        if isinstance(fukuwa, list) and len(fukuwa) > 0:
                            agency_detail = fukuwa[0].get("tblrokkaagency", {}).get("agencyname_np", "-")

                    c1, c2, c3, c4 = st.columns(4)
                    # c1.metric("Municipality", munc)
                    # c2.metric("Agency", agency_detail)
                    # c3.metric("Process", process.get("processname", "-"))
                    # c4.metric("Date", process.get("dateofapplication", "-"))

                    c1.markdown(f"**Municipality**  \n<small>{munc}</small>", unsafe_allow_html=True)
                    c2.markdown(f"**Agency**  \n<small>{agency_detail}</small>", unsafe_allow_html=True)
                    c3.markdown(f"**Process**  \n<small>{process.get('processname', '-')}</small>", unsafe_allow_html=True)
                    c4.markdown(f"**Date**  \n<small>{process.get('dateofapplication', '-')}</small>", unsafe_allow_html=True)
                else:
                    st.error("❌ Failed to load detail data")
            st.divider()

def sidebar():
    st.sidebar.title("🏛️ DOLMA Portal")
    st.sidebar.caption(f"👤 {st.session_state.get('username', '')}")
    st.sidebar.divider()
    
    selected = st.sidebar.radio("📂 Workspaces", PAGES, key="nav_radio", index=PAGES.index(st.session_state["selected_page"]))
    st.session_state["selected_page"] = selected
    
    # Reset state on page switch
    if selected != st.session_state.get("_last_page_rendered"):
        st.session_state["_last_page_rendered"] = selected
        st.session_state["table_data"] = None
        st.session_state["page_num"] = 1
        st.session_state["expanded_row"] = None
        
    st.sidebar.divider()
    if st.sidebar.button("🧹 Clear Cache", key="btn_cache"): st.cache_data.clear(); st.sidebar.success("Cache cleared")
    if st.sidebar.button("🚪 Logout", key="btn_logout"): st.session_state.clear(); st.rerun()

def login_page():
    _, center, _ = st.columns([3, 1.2, 3])
    with center:
        st.title("🔐 DOLMA Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Sign In", use_container_width=True, type="primary", key="btn_login"):
            if not username or not password:
                st.warning("Enter credentials")
                return
            if login_api(username, password):
                st.success("Login successful")
                st.rerun()

def main():
    if not st.session_state["logged_in"]:
        login_page()
        return
    sidebar()
    render_table(st.session_state["selected_page"])

if __name__ == "__main__":
    main()
