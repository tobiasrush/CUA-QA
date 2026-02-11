"""
Agentic sampling loop for Google Gemini Computer Use API.
Reuses pyautogui-based action execution from the existing tools.
"""

import asyncio
import base64
import io
import platform
import subprocess
import time
from datetime import datetime
from typing import Any, Callable

import pyautogui
from google import genai
from google.genai import types
from google.genai.types import Content, Part, FunctionResponse, FunctionResponsePart, FunctionResponseBlob

from .tools import ToolResult

GEMINI_MODEL = "gemini-2.5-computer-use-preview-10-2025"

SYSTEM_PROMPT = f"""<SYSTEM_CAPABILITY>
* You are utilizing a MacOS computer using {platform.machine()} architecture with internet access.
* You can see the screen through screenshots provided after each action.
* The current date is {datetime.today().strftime('%A, %B %-d, %Y')}.
</SYSTEM_CAPABILITY>

<IMPORTANT>
* When using browsers or other applications, if any startup wizards or prompts appear, IGNORE THEM.
* If content is below the fold, scroll down before interacting.
</IMPORTANT>"""


def denormalize_coords(norm_x: int, norm_y: int, screen_width: int, screen_height: int) -> tuple[int, int]:
    """Convert Gemini's 0-999 normalized coordinates to actual screen pixels."""
    return int(norm_x / 1000 * screen_width), int(norm_y / 1000 * screen_height)


