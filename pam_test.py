import requests
from dotenv import load_dotenv
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://public.dolma.gov.np"

load_dotenv()

USERNAME = os.getenv("USERNAME_")
PASSWORD = os.getenv("PASSWORD_")

if not USERNAME or not PASSWORD:
    raise ValueError("USERNAME_ or PASSWORD_ not set in .env")

session = requests.Session()

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/dolma/",
    "user-type": "3"
}

# -------------------------
# 1. LOGIN
# -------------------------
login_url = f"{BASE_URL}/pam/api/auth/login"

login_payload = {
    "usernameOrEmail": USERNAME,
    "password": PASSWORD,
    "remember": True
}

login_response = session.post(login_url, json=login_payload, headers=headers,  verify=False)
login_data = login_response.json()

token = login_data["data"]["accessToken"]
# Extract user details
user_data = login_data["data"]["user"]

user_id = user_data["userId"]
role_id = user_data["roles"][0]["roleId"]
office_id = user_data["officeId"]

print("Status Code:", login_response.status_code)
 
try:
    print("Response JSON:", login_data)
except Exception:
    print("Response is not valid JSON")
    print("Response Text:", login_response.text[:500])

# -------------------------
# 2. CALL NEXT API
# -------------------------
api_url = f"{BASE_URL}/pam/app/allregprocess"

api_headers = {
    **headers,
    "Authorization": f"Bearer {token}"
}

api_payload = {
    "pid": "8,15",
    "statusid": 1,
    "userid": user_id,
    "roleid": 1,
    "phoneno": "",
    "officeid": office_id,
    "kitta": "",
    "district": "",
    "munVdc": "",
    "dateFrom": "",
    "dateTo": "",
    "refNo": ""
}

api_response = session.post(
    api_url,
    json=api_payload,
    headers=api_headers,
    verify=False
)

print("API Status:", api_response.status_code)

try:
    print("API Response:", api_response.json())
except:
    print("API Text:", api_response.text[:500])