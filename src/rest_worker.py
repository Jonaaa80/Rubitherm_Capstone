import os
import requests
from dotenv import load_dotenv

load_dotenv()

CSCRM_API_KEY = (os.getenv("CSCRM_API_KEY") or "").strip()
CSCRM_SERVER = (os.getenv("CSCRM_SERVER") or "").strip().rstrip("/")

if not CSCRM_API_KEY or not CSCRM_SERVER:
    raise RuntimeError("CSCRM_API_KEY or CSCRM_SERVER not set in environment")

HEADER_VARIANTS = [
    {"X-apikey": CSCRM_API_KEY, "Accept": "application/json"},
    {"X-ApiKey": CSCRM_API_KEY, "Accept": "application/json"},
]

def get_people(per_page: int = 50, page: int = 1):
    """Retrieve people from CentralStationCRM."""
    url = f"{CSCRM_SERVER}/api/people.json"
    params = {"perpage": per_page, "page": page}
    last_resp = None
    for headers in HEADER_VARIANTS:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
        last_resp = resp
        if resp.status_code == 200:
            return resp.json()
        # 401 means auth header not accepted; try next variant
        if resp.status_code in (401, 403):
            continue
        # other errors: break early
        break
    # If we get here, all variants failed
    detail = last_resp.text if last_resp is not None else "<no response>"
    raise RuntimeError(f"Failed to get people (tried {len(HEADER_VARIANTS)} header variants): {last_resp.status_code if last_resp else 'n/a'} {detail}")

if __name__ == "__main__":
    data = get_people(per_page=5, page=1)
    if isinstance(data, list):
        print(f"Received {len(data)} people entries")
        for person in data[:10]:
            print(person)
    else:
        print(data)