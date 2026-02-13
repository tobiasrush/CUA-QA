"""
Definitive CUA flow test: uses Selenium for DOM access to find real input coordinates,
but pyautogui for all interactions (exactly replicating CUA's mechanism).
Tests whether pbcopy + cmd+v works after the CUA timing pattern.
"""
import asyncio
import subprocess
import time
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.by import By

URL = "https://demo.useideem.com/umfa.html?debug=true"
DIAG_DIR = "/Users/tobyrush/Documents/GitHub/CUA-QA/diagnostics"


def pbcopy(text):
    """Exact CUA mechanism"""
    subprocess.run(["pbcopy"], input=text.encode(), check=True)


def pbpaste():
    r = subprocess.run(["pbpaste"], capture_output=True, timeout=3)
    return r.stdout.decode()


def get_frontmost_app():
    r = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        capture_output=True, timeout=5
    )
    return r.stdout.decode().strip()


async def cua_type(text):
    """Exact replica of CUA's type action from computer.py lines 163-170"""
    process = await asyncio.to_thread(
        subprocess.run, ["pbcopy"], input=text.encode(), check=True
    )
    await asyncio.to_thread(pyautogui.hotkey, "command", "v")


def get_input_state(driver):
    """Get input value and focus state from DOM"""
    return driver.execute_script("""
        const input = document.querySelector('input#username')
                   || document.querySelector('input[type="text"]')
                   || document.querySelector('input');
        if (!input) return {found: false};
        return {
            found: true,
            value: input.value,
            hasFocus: document.activeElement === input,
            activeElement: document.activeElement.tagName + '#' + (document.activeElement.id || ''),
            scrollY: window.scrollY
        };
    """)


def get_screen_coords(driver, input_el):
    """Get real screen coordinates of input element center"""
    info = driver.execute_script("""
        const el = arguments[0];
        el.scrollIntoView({ block: 'center', behavior: 'instant' });
        const rect = el.getBoundingClientRect();
        // Chrome DevTools Protocol coords
        return {
            rect_x: rect.x,
            rect_y: rect.y,
            rect_w: rect.width,
            rect_h: rect.height,
            center_x: rect.x + rect.width / 2,
            center_y: rect.y + rect.height / 2,
            dpr: window.devicePixelRatio,
            innerW: window.innerWidth,
            innerH: window.innerHeight,
            outerW: window.outerWidth,
            outerH: window.outerHeight,
            screenX: window.screenX,
            screenY: window.screenY,
            scrollY: window.scrollY
        };
    """, input_el)
    return info


print("=" * 60)
print("Definitive CUA Flow Test (Selenium + pyautogui)")
print("=" * 60)

# Set up Chrome via Selenium for DOM access
options = webdriver.ChromeOptions()
options.add_argument("--window-position=0,0")
options.add_argument("--window-size=1280,900")
options.add_argument("--disable-search-engine-choice-screen")

driver = webdriver.Chrome(options=options)
time.sleep(1)

