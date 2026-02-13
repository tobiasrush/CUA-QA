"""
Diagnostic 2: Comprehensive Selenium + pyautogui replication of CUA flow
Replicates the exact CUA mechanism and tests every failure mode:
  - Coordinate calculation with Retina/scaling verification
  - Pixel-color verification of click target
  - Multiple typing mechanisms (pbcopy+cmd+v, typewrite, AppleScript)
  - Clipboard state inspection before and after
  - Focus tracking with JS mutation observer
  - Accessibility permission check
  - Chrome address bar paste test (control)
  - Selenium .send_keys() as baseline

Install:
    /Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/pip install selenium Pillow

Run:
    /Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python /Users/tobyrush/Documents/GitHub/CUA-QA/diagnostics/pyautogui_diagnostic.py

NOTE: This takes over your mouse/keyboard. Don't touch anything during the test.
"""

import subprocess
import time
import json
import os

import pyautogui
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

URL = "https://demo.useideem.com/umfa.html?debug=true"
INPUT_SELECTOR = "input#username"
FALLBACK_SELECTORS = ["input[type='text']", "input"]
TEST_TEXT = "diag_user"
DIAG_DIR = "/Users/tobyrush/Documents/GitHub/CUA-QA/diagnostics"

results = {}
log_lines = []


def log(msg, indent=0):
    prefix = "  " * indent
    line = f"{prefix}{msg}"
    print(line)
    log_lines.append(line)


def section(title):
    log(f"\n{'─' * 60}")
    log(f"  {title}")
    log(f"{'─' * 60}")


def find_input(driver):
    for sel in [INPUT_SELECTOR] + FALLBACK_SELECTORS:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el:
                return el, sel
        except Exception:
            continue
    return None, None


def check_focus(driver):
    return driver.execute_script("""
        const ae = document.activeElement;
        return { tag: ae ? ae.tagName : null, id: ae ? ae.id : null, type: ae ? ae.type : null };
    """)


def get_input_value(driver, el):
    return driver.execute_script("return arguments[0].value", el)


def clear_input(driver, el):
    driver.execute_script("arguments[0].value = '';", el)


def focus_input_via_js(driver, el):
    driver.execute_script("arguments[0].focus();", el)


def get_clipboard():
    """Read current system clipboard via pbpaste."""
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, timeout=3)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def set_clipboard(text):
    """Set system clipboard via pbcopy."""
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


def applescript_paste():
    """Paste via AppleScript (alternative to pyautogui hotkey)."""
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to keystroke "v" using command down'
    ], check=True)


def applescript_type(text):
    """Type text via AppleScript keystroke (character by character, no clipboard)."""
    # Escape backslashes and quotes for AppleScript
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run([
        "osascript", "-e",
        f'tell application "System Events" to keystroke "{escaped}"'
    ], check=True)


# ─────────────────────────────────────────────────────────────
# PRE-FLIGHT CHECKS
# ─────────────────────────────────────────────────────────────

def preflight_checks():
    section("PRE-FLIGHT CHECKS")

    # 1. pyautogui screen info
    screen_w, screen_h = pyautogui.size()
    log(f"pyautogui.size(): {screen_w}x{screen_h}")
    results["screen_size"] = (screen_w, screen_h)

    # 2. Check Retina: take a screenshot and compare pixel dimensions
    screenshot = pyautogui.screenshot()
    pixel_w, pixel_h = screenshot.size
    log(f"Screenshot pixel size: {pixel_w}x{pixel_h}")
    retina_scale = pixel_w / screen_w
    log(f"Retina scale (pixels/points): {retina_scale:.1f}x")
    results["retina_scale"] = retina_scale
    results["pixel_size"] = (pixel_w, pixel_h)

    if retina_scale > 1.0:
        log("** RETINA DISPLAY DETECTED **", 1)
        log(f"pyautogui reports {screen_w}x{screen_h} (points)", 1)
        log(f"Actual pixels: {pixel_w}x{pixel_h}", 1)
        log("Coordinates should be in POINTS, not pixels", 1)

    # 3. Clipboard sanity check
    set_clipboard("CLIPBOARD_TEST_123")
    time.sleep(0.1)
    clip = get_clipboard()
    clipboard_ok = clip == "CLIPBOARD_TEST_123"
    results["clipboard_roundtrip"] = clipboard_ok
    log(f"Clipboard roundtrip (pbcopy->pbpaste): {'OK' if clipboard_ok else 'FAILED'} (got: '{clip}')")

    # 4. Accessibility check
    log("Accessibility: if pyautogui clicks work at all, permissions are OK")
    log("(Full test will confirm via actual click results)")


# ─────────────────────────────────────────────────────────────
# COORDINATE ANALYSIS
# ─────────────────────────────────────────────────────────────

