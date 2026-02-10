# CUA QA - Computer Use Agent Testing Tool

## Critical: API Access Requirements

### Claude Max vs Anthropic API

| Product | What It Is | Computer Use Access |
|---------|------------|---------------------|
| **Claude Max** ($100-200/mo) | Web/app chat + Claude Code | NO - does not include API |
| **Anthropic API** (pay-as-you-go) | Developer API access | YES - required for computer use |

**You need an Anthropic API key** from [console.anthropic.com](https://console.anthropic.com/settings/keys).

API costs are usage-based (~$15/million input tokens for Opus). For testing, expect minimal costs ($1-5 for initial development).

---

## Recommended Starting Point: macOS Demo

### [PallavAg/claude-computer-use-macos](https://github.com/PallavAg/claude-computer-use-macos)

This is the **best starting point** because:
- Runs **natively on macOS** (no Docker required)
- Already working code with pyautogui
- Simple Python script - easy to understand and modify
- MIT licensed, 278 stars, actively maintained

**Setup:**
```bash
git clone https://github.com/PallavAg/claude-computer-use-macos.git
cd claude-computer-use-macos
python3.12 -m venv venv
source venv/bin/activate
pip3.12 install -r requirements.txt
export ANTHROPIC_API_KEY="your_key"
python3.12 main.py 'Open Safari and go to google.com'
```

**Requires:** macOS Accessibility permissions for terminal/Python.

---

## Research Summary

### What is CUA (Computer Use Agent)?

CUA is Anthropic's capability that allows Claude to **see and control** a computer's GUI via:
1. **Perceive**: Capture screenshot of current screen state
2. **Reason**: Analyze the image, identify UI elements, decide next action
3. **Act**: Execute mouse/keyboard actions (click, type, scroll, drag)
4. **Iterate**: Repeat until task complete

### Claude Opus 4.6 (Released Feb 5, 2026) - Key Features

- **Model**: `claude-opus-4-6` with tool version `computer_20251124`
- **Beta header**: `computer-use-2025-11-24`
- **New zoom action**: `enable_zoom: true` for full-resolution view of screen regions
- **Best-in-class OSWorld benchmark scores** for computer use
- **Supported actions**: `screenshot`, `mouse_move`, `left_click`, `right_click`, `double_click`, `type`, `key`, `scroll`, `left_click_drag`, `wait`, `zoom`

### Key GitHub Repositories

| Repository | Description |
|------------|-------------|
| [PallavAg/claude-computer-use-macos](https://github.com/PallavAg/claude-computer-use-macos) | **macOS native** - no Docker, uses pyautogui |
| [anthropics/anthropic-quickstarts](https://github.com/anthropics/anthropic-quickstarts) | Official reference (Docker-based) |
| [ashbuilds/computer-use](https://github.com/ashbuilds/computer-use) | Node.js/TypeScript port |
| [firstloophq/claude-code-test-runner](https://github.com/firstloophq/claude-code-test-runner) | E2E natural language test runner |

### CUA for QA Testing - Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CUA QA Framework                          │
├─────────────────────────────────────────────────────────────────┤
│  Test Spreadsheet (Google Sheets / Excel)                        │
│  ┌──────────┬──────────────────────┬─────────────────────────┐  │
│  │ Step #   │ Action               │ Expected Result          │  │
│  ├──────────┼──────────────────────┼─────────────────────────┤  │
│  │ 1        │ Click Login button   │ Login form appears       │  │
│  │ 2        │ Enter username       │ Username field populated │  │
│  └──────────┴──────────────────────┴─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CUA Agent (Opus 4.6)                         │
│  - Reads test steps from spreadsheet                             │
│  - Executes actions via computer use API                         │
│  - Verifies expected results visually                            │
│  - Generates test report with screenshots                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────┬────────────────┬────────────────┐
│    Browser     │  iOS (Mirror)  │ Android (scrcpy)│
│   (Native)     │  iPhone Mirror │   or similar    │
└────────────────┴────────────────┴────────────────┘
```

### Platform-Specific Approaches

**Browser Testing**
- Direct screen capture + mouse/keyboard control
- Can also use Playwright MCP for DOM-level automation when appropriate

**iOS Testing (iPhone Mirroring)**
- Apple's native iPhone Mirroring (macOS Sequoia+)
- CUA sees mirrored iPhone screen on Mac desktop
- Controls via Mac's mouse/keyboard → translates to iPhone touch

**Android Testing**
- Options: scrcpy, Vysor, Android Studio Emulator
- Mirror Android screen to Mac window
- CUA controls the mirrored window

---

## User Decisions

| Decision | Choice |
|----------|--------|
| Test script source | **Google Sheets** |
| Start with platform | **Browser** (then iOS, then Android) |
| Android mirroring | **scrcpy** |

---

## Implementation Plan

### Phase 0: Validate CUA Works (First!) ✅ COMPLETE

**Goal:** Get the macOS demo running with a simple test before building anything.

**Steps:**
1. ✅ Get Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
2. ✅ Clone `PallavAg/claude-computer-use-macos` into CUA-QA folder
3. ✅ Set up Python environment and install deps
4. ⏳ Grant macOS Accessibility permissions
5. ⏳ Run validation test
6. ⏳ Confirm: Claude takes screenshots, clicks, types, completes task

**Success criteria:** Claude successfully navigates Safari and performs a search.

---

### Phase 1: Build Test Script Runner ✅ COMPLETE

**Goal:** Create our own test scripts (JSON/YAML) and runner.

**Project Structure:**
```
CUA-QA/
├── main.py                 # Entry point (from macOS demo)
├── test_runner.py          # Our test script executor
├── tests/
│   └── example_test.yaml   # Sample test script
├── reports/
│   └── (generated HTML reports)
└── requirements.txt
```

**Sample Test Script (tests/example_test.yaml):**
```yaml
name: Google Search Test
platform: browser
steps:
  - action: "Open Safari"
    expected: "Safari window appears"
  - action: "Navigate to google.com"
    expected: "Google homepage loads"
  - action: "Type 'Claude AI' in search box and press Enter"
    expected: "Search results appear"
  - action: "Click the first result"
    expected: "Website loads"
```

**Test Runner Logic:**
1. Load test script (YAML/JSON)
2. For each step:
   - Send action to Claude with current screenshot
   - Execute Claude's mouse/keyboard commands
   - Ask Claude to verify expected result
   - Log pass/fail with screenshot
3. Generate HTML report

---

## Verification Plan

### Phase 0 Verification
- [x] Anthropic API key obtained and working
- [x] macOS demo cloned and dependencies installed
- [ ] Accessibility permissions granted
- [ ] Simple test runs successfully (Safari + Google search)

### Phase 1 Verification
- [x] Test script (YAML) loads correctly
- [x] Runner executes each step
- [x] Screenshots captured at each step
- [x] HTML report generated with pass/fail

---

## Dependencies (Python)

```
anthropic[bedrock,vertex]>=0.40.0
pillow>=10.0.0
PyAutoGUI>=0.9.54
PyYAML>=6.0
Jinja2>=3.1.0
python-dotenv>=1.0.0
```

---

## macOS Permissions Required

1. **System Settings > Privacy & Security > Accessibility**
   - Add iTerm2 (or your terminal app)

2. **System Settings > Privacy & Security > Screen Recording**
   - Add iTerm2 (or your terminal app)

---

## Future Phases (Out of Scope)

- Phase 2: Google Sheets integration
- Phase 3: iOS testing (iPhone Mirroring)
- Phase 4: Android testing (scrcpy)

---

## Sources

- [PallavAg/claude-computer-use-macos](https://github.com/PallavAg/claude-computer-use-macos) - macOS native demo
- [Anthropic Computer Use Tool Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [Claude Opus 4.6 Announcement](https://www.anthropic.com/claude/opus)
- [Anthropic API Console](https://console.anthropic.com/settings/keys)
- [Claude Max vs API FAQ](https://support.claude.com/en/articles/9876003)
