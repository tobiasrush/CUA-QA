"""
Google Sheets integration for CUA QA.
Loads test scripts from Google Sheets and writes results back.
"""

import os
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

# Credential path: set GOOGLE_SERVICE_ACCOUNT_KEY env var, or place file at ./service-account.json
DEFAULT_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    os.path.join(os.path.dirname(__file__), "service-account.json"),
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_sheets_client(credentials_path: str = DEFAULT_CREDENTIALS_PATH) -> gspread.Client:
    """Authenticate with service account and return a gspread client."""
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def load_tests_from_sheet(sheet_id: str, platform: str = "browser", tab_name: str = "TestScripts") -> list[dict]:
    """Read the TestScripts tab and return a list of test dicts.

    Each row with a Test_Name becomes one test. Groupings carry forward
    from the last group-header row. Rows without a Test_Name are skipped.

    The special "Initialization" test is excluded from the test list and
    returned separately via load_initialization_from_sheet().

    Action resolution: uses Action_{platform} if non-empty, else Action_General.
    Rows where the resolved action is empty are skipped.

    Returns list of:
        {
            "name": "CheckAllEnrollment_NoZSM_NoPK",
            "grouping": "Enroll ZSM",
            "platform": "browser",
            "steps": [{
                "action": "...",
                "expected": "...",
                "state_before": "...",
                "state_after": "..."
            }]
        }
    """
    client = get_sheets_client()
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(tab_name)
    rows = worksheet.get_all_values()

    if not rows:
        return []

    # Map columns by header name so column order doesn't matter
    header = [h.strip().lower().replace(" ", "_") for h in rows[0]]
    col = {}
    for name in [
        "step", "groupings", "action_general", "action_browser", "action_ios", "action_android",
        "test_name", "state_before", "state_after", "expected_outcome",
    ]:
        col[name] = header.index(name) if name in header else None

    data_rows = rows[1:]

    tests = []
    current_grouping = ""

    for row in data_rows:
        # Pad short rows to match header length
        while len(row) < len(header):
            row.append("")

        def get(name):
            idx = col.get(name)
            return row[idx].strip() if idx is not None else ""

        step = get("step")
        grouping_cell = get("groupings")
        test_name = get("test_name")
        state_before = get("state_before")
        state_after = get("state_after")
        expected_outcome = get("expected_outcome")

        # Resolve action: platform-specific column wins, then general fallback
        action = get(f"action_{platform}") or get("action_general")

        # Update current grouping if a new one appears
        if grouping_cell:
            current_grouping = grouping_cell

        # Skip rows without a test name (group headers or empty rows)
        if not test_name:
            continue

        # Skip the Initialization row — it's loaded separately
        if test_name.lower() == "initialization":
            continue

        # Skip rows where no action is available for this platform
        if not action:
            continue

        tests.append({
            "step": step,
            "name": test_name,
            "grouping": current_grouping,
            "platform": platform,
            "steps": [{
                "action": action,
                "expected": expected_outcome,
                "state_before": state_before,
                "state_after": state_after,
            }],
        })

    return tests


def load_initialization_from_sheet(sheet_id: str, platform: str = "browser", tab_name: str = "TestScripts") -> str:
    """Load platform-specific initialization instructions from the Initialization row.

    Returns the resolved action text (platform-specific or general fallback),
    or empty string if no Initialization row exists.
    """
    client = get_sheets_client()
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(tab_name)
    rows = worksheet.get_all_values()

    if not rows:
        return ""

    header = [h.strip().lower().replace(" ", "_") for h in rows[0]]
    col = {}
    for name in [
        "action_general", "action_browser", "action_ios", "action_android", "test_name",
    ]:
        col[name] = header.index(name) if name in header else None

    for row in rows[1:]:
        while len(row) < len(header):
            row.append("")

        def get(name):
            idx = col.get(name)
            return row[idx].strip() if idx is not None else ""

        if get("test_name").lower() == "initialization":
            return get(f"action_{platform}") or get("action_general")

    return ""


RESULTS_HEADER = ["Test_Run", "Date", "Groupings", "Test_Name", "TestScript_Action", "CUA_Action", "Expected_Outcome", "CUA_Result", "Debug_Results", "CUA_Thinking", "Claude_Evaluating"]


def _get_next_test_run(worksheet) -> int:
    """Determine the next Test_Run number by reading existing data."""
    all_values = worksheet.get_all_values()
    if len(all_values) <= 1:
        return 1
    max_run = 0
    for row in all_values[1:]:
        try:
            val = int(row[0])
            if val > max_run:
                max_run = val
        except (ValueError, IndexError):
            continue
    return max_run + 1


def write_results_to_sheet(
    sheet_id: str, results: list[dict], tab_name: str = "Results",
    test_run: int | None = None,
) -> int:
    """Append test results to the Results tab.

    Columns: Test_Run, Date, Groupings, Test_Name, TestScript_Action, CUA_Action,
             Expected_Outcome, CUA_Result, Debug_Results, CUA_Thinking, Claude_Evaluating.

    Args:
        sheet_id: Google Sheet ID.
        results: List of result dicts (see column mapping below).
        tab_name: Worksheet name (default "Results").
        test_run: Explicit run number. If None, auto-increments from existing data.

    Returns the test_run number used.
    """
    client = get_sheets_client()
    sheet = client.open_by_key(sheet_id)

    try:
        worksheet = sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=tab_name, rows=1000, cols=len(RESULTS_HEADER))
        worksheet.append_row(RESULTS_HEADER)

    if test_run is None:
        test_run = _get_next_test_run(worksheet)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_write = []

    for r in results:
        rows_to_write.append([
            test_run,
            timestamp,
            r.get("grouping", ""),
            r.get("test_name", ""),
            r.get("testscript_action", ""),
            r.get("cua_action", ""),
            r.get("expected", ""),
            r.get("cua_result", ""),
            r.get("debug_results", ""),
            r.get("cua_thinking", ""),
            r.get("claude_evaluating", ""),
        ])

    if rows_to_write:
        worksheet.append_rows(rows_to_write, value_input_option="USER_ENTERED")

    return test_run


if __name__ == "__main__":
    """Standalone test: read the sheet and print parsed tests."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Test Google Sheets loader")
    parser.add_argument("sheet_id", nargs="?", default="12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k")
    parser.add_argument("--platform", choices=["browser", "ios", "android"], default="browser")
    parser.add_argument("--json", action="store_true", help="Output tests and initialization as JSON")
    args = parser.parse_args()

    tests = load_tests_from_sheet(args.sheet_id, platform=args.platform)
    initialization = load_initialization_from_sheet(args.sheet_id, platform=args.platform)

    if args.json:
        output = {
            "sheet_id": args.sheet_id,
            "platform": args.platform,
            "initialization": initialization,
            "test_count": len(tests),
            "tests": tests,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Loading tests from sheet: {args.sheet_id} (platform: {args.platform})")
        print(f"\nFound {len(tests)} tests:\n")
        for t in tests:
            print(f"  [{t['grouping']}] {t['name']} (platform: {t['platform']})")
            step = t["steps"][0]
            print(f"    Action: {step['action']}")
            print(f"    State Before: {step['state_before']}")
            print(f"    State After: {step['state_after']}")
            print(f"    Expected: {step['expected']}")
            print()
