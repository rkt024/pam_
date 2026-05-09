# 📄 DOLMA Dashboard

A Streamlit-based web application for managing, monitoring, and processing registration records from the DOLMA system. Features automated token refresh, data pagination, CSV export, and quick transaction handling directly from the sidebar.

---

## ✨ Features
- 🔐 **Secure Login** with automatic session management
- 🔄 **Auto Token Refresh** – Seamlessly handles `401/403` errors by re-authenticating in the background
- 📊 **Dashboard** – View key metrics and process distribution charts
- 📋 **Records Management** – Search, paginate, and export data to CSV
- 🔍 **Expandable Details** – Click to view detailed application info inline
- 💰 **Quick Transactions** – Compact Transfer & Return forms in the sidebar
- ⚡ **Cached API Calls** – Optimized performance with `@st.cache_data`
- 📱 **Responsive Layout** – Built with Streamlit's wide layout mode

---

## 🛠️ Prerequisites
- Python `3.8+`
- `pip` package manager
- Network access to `https://public.dolma.gov.np`

---

## 📦 Installation & Setup

1. **Save the script** as `app.py` (or your preferred filename)

2. **Install dependencies:**
   ```bash
   pip install streamlit requests pandas python-dotenv urllib3
   ```
3. **Run the application:**
    ```bash
    streamlit run app.py
    ```
## 🚀 Usage
- Open the app in your browser (default: http://localhost:8501)
- Log in with your authorized DOLMA credentials
- Click 📥 Load Data in the sidebar to fetch registration records
- Navigate between Dashboard and Records
- Use the 💰 Quick Transactions expander in the sidebar to Transfer or Return applications
- ✅ The app automatically handles expired tokens. No manual re-login required!
