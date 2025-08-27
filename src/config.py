import os
from dotenv import load_dotenv

load_dotenv()

# --- Optional (nur relevant für XOAUTH2/Exchange) ---
TENANT_ID = os.getenv("TENANT_ID", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")

# --- IMAP Settings ---
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")   # <--- wichtig für LOGIN
IMAP_HOST = os.getenv("IMAP_HOST", "outlook.office365.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

# --- Auth Mode ---
AUTH_METHOD = os.getenv("AUTH_METHOD", "LOGIN")  # LOGIN or XOAUTH2

# --- General Polling & Timeouts ---
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60

# --- Nur für Exchange OAUTH2 wichtig ---
TOKEN_SCOPE = "https://outlook.office365.com/.default"