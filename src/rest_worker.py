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
            resp = requests.get(url, headers=headers,
                                params=params, timeout=20)
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
    raise RuntimeError(
        f"Failed to get people (tried {len(HEADER_VARIANTS)} header variants): {last_resp.status_code if last_resp else 'n/a'} {detail}")


def is_email_exist_in_crm(email):
    url = f"{CSCRM_SERVER}/api/people/search"
    params = {'email': email}

    for headers in HEADER_VARIANTS:
        try:
            resp = requests.get(url, headers=headers, params=params)
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
        if resp.status_code == 200 and len(resp.json()) > 0:
            return True

    return False


def is_person_name_exist_in_crm(first_name, last_name):
    url = f"{CSCRM_SERVER}/api/people/search"
    params = {'first_name': first_name, "name": last_name}
    for headers in HEADER_VARIANTS:
        try:
            resp = requests.get(url, headers=headers, params=params)
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
        if resp.status_code == 200 and len(resp.json()) > 0:
            return True

    return False


def is_person_exist_in_crm(email, first_name, last_name):
    url = f"{CSCRM_SERVER}/api/people/search"
    params = {'email': email, 'first_name': first_name, "name": last_name}
    for headers in HEADER_VARIANTS:
        try:
            resp = requests.get(url, headers=headers, params=params)
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
        if resp.status_code == 200 and len(resp.json()) > 0:
            return True

    return False

# TODO


def update_email(person_id, email):
    url = f"{CSCRM_SERVER}/api/people/" + \
        str(person_id) + "/contact_details"
    params = {
        "includes": "positions companies deals",
        "methods": "responsible_user_natural_name salutation_official",
        "no_log": "true"
    }
    payload_tel = {
        "email": {
            "attachable_type": "Person",
            "attachable_id": 0,
            "atype": "office",
            "name": email
        }
    }

    for headers in HEADER_VARIANTS:
        try:
            resp = requests.post(url, headers=headers,
                                 params=params, json=payload_tel)
            return resp.status_code == 201
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
    return False

# TODO


def update_tel(person_id, tel):
    url = f"{CSCRM_SERVER}/api/people/" + \
        str(person_id) + "/contact_details"
    params = {
        "includes": "positions companies deals",
        "methods": "responsible_user_natural_name salutation_official",
        "no_log": "true"
    }
    payload_tel = {
        "tel": {
            "attachable_type": "Person",
            "attachable_id": 0,
            "atype": "office",
            "name": tel
        }
    }

    for headers in HEADER_VARIANTS:
        try:
            resp = requests.post(url, headers=headers,
                                 params=params, json=payload_tel)
            return resp.status_code == 201
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e
    return False

# add a new person details, first it will check if existance of person in crm before than only create


def create_person_in_crm(email, first_name, last_name, gender, salutation="Mr", title="", tel="121212112"):
    if is_person_exist_in_crm(email, first_name, last_name):
        print(
            f"Person with name: {first_name} {last_name} and email {email} exist in CRM")
        return

    url = f"{CSCRM_SERVER}/api/people"

    params = {
        "includes": "positions companies deals",
        "methods": "responsible_user_natural_name salutation_official",
        "no_log": "true"
    }

    payload = {
        "person": {
            "country_code": "de",
            "salutation": salutation,
            "title": title,
            "gender": gender,
            "first_name": first_name,
            "name": last_name,
            'email': email
        }
    }
    # response = requests.post(url, headers=headers, params=params, json=payload)
    for headers in HEADER_VARIANTS:
        try:
            resp = requests.post(url, headers=headers,
                                 params=params, json=payload)
            print("Status:", resp.status_code)
            resp_out = resp.json()
            person_id = resp_out["person"]["id"]
            update_email(person_id, email)
            update_tel(person_id, tel)
            break
        except requests.RequestException as e:
            raise RuntimeError(f"Network error calling {url}: {e}") from e


if __name__ == "__main__":
    data = get_people(per_page=10, page=1)
    if isinstance(data, list):
        print(f"Received {len(data)} people entries")
        for person in data[:10]:
            print(person)

    else:
        print(data)

    email = 'mahegupt@gmail.com'
    print(f"\n Does Email id {email} ", is_email_exist_in_crm(email))
    email = 'mahesh@luxhaus.de'
    print(f"\n Does Email id {email} ", is_email_exist_in_crm(email))
    first_name = 'Mahesh'
    last_name = "Gupta"
    print(f"\n{first_name},{last_name} does exist in CRM:",
          is_person_name_exist_in_crm(first_name, last_name))

    first_name = 'Carole'
    last_name = "Allal"
    print(f"\n{first_name},{last_name} does exist in CRM:",
          is_person_name_exist_in_crm(first_name, last_name))

    print(f"\nis the Person: {first_name},{last_name} with email {email} exist in CRM?",
          is_person_exist_in_crm(email, first_name, last_name))
    email = 'carole.allal@emballiso.com'
    print(f"\n Does the Person: {first_name},{last_name} with email {email} exist in CRM?",
          is_person_exist_in_crm(email, first_name, last_name))

    # Test to add a new person..
    print("Create a new person\n\n")
    create_person_in_crm("mahegupt@gmail.com", "Mahesh", "Gupta", "Male")

    email = 'mahegupt@gmail.com'
    print(
        f"\nDoes Email id {email} exists in CRM", is_email_exist_in_crm(email))

    first_name = 'Mahesh'
    last_name = "Gupta"
    print(f"\nDoes Person {first_name},{last_name} exist in CRM:",
          is_person_name_exist_in_crm(first_name, last_name))
