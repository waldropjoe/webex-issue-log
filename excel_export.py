"""
excel_export.py — regenerates issue_log.xlsx as a read-only snapshot
of the issue store, for a human to look at.

This file is NOT part of the program's working state — issue_store.py
is the source of truth. This module only ever READS from the store and
writes a fresh copy of issue_log.xlsx; nothing in the pipeline ever
reads issue_log.xlsx back in. That's what eliminates the Excel
concurrency problem we redesigned around — there's no read-modify-
write cycle on this file anymore, just a full regenerate-and-replace
on every run.
"""

import os
from openpyxl import Workbook

from issue_store import get_all_issues

EXPORT_FILE = "issue_log.xlsx"
TEMP_EXPORT_FILE = "issue_log.xlsx.tmp"

COLUMNS = [
    "Issue ID",
    "Date/Time",
    "Reporter",
    "Issue Title",
    "Original Message",
    "Webex Link",
    "Category",
    "Severity",
    "Duplicate Of",
    "Status",
    "ADO Work Item ID",
]


def export_to_excel():
    """
    Builds a fresh issue_log.xlsx from everything currently in the
    store, then atomically swaps it in for the real file — writing to
    a temp file first means a crash mid-write can never leave a
    truncated or half-written file behind.
    """
    issues = get_all_issues()

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(COLUMNS)

    for row in issues:
        sheet.append(row)

    workbook.save(TEMP_EXPORT_FILE)
    os.replace(TEMP_EXPORT_FILE, EXPORT_FILE)  # atomic swap — same directory, same filesystem

    print(f"Exported {len(issues)} issue(s) to {EXPORT_FILE}")


if __name__ == "__main__":
    export_to_excel()