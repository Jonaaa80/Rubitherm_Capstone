import os
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.getenv("TENANT_ID", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")

IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_HOST = os.getenv("IMAP_HOST", "outlook.office365.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

# Scopes für Client-Credentials-Flow (IMAP / POP verwenden die .default Scope auf Exchange Ressource)
TOKEN_SCOPE = "https://outlook.office365.com/.default"

# Robustere Defaults
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60
