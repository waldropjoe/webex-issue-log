import time

from webex_messages import list_messages
from issue_store import initialize_store, get_next_issue_id, add_issue, get_open_issues, update_issue_status
from classifier import classify_message
from state import load_last_seen_id, save_last_seen_id
from ado_adapter import get_or_create_work_item, get_work_item_state, is_resolved_state
from excel_export import export_to_excel

# Self-imposed delay between classifier calls — a proactive guardrail so we
# don't hammer the Gemini API in a tight loop, especially on a first run
# that might process many messages at once. On top of, not instead of, the
# reactive retry logic already inside classify_message().
BACKFILL_DELAY_SECONDS = 1


def get_new_messages(last_seen_id):
    """
    Fetches messages from Webex (newest-first) and returns only the ones
    after last_seen_id, in OLDEST-to-NEWEST order — so an earlier new issue
    is already logged and available as dedup context by the time a later
    one in the same batch gets classified.

    If last_seen_id is None (very first run ever), every message currently
    returned by list_messages() is treated as new.
    """
    messages = list_messages()  # newest -> oldest

    if last_seen_id is None:
        new_messages = messages
    else:
        new_messages = []
        for msg in messages:
            if msg["id"] == last_seen_id:
                break
            new_messages.append(msg)

    new_messages.reverse()  # oldest -> newest
    return new_messages


def process_message(msg):
    """
    Runs one Webex message through the classifier and, if it's flagged as
    an issue, writes it into the issue store (SQLite).
    """
    text = msg.get("text")

    if not text:
        # Known deferred edge case: attachment-only messages have no text
        # for the classifier to read. Skipping rather than guessing.
        print(f"Skipping {msg['id']} — no text content (attachment-only?).")
        return

    open_issues = get_open_issues()
    result = classify_message(text, open_issues)

    if not result.is_issue:
        print(f"Not an issue, skipping: {text[:60]}")
        return

    if result.duplicate_of:
        # Reuse the ORIGINAL issue's work item — no new one created.
        ado_id = next(
            (i["ado_work_item_id"] for i in open_issues if i["issue_id"] == result.duplicate_of),
            "",
        )
    else:
        # get_or_create_work_item checks ADO for an existing item tagged
        # with this message's ID before creating a new one — this is the
        # idempotency guard: if a crash forces this exact message to be
        # reprocessed later, we reuse the item that was already created
        # instead of creating a duplicate bug.
        ado_id = get_or_create_work_item(
            title=result.issue_title or text[:120],
            description=(
                f"Reported by: {msg.get('personEmail', '')}\n"
                f"Original message: {text}"
            ),
            message_id=msg["id"],
        )

    issue_id = get_next_issue_id()
    webex_link = f"webexteams://im?space={msg['roomId']}"

    add_issue(
        issue_id=issue_id,
        message_id=msg["id"],
        date_time=msg.get("created", ""),
        reporter=msg.get("personEmail", ""),
        issue_title=result.issue_title or "",
        original_message=text,
        webex_link=webex_link,
        category=result.category.value,
        severity=result.severity.value,
        duplicate_of=result.duplicate_of or "",
        status="New",
        ado_work_item_id=ado_id,
    )
    print(f"Logged {issue_id}: {text[:60]}")


def sync_resolved_issues():
    """
    Checks every currently-open issue's ADO work item against its real
    current state, and marks it Resolved locally if that state counts
    as resolved (see ado_adapter.is_resolved_state).

    This is also the trigger for a future reporter notification: "a
    developer marking their own work resolved in ADO" — their normal
    workflow — rather than anyone having to remember to update a second
    place by hand.
    """
    open_issues = get_open_issues()
    for issue in open_issues:
        work_item_id = issue["ado_work_item_id"]
        if not work_item_id:
            continue

        state = get_work_item_state(work_item_id)
        if is_resolved_state(state):
            update_issue_status(issue["issue_id"], "Resolved")
            print(f"{issue['issue_id']} marked Resolved (ADO work item {work_item_id} is '{state}').")


def main():
    initialize_store()

    last_seen_id = load_last_seen_id()
    new_messages = get_new_messages(last_seen_id)

    # --- GUARDRAIL (inactive by default) -----------------------------------
    # What this does: limits how far back the very first run reaches,
    # instead of processing the room's entire message history.
    # When to turn it on: if you'd rather start with a recent slice of
    # history than the full backlog — avoids flooding a fresh log with old,
    # possibly-already-resolved chatter, and reduces first-run API calls.
    # -------------------------------------------------------------------------
    # from datetime import datetime, timedelta, timezone
    # WEBEX_BACKFILL_DAYS = 7
    # cutoff = datetime.now(timezone.utc) - timedelta(days=WEBEX_BACKFILL_DAYS)
    # new_messages = [
    #     m for m in new_messages
    #     if datetime.fromisoformat(m["created"].replace("Z", "+00:00")) >= cutoff
    # ]

    print(f"Found {len(new_messages)} new message(s) to process.")

    for msg in new_messages:
        process_message(msg)

        # Checkpoint after EVERY message, not just at the end of the run —
        # so an interrupted run resumes safely instead of reprocessing
        # everything from scratch.
        save_last_seen_id(msg["id"])

        time.sleep(BACKFILL_DELAY_SECONDS)

    sync_resolved_issues()
    export_to_excel()


if __name__ == "__main__":
    main()