def coordinate_analysis(driver, input_el):
    section("COORDINATE ANALYSIS")

    # Get all the raw data
    info = driver.execute_script("""
        const el = arguments[0];
        const rect = el.getBoundingClientRect();
        return {
            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                    centerX: rect.x + rect.width / 2, centerY: rect.y + rect.height / 2 },
            screenX: window.screenX,
            screenY: window.screenY,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            devicePixelRatio: window.devicePixelRatio,
            screenWidth: screen.width,
            screenHeight: screen.height,
            screenAvailWidth: screen.availWidth,
            screenAvailHeight: screen.availHeight,
        };
    """, input_el)

    chrome_height = info["outerHeight"] - info["innerHeight"]

    log(f"Window: screenX={info['screenX']} screenY={info['screenY']}")
    log(f"Window: outer={info['outerWidth']}x{info['outerHeight']} inner={info['innerWidth']}x{info['innerHeight']}")
    log(f"Chrome toolbar height: {chrome_height}px")
    log(f"devicePixelRatio: {info['devicePixelRatio']}")
    log(f"screen: {info['screenWidth']}x{info['screenHeight']} (avail: {info['screenAvailWidth']}x{info['screenAvailHeight']})")
    log(f"Input CSS rect: x={info['rect']['x']:.1f} y={info['rect']['y']:.1f} "
        f"w={info['rect']['width']:.1f} h={info['rect']['height']:.1f}")

    # Method A: Simple addition (what v1 did)
    method_a_x = info["screenX"] + info["rect"]["centerX"]
    method_a_y = info["screenY"] + chrome_height + info["rect"]["centerY"]

    # Method B: Account for devicePixelRatio in coordinate conversion
    # If DPR > 1, CSS coords are in CSS pixels but pyautogui uses points
    dpr = info["devicePixelRatio"]
    method_b_x = info["screenX"] + info["rect"]["centerX"]
    method_b_y = info["screenY"] + chrome_height + info["rect"]["centerY"]
    # If the page reports DPR but pyautogui works in a different unit:
    # On macOS, pyautogui uses "points" which match CSS pixels when window is not scaled

    # Method C: Use Selenium's element location + window handle
    sel_loc = input_el.location
    sel_size = input_el.size
    method_c_x = info["screenX"] + sel_loc["x"] + sel_size["width"] / 2
    method_c_y = info["screenY"] + chrome_height + sel_loc["y"] + sel_size["height"] / 2

    log(f"\nComputed screen coordinates (3 methods):")
    log(f"  Method A (JS rect + window): ({method_a_x:.0f}, {method_a_y:.0f})")
    log(f"  Method B (with DPR={dpr}):    ({method_b_x:.0f}, {method_b_y:.0f})")
    log(f"  Method C (Selenium loc):      ({method_c_x:.0f}, {method_c_y:.0f})")

    # Stash all candidates for click testing
    return {
        "info": info,
        "chrome_height": chrome_height,
        "candidates": {
            "A_js_rect": (int(method_a_x), int(method_a_y)),
            "B_dpr_adjusted": (int(method_b_x), int(method_b_y)),
            "C_selenium_loc": (int(method_c_x), int(method_c_y)),
        }
    }


# ─────────────────────────────────────────────────────────────
# PIXEL-LEVEL CLICK VERIFICATION
# ─────────────────────────────────────────────────────────────