try:
    driver.get(URL)
    time.sleep(3)  # Let page fully load

    # Find the input
    input_el = None
    for selector in ["input#username", "input[type='text']", "input"]:
        try:
            input_el = driver.find_element(By.CSS_SELECTOR, selector)
            print(f"Found input via: {selector}")
            break
        except Exception:
            continue

    if not input_el:
        print("FATAL: No input found!")
        driver.quit()
        exit(1)

    # Get real screen coordinates
    info = get_screen_coords(driver, input_el)
    print(f"\nInput location:")
    print(f"  CSS rect: ({info['rect_x']:.0f}, {info['rect_y']:.0f}) {info['rect_w']:.0f}x{info['rect_h']:.0f}")
    print(f"  CSS center: ({info['center_x']:.0f}, {info['center_y']:.0f})")
    print(f"  DPR: {info['dpr']}, scrollY: {info['scrollY']}")
    print(f"  Window: screenX={info['screenX']}, screenY={info['screenY']}")
    print(f"  Inner: {info['innerW']}x{info['innerH']}, Outer: {info['outerW']}x{info['outerH']}")

    # Calculate screen coordinates
    # On macOS with Retina, CSS pixels = screen points (pyautogui uses points)
    # Chrome toolbar height = outerH - innerH
    toolbar_h = info['outerH'] - info['innerH']
    screen_x = int(info['screenX'] + info['center_x'])
    screen_y = int(info['screenY'] + toolbar_h + info['center_y'])

    print(f"\n  Toolbar height: {toolbar_h}px")
    print(f"  Screen click target: ({screen_x}, {screen_y})")

    # Verify with pyautogui screen size
    sw, sh = pyautogui.size()
    print(f"  pyautogui screen: {sw}x{sh}")

    if screen_x < 0 or screen_x >= sw or screen_y < 0 or screen_y >= sh:
        print(f"  WARNING: Click target out of screen bounds!")

    print(f"\nStarting tests in 2 seconds... Don't touch anything!\n")
    time.sleep(2)

    # ── Verify coordinates by clicking and checking DOM focus ──
    print("--- Pre-check: Click at computed coords and verify DOM focus ---")
    pyautogui.click(screen_x, screen_y)
    time.sleep(0.3)
    state = get_input_state(driver)
    print(f"  After click: hasFocus={state.get('hasFocus')}, activeElement={state.get('activeElement')}")
    if not state.get('hasFocus'):
        print("  COORDINATE MISS! Trying offset corrections...")
        # Try different offsets
        for dx, dy in [(0, -20), (0, 20), (-20, 0), (20, 0), (0, -40), (0, 40)]:
            test_x, test_y = screen_x + dx, screen_y + dy
            pyautogui.click(test_x, test_y)
            time.sleep(0.2)
            state = get_input_state(driver)
            if state.get('hasFocus'):
                print(f"  FOUND! Offset ({dx}, {dy}) → ({test_x}, {test_y}) gives focus")
                screen_x, screen_y = test_x, test_y
                break
        else:
            print("  Could not find working coordinates via offset search!")
            # Try Selenium's element location as fallback
            loc = input_el.location
            size = input_el.size
            alt_x = loc['x'] + size['width'] // 2
            alt_y = info['screenY'] + toolbar_h + loc['y'] + size['height'] // 2 - int(info['scrollY'])
            print(f"  Trying Selenium location fallback: ({alt_x}, {alt_y})")
            pyautogui.click(alt_x, alt_y)
            time.sleep(0.2)
            state = get_input_state(driver)
            if state.get('hasFocus'):
                print(f"  Selenium fallback works!")
                screen_x, screen_y = alt_x, alt_y
            else:
                print("  ALL COORDINATE METHODS FAILED. Results will be unreliable.")

    # ── Test 1: Basic paste (no delay) — sanity check ──
    print("\n--- Test 1: Click + immediate paste (sanity check) ---")
    # Clear field
    driver.execute_script("""
        const input = document.querySelector('input#username') || document.querySelector('input');
        if (input) { input.value = ''; input.focus(); }
    """)
    time.sleep(0.2)

    pyautogui.click(screen_x, screen_y)
    time.sleep(0.3)
    state = get_input_state(driver)
    print(f"  Focus before paste: {state.get('hasFocus')}")

    pbcopy("test1_basic")
    time.sleep(0.05)
    pyautogui.hotkey("command", "v")
    time.sleep(0.5)

    state = get_input_state(driver)
    clipboard = pbpaste()
    print(f"  Clipboard contains: '{clipboard}'")
    print(f"  Input value: '{state.get('value')}'")
    print(f"  Focus after paste: {state.get('hasFocus')}")
    test1_pass = state.get('value') == "test1_basic"
    print(f"  Result: {'PASS' if test1_pass else 'FAIL'}")

    # ── Test 2: CUA exact pattern (click → screenshot → 5s delay → paste) ──
    print("\n--- Test 2: CUA pattern (click → screenshot → 5s → paste) ---")
    driver.execute_script("""
        const input = document.querySelector('input#username') || document.querySelector('input');
        if (input) { input.value = ''; input.focus(); }
    """)
    time.sleep(0.2)

    # Step 1: Click (CUA's left_click action)
    pyautogui.click(screen_x, screen_y)
    time.sleep(0.2)
    state = get_input_state(driver)
    print(f"  After click: focus={state.get('hasFocus')}, active={state.get('activeElement')}")

    # Step 2: Screenshot (CUA takes this after click action)
    pyautogui.screenshot()
    state = get_input_state(driver)
    print(f"  After screenshot: focus={state.get('hasFocus')}")

    # Step 3: API delay (simulates API round-trip)
    print(f"  Waiting 5 seconds (API delay)...")
    time.sleep(5)
    state = get_input_state(driver)
    print(f"  After 5s delay: focus={state.get('hasFocus')}, active={state.get('activeElement')}")

    # Step 4: Type action (exact CUA mechanism)
    pbcopy("test2_cua_pattern")
    # CUA has NO delay here
    pyautogui.hotkey("command", "v")
    time.sleep(0.5)

    state = get_input_state(driver)
    print(f"  Input value: '{state.get('value')}'")
    print(f"  Focus after paste: {state.get('hasFocus')}")
    test2_pass = state.get('value') == "test2_cua_pattern"
    print(f"  Result: {'PASS' if test2_pass else 'FAIL'}")

    # ── Test 3: CUA pattern with asyncio (exact code path) ──
    print("\n--- Test 3: CUA exact async mechanism ---")
    driver.execute_script("""
        const input = document.querySelector('input#username') || document.querySelector('input');
        if (input) { input.value = ''; input.focus(); }
    """)
    time.sleep(0.2)

    pyautogui.click(screen_x, screen_y)
    time.sleep(0.2)

    pyautogui.screenshot()
    time.sleep(5)

    state = get_input_state(driver)
    print(f"  Before async type: focus={state.get('hasFocus')}")

    # Use exact CUA async mechanism
    asyncio.run(cua_type("test3_async"))
    time.sleep(0.5)

    state = get_input_state(driver)
    print(f"  Input value: '{state.get('value')}'")
    test3_pass = state.get('value') == "test3_async"
    print(f"  Result: {'PASS' if test3_pass else 'FAIL'}")

    # ── Test 4: After cmd+a + Delete (like CUA's actual flow) ──
    print("\n--- Test 4: Click + cmd+a + Delete + screenshot + 5s + type ---")
    driver.execute_script("""
        const input = document.querySelector('input#username') || document.querySelector('input');
        if (input) { input.value = 'prefilled_text'; input.focus(); }
    """)
    time.sleep(0.2)

    # CUA Turn 1: click + select all + delete
    pyautogui.click(screen_x, screen_y)
    time.sleep(0.2)
    pyautogui.hotkey("command", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.2)

    state = get_input_state(driver)
    print(f"  After clear: value='{state.get('value')}', focus={state.get('hasFocus')}")

    # CUA takes screenshot at end of turn
    pyautogui.screenshot()

    # API round-trip
    print(f"  Waiting 5 seconds (API delay)...")
    time.sleep(5)

    state = get_input_state(driver)
    print(f"  After 5s: focus={state.get('hasFocus')}, active={state.get('activeElement')}")

    # CUA Turn 2: type
    asyncio.run(cua_type("test4_full_flow"))
    time.sleep(0.5)

    state = get_input_state(driver)
    print(f"  Input value: '{state.get('value')}'")
    test4_pass = state.get('value') == "test4_full_flow"
    print(f"  Result: {'PASS' if test4_pass else 'FAIL'}")

    # ── Test 5: With 100ms delay between pbcopy and cmd+v ──
    print("\n--- Test 5: Same as Test 4 but with 100ms delay before paste ---")
    driver.execute_script("""
        const input = document.querySelector('input#username') || document.querySelector('input');
        if (input) { input.value = 'prefilled'; input.focus(); }
    """)
    time.sleep(0.2)

    pyautogui.click(screen_x, screen_y)
    time.sleep(0.2)
    pyautogui.hotkey("command", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.2)

    pyautogui.screenshot()
    time.sleep(5)

    # Type with delay
    pbcopy("test5_with_delay")
    time.sleep(0.1)  # 100ms delay between pbcopy and paste
    pyautogui.hotkey("command", "v")
    time.sleep(0.5)

    state = get_input_state(driver)
    print(f"  Input value: '{state.get('value')}'")
    test5_pass = state.get('value') == "test5_with_delay"
    print(f"  Result: {'PASS' if test5_pass else 'FAIL'}")

    # ── Test 6: Focus recovery before paste ──
    print("\n--- Test 6: Same as Test 4 but re-click input before paste ---")
    driver.execute_script("""
        const input = document.querySelector('input#username') || document.querySelector('input');
        if (input) { input.value = 'prefilled'; input.focus(); }
    """)
    time.sleep(0.2)

    pyautogui.click(screen_x, screen_y)
    time.sleep(0.2)
    pyautogui.hotkey("command", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.2)

    pyautogui.screenshot()
    time.sleep(5)

    # Re-click input to ensure focus
    pyautogui.click(screen_x, screen_y)
    time.sleep(0.3)

    state = get_input_state(driver)
    print(f"  After re-click: focus={state.get('hasFocus')}")

    asyncio.run(cua_type("test6_reclick"))
    time.sleep(0.5)

    state = get_input_state(driver)
    print(f"  Input value: '{state.get('value')}'")
    test6_pass = state.get('value') == "test6_reclick"
    print(f"  Result: {'PASS' if test6_pass else 'FAIL'}")

    # ── Take final screenshot ──
    ss = pyautogui.screenshot()
    ss.save(f"{DIAG_DIR}/flow_test_final.png")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    tests = [
        ("Test 1: Basic paste (no delay)", test1_pass),
        ("Test 2: CUA pattern (5s delay)", test2_pass),
        ("Test 3: CUA async mechanism", test3_pass),
        ("Test 4: Full CUA flow (clear+delay+type)", test4_pass),
        ("Test 5: With 100ms pbcopy delay", test5_pass),
        ("Test 6: Re-click before paste", test6_pass),
    ]
    for name, passed in tests:
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")

    all_pass = all(p for _, p in tests)
    print()
    if all_pass:
        print("ALL TESTS PASS - pbcopy+cmd+v works correctly.")
        print("Issue must be in CUA's coordinate scaling or the model's actions.")
    elif test1_pass and not test2_pass:
        print("TIMING ISSUE: Paste works immediately but fails after delay.")
        print("The input loses focus during the API round-trip.")
    elif not test1_pass:
        print("BASIC PASTE FAILURE: pbcopy+cmd+v doesn't work even without delay.")
        print("Issue is in the paste mechanism itself, not timing.")
    elif test5_pass and not test4_pass:
        print("CLIPBOARD SYNC: Adding delay between pbcopy and cmd+v fixes it.")
    elif test6_pass and not test4_pass:
        print("FOCUS RECOVERY: Re-clicking input before paste fixes it.")
    print("=" * 60)

finally:
    driver.quit()
