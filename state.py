import json
import os

STATE_FILE = "state.json"


def load_last_seen_id():
    """
    Returns the ID of the most recently processed Webex message,
    or None if this is the very first run (no state.json yet).
    """
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r") as f:
        data = json.load(f)

    return data.get("last_seen_id")


def save_last_seen_id(message_id):
    """
    Records message_id as the new checkpoint.

    IMPORTANT: this is meant to be called after EVERY message is
    processed (not just once at the end of a run) — that's what makes
    an interrupted run safe to resume instead of reprocessing
    everything from scratch. See main.py's processing loop.
    """
    with open(STATE_FILE, "w") as f:
        json.dump({"last_seen_id": message_id}, f)


if __name__ == "__main__":
    print("Last seen ID:", load_last_seen_id())