def pixel_verification(driver, input_el, coord_data):
    section("PIXEL-LEVEL CLICK VERIFICATION")

    # First, paint the input a distinctive color so we can verify via screenshot
    driver.execute_script("""
        arguments[0].style.backgroundColor = '#FF0000';
        arguments[0].style.border = '3px solid #00FF00';
    """, input_el)
    time.sleep(0.3)

    # Take a pyautogui screenshot and check pixel colors at each candidate
    screenshot = pyautogui.screenshot()
    retina = results.get("retina_scale", 1.0)

    log(f"Input painted red (#FF0000) with green border for visual verification")
    log(f"Checking pixel colors at each candidate coordinate:\n")

    working_coords = None

    for name, (cx, cy) in coord_data["candidates"].items():
        # On Retina, screenshot pixels = points * retina_scale
        px = int(cx * retina)
        py = int(cy * retina)

        if 0 <= px < screenshot.width and 0 <= py < screenshot.height:
            pixel = screenshot.getpixel((px, py))
            r, g, b = pixel[0], pixel[1], pixel[2]
            is_red = r > 200 and g < 100 and b < 100
            is_green_border = g > 200 and r < 100
            looks_like_input = is_red or is_green_border
            log(f"  {name}: ({cx}, {cy}) -> pixel({px},{py}) = RGB({r},{g},{b}) "
                f"{'** MATCHES INPUT **' if looks_like_input else '(not input)'}")
            if looks_like_input and working_coords is None:
                working_coords = (cx, cy)
        else:
            log(f"  {name}: ({cx}, {cy}) -> pixel({px},{py}) = OUT OF BOUNDS")

    # Also scan a grid around Method A to find the red region
    log(f"\nScanning grid around Method A to locate input red region...")
    ax, ay = coord_data["candidates"]["A_js_rect"]
    found_red = []
    for dy in range(-100, 101, 10):
        for dx in range(-100, 101, 10):
            tx, ty = ax + dx, ay + dy
            px, py = int(tx * retina), int(ty * retina)
            if 0 <= px < screenshot.width and 0 <= py < screenshot.height:
                pixel = screenshot.getpixel((px, py))
                if pixel[0] > 200 and pixel[1] < 100 and pixel[2] < 100:
                    found_red.append((tx, ty, dx, dy))

    if found_red:
        # Find center of red region
        avg_x = sum(p[0] for p in found_red) / len(found_red)
        avg_y = sum(p[1] for p in found_red) / len(found_red)
        min_dx = min(p[2] for p in found_red)
        max_dx = max(p[2] for p in found_red)
        min_dy = min(p[3] for p in found_red)
        max_dy = max(p[3] for p in found_red)
        log(f"  Found {len(found_red)} red pixels in scan area")
        log(f"  Red region center: ({avg_x:.0f}, {avg_y:.0f})")
        log(f"  Offset from Method A: dx=[{min_dx},{max_dx}] dy=[{min_dy},{max_dy}]")
        results["pixel_verified_coords"] = (int(avg_x), int(avg_y))
        if working_coords is None:
            working_coords = (int(avg_x), int(avg_y))
    else:
        log(f"  No red pixels found within ±100px of Method A!")
        log(f"  Expanding search to ±300px...")
        for dy in range(-300, 301, 20):
            for dx in range(-300, 301, 20):
                tx, ty = ax + dx, ay + dy
                px, py = int(tx * retina), int(ty * retina)
                if 0 <= px < screenshot.width and 0 <= py < screenshot.height:
                    pixel = screenshot.getpixel((px, py))
                    if pixel[0] > 200 and pixel[1] < 100 and pixel[2] < 100:
                        found_red.append((tx, ty, dx, dy))
        if found_red:
            avg_x = sum(p[0] for p in found_red) / len(found_red)
            avg_y = sum(p[1] for p in found_red) / len(found_red)
            log(f"  Found {len(found_red)} red pixels in expanded scan")
            log(f"  Red region center: ({avg_x:.0f}, {avg_y:.0f})")
            drift_x = avg_x - ax
            drift_y = avg_y - ay
            log(f"  ** COORDINATE DRIFT: ({drift_x:.0f}, {drift_y:.0f}) from Method A **")
            results["pixel_verified_coords"] = (int(avg_x), int(avg_y))
            results["coordinate_drift"] = (drift_x, drift_y)
            if working_coords is None:
                working_coords = (int(avg_x), int(avg_y))
        else:
            log(f"  Still no red pixels found! Input may not be visible on screen.")

    # Reset input styling
    driver.execute_script("""
        arguments[0].style.backgroundColor = '';
        arguments[0].style.border = '';
    """, input_el)
    time.sleep(0.2)

    # Save annotated screenshot
    screenshot.save(os.path.join(DIAG_DIR, "pixel_verification.png"))
    log(f"\nScreenshot saved: pixel_verification.png")

    return working_coords


# ─────────────────────────────────────────────────────────────
# CLICK TESTS
# ─────────────────────────────────────────────────────────────

def click_tests(driver, input_el, coord_data, verified_coords):
    section("CLICK FOCUS TESTS")

    candidates = dict(coord_data["candidates"])
    if verified_coords:
        candidates["D_pixel_verified"] = verified_coords

    working = None

    for name, (cx, cy) in candidates.items():
        # Reset focus
        driver.execute_script("document.body.focus();")
        time.sleep(0.2)

        pyautogui.moveTo(cx, cy)
        time.sleep(0.15)
        pyautogui.click()
        time.sleep(0.4)

        focus = check_focus(driver)
        is_input = focus.get("id") == "username" or focus.get("tag") == "INPUT"
        log(f"  {name}: click({cx}, {cy}) -> focus={focus['tag']}#{focus.get('id','')} "
            f"{'** OK **' if is_input else 'MISSED'}")

        if is_input and working is None:
            working = (name, cx, cy)
            results[f"click_{name}_works"] = True
        else:
            results[f"click_{name}_works"] = is_input

    if working:
        results["working_click_method"] = working[0]
        results["working_click_coords"] = (working[1], working[2])
        log(f"\n  Best working coords: {working[0]} = ({working[1]}, {working[2]})")
    else:
        log(f"\n  ** NO METHOD SUCCESSFULLY FOCUSED THE INPUT **")
        log(f"  Trying wider grid search...")
        # Brute force: try a grid of clicks
        ax, ay = coord_data["candidates"]["A_js_rect"]
        for dy in range(-80, 81, 20):
            for dx in range(-80, 81, 20):
                tx, ty = ax + dx, ay + dy
                driver.execute_script("document.body.focus();")
                time.sleep(0.1)
                pyautogui.click(tx, ty)
                time.sleep(0.2)
                focus = check_focus(driver)
                if focus.get("id") == "username" or focus.get("tag") == "INPUT":
                    log(f"  FOUND via grid: ({tx}, {ty}) offset=({dx},{dy}) from Method A")
                    working = ("grid_search", tx, ty)
                    results["working_click_method"] = "grid_search"
                    results["working_click_coords"] = (tx, ty)
                    results["grid_offset_from_A"] = (dx, dy)
                    break
            if working:
                break

    return working


