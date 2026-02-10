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


def load_tests_from_sheet(sheet_id: str, tab_name: str = "TestScripts") -> list[dict]:
    """Read the TestScripts tab and return a list of test dicts.

    Each row with a Test_Name becomes one test. Groupings carry forward
    from the last group-header row. Rows without a Test_Name are skipped.

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

    # First row is header — skip it
    header = rows[0]
    data_rows = rows[1:]

    tests = []
    current_grouping = ""

    for row in data_rows:
        # Pad short rows
        while len(row) < 6:
            row.append("")

        grouping_cell = row[0].strip()
        action = row[1].strip()
        test_name = row[2].strip()
        state_before = row[3].strip()
        state_after = row[4].strip()
        expected_outcome = row[5].strip()

        # Update current grouping if a new one appears
        if grouping_cell:
            current_grouping = grouping_cell

        # Skip rows without a test name (group headers or empty rows)
        if not test_name:
            continue

        tests.append({
            "name": test_name,
            "grouping": current_grouping,
            "platform": "browser",
            "steps": [{
                "action": action,
                "expected": expected_outcome,
                "state_before": state_before,
                "state_after": state_after,
            }],
        })

    return tests


def write_results_to_sheet(
    sheet_id: str, results: list[dict], tab_name: str = "Results"
) -> int:
    """Append test results to the Results tab.

    Each result dict should have: grouping, test_name, expected, actual.
    Returns the number of rows written.
    """
    client = get_sheets_client()
    sheet = client.open_by_key(sheet_id)

    try:
        worksheet = sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=tab_name, rows=1000, cols=5)
        worksheet.append_row(["Date/Time", "Grouping", "Test_Name", "Expected", "Actual"])

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_write = []

    for r in results:
        rows_to_write.append([
            timestamp,
            r.get("grouping", ""),
            r.get("test_name", ""),
            r.get("expected", ""),
            r.get("actual", ""),
        ])

    if rows_to_write:
        worksheet.append_rows(rows_to_write, value_input_option="USER_ENTERED")

    return len(rows_to_write)


if __name__ == "__main__":
    """Standalone test: read the sheet and print parsed tests."""
    import sys

    sheet_id = sys.argv[1] if len(sys.argv) > 1 else "12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k"

    print(f"Loading tests from sheet: {sheet_id}")
    tests = load_tests_from_sheet(sheet_id)

    print(f"\nFound {len(tests)} tests:\n")
    for t in tests:
        print(f"  [{t['grouping']}] {t['name']}")
        step = t["steps"][0]
        print(f"    Action: {step['action']}")
        print(f"    State Before: {step['state_before']}")
        print(f"    State After: {step['state_after']}")
        print(f"    Expected: {step['expected']}")
        print()
