# Webex Pilot Chat Issue Log

Reads an alpha pilot's Webex feedback channel, uses an LLM to figure out which messages are actually reporting issues, triages them, and turns them into deduplicated Azure DevOps work items — automatically, on a schedule.

> **A concept build.** This was designed around a hypothetical alpha pilot and tested against my own Webex space and a personal Azure DevOps sandbox. It hasn't been used with any real company data.

## Why I built this

Picture an alpha pilot whose feedback all flows into a single Webex space. Reading through it by hand to find real issues (versus general chatter) doesn't scale. I built this partly to solve that problem and partly to learn how to wire together a real, API-driven pipeline end to end: OAuth against a chat platform, structured output from an LLM, state checkpointing, idempotent external side effects, and a storage layer that's actually safe for concurrent access — not just a script that works once.

## How it works

Every scheduled run does three things, in order:

```
1. INGEST NEW MESSAGES

   Webex Space
        │
        ▼
   Fetch new messages ─────────────────────── webex_messages.py
        │
        ▼
   Already processed? ──────────────────────── state.py
      │ yes                  │ no
      ▼                      ▼
    skip            Classify with an LLM ────── classifier.py (Gemini)
                             │
                       is it a real issue?
                       category / severity
                       inferred, dev-friendly title
                       duplicate of an open issue?
                             │
                  ┌──────────┴──────────┐
                  │ not an issue          │ is an issue
                  ▼                       ▼
              discarded          Get-or-create ADO work item
                                  (tagged with the message ID —
                                  a retry after a crash reuses the
                                  same item instead of creating
                                  a duplicate) ─────────────────── ado_adapter.py
                                          │
                                          ▼
                             Write the issue ──────────────────── issue_store.py
                                                                    (SQLite — the
                                                                    source of truth)

2. SYNC RESOLVED STATUS

   For every still-open issue, check its ADO work
   item's real current state ────────────────────────────────── ado_adapter.py
        │
        ▼
   Resolved in ADO? → update the store ──────────────────────── issue_store.py

3. EXPORT A SNAPSHOT

   Regenerate issue_log.xlsx fresh from the store,
   written atomically so a crash mid-write never
   leaves a corrupt file behind ─────────────────────────────── excel_export.py
```

The whole pipeline runs on a schedule (every 15 minutes via `launchd` on macOS), so once it's set up it needs no manual attention. `issue_log.xlsx` is a read-only snapshot regenerated from the database on every run — it's never read back in, which is what keeps two writers (a scheduled run and someone with the file open) from ever corrupting each other's data.

## Tech stack

- Python 3.10
- Webex REST API, via an OAuth Integration (not a bot — bots can't see un-mentioned messages in a group space)
- Google Gemini (`google-genai` SDK), structured output via Pydantic
- SQLite (`sqlite3`, built into Python) as the source of truth — chosen as a concrete local stand-in for whatever managed database a production deployment would actually use; the rest of the app only depends on `issue_store.py`'s functions, not on SQLite specifically
- `openpyxl` for the read-only Excel export
- Azure DevOps REST API for work item creation and status polling
- `launchd` (macOS) for scheduling

## Setup

1. Clone the repo and create a virtual environment:
   ```
   git clone <this repo>
   cd webex-issue-log
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your own credentials:
   - `WEBEX_*` — from a Webex Integration you register yourself at [developer.webex.com](https://developer.webex.com)
   - `GEMINI_API_KEY` — a free-tier key from Google AI Studio
   - `ADO_ORG`, `ADO_PROJECT`, `ADO_PAT`, `ADO_WORK_ITEM_TYPE` — from your own Azure DevOps organization and a Personal Access Token
   - `ADO_RESOLVED_STATES` — comma-separated list of your ADO board's work item states that count as "resolved" (e.g. `Done`, or `Resolved,Closed`) — this varies by process template, so check your board's actual State dropdown rather than assuming
3. Sign in to Webex once to create a local `tokens.json` (gitignored):
   ```
   python3 webex_auth.py login
   ```
   This opens Webex in your browser, catches the redirect on `WEBEX_REDIRECT_URI`, and saves the tokens. After that, `main.py` refreshes them on its own.
4. Run `python3 main.py` once by hand to confirm everything is wired up before scheduling it.

None of these credentials are stored in code — everything is read from `.env`, which is gitignored, so this can point at any Webex space, Gemini key, or ADO org/board without touching a single line of code.

## Usage

```
python3 main.py
```

Each run fetches any new messages, classifies them, writes real issues to the database, checks whether any previously-logged issue has since been resolved in Azure DevOps, and regenerates `issue_log.xlsx` as a fresh snapshot.

For hands-off operation, schedule it to run periodically — this project uses a `launchd` LaunchAgent on macOS. A template is in [`launchd/com.example.webex-issue-log.plist`](launchd/com.example.webex-issue-log.plist): fill in your paths, copy it to `~/Library/LaunchAgents/`, and load it with `launchctl load`. Porting to Windows would mean swapping in Task Scheduler instead.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Orchestrates the full pipeline: ingest → classify → store → sync ADO status → export |
| `webex_auth.py` | Webex OAuth token exchange and refresh |
| `webex_messages.py` | Fetches messages from the Webex space |
| `classifier.py` | LLM-based issue detection, triage, and title generation (Gemini) |
| `issue_store.py` | SQLite-backed issue store — the program's source of truth |
| `excel_export.py` | Regenerates `issue_log.xlsx` as a read-only snapshot of the store |
| `ado_adapter.py` | Creates ADO work items (idempotently) and polls their resolution status |
| `state.py` | Tracks the last processed Webex message so nothing is reprocessed |

## Roadmap

- More robust, structured issue descriptions (beyond the raw message text)
- Notify the original reporter when their issue is resolved — the trigger is solved (a developer marking their work resolved in ADO), the actual notification delivery (likely a Webex bot messaging the reporter directly) isn't built yet
- Handle image attachments on bug reports
- Replace the Webex polling loop with a webhook listener

## License

MIT — see [LICENSE](LICENSE).