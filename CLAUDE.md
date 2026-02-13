# CUA QA - Orchestrator Instructions

## Role

Claude is the Orchestrator for CUA QA testing. The CUA (Computer Use Agent) executes visual actions using Gemini (default) or Opus — it only does what the Orchestrator tells it. The Orchestrator loads test steps from a Google Sheet, sends them to CUA one at a time, judges pass/fail, handles failures, and writes results back to the sheet.

The user must specify the platform (browser, ios, android) before beginning. Do not start without it.

## Execution Workflow

### 1. Load TestScripts from Google Sheet

```bash
/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python \
  /Users/tobyrush/Documents/GitHub/CUA-QA/sheets_loader.py SHEET_ID --platform browser --json
```

Outputs JSON with `initialization`, `tests[]`, each test having `step`, `name`, `grouping`, `steps[].action`, `steps[].expected`, `steps[].state_before`, `steps[].state_after`.

**Selecting which tests to run:** The user may specify tests in two ways:
- **By Step number** (e.g., "run steps 1-11"): Match against the `Step` column in the TestScripts sheet.
- **By Test_Name** (e.g., "run Auth_ZSM_Only"): Match against the `Test_Name` column.

### 2. Initialize

Each CUA call starts with a fresh conversation — no context carries over between steps. This is the default behavior of `cua_step_runner.py`. Do NOT pass `--persist-context`.

**Browser:**
```bash
/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python \
  /Users/tobyrush/Documents/GitHub/CUA-QA/cua_step_runner.py \
  --prompt "Open a new tab in Google Chrome (Cmd+T) and navigate to https://demo.useideem.com/umfa.html?debug=true. Wait for the page to be fully loaded." \
  --output /tmp/step_init.json
```

**iOS / Android:** Not yet configured. Stop immediately if requested.

### 3. Execute each test step

For each step: build the prompt → send to CUA → read the result → evaluate → **write to sheet immediately** (do not proceed to the next step until the write completes).

#### 3.1 - Build the Prompt

The TestScripts sheet has four action columns: `Action_General`, `Action_Browser`, `Action_iOS`, `Action_Android`. Use the platform-specific column if it has content, otherwise fall back to `Action_General`.

**Browser template:**
```
You are already on the correct page. Do NOT open a new tab or navigate away. Work on the current page.

ACTION: [Exact text from TestScripts sheet]

After the action, read the DEBUG OUTPUT section (dark header bar near the top of the page) and report what it says. This will be JSON String. Return the exact strings. No commentary or descriptions, just the exact text.
```

**Prompt rules:**
- Never use `triple_click` or `wait` — these are invalid CUA actions. Use `cmd+a` to select all text.
- **Prevented vs Preferred radio buttons:** CUA frequently misreads these labels because they look similar. When the action references a radio button selection, inject positional hints into the prompt. Both the Enroll (left) and Authenticate (right) panels have 3 radio buttons in this order top-to-bottom and a checkbox:
  1. **Required** (1st/top)
  2. **Preferred** (2nd)
  3. **Discouraged** (3rd)
  4. **Prevented** (4th/bottom)
  - Example: if the action says "make sure [Prevented] is selected", rewrite as: "make sure [Prevented] is selected — this is the 4th (bottom), below Discouraged. Do NOT select Preferred (2nd radio button)."

#### 3.2 - Send to CUA

Every call to `cua_step_runner.py` requires two arguments:
- `--prompt` — the assembled prompt from step 3.1
- `--system-suffix` — the CUA system instructions below (pass this exact text on every call)

**CUA system suffix:**
```
You are a QA testing agent. Execute actions precisely. IMPORTANT: wait is NOT a valid action. triple_click is NOT a valid action. To select all text in an input field, use the key action with cmd+a. VISUAL VERIFICATION: Before clicking any button or radio button, read its exact label character by character. Do NOT assume based on position or first few letters. After selecting a radio button, verify which one is filled by reading ALL labels in the group. Common confusion: 'Prevented' (4th/bottom) vs 'Preferred' (2nd) — these are DIFFERENT options. Read the FULL word before clicking.
```

**Command:**
```bash
/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python \
  /Users/tobyrush/Documents/GitHub/CUA-QA/cua_step_runner.py \
  --prompt "..." \
  --system-suffix "<CUA system suffix above>" \
  --output /tmp/step_N.json
```