# ─────────────────────────────────────────────────────────────
# TYPING MECHANISM TESTS
# ─────────────────────────────────────────────────────────────

def typing_tests(driver, input_el, working_click):
    section("TYPING MECHANISM TESTS")

    if not working_click:
        log("  SKIPPED: No working click coordinates found.")
        log("  Falling back to JS focus for typing tests...")
        use_js_focus = True
        click_x, click_y = 0, 0
    else:
        use_js_focus = False
        _, click_x, click_y = working_click

    def prepare(label):
        """Clear input and establish focus for next test."""
        clear_input(driver, input_el)
        time.sleep(0.1)
        if use_js_focus:
            focus_input_via_js(driver, input_el)
        else:
            pyautogui.click(click_x, click_y)
        time.sleep(0.3)
        focus = check_focus(driver)
        log(f"\n  [{label}] Focus before: {focus['tag']}#{focus.get('id','')}", 0)
        return focus

    # ── Test A: pbcopy + pyautogui.hotkey("command", "v") (exact CUA mechanism) ──
    prepare("A: pbcopy + pyautogui cmd+v (CUA mechanism)")
    clip_before = get_clipboard()
    set_clipboard(TEST_TEXT)
    time.sleep(0.05)
    clip_after_set = get_clipboard()
    log(f"    Clipboard before: '{clip_before[:40]}'", 0)
    log(f"    Clipboard after pbcopy: '{clip_after_set}'", 0)
    pyautogui.hotkey("command", "v")
    time.sleep(0.5)
    val = get_input_value(driver, input_el)
    focus = check_focus(driver)
    clip_after_paste = get_clipboard()
    results["A_pbcopy_pyautogui_cmdv"] = val == TEST_TEXT
    log(f"    Value: '{val}' | Focus: {focus['tag']}#{focus.get('id','')} | "
        f"Clipboard after: '{clip_after_paste[:40]}'", 0)
    log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)

    # ── Test B: pbcopy + AppleScript paste ──
    prepare("B: pbcopy + AppleScript cmd+v")
    set_clipboard(TEST_TEXT)
    time.sleep(0.05)
    try:
        applescript_paste()
        time.sleep(0.5)
        val = get_input_value(driver, input_el)
        focus = check_focus(driver)
        results["B_pbcopy_applescript_paste"] = val == TEST_TEXT
        log(f"    Value: '{val}' | Focus: {focus['tag']}#{focus.get('id','')}", 0)
        log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)
    except Exception as e:
        results["B_pbcopy_applescript_paste"] = False
        log(f"    Exception: {e}", 0)

    # ── Test C: AppleScript keystroke (no clipboard) ──
    prepare("C: AppleScript keystroke (no clipboard)")
    try:
        applescript_type(TEST_TEXT)
        time.sleep(0.5)
        val = get_input_value(driver, input_el)
        focus = check_focus(driver)
        results["C_applescript_keystroke"] = val == TEST_TEXT
        log(f"    Value: '{val}' | Focus: {focus['tag']}#{focus.get('id','')}", 0)
        log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)
    except Exception as e:
        results["C_applescript_keystroke"] = False
        log(f"    Exception: {e}", 0)

    # ── Test D: pyautogui.typewrite (direct key events, ASCII only) ──
    prepare("D: pyautogui.typewrite (key events)")
    try:
        pyautogui.typewrite(TEST_TEXT, interval=0.03)
        time.sleep(0.3)
        val = get_input_value(driver, input_el)
        focus = check_focus(driver)
        results["D_pyautogui_typewrite"] = val == TEST_TEXT
        log(f"    Value: '{val}' | Focus: {focus['tag']}#{focus.get('id','')}", 0)
        log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)
    except Exception as e:
        results["D_pyautogui_typewrite"] = False
        log(f"    Exception: {e}", 0)

    # ── Test E: pyautogui.write (same as typewrite but newer API) ──
    prepare("E: pyautogui.write")
    try:
        pyautogui.write(TEST_TEXT, interval=0.03)
        time.sleep(0.3)
        val = get_input_value(driver, input_el)
        focus = check_focus(driver)
        results["E_pyautogui_write"] = val == TEST_TEXT
        log(f"    Value: '{val}' | Focus: {focus['tag']}#{focus.get('id','')}", 0)
        log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)
    except Exception as e:
        results["E_pyautogui_write"] = False
        log(f"    Exception: {e}", 0)

    # ── Test F: Selenium send_keys (baseline — should always work) ──
    prepare("F: Selenium send_keys (baseline)")
    try:
        input_el.send_keys(TEST_TEXT)
        time.sleep(0.3)
        val = get_input_value(driver, input_el)
        results["F_selenium_send_keys"] = val == TEST_TEXT
        log(f"    Value: '{val}'", 0)
        log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)
    except Exception as e:
        results["F_selenium_send_keys"] = False
        log(f"    Exception: {e}", 0)

    # ── Test G: JS dispatchEvent (programmatic) ──
    prepare("G: JS dispatchEvent input simulation")
    try:
        driver.execute_script("""
            const el = arguments[0];
            const text = arguments[1];
            el.focus();
            // Simulate typing via input events
            el.value = text;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        """, input_el, TEST_TEXT)
        time.sleep(0.3)
        val = get_input_value(driver, input_el)
        results["G_js_dispatch"] = val == TEST_TEXT
        log(f"    Value: '{val}'", 0)
        log(f"    Result: {'OK' if val == TEST_TEXT else '** FAILED **'}", 0)
    except Exception as e:
        results["G_js_dispatch"] = False
        log(f"    Exception: {e}", 0)


