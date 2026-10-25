import os
import time
from google import genai
from dotenv import load_dotenv
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from google.genai.errors import ServerError

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Category(str, Enum):
    BUG = "Bug"
    PERFORMANCE = "Performance"
    UI_UX = "UI/UX"
    OTHER = "Other"


class ClassificationResult(BaseModel):
    is_issue: bool
    issue_title: Optional[str] = None
    category: Optional[Category] = None
    severity: Optional[Severity] = None
    duplicate_of: Optional[str] = None

def classify_message(message_text, open_issues, max_retries=3):
    open_issues_text = "\n".join(
        f"- {issue['issue_id']}: {issue['message']}" for issue in open_issues
    )
    prompt = f"""
You are triaging messages from a software pilot feedback channel.

Determine whether the following message is reporting a real software issue
(a bug, a performance problem, broken functionality) as opposed to general
chatter, questions, or unrelated conversation.

If it IS an issue, also determine:
- issue_title: a short, clear bug-report-style title, the way a developer
  would write one for a tracking system — state what's broken and where,
  in a few words. Do not just repeat the user's message verbatim, and do
  not write something vague like "there's a bug." For example, a message
  like "the export button is broken" might become
  "Export button unresponsive on click." Null if not an issue.
- category: one of Bug, Performance, UI/UX, Other
- severity: one of Low, Medium, High, Critical
- duplicate_of: the Issue ID of an existing open issue below that this message
  appears to describe the same underlying problem as, or null if it's a new issue

Currently open issues:
{open_issues_text if open_issues_text else "(none)"}

Message to classify:
"{message_text}"
"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config={
                "response_mime_type": "application/json",
                "response_schema": ClassificationResult,
                },
            )
            return ClassificationResult.model_validate_json(response.text)
        except ServerError as e:
            print(f"Gemini server error (attempt {attempt + 1}/{max_retries}):",e)
            if attempt < max_retries - 1:
                time.sleep(5)

    raise RuntimeError("Gemini API unavailable after multiple retries.")


if __name__ == "__main__":
    from issue_store import initialize_store, get_open_issues

    initialize_store()

    open_issues = get_open_issues()

    result = classify_message("this is a buig", open_issues)
    print("Test 1 (known duplicate):", result)

    result2 = classify_message("lol yeah happy hour at 5 today", open_issues)
    print("Test 2 (not an issue):", result2)