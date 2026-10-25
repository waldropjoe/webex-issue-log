import os
import sqlite3

DB_FILE = "issue_log.db"


def initialize_store():
    """
    Creates the issues table if it doesn't already exist. Safe to call
    on every run.
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                issue_id TEXT PRIMARY KEY,
                message_id TEXT UNIQUE,
                date_time TEXT,
                reporter TEXT,
                issue_title TEXT,
                original_message TEXT,
                webex_link TEXT,
                category TEXT,
                severity TEXT,
                duplicate_of TEXT,
                status TEXT,
                ado_work_item_id INTEGER
            )
            """
        )


def get_next_issue_id():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT issue_id FROM issues")
        existing_ids = [row[0] for row in cursor.fetchall()]

    if not existing_ids:
        return "ISSUE-0001"

    numbers = [int(issue_id.split("-")[1]) for issue_id in existing_ids]
    next_number = max(numbers) + 1
    return f"ISSUE-{next_number:04d}"


def add_issue(
    issue_id,
    message_id,
    date_time,
    reporter,
    issue_title,
    original_message,
    webex_link,
    category,
    severity,
    duplicate_of,
    status,
    ado_work_item_id,
):
    """
    Inserts one new issue row. Using "with sqlite3.connect(...)" means
    this insert is a real transaction — it either fully commits or
    fully rolls back if something goes wrong mid-write, unlike
    openpyxl's load-entire-file/save-entire-file pattern.
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            """
            INSERT INTO issues (
                issue_id, message_id, date_time, reporter, issue_title,
                original_message, webex_link, category, severity,
                duplicate_of, status, ado_work_item_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                message_id,
                date_time,
                reporter,
                issue_title,
                original_message,
                webex_link,
                category,
                severity,
                duplicate_of,
                status,
                ado_work_item_id,
            ),
        )


def get_open_issues():
    """
    Returns every issue that isn't resolved, as a list of dicts with
    issue_id, message and ado_work_item_id — the classifier uses these
    as duplicate-detection context.
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            "SELECT issue_id, original_message, ado_work_item_id "
            "FROM issues WHERE status != 'Resolved'"
        )
        rows = cursor.fetchall()

    return [
        {"issue_id": row[0], "message": row[1], "ado_work_item_id": row[2]}
        for row in rows
    ]
def get_all_issues():
    """
    Returns every issue in the store, in the exact column order
    excel_export.py needs — used to regenerate the full Excel export,
    as opposed to get_open_issues() above, which only returns a subset
    of fields for still-open issues (used for dedup context).
    """
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            "SELECT issue_id, date_time, reporter, issue_title, "
            "original_message, webex_link, category, severity, "
            "duplicate_of, status, ado_work_item_id "
            "FROM issues ORDER BY issue_id"
        )
        return cursor.fetchall()

def update_issue_status(issue_id, status):
    """
    Called by main.sync_resolved_issues() once a work item has moved
    to a resolved state in Azure DevOps.
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE issues SET status = ? WHERE issue_id = ?",
            (status, issue_id),
        )


if __name__ == "__main__":
    initialize_store()
    print("Next issue ID:", get_next_issue_id())

    add_issue(
        issue_id="ISSUE-TEST-0001",
        message_id="manual-test-message-id",
        date_time="2026-09-17T00:00:00Z",
        reporter="test@example.com",
        issue_title="Test issue from issue_store.py",
        original_message="This is a test row — safe to delete.",
        webex_link="webexteams://im?space=test",
        category="Bug",
        severity="Low",
        duplicate_of="",
        status="New",
        ado_work_item_id=None,
    )

    print("Open issues:", get_open_issues())