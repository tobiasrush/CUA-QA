"""
Diagnostic 1: Playwright DOM-level test
Tests whether the webapp input accepts text via different methods.
Tests hypotheses C (CSS overlay) and D (paste blocked).
No CUA API cost. ~30 seconds.

Install:
    /Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/pip install playwright
    /Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python -m playwright install chromium

Run:
    /Users/tobyrush/Documents/GitHub/CUA-QA/venv/bin/python /Users/tobyrush/Documents/GitHub/CUA-QA/diagnostics/test_webapp_input.py
"""

import sys
from playwright.sync_api import sync_playwright

URL = "https://demo.useideem.com/umfa.html?debug=true"
INPUT_SELECTOR = "input#username"
TEST_TEXT = "diagnostic_test_user"

results = {}


def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(2000)  # Let any JS settle

        # --- Test 1: Can we find the input? ---
        input_el = page.query_selector(INPUT_SELECTOR)
        if not input_el:
            # Try broader selectors
            input_el = page.query_selector("input[type='text']")
            if not input_el:
                input_el = page.query_selector("input")
            if input_el:
                actual_selector = "input (fallback)"
            else:
                results["input_found"] = False
                print("FATAL: No input element found on page")
                print_summary()
                browser.close()
                return
        else:
            actual_selector = INPUT_SELECTOR

        results["input_found"] = True
        print(f"Input found via: {actual_selector}")

        # Get input bounding box
        bbox = input_el.bounding_box()
        if bbox:
            print(f"Input bounding box: x={bbox['x']:.0f} y={bbox['y']:.0f} "
                  f"w={bbox['width']:.0f} h={bbox['height']:.0f}")
        else:
            print("WARNING: Input has no bounding box (hidden?)")

        # --- Test 2: Overlapping elements (Hypothesis C) ---
        if bbox:
            center_x = bbox["x"] + bbox["width"] / 2
            center_y = bbox["y"] + bbox["height"] / 2
            top_element = page.evaluate(
                """([x, y]) => {
                    const el = document.elementFromPoint(x, y);
                    if (!el) return null;
                    return {
                        tag: el.tagName,
                        id: el.id || null,
                        className: el.className || null,
                        isInput: el.tagName === 'INPUT'
                    };
                }""",
                [center_x, center_y],
            )
            if top_element:
                is_input = top_element["isInput"]
                results["click_hits_input"] = is_input
                print(f"\nelementFromPoint at center ({center_x:.0f}, {center_y:.0f}):")
                print(f"  Tag: {top_element['tag']}, id: {top_element['id']}, "
                      f"class: {top_element['className']}")
                if not is_input:
                    print("  ** OVERLAY DETECTED: Click would NOT hit the input! **")
                else:
                    print("  OK: Click reaches the input directly")
            else:
                results["click_hits_input"] = False
                print("WARNING: elementFromPoint returned null")

        # --- Test 3: fill() method ---
        try:
            input_el.fill("")  # Clear first
            input_el.fill(TEST_TEXT)
            value = input_el.input_value()
            results["fill_works"] = value == TEST_TEXT
            print(f"\nfill() method: value='{value}' -> {'OK' if results['fill_works'] else 'FAILED'}")
        except Exception as e:
            results["fill_works"] = False
            print(f"\nfill() method: EXCEPTION: {e}")

        # --- Test 4: keyboard.type() after click ---
        try:
            input_el.fill("")  # Clear
            input_el.click()
            page.wait_for_timeout(200)

            # Check focus
            focused_tag = page.evaluate("document.activeElement?.tagName")
            focused_id = page.evaluate("document.activeElement?.id")
            has_focus = focused_id == "username" or focused_tag == "INPUT"
            results["click_gives_focus"] = has_focus
            print(f"\nAfter click: activeElement = {focused_tag}#{focused_id} -> "
                  f"{'OK' if has_focus else 'FOCUS LOST'}")

            page.keyboard.type(TEST_TEXT, delay=50)
            page.wait_for_timeout(200)
            value = input_el.input_value()
            results["keyboard_type_works"] = value == TEST_TEXT
            print(f"keyboard.type(): value='{value}' -> "
                  f"{'OK' if results['keyboard_type_works'] else 'FAILED'}")
        except Exception as e:
            results["keyboard_type_works"] = False
            print(f"keyboard.type(): EXCEPTION: {e}")

        # --- Test 5: Clipboard paste via Meta+v (Hypothesis D) ---
        try:
            input_el.fill("")  # Clear
            input_el.click()
            page.wait_for_timeout(200)

            # Set clipboard via page.evaluate
            page.evaluate(
                """(text) => {
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }""",
                TEST_TEXT,
            )

            # Re-focus input after clipboard operation
            input_el.click()
            page.wait_for_timeout(200)

            # Paste
            page.keyboard.press("Meta+v")
            page.wait_for_timeout(500)
            value = input_el.input_value()
            results["paste_works"] = value == TEST_TEXT
            print(f"\nMeta+v paste: value='{value}' -> "
                  f"{'OK' if results['paste_works'] else 'FAILED'}")
        except Exception as e:
            results["paste_works"] = False
            print(f"Meta+v paste: EXCEPTION: {e}")

        # --- Test 6: Check for paste event listeners that block ---
        try:
            paste_blocked = page.evaluate(
                """() => {
                    const input = document.querySelector('input#username') ||
                                  document.querySelector('input[type="text"]') ||
                                  document.querySelector('input');
                    if (!input) return 'no_input';

                    // Check for paste event listeners (indirect check)
                    let pasteBlocked = false;
                    const origOnPaste = input.onpaste;
                    if (origOnPaste) {
                        pasteBlocked = true;
                    }

                    // Check via getEventListeners if available (Chrome DevTools only)
                    // Fall back to checking if paste event is prevented
                    let testResult = null;
                    const handler = (e) => { testResult = e.defaultPrevented; };
                    input.addEventListener('paste', handler);
                    const event = new ClipboardEvent('paste', {
                        bubbles: true,
                        cancelable: true,
                        clipboardData: new DataTransfer()
                    });
                    input.dispatchEvent(event);
                    input.removeEventListener('paste', handler);

                    return {
                        onpaste_handler: origOnPaste !== null && origOnPaste !== undefined,
                        paste_prevented: event.defaultPrevented,
                        test_result: testResult
                    };
                }"""
            )
            results["paste_event_blocked"] = (
                paste_blocked.get("paste_prevented", False)
                if isinstance(paste_blocked, dict)
                else False
            )
            print(f"\nPaste event inspection: {paste_blocked}")
            if isinstance(paste_blocked, dict) and paste_blocked.get("paste_prevented"):
                print("  ** PASTE BLOCKED: webapp prevents paste events! **")
            else:
                print("  OK: Paste events are not blocked")
        except Exception as e:
            print(f"Paste event inspection: EXCEPTION: {e}")

        # --- Test 7: Check input attributes ---
        try:
            attrs = page.evaluate(
                """() => {
                    const input = document.querySelector('input#username') ||
                                  document.querySelector('input[type="text"]') ||
                                  document.querySelector('input');
                    if (!input) return null;
                    return {
                        type: input.type,
                        id: input.id,
                        name: input.name,
                        readOnly: input.readOnly,
                        disabled: input.disabled,
                        autocomplete: input.autocomplete,
                        tabIndex: input.tabIndex,
                        style_pointerEvents: getComputedStyle(input).pointerEvents,
                        style_userSelect: getComputedStyle(input).userSelect,
                        inIframe: input.ownerDocument !== document,
                        inShadowRoot: !!input.getRootNode().host
                    };
                }"""
            )
            print(f"\nInput attributes: {attrs}")
            if attrs:
                if attrs.get("readOnly"):
                    print("  ** WARNING: Input is readOnly! **")
                if attrs.get("disabled"):
                    print("  ** WARNING: Input is disabled! **")
                if attrs.get("style_pointerEvents") == "none":
                    print("  ** WARNING: pointer-events: none! **")
                if attrs.get("inShadowRoot"):
                    print("  ** WARNING: Input is inside Shadow DOM! **")
        except Exception as e:
            print(f"Input attributes: EXCEPTION: {e}")

        # Take a screenshot for reference
        page.screenshot(
            path="/Users/tobyrush/Documents/GitHub/CUA-QA/diagnostics/webapp_screenshot.png"
        )
        print("\nScreenshot saved to diagnostics/webapp_screenshot.png")

        browser.close()

    print_summary()


def print_summary():
    print("\n" + "=" * 60)
    print("SUMMARY - Playwright Webapp Input Test")
    print("=" * 60)

    checks = [
        ("Input element found", "input_found"),
        ("Click hits input (no overlay)", "click_hits_input"),
        ("fill() works", "fill_works"),
        ("Click gives focus", "click_gives_focus"),
        ("keyboard.type() works", "keyboard_type_works"),
        ("Meta+v paste works", "paste_works"),
    ]

    all_pass = True
    for label, key in checks:
        val = results.get(key)
        status = "YES" if val else "NO" if val is False else "N/A"
        if not val and val is not None:
            all_pass = False
        print(f"  {label}: {status}")

    print()
    if results.get("click_hits_input") is False:
        print("-> Hypothesis C CONFIRMED: CSS overlay blocks clicks")
    if results.get("paste_works") is False and results.get("keyboard_type_works"):
        print("-> Hypothesis D CONFIRMED: Paste is blocked, but keystroke typing works")
    if results.get("paste_works") is False and results.get("paste_event_blocked"):
        print("-> Hypothesis D CONFIRMED: Webapp blocks paste events")
    if all_pass:
        print("-> Webapp accepts input normally. Problem is in CUA layer (focus/coords/timing).")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
