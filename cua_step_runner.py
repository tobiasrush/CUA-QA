"""
Single-step CUA executor for Claude Code orchestration.

Runs one CUA prompt and returns structured JSON results.
Each call starts with a fresh conversation by default (no prior context).
Use --persist-context to carry conversation state across calls.

Usage:
    venv/bin/python cua_step_runner.py \
        --prompt "Navigate to https://example.com" \
        --output /tmp/step_result.json
"""

import asyncio
import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / ".env")

from computer_use_demo.loop import sampling_loop, APIProvider
from computer_use_demo.tools import ToolResult
from anthropic.types.beta import BetaMessage, BetaMessageParam
from anthropic import APIResponse


def load_context(context_file: str) -> list:
    """Load conversation messages from a context file."""
    if not os.path.exists(context_file):
        return []
    with open(context_file, "r") as f:
        return json.load(f)


def save_context(context_file: str, messages: list):
    """Save conversation messages to a context file.

    Strips base64 image data from older messages to keep the file manageable.
    The sampling_loop's only_n_most_recent_images handles the API-side trimming.
    """
    # Deep copy to avoid mutating the live messages
    serializable = json.loads(json.dumps(messages, default=str))
    with open(context_file, "w") as f:
        json.dump(serializable, f)


async def run_step(
    prompt: str,
    system_suffix: str,
    messages: list,
    provider_name: str,
    screenshots_dir: Path,
) -> dict:
    """Execute a single CUA step and return structured results."""
    # Select provider and API key
    if provider_name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"status": "error", "error_message": "GEMINI_API_KEY not set"}
        from computer_use_demo.gemini_loop import GEMINI_MODEL
        model = GEMINI_MODEL
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {"status": "error", "error_message": "ANTHROPIC_API_KEY not set"}
        model = "claude-opus-4-6"

    # Build system prompt suffix — all prompting text comes from CLAUDE.md via --system-suffix
    system_parts = []
    if system_suffix:
        system_parts.append(system_suffix)

    # Append the user prompt to conversation
    messages.append({"role": "user", "content": prompt})

    collected_output = []
    screenshot_paths = []
    screenshot_counter = [0]
    step_id = f"step_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def output_callback(content_block):
        if hasattr(content_block, "type") and content_block.type == "text":
            collected_output.append(content_block.text)
        elif isinstance(content_block, dict) and content_block.get("type") == "text":
            collected_output.append(content_block.get("text", ""))

    def tool_output_callback(result: ToolResult, tool_use_id: str):
        if result.base64_image:
            screenshot_counter[0] += 1
            path = screenshots_dir / f"{step_id}_{screenshot_counter[0]}.png"
            with open(path, "wb") as f:
                f.write(base64.b64decode(result.base64_image))
            screenshot_paths.append(str(path))

    def api_response_callback(response: APIResponse[BetaMessage]):
        pass

    step_start = time.monotonic()

    try:
        if provider_name == "gemini":
            from computer_use_demo.gemini_loop import sampling_loop_gemini
            _, token_usage = await sampling_loop_gemini(
                model=model,
                system_prompt_suffix="\n".join(system_parts),
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_key=api_key,
                max_turns=15,
            )
        else:
            _, token_usage = await sampling_loop(
                model=model,
                provider=APIProvider.ANTHROPIC,
                system_prompt_suffix="\n".join(system_parts),
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=api_key,
                only_n_most_recent_images=3,
                max_tokens=4096,
            )

        duration = time.monotonic() - step_start
        full_output = " ".join(collected_output)

        # Extract DEBUG_RESULTS from CUA output
        if "DEBUG_RESULTS:" in full_output:
            dr_start = full_output.find("DEBUG_RESULTS:") + len("DEBUG_RESULTS:")
            debug_results = full_output[dr_start:].strip()
        else:
            debug_results = full_output[:500] if full_output else ""

        return {
            "status": "done",
            "debug_results": debug_results,
            "cua_comments": full_output,
            "screenshot_paths": screenshot_paths,
            "input_tokens": token_usage["input_tokens"],
            "output_tokens": token_usage["output_tokens"],
            "model": token_usage["model"],
            "duration_seconds": round(duration, 1),
            "error_message": None,
        }

    except Exception as e:
        duration = time.monotonic() - step_start
        return {
            "status": "error",
            "debug_results": "",
            "cua_comments": "",
            "screenshot_paths": screenshot_paths,
            "input_tokens": 0,
            "output_tokens": 0,
            "model": model,
            "duration_seconds": round(duration, 1),
            "error_message": str(e),
        }


async def main():
    parser = argparse.ArgumentParser(description="Single-step CUA executor")
    parser.add_argument("--prompt", required=True, help="The full prompt to send to CUA")
    parser.add_argument("--system-suffix", default="", help="Additional system prompt text")
    parser.add_argument("--context-file", default="/tmp/cua_context.json",
                        help="Path to conversation context file")
    parser.add_argument("--persist-context", action="store_true",
                        help="Carry conversation context from previous step (default: start fresh)")
    parser.add_argument("--output", default="/tmp/step_result.json",
                        help="Path to write the JSON result")
    parser.add_argument("--provider", choices=["anthropic", "gemini"], default="gemini",
                        help="AI provider (default: gemini)")
    args = parser.parse_args()

    # Ensure screenshots directory exists
    screenshots_dir = Path(__file__).parent / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    # Load existing conversation context only if --persist-context is set
    if args.persist_context:
        messages = load_context(args.context_file)
    else:
        messages = []

    # Run the step
    result = await run_step(
        prompt=args.prompt,
        system_suffix=args.system_suffix,
        messages=messages,
        provider_name=args.provider,
        screenshots_dir=screenshots_dir,
    )

    # Save updated conversation context
    save_context(args.context_file, messages)

    # Write result JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary to stderr (stdout stays clean for piping)
    print(f"Step {result['status']}: {result['duration_seconds']}s, "
          f"{result.get('input_tokens', 0):,} in / {result.get('output_tokens', 0):,} out",
          file=sys.stderr)
    if result["error_message"]:
        print(f"Error: {result['error_message']}", file=sys.stderr)

    sys.exit(0 if result["status"] == "done" else 1)


if __name__ == "__main__":
    asyncio.run(main())
