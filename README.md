# CUA-QA: Computer Use Agent QA Testing Tool

A QA testing framework that uses Claude's Computer Use API to automate UI testing. Built on top of the [claude-computer-use-macos](https://github.com/PallavAg/claude-computer-use-macos) demo.

> [!WARNING]
> Use this tool with caution. It allows Claude to control your computer. By running this, you assume all responsibility and liability.

## Requirements

- **Anthropic API key** - Get one from [console.anthropic.com](https://console.anthropic.com/settings/keys)
- macOS with Accessibility permissions
- Python 3.10+

## Quick Start

### 1. Setup

```bash
cd /Users/tobyrush/Documents/GitHub/CUA-QA
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set API Key

```bash
export ANTHROPIC_API_KEY="your_api_key_here"
```

### 3. Grant Accessibility Permissions

Go to **System Settings** > **Privacy & Security** > **Accessibility** and add your terminal app.

### 4. Run a Test

```bash
# Simple validation test
python test_runner.py tests/simple_test.yaml --report

# Full browser test
python test_runner.py tests/example_test.yaml --report
```

## Test Script Format

Tests are defined in YAML format:

```yaml
name: My Test
platform: browser

steps:
  - action: "Open Safari browser"
    expected: "Safari window appears"

  - action: "Navigate to google.com"
    expected: "Google homepage loads"
```

## Project Structure

```
CUA-QA/
├── main.py                 # Original demo entry point
├── test_runner.py          # QA test runner
├── tests/                  # Test scripts
│   ├── simple_test.yaml
│   ├── example_test.yaml
│   └── validation_test.yaml
├── reports/                # Generated HTML reports
├── screenshots/            # Captured screenshots
└── computer_use_demo/      # CUA implementation
```

## Usage

### Run Tests

```bash
# Run a test
python test_runner.py tests/example_test.yaml

# Run with HTML report generation
python test_runner.py tests/example_test.yaml --report
```

### Original Demo Mode

You can also use the original demo mode for freeform commands:

```bash
python main.py 'Open Safari and search for Anthropic'
```

## Creating Test Scripts

Create a new YAML file in `tests/`:

```yaml
name: Login Test
platform: browser

steps:
  - action: "Open Safari and navigate to myapp.com/login"
    expected: "Login page appears with username and password fields"

  - action: "Enter 'testuser' in the username field"
    expected: "Username field shows 'testuser'"

  - action: "Enter 'password123' in the password field"
    expected: "Password field is filled (dots visible)"

  - action: "Click the Login button"
    expected: "User is logged in and dashboard appears"
```

## Platform Support

Currently supported:
- **Browser** - Safari, Chrome, Firefox (any browser on macOS)

Future phases:
- iOS (via iPhone Mirroring)
- Android (via scrcpy)

## API Costs

Claude API is usage-based (~$15/million input tokens for Opus, ~$3 for Sonnet). Typical test runs cost $0.10-0.50 depending on complexity.

## Troubleshooting

### "Accessibility permission denied"

Add your terminal app to System Settings > Privacy & Security > Accessibility.

### "ANTHROPIC_API_KEY not set"

Make sure you've exported the key:
```bash
export ANTHROPIC_API_KEY="your_key"
```

### Screenshots not capturing

Ensure Screen Recording permission is granted for your terminal app.

## Credits

- Based on [PallavAg/claude-computer-use-macos](https://github.com/PallavAg/claude-computer-use-macos)
- Uses [Anthropic Computer Use API](https://docs.anthropic.com/en/docs/build-with-claude/computer-use)