Optional: add `--provider anthropic` to use Opus instead of Gemini (default).

#### 3.3 - Read the result

Read the output file (`/tmp/step_N.json`). Key fields:
- `status`: `"done"` or `"error"`
- `debug_results`: text CUA read from the DEBUG OUTPUT panel (may contain JSON log lines)
- `cua_comments`: CUA's full narration of what it did and saw

The debug panel output contains JSON log lines like:
```json
{"_ts":"20260212173613","type":"result","action":"enroll","result":"success","ctx":"enroll"}
{"_ts":"20260212173613","type":"result","action":"validateToken","result":"success","ctx":"validateToken","webauthn_uv":true}
```

#### 3.4 - Evaluate the result

Compare:
- **Expected**: `step.expected` from the Google Sheet
- **Actual**: `debug_results` from the CUA output

Use your intelligence to determine if the actual output satisfies the expected outcome. No rigid string matching — read both, understand the intent, and decide PASS or FAIL.

Prioritize JSON lines with `"type":"result"`. Sometimes an error message in the output is the correct expected outcome.

Special cases:
- If CUA `status` is `"error"` → mark ERROR (CUA couldn't execute, not a test failure)
- If `debug_results` is empty → decide based on whether the expected outcome required debug output

#### 3.5 - Write result to Google Sheet (MANDATORY — DO NOT SKIP)

**CRITICAL: You MUST write each result to the Google Sheet immediately after evaluating it — before moving to the next step. Do NOT batch results or defer writing to the end. Every step must be written individually, right after evaluation.**

```bash
/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python -c "
import sys; sys.path.insert(0, '/Users/tobyrush/Documents/GitHub/CUA-QA')
from sheets_loader import write_results_to_sheet
test_run = write_results_to_sheet('SHEET_ID', [{
    'grouping': '...',
    'test_name': '...',
    'testscript_action': '...',
    'cua_action': '...',
    'expected': '...',
    'cua_result': 'PASS',
    'debug_results': '...',
    'cua_thinking': '...',
    'claude_evaluating': '...',
}], test_run=N)
print(test_run)
"
```

**test_run handling:** On the first step, omit `test_run` (or pass `test_run=None`) to auto-increment. The script prints the assigned `test_run` to stdout — capture it and pass it to all subsequent steps.

#### Results columns — what goes in each field

| Column | What to write |
|--------|---------------|
| **Test_Run** | Run number (shared across all steps in a session) — auto-filled |
| **Date** | Execution timestamp — auto-filled |
| **Groupings** | `test["grouping"]` from TestScripts |
| **Test_Name** | `test["name"]` from TestScripts |
| **TestScript_Action** | Verbatim `test["steps"][0]["action"]` from TestScripts — the raw action text, not the prompt |
| **CUA_Action** | The **exact, complete `--prompt` string** passed to `cua_step_runner.py`. This is the full assembled prompt including the template pre-text, `ACTION:` line, and post-text. Never abbreviate or summarize. |
| **Expected_Outcome** | `test["steps"][0]["expected"]` from TestScripts |
| **CUA_Result** | PASS / FAIL / ERROR |
| **Debug_Results** | `debug_results` from the step output JSON — the raw debug panel content |
| **CUA_Thinking** | `cua_comments` from the step output JSON — CUA's full narration |
| **Claude_Evaluating** | Orchestrator's reasoning for the PASS/FAIL/ERROR determination |

## Screen Output

Print progress so the user can follow along.

**Before each step:**
```
--- Step 3/12: [Test_Name] ---
Prompt: ACTION: Enter "12345" into the User ID field and tap Submit
```

**After each step:**
```
Result: PASS
```
```
Result: FAIL — Expected "success with token", got "error: invalid user"
```
```
Result: ERROR — CUA error: screenshot timeout
```

**On retries:**
```
Retrying step 3/12...
Result: PASS (retry)
```

## Failure Handling

- **CUA error** (status=error): Retry once with same prompt. If still error → mark ERROR, continue.
- **Judgment FAIL** (debug doesn't match expected): Retry once with an adapted prompt (add scroll instruction, be more explicit about element). If still FAIL → mark FAIL, continue.
- **Abort rule**: If 3 consecutive steps fail within the same test, abort remaining steps in that test and move to next test.
- Never retry on clear logical failures (debug output shows wrong state — the app is wrong, not CUA).

---

## Reference

### Project Path

`/Users/tobyrush/Documents/GitHub/CUA-QA/`

### Python Environment

- Python 3.13 via venv: `/Users/tobyrush/Documents/GitHub/CUA-QA/venv/`
- Always use the venv Python: `/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python`
- Install packages: `/Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/pip install <package>`

### Key Files

| File | Purpose |
|------|---------|
| `cua_step_runner.py` | Single-step CUA executor — runs one prompt, returns JSON. Default: Gemini. Use `--provider anthropic` for Opus. |
| `sheets_loader.py` | Loads tests + initialization from Google Sheet (`--json` for JSON output) |
| `sheets_loader.write_results_to_sheet()` | Writes results (Test_Run, CUA_Result, Debug_Results, etc.) back to Results tab |
| `main.py` | Standalone entry point — runs CUA agent with a task string |
| `test_runner.py` | Executes YAML test scripts via CUA |
| `computer_use_demo/` | Core CUA loop and tool implementations |

### Credentials

**Gemini API** (default provider)
- Key: `GEMINI_API_KEY` in environment or `.env`

**Anthropic API** (optional, for `--provider anthropic`)
- Key: `ANTHROPIC_API_KEY` in environment or `.env`

**Google Sheets / Drive (Service Account)**
- **GCP Project:** `cua-qa` (owner: `toby@useideem.com`)
- **Service Account:** `cua-qa-sheets@cua-qa.iam.gserviceaccount.com`
- **Key:** `~/Library/CloudStorage/GoogleDrive-tobyrush@gmail.com/My Drive/claude-config/credentials/cua-qa-service-account.json`
- **Scoped to:** Google Sheets API + Google Drive API only
- **Access:** Only files shared with the service account email
- **Test Sheet:** https://docs.google.com/spreadsheets/d/12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k
- **Sheet ID:** `12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k`

### Platforms

| Platform | Flag | Description |
|----------|------|-------------|
| Browser | `--platform browser` (default) | Chrome on macOS |
| iOS | `--platform ios` | iPhone Mirroring on macOS — not yet configured |
| Android | `--platform android` | scrcpy on macOS — not yet configured |

The Google Sheet has platform-specific action columns: `Action_General`, `Action_Browser`, `Action_iOS`, `Action_Android`. The loader uses the platform-specific action if present, otherwise falls back to `Action_General`. Tests with no resolved action for the selected platform are skipped.

### Test Target (Browser)

- **URL:** https://demo.useideem.com/umfa.html?debug=true
- The `?debug=true` flag enables a **DEBUG OUTPUT** section near the top of the page
- The DEBUG OUTPUT section has a dark header bar and displays JSON log lines below it
- CUA must ONLY read the DEBUG OUTPUT section to determine test outcomes — never interpret the visual UI
- The DEBUG OUTPUT shows API responses, token values, error messages, and enrollment states

### Known Issues

**pyautogui.hotkey("command", "v") is unreliable on macOS**
- The `type` action in `computer_use_demo/tools/computer.py` uses AppleScript paste instead:
  ```python
  subprocess.run(["osascript", "-e",
      'tell application "System Events" to keystroke "v" using command down'],
      check=True, timeout=5)
  ```
- **Do NOT revert this to use pyautogui.hotkey** — the AppleScript mechanism is the fix

**Input below the fold on debug=true page**
- On `umfa.html?debug=true`, the debug console pushes the phone mockup down
- CUA must scroll down before interacting with the input

### Diagnostics

Located in `diagnostics/` directory:
- `pyautogui_diagnostic.py` — Selenium + pyautogui test
- `test_webapp_input.py` — Playwright DOM-level test
- `cua_flow_test.py` — CUA timing pattern test
- `simple_input.html` — minimal test page for CUA

## Rules

- **Write results to the Google Sheet after EVERY step** — never batch or defer. The user monitors the Results tab in real time.
- Never run CUA tests without user confirmation (they take over mouse/keyboard)
- Use absolute paths for all script execution
- Do not modify `computer_use_demo/` files unless explicitly asked
