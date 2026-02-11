# Setup New Machine

## Prerequisites

- macOS (Apple Silicon or Intel)
- Python 3.13+
- Google Chrome installed
- Git

## 1. Clone the repo

```bash
git clone git@github.com:tobiasrush/CUA-QA.git
cd CUA-QA
```

## 2. Create Python virtual environment

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## 3. Configure credentials

### Anthropic API key

```bash
cp .env.example .env
```

Edit `.env` and set your `ANTHROPIC_API_KEY`.

### Google Sheets service account

Copy the service account JSON to the project root:

```bash
cp ~/Library/CloudStorage/GoogleDrive-tobyrush@gmail.com/My\ Drive/claude-config/credentials/cua-qa-service-account.json ./service-account.json
```

This file is gitignored. The service account needs access to the test Google Sheet (shared with `cua-qa-sheets@cua-qa.iam.gserviceaccount.com`).

## 4. Grant macOS permissions

Go to **System Settings > Privacy & Security** and grant your terminal app (iTerm2, Terminal, etc.):

- **Accessibility** (required for pyautogui keyboard/mouse control)
- **Screen Recording** (required for pyautogui screenshots)

You may need to restart your terminal after granting permissions.

## 5. Prevent screen lock and sleep

CUA takes over mouse/keyboard, so the screen must stay awake and unlocked.

```bash
# Disable display and system sleep
sudo pmset -a displaysleep 0 sleep 0

# Disable screen saver
defaults -currentHost write com.apple.screensaver idleTime -int 0
```

Also in **System Settings > Lock Screen**, set "Require password after screen saver begins or display is turned off" to **Never**.

## 6. Verify setup

Run a dry run to confirm the Google Sheet connection works:

```bash
venv/bin/python test_runner.py --sheet 12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k --platform browser --dry-run
```

You should see a list of tests loaded from the sheet.

## 7. Run tests

Open Chrome and navigate to the test page, then run:

```bash
caffeinate -dims venv/bin/python test_runner.py \
  --sheet 12zDcMDPiGV-0UhbIFT50K7DgOwIRebg9u8eCV9umg4k \
  --platform browser \
  --sequential \
  --report \
  --url "https://demo.useideem.com/umfa.html?debug=true" \
  --test Setup \
  --test CheckAllEnrollment_NoZSM_NoPK
```

Use `caffeinate -dims` to prevent sleep during the run. Results are written back to the Google Sheet Results tab.

### Common flags

| Flag | Description |
|------|-------------|
| `--sheet SHEET_ID` | Load tests from Google Sheet |
| `--platform browser\|ios\|android` | Target platform (default: browser) |
| `--test TEST_NAME` | Run specific test(s) by name (repeatable) |
| `--group GROUP_NAME` | Run all tests in a group |
| `--sequential` | Share CUA context across tests |
| `--report` | Generate HTML report in `reports/` |
| `--url URL` | Navigate to URL before tests (browser only) |
| `--dry-run` | List tests without running CUA |