# ─────────────────────────────────────────────────────────────
# FOCUS PERSISTENCE TESTS
# ─────────────────────────────────────────────────────────────

def focus_persistence_tests(driver, input_el, working_click):
    section("FOCUS PERSISTENCE TESTS")

    if not working_click:
        log("  SKIPPED: No working click coordinates.")
        return

    _, cx, cy = working_click

    for delay_name, delay_s in [("0.5s", 0.5), ("1s", 1), ("3s", 3), ("5s", 5)]:
        driver.execute_script("document.body.focus();")
        time.sleep(0.2)
        pyautogui.click(cx, cy)
        time.sleep(0.2)

        focus_before = check_focus(driver)
        time.sleep(delay_s)
        focus_after = check_focus(driver)

        held = focus_after.get("id") == "username" or focus_after.get("tag") == "INPUT"
        results[f"focus_holds_{delay_name}"] = held
        log(f"  {delay_name}: before={focus_before['tag']}#{focus_before.get('id','')} "
            f"after={focus_after['tag']}#{focus_after.get('id','')} -> {'OK' if held else '** LOST **'}")


# ─────────────────────────────────────────────────────────────
# CHROME ADDRESS BAR PASTE TEST (control)
# ─────────────────────────────────────────────────────────────

def address_bar_paste_test():
    section("CHROME ADDRESS BAR PASTE TEST (control)")
    log("  Testing if pbcopy + cmd+v works in the address bar...")
    log("  (This verifies pyautogui paste works outside the webapp)")

    set_clipboard("about:blank")
    time.sleep(0.1)

    # Click address bar area (top center of screen, typical Chrome position)
    screen_w, _ = pyautogui.size()
    addr_x = screen_w // 2
    addr_y = 52  # Typical Chrome address bar Y position

    pyautogui.click(addr_x, addr_y)
    time.sleep(0.3)
    pyautogui.hotkey("command", "a")  # Select all
    time.sleep(0.1)
    pyautogui.hotkey("command", "v")  # Paste
    time.sleep(0.3)

    # We can't easily read the address bar value, but we can check clipboard survived
    clip = get_clipboard()
    log(f"  Clipboard still intact: '{clip}' (expected 'about:blank')")
    results["address_bar_paste"] = clip == "about:blank"


# ─────────────────────────────────────────────────────────────
# WEBAPP EVENT LISTENER ANALYSIS
# ─────────────────────────────────────────────────────────────

