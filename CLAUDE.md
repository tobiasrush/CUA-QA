# CUA QA - Project Instructions

## Project Overview
Computer Use Agent (CUA) QA testing framework. Uses Claude Opus 4.6 computer use API to visually automate QA tests defined in YAML or Google Sheets.

## Project Path
`/Users/tobyrush/Documents/GitHub/CUA-QA/`

## Python Environment
- Python 3.13 via venv: `/Users/tobyrush/Documents/GitHub/CUA-QA/venv/`
- Always use the venv Python: `/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python`
- Install packages: `/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/pip install <package>`

## Key Files
| File | Purpose |
|------|---------|
| `main.py` | Entry point - runs CUA agent with a task string |
| `test_runner.py` | Executes YAML test scripts via CUA |
| `computer_use_demo/` | Core CUA loop and tool implementations |
| `tests/*.yaml` | Test script definitions |
| `reports/` | Generated HTML test reports |

## Credentials

### Anthropic API
- Key stored in environment or `.env`
- Required for all CUA operations

### Google Sheets / Drive (Service Account)
- **GCP Project:** `cua-qa` (owner: `toby@useideem.com`)
- **Service Account:** `cua-qa-sheets@cua-qa.iam.gserviceaccount.com`
- **Key:** `~/Library/CloudStorage/GoogleDrive-tobyrush@gmail.com/My Drive/claude-config/credentials/cua-qa-service-account.json`
- **Scoped to:** Google Sheets API + Google Drive API only
- **Access:** Only files shared with the service account email
- **Test Sheet:** https://docs.google.com/spreadsheets/d/12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k
- **Sheet ID:** `12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k`

## Platforms

Tests can run on multiple platforms via `--platform`:

| Platform | Flag | Description |
|----------|------|-------------|
| Browser | `--platform browser` (default) | Chrome on macOS — supports `--url` for navigation |
| iOS | `--platform ios` | iPhone Mirroring on macOS — app must already be open |
| Android | `--platform android` | scrcpy on macOS — app must already be open |

The Google Sheet has platform-specific action columns: `Action_General`, `Action_Browser`, `Action_iOS`, `Action_Android`. For each test, the runner uses the platform-specific action if present, otherwise falls back to `Action_General`. Tests with no resolved action for the selected platform are skipped.

## Test Target (Browser)
- **URL:** https://demo.useideem.com/umfa.html?debug=true
- The `?debug=true` flag enables a **DEBUG OUTPUT** section near the top of the page
- The DEBUG OUTPUT section has a dark header bar labeled "DEBUG OUTPUT" and displays JSON log lines below it
- CUA must ONLY read the DEBUG OUTPUT section to determine test outcomes — never interpret the visual UI
- The DEBUG OUTPUT shows API responses, token values, error messages, and enrollment states
- Each test is self-contained; no shared context needed between tests

## Debug Output Instructions (Browser-Specific)
When running browser tests against the debug page:
- After performing any action, ONLY read the DEBUG OUTPUT section (near the top, with dark header bar) to extract results
- Do NOT interpret the visual UI elements — the DEBUG OUTPUT is the sole source of truth
- Read the JSON text in the DEBUG OUTPUT section carefully and report exactly what it says

## macOS Permissions Required
- **Accessibility:** iTerm2 (for pyautogui keyboard/mouse control)
- **Screen Recording:** iTerm2 (for pyautogui screenshots)

## Known Issues & Fixes

### pyautogui.hotkey("command", "v") is unreliable on macOS
- `pyautogui.hotkey("command", "v")` intermittently fails to deliver Cmd+V to the frontmost app
- The `type` action in `computer_use_demo/tools/computer.py` uses AppleScript paste instead:
  ```python
  subprocess.run(["osascript", "-e",
      'tell application "System Events" to keystroke "v" using command down'],
      check=True, timeout=5)
  ```
- This works reliably for Chrome, native macOS apps, iPhone Mirroring, and scrcpy
- **Do NOT revert this to use pyautogui.hotkey** — the AppleScript mechanism is the fix

### triple_click is NOT a valid CUA action
- The CUA model sometimes invents `triple_click` — this action does not exist
- Valid click actions: `left_click`, `right_click`, `double_click`
- To select all text in an input: use `key` action with `cmd+a`, NOT triple_click

### Input below the fold on debug=true page
- On `umfa.html?debug=true`, the debug console pushes the phone mockup down
- The User ID input is ~77px below the viewport fold
- CUA must scroll down before interacting with the input
- On `umfa.html?region=alipay` (no debug console), the input is in view without scrolling

## Diagnostics
- Located in `diagnostics/` directory
- `pyautogui_diagnostic.py` — comprehensive Selenium + pyautogui test (7 typing mechanisms, coordinate analysis, focus persistence)
- `test_webapp_input.py` — Playwright DOM-level test
- `cua_flow_test.py` — CUA timing pattern test (Selenium for coords, pyautogui for interactions)
- `simple_input.html` — minimal test page for CUA

## Rules
- Never run CUA tests without user confirmation (they take over mouse/keyboard)
- Use absolute paths for all script execution
- Do not modify `computer_use_demo/` files unless explicitly asked