async def get_chrome_url() -> str:
    """Get the current URL from Google Chrome via AppleScript."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", 'tell application "Google Chrome" to get URL of active tab of front window'],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "about:blank"
    except Exception:
        return "about:blank"


async def take_screenshot_bytes() -> bytes:
    """Take a screenshot via pyautogui and return raw PNG bytes."""
    screenshot = await asyncio.to_thread(pyautogui.screenshot)
    buf = io.BytesIO()
    screenshot.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


# Key name mapping: Gemini conventions -> pyautogui conventions
GEMINI_KEY_MAP = {
    "control": "ctrl", "ctrl": "ctrl",
    "meta": "command", "command": "command",
    "alt": "alt", "option": "alt",
    "shift": "shift",
    "enter": "enter", "return": "enter",
    "escape": "esc", "esc": "esc",
    "tab": "tab", "space": "space",
    "backspace": "backspace", "delete": "delete",
    "arrowup": "up", "arrowdown": "down",
    "arrowleft": "left", "arrowright": "right",
}


async def execute_gemini_action(func_name: str, args: dict[str, Any]) -> str:
    """Execute a Gemini computer use function call via pyautogui.

    Returns a description string of what was done.
    """
    screen_width, screen_height = pyautogui.size()

    if func_name == "click_at":
        x, y = denormalize_coords(int(args["x"]), int(args["y"]), screen_width, screen_height)
        await asyncio.to_thread(pyautogui.click, x, y)
        return f"Clicked at ({x}, {y})"

    elif func_name == "hover_at":
        x, y = denormalize_coords(int(args["x"]), int(args["y"]), screen_width, screen_height)
        await asyncio.to_thread(pyautogui.moveTo, x, y)
        return f"Hovered at ({x}, {y})"

    elif func_name == "type_text_at":
        x, y = denormalize_coords(int(args["x"]), int(args["y"]), screen_width, screen_height)
        text = args.get("text", "")
        clear_before = args.get("clear_before_typing", False)
        press_enter = args.get("press_enter", False)

        await asyncio.to_thread(pyautogui.click, x, y)

        if clear_before:
            await asyncio.to_thread(pyautogui.hotkey, "command", "a")
            await asyncio.to_thread(pyautogui.press, "delete")

        # Use clipboard paste (same macOS workaround as ComputerTool)
        await asyncio.to_thread(subprocess.run, ["pbcopy"], input=text.encode(), check=True)
        await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True, timeout=5,
        )

        if press_enter:
            await asyncio.to_thread(pyautogui.press, "enter")

        return f"Typed '{text}' at ({x}, {y})"

    elif func_name == "key_combination":
        keys = args.get("keys", "")
        key_parts = [k.strip().lower() for k in keys.split("+")]
        mapped = [GEMINI_KEY_MAP.get(k, k) for k in key_parts]
        await asyncio.to_thread(pyautogui.hotkey, *mapped)
        return f"Pressed {keys}"

    elif func_name == "scroll_at":
        x, y = denormalize_coords(int(args["x"]), int(args["y"]), screen_width, screen_height)
        direction = args.get("direction", "down")
        magnitude = int(args.get("magnitude", 3))
        await asyncio.to_thread(pyautogui.moveTo, x, y)
        clicks = magnitude if direction == "up" else -magnitude
        await asyncio.to_thread(pyautogui.scroll, clicks)
        return f"Scrolled {direction} by {magnitude} at ({x}, {y})"

    elif func_name == "scroll_document":
        direction = args.get("direction", "down")
        cx, cy = screen_width // 2, screen_height // 2
        await asyncio.to_thread(pyautogui.moveTo, cx, cy)
        clicks = 5 if direction == "up" else -5
        await asyncio.to_thread(pyautogui.scroll, clicks)
        return f"Scrolled document {direction}"

    elif func_name == "navigate":
        url = args.get("url", "")
        await asyncio.to_thread(pyautogui.hotkey, "command", "l")
        await asyncio.sleep(0.3)
        await asyncio.to_thread(subprocess.run, ["pbcopy"], input=url.encode(), check=True)
        await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            check=True, timeout=5,
        )
        await asyncio.to_thread(pyautogui.press, "enter")
        return f"Navigated to {url}"

    elif func_name == "go_back":
        await asyncio.to_thread(pyautogui.hotkey, "command", "[")
        return "Went back"

    elif func_name == "go_forward":
        await asyncio.to_thread(pyautogui.hotkey, "command", "]")
        return "Went forward"

    elif func_name == "wait_5_seconds":
        await asyncio.sleep(5)
        return "Waited 5 seconds"

    elif func_name == "open_web_browser":
        await asyncio.to_thread(subprocess.run, ["open", "-a", "Google Chrome"], check=True)
        return "Opened web browser"

    elif func_name == "drag_and_drop":
        sx, sy = denormalize_coords(int(args["x"]), int(args["y"]), screen_width, screen_height)
        ex, ey = denormalize_coords(int(args["destination_x"]), int(args["destination_y"]), screen_width, screen_height)
        await asyncio.to_thread(pyautogui.moveTo, sx, sy)
        await asyncio.to_thread(pyautogui.mouseDown)
        await asyncio.to_thread(pyautogui.moveTo, ex, ey, duration=0.5)
        await asyncio.to_thread(pyautogui.mouseUp)
        return f"Dragged from ({sx},{sy}) to ({ex},{ey})"

    elif func_name == "search":
        await asyncio.to_thread(subprocess.run, ["open", "https://www.google.com"], check=True)
        return "Opened search"

    else:
        return f"Unknown action: {func_name}"


async def sampling_loop_gemini(
    *,
    model: str = GEMINI_MODEL,
    system_prompt_suffix: str,
    api_key: str,
    messages: list,
    output_callback: Callable,
    tool_output_callback: Callable,
    max_turns: int = 15,
) -> tuple[list, dict]:
    """
    Agentic sampling loop for Gemini computer use.
    Returns (messages, {"input_tokens": N, "output_tokens": N, "model": "..."})
    """
    client = genai.Client(api_key=api_key)

    system_text = f"{SYSTEM_PROMPT}\n{system_prompt_suffix}" if system_prompt_suffix else SYSTEM_PROMPT

    config = types.GenerateContentConfig(
        system_instruction=system_text,
        max_output_tokens=8192,
        tools=[
            types.Tool(
                computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER,
                )
            )
        ],
    )

    # Convert caller's messages to Gemini Content format
    contents: list[Content] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            gemini_role = "user" if role == "user" else "model"
            contents.append(Content(role=gemini_role, parts=[Part(text=content)]))

    # Attach initial screenshot to the last user message
    initial_screenshot = await take_screenshot_bytes()
    if contents and contents[-1].role == "user":
        contents[-1].parts.append(Part.from_bytes(data=initial_screenshot, mime_type="image/png"))

    total_input_tokens = 0
    total_output_tokens = 0

    for turn in range(max_turns):
        time.sleep(0.5)

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        # Track tokens
        if response.usage_metadata:
            total_input_tokens += response.usage_metadata.prompt_token_count or 0
            total_output_tokens += response.usage_metadata.candidates_token_count or 0

        candidate = response.candidates[0]
        if candidate.content:
            contents.append(candidate.content)

        # Extract text and function calls from response
        function_calls = []
        for part in (candidate.content.parts if candidate.content and candidate.content.parts else []):
            if hasattr(part, "text") and part.text:

                class _TextBlock:
                    def __init__(self, text):
                        self.type = "text"
                        self.text = text

                output_callback(_TextBlock(part.text))

            if hasattr(part, "function_call") and part.function_call:
                function_calls.append(part.function_call)

        # No function calls = task complete
        if not function_calls:
            break

        # Execute each function call
        func_response_parts = []
        for fc in function_calls:
            fname = fc.name
            fargs = dict(fc.args) if fc.args else {}

            print(f"### Performing action: {fname}, args: {fargs}")

            result_text = await execute_gemini_action(fname, fargs)
            print(f"    Tool output: {result_text}")

            # Wait for UI to settle, then screenshot + get current URL
            await asyncio.sleep(1)
            screenshot_bytes = await take_screenshot_bytes()
            current_url = await get_chrome_url()

            # Notify callback (for saving screenshots to disk)
            b64_screenshot = base64.b64encode(screenshot_bytes).decode()
            tool_result = ToolResult(output=result_text, base64_image=b64_screenshot)
            tool_output_callback(tool_result, fname)

            # Build Gemini FunctionResponse (must include 'url' field + screenshot in parts)
            func_response_parts.append(Part(function_response=FunctionResponse(
                name=fname,
                response={"url": current_url},
                parts=[
                    FunctionResponsePart(
                        inline_data=FunctionResponseBlob(
                            mime_type="image/png",
                            data=screenshot_bytes,
                        )
                    )
                ],
            )))

        contents.append(Content(role="user", parts=func_response_parts))

    return messages, {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "model": model,
    }
