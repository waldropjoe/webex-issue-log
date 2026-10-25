import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

ADO_ORG = os.getenv("ADO_ORG")
ADO_PROJECT = os.getenv("ADO_PROJECT")
ADO_PAT = os.getenv("ADO_PAT")
ADO_WORK_ITEM_TYPE = os.getenv("ADO_WORK_ITEM_TYPE", "Bug")
ADO_RESOLVED_STATES = {state.strip() for state in os.getenv("ADO_RESOLVED_STATES", "Done").split(",")}


def _auth_header():
    """
    Azure DevOps PATs use Basic auth with an EMPTY username and the PAT
    as the password — the string to encode is ":" + PAT, not PAT + ":".
    Verified against multiple sources before writing this; getting the
    order backwards is a documented, easy-to-make mistake that causes a
    silent 401.
    """
    token = base64.b64encode(f":{ADO_PAT}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def create_work_item(title, description, message_id):
    """
    Creates a new Azure DevOps work item and returns its numeric ID.

    Tags the new item with "webex:<message_id>" so that
    find_work_item_by_message_id() can find it again later. That tag is
    what makes get_or_create_work_item() below safe to call more than
    once for the same Webex message — without it, a crash between
    creating this item and recording that fact locally could cause a
    retried message to create a second, duplicate work item.

    Don't call this directly from main.py — go through
    get_or_create_work_item() instead, so the idempotency check always
    runs first.
    """
    url = (
        f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/wit/workitems/"
        f"${ADO_WORK_ITEM_TYPE}?api-version=7.2-preview.3"
    )

    headers = _auth_header()
    headers["Content-Type"] = "application/json-patch+json"

    body = [
        {"op": "add", "path": "/fields/System.Title", "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": description},
        {"op": "add", "path": "/fields/System.Tags", "value": f"webex:{message_id}"},
    ]

    response = requests.post(url, headers=headers, json=body)

    if not response.ok:
        print("Azure DevOps returned an error:", response.status_code)
        print(response.text)
    response.raise_for_status()

    return response.json()["id"]


def find_work_item_by_message_id(message_id):
    """
    Searches Azure DevOps for a work item already tagged with this
    Webex message ID (see the "webex:<message_id>" tag set in
    create_work_item). Returns the work item's numeric ID if one is
    found, or None if not.

    This is what lets get_or_create_work_item() avoid creating a
    duplicate work item if a message is ever processed twice — e.g. if
    the pipeline crashes after creating a work item but before
    checkpointing state.json, and the same message gets reprocessed.

    Uses Azure DevOps's WIQL (Work Item Query Language) — a separate,
    SQL-like query endpoint, distinct from the create/update endpoint
    above.

    If this ever starts returning 400 or 404, check Microsoft's REST
    API reference for the "Query By Wiql" endpoint's current
    api-version before assuming the query logic itself is wrong.
    """
    url = f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/wit/wiql?api-version=7.2-preview.2"

    headers = _auth_header()
    headers["Content-Type"] = "application/json"

    tag = f"webex:{message_id}"
    query = {
        "query": (
            "SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{ADO_PROJECT}' "
            f"AND [System.Tags] CONTAINS '{tag}'"
        )
    }

    response = requests.post(url, headers=headers, json=query)

    if not response.ok:
        print("Azure DevOps returned an error:", response.status_code)
        print(response.text)
    response.raise_for_status()

    work_items = response.json()["workItems"]
    return work_items[0]["id"] if work_items else None


def get_or_create_work_item(title, description, message_id):
    """
    The function main.py should actually call — not create_work_item()
    directly.

    Idempotency guard: checks whether a work item already exists for
    this exact Webex message before creating a new one. Safe to call
    more than once for the same message_id — always converges on the
    same single work item, no matter how many times a crash forces
    main.py to reprocess that message.
    """
    existing_id = find_work_item_by_message_id(message_id)
    if existing_id:
        print(f"Found existing ADO work item {existing_id} for message {message_id}, reusing it.")
        return existing_id
    return create_work_item(title, description, message_id)
def get_work_item_state(work_item_id):
    """
    Fetches a work item's current State field from Azure DevOps — used
    by the status-sync step to check whether an issue we created has
    since been resolved by a developer working directly in ADO.

    Uses ADO's basic "get one work item" endpoint — about as
    foundational and stable a part of their REST API as exists.
    """
    url = f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/wit/workitems/{work_item_id}?api-version=7.2-preview.3"

    headers = _auth_header()
    response = requests.get(url, headers=headers)

    if not response.ok:
        print("Azure DevOps returned an error:", response.status_code)
        print(response.text)
    response.raise_for_status()

    return response.json()["fields"]["System.State"]

def is_resolved_state(state):
    """
    Returns True if the given ADO work item state counts as "resolved"
    for this project. Configurable via ADO_RESOLVED_STATES in .env
    (comma-separated), since different process templates use different
    state names — this personal sandbox's "Basic" template only has
    "Done", while a company board on the "Agile" template might use
    "Resolved" and/or "Closed" instead. Defaults to "Done" if unset.
    """
    return state in ADO_RESOLVED_STATES

if __name__ == "__main__":
    new_id = get_or_create_work_item(
        "Test work item from webex-issue-log",
        "This is a test — safe to delete.",
        "manual-test-message-id",
    )
    print("Created/found work item:", new_id)