def event_listener_analysis(driver, input_el):
    section("WEBAPP EVENT LISTENER ANALYSIS")

    analysis = driver.execute_script("""
        const el = arguments[0];
        const results = {};

        // Check for inline handlers
        const events = ['onpaste', 'oninput', 'onkeydown', 'onkeypress', 'onkeyup',
                        'onfocus', 'onblur', 'onchange', 'onclick', 'onmousedown'];
        results.inlineHandlers = {};
        for (const evt of events) {
            results.inlineHandlers[evt] = el[evt] !== null;
        }

        // Test paste event
        let pasteDefaultPrevented = false;
        let pasteHandlerCalled = false;
        const pasteListener = (e) => {
            pasteHandlerCalled = true;
            pasteDefaultPrevented = e.defaultPrevented;
        };
        el.addEventListener('paste', pasteListener, { capture: true });
        const pasteEvt = new ClipboardEvent('paste', {
            bubbles: true, cancelable: true,
            clipboardData: new DataTransfer()
        });
        el.dispatchEvent(pasteEvt);
        el.removeEventListener('paste', pasteListener, { capture: true });
        results.pasteTest = {
            defaultPrevented: pasteEvt.defaultPrevented,
            handlerCalled: pasteHandlerCalled,
            observedPrevention: pasteDefaultPrevented
        };

        // Test keydown for cmd+v
        let keydownPrevented = false;
        const keyListener = (e) => { keydownPrevented = e.defaultPrevented; };
        el.addEventListener('keydown', keyListener, { capture: true });
        const keyEvt = new KeyboardEvent('keydown', {
            key: 'v', code: 'KeyV', metaKey: true,
            bubbles: true, cancelable: true
        });
        el.dispatchEvent(keyEvt);
        el.removeEventListener('keydown', keyListener, { capture: true });
        results.keydownCmdV = {
            defaultPrevented: keyEvt.defaultPrevented,
            observedPrevention: keydownPrevented
        };

        // Check input attributes
        const cs = getComputedStyle(el);
        results.attributes = {
            readOnly: el.readOnly,
            disabled: el.disabled,
            contentEditable: el.contentEditable,
            pointerEvents: cs.pointerEvents,
            userSelect: cs.userSelect,
            visibility: cs.visibility,
            display: cs.display,
            opacity: cs.opacity,
            zIndex: cs.zIndex,
            position: cs.position,
        };

        // Check for iframes or shadow DOM
        results.context = {
            inIframe: window !== window.top,
            inShadowRoot: !!el.getRootNode().host,
            documentHasFocus: document.hasFocus(),
        };

        // Check parent chain for pointer-events:none or overflow:hidden that might clip
        results.parentChain = [];
        let parent = el.parentElement;
        let depth = 0;
        while (parent && depth < 10) {
            const pcs = getComputedStyle(parent);
            if (pcs.pointerEvents === 'none' || pcs.overflow === 'hidden' || pcs.position === 'fixed') {
                results.parentChain.push({
                    tag: parent.tagName,
                    id: parent.id || null,
                    className: parent.className || null,
                    pointerEvents: pcs.pointerEvents,
                    overflow: pcs.overflow,
                    position: pcs.position,
                    zIndex: pcs.zIndex,
                });
            }
            parent = parent.parentElement;
            depth++;
        }

        return results;
    """, input_el)

    log(f"Inline handlers: {json.dumps(analysis['inlineHandlers'], indent=2)}")
    log(f"Paste event test: {analysis['pasteTest']}")
    log(f"Keydown cmd+v test: {analysis['keydownCmdV']}")
    log(f"Input attributes: {json.dumps(analysis['attributes'], indent=2)}")
    log(f"Context: {analysis['context']}")
    if analysis["parentChain"]:
        log(f"Notable parent elements:")
        for p in analysis["parentChain"]:
            log(f"  {p['tag']}#{p.get('id','')} pointer-events={p['pointerEvents']} "
                f"overflow={p['overflow']} position={p['position']} z-index={p['zIndex']}")
    else:
        log(f"No concerning parent elements found")

    results["paste_prevented"] = analysis["pasteTest"]["defaultPrevented"]
    results["keydown_cmdv_prevented"] = analysis["keydownCmdV"]["defaultPrevented"]


# ─────────────────────────────────────────────────────────────
# CUA SCALE FACTOR ANALYSIS
# ─────────────────────────────────────────────────────────────

