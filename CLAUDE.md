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

## macOS Permissions Required
- **Accessibility:** iTerm2 (for pyautogui keyboard/mouse control)
- **Screen Recording:** iTerm2 (for pyautogui screenshots)

## Rules
- Never run CUA tests without user confirmation (they take over mouse/keyboard)
- Use absolute paths for all script execution
- Do not modify `computer_use_demo/` files unless explicitly asked
