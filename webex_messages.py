import requests
import os
from webex_auth import get_valid_access_token
from dotenv import load_dotenv

load_dotenv()

room_id = os.getenv("WEBEX_ROOM_ID")


def list_messages():
    token = get_valid_access_token()
    response = requests.get(
        "https://webexapis.com/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"roomId": room_id},
    )
    if not response.ok:
        print("Webex returned an error:", response.status_code)
        print(response.text)
    response.raise_for_status()
    messages = response.json()["items"]

    # --- GUARDRAIL (inactive by default) -----------------------------------
    # Follows Webex's pagination (a "Link" response header with rel="next")
    # to keep fetching older pages until there are none left, instead of
    # only ever returning the first page of results.
    while "next" in response.links:
        next_url = response.links["next"]["url"]
        response = requests.get(next_url, headers={"Authorization": f"Bearer {token}"})
        if not response.ok:
            print("Webex returned an error on a follow-up page:", response.status_code)
            print(response.text)
        response.raise_for_status()
        messages.extend(response.json()["items"])

    return messages


if __name__ == "__main__":
    messages = list_messages()
    for msg in messages:
        print(msg.get("personEmail"), "-", msg.get("text"))