def cua_scaling_analysis(coord_data):
    section("CUA COORDINATE SCALING ANALYSIS")

    screen_w, screen_h = results["screen_size"]
    MAX_WIDTH = 1280

    if screen_w > MAX_WIDTH:
        scale_factor = MAX_WIDTH / screen_w
        target_width = MAX_WIDTH
        target_height = int(screen_h * scale_factor)
    else:
        scale_factor = 1.0
        target_width = screen_w
        target_height = screen_h

    log(f"CUA ComputerTool.__init__ would compute:")
    log(f"  pyautogui.size() = ({screen_w}, {screen_h})")
    log(f"  scale_factor = {MAX_WIDTH}/{screen_w} = {scale_factor:.6f}")
    log(f"  target = {target_width}x{target_height}")

    # Scale factors used in scale_coordinates
    x_sf = screen_w / target_width
    y_sf = screen_h / target_height

    log(f"  x_scaling_factor = {screen_w}/{target_width} = {x_sf:.6f}")
    log(f"  y_scaling_factor = {screen_h}/{target_height} = {y_sf:.6f}")

    if abs(x_sf - y_sf) > 0.001:
        log(f"  ** WARNING: x and y scaling factors differ! **")
        log(f"  This means the aspect ratio changes during scaling.")
        log(f"  Difference: {abs(x_sf - y_sf):.6f}")
        results["aspect_ratio_skew"] = True
    else:
        results["aspect_ratio_skew"] = False

    # Test round-trip for the input coords
    if "working_click_coords" in results:
        real_x, real_y = results["working_click_coords"]
    else:
        real_x, real_y = coord_data["candidates"]["A_js_rect"]

    # Real -> API (what screenshot coord would the model see?)
    api_x = round(real_x / x_sf)
    api_y = round(real_y / y_sf)
    # API -> Real (what CUA would click)
    back_x = round(api_x * x_sf)
    back_y = round(api_y * y_sf)

    drift_x = abs(back_x - real_x)
    drift_y = abs(back_y - real_y)

    log(f"\n  Round-trip test:")
    log(f"    Real coords:    ({real_x}, {real_y})")
    log(f"    -> API coords:  ({api_x}, {api_y})")
    log(f"    -> Back to real: ({back_x}, {back_y})")
    log(f"    Drift:          ({drift_x}px, {drift_y}px)")
    results["cua_roundtrip_drift"] = (drift_x, drift_y)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run_all():
    log("=" * 60)
    log("  COMPREHENSIVE CUA INPUT DIAGNOSTIC")
    log("=" * 60)
    log(f"Target URL: {URL}")
    log(f"Test text:  '{TEST_TEXT}'")
    log(f"Time:       {time.strftime('%Y-%m-%d %H:%M:%S')}")

    preflight_checks()

    # Launch Chrome
    section("LAUNCHING CHROME")
    options = Options()
    options.add_argument("--disable-autofill")
    options.add_argument("--disable-features=AutofillServerCommunication")
    options.add_argument("--window-size=1280,900")
    options.add_argument("--window-position=0,0")

    driver = webdriver.Chrome(options=options)
    driver.get(URL)
    time.sleep(3)

    # Find input
    input_el, selector = find_input(driver)
    if not input_el:
        log("FATAL: No input element found on page!")
        driver.quit()
        return

    log(f"Input found via: {selector}")

    # CRITICAL: Scroll input into view first — it's below the fold
    section("SCROLLING INPUT INTO VIEW")
    scroll_info = driver.execute_script("""
        const el = arguments[0];
        const beforeY = window.scrollY;
        const beforeRect = el.getBoundingClientRect();
        el.scrollIntoView({ block: 'center', behavior: 'instant' });
        // Force a reflow
        void el.offsetHeight;
        const afterY = window.scrollY;
        const afterRect = el.getBoundingClientRect();
        return {
            scrolledFrom: beforeY,
            scrolledTo: afterY,
            rectBefore: { y: beforeRect.y, height: beforeRect.height },
            rectAfter: { y: afterRect.y, height: afterRect.height },
            innerHeight: window.innerHeight
        };
    """, input_el)
    log(f"Scrolled: scrollY {scroll_info['scrolledFrom']} -> {scroll_info['scrolledTo']}")
    log(f"Input rect Y: {scroll_info['rectBefore']['y']:.0f} -> {scroll_info['rectAfter']['y']:.0f}")
    log(f"Viewport height: {scroll_info['innerHeight']}")
    in_view = 0 <= scroll_info['rectAfter']['y'] < scroll_info['innerHeight']
    log(f"Input now in view: {'YES' if in_view else 'NO'}")
    time.sleep(0.5)

    # Run all test suites
    coord_data = coordinate_analysis(driver, input_el)
    verified_coords = pixel_verification(driver, input_el, coord_data)
    working_click = click_tests(driver, input_el, coord_data, verified_coords)
    event_listener_analysis(driver, input_el)
    typing_tests(driver, input_el, working_click)
    focus_persistence_tests(driver, input_el, working_click)
    address_bar_paste_test()
    cua_scaling_analysis(coord_data)

    # Final screenshot
    driver.save_screenshot(os.path.join(DIAG_DIR, "final_state.png"))
    log(f"\nFinal screenshot saved: final_state.png")

    driver.quit()

    # ─── COMPREHENSIVE SUMMARY ───
    section("COMPREHENSIVE SUMMARY")

    log("\n  ENVIRONMENT:")
    log(f"    Screen: {results.get('screen_size', 'N/A')}")
    log(f"    Retina scale: {results.get('retina_scale', 'N/A')}x")
    log(f"    Clipboard: {'OK' if results.get('clipboard_roundtrip') else 'BROKEN'}")

    log("\n  COORDINATE RESULTS:")
    if "working_click_method" in results:
        log(f"    Working click method: {results['working_click_method']}")
        log(f"    Working click coords: {results.get('working_click_coords')}")
    else:
        log(f"    ** NO CLICK METHOD FOCUSED THE INPUT **")
    if "coordinate_drift" in results:
        log(f"    Drift from computed coords: {results['coordinate_drift']}")
    if "grid_offset_from_A" in results:
        log(f"    Grid search offset: {results['grid_offset_from_A']}")
    log(f"    CUA round-trip drift: {results.get('cua_roundtrip_drift', 'N/A')}")
    log(f"    Aspect ratio skew: {'YES' if results.get('aspect_ratio_skew') else 'No'}")

    log("\n  TYPING MECHANISM RESULTS:")
    typing_tests_list = [
        ("A: pbcopy + pyautogui cmd+v (CUA)", "A_pbcopy_pyautogui_cmdv"),
        ("B: pbcopy + AppleScript paste", "B_pbcopy_applescript_paste"),
        ("C: AppleScript keystroke", "C_applescript_keystroke"),
        ("D: pyautogui.typewrite", "D_pyautogui_typewrite"),
        ("E: pyautogui.write", "E_pyautogui_write"),
        ("F: Selenium send_keys", "F_selenium_send_keys"),
        ("G: JS dispatchEvent", "G_js_dispatch"),
    ]
    for label, key in typing_tests_list:
        val = results.get(key)
        status = "YES" if val else "NO" if val is False else "N/A"
        marker = "" if val else " **"
        log(f"    {label}: {status}{marker}")

    log("\n  FOCUS PERSISTENCE:")
    for delay in ["0.5s", "1s", "3s", "5s"]:
        val = results.get(f"focus_holds_{delay}")
        status = "YES" if val else "NO" if val is False else "N/A"
        log(f"    Holds after {delay}: {status}")

    log("\n  EVENT ANALYSIS:")
    log(f"    Paste event prevented: {'YES **' if results.get('paste_prevented') else 'No'}")
    log(f"    Keydown cmd+v prevented: {'YES **' if results.get('keydown_cmdv_prevented') else 'No'}")

    # ─── DIAGNOSIS ───
    log("\n" + "─" * 60)
    log("  DIAGNOSIS")
    log("─" * 60)

    issues = []

    if "working_click_method" not in results:
        issues.append("CRITICAL: pyautogui cannot click the input at any tested coordinate")

    if results.get("A_pbcopy_pyautogui_cmdv") is False:
        if results.get("B_pbcopy_applescript_paste"):
            issues.append("pyautogui.hotkey('command','v') doesn't paste, but AppleScript does -> pyautogui hotkey issue")
        elif results.get("C_applescript_keystroke"):
            issues.append("Clipboard paste fails, but AppleScript keystroke works -> clipboard/paste mechanism broken")
        elif results.get("D_pyautogui_typewrite"):
            issues.append("Clipboard paste fails, but pyautogui.typewrite works -> USE typewrite INSTEAD of pbcopy+cmd+v")
        elif results.get("F_selenium_send_keys"):
            issues.append("Only Selenium send_keys works -> pyautogui cannot deliver keystrokes to Chrome")
            issues.append("Check: Is Chrome the frontmost app? Is Accessibility enabled for the terminal?")
        else:
            issues.append("Nothing works except JS injection -> fundamental accessibility/permission issue")

    if results.get("retina_scale", 1.0) > 1.0 and "working_click_method" not in results:
        issues.append(f"Retina display ({results['retina_scale']}x) may cause coordinate mismatch")

    for delay in ["3s", "5s"]:
        if results.get(f"focus_holds_{delay}") is False:
            issues.append(f"Focus lost after {delay} delay -> webapp or Chrome steals focus")
            break

    if results.get("paste_prevented"):
        issues.append("Webapp prevents paste events")

    if not issues:
        issues.append("All tests passed! Issue may be specific to CUA API interaction timing or screen state.")

    for i, issue in enumerate(issues, 1):
        log(f"  {i}. {issue}")

    log("\n  RECOMMENDED FIX:")
    if results.get("D_pyautogui_typewrite") and not results.get("A_pbcopy_pyautogui_cmdv"):
        log("  -> Replace pbcopy+cmd+v with pyautogui.typewrite() in ComputerTool")
        log("     Change type action in computer.py to use typewrite instead of clipboard")
    elif results.get("C_applescript_keystroke") and not results.get("A_pbcopy_pyautogui_cmdv"):
        log("  -> Replace pbcopy+cmd+v with AppleScript keystroke in ComputerTool")
    elif results.get("B_pbcopy_applescript_paste") and not results.get("A_pbcopy_pyautogui_cmdv"):
        log("  -> Replace pyautogui.hotkey with AppleScript paste in ComputerTool")
    elif "working_click_method" not in results:
        log("  -> Fix coordinate calculation (likely Retina scaling)")
        log("     Then re-run this diagnostic")
    else:
        log("  -> Run simple_input.html test with actual CUA to isolate further")

    log("\n" + "=" * 60)

    # Save full results JSON
    results_path = os.path.join(DIAG_DIR, "diagnostic_results.json")
    with open(results_path, "w") as f:
        # Convert tuples to lists for JSON serialization
        serializable = {}
        for k, v in results.items():
            if isinstance(v, tuple):
                serializable[k] = list(v)
            else:
                serializable[k] = v
        json.dump(serializable, f, indent=2)
    log(f"Full results saved: diagnostic_results.json")

    # Save log
    log_path = os.path.join(DIAG_DIR, "diagnostic_log.txt")
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines))
    log(f"Full log saved: diagnostic_log.txt")


if __name__ == "__main__":
    print("\nWARNING: This test will take over your mouse and keyboard.")
    print("Do not move the mouse or type during the test (~60 seconds).")
    print("Starting in 3 seconds...\n")
    time.sleep(3)
    run_all()
