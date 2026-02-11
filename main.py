import argparse
import asyncio
import os
import sys
import json
import base64
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / ".env")

from computer_use_demo.loop import sampling_loop, APIProvider
from computer_use_demo.tools import ToolResult
from anthropic.types.beta import BetaMessage, BetaMessageParam
from anthropic import APIResponse


async def main():
    parser = argparse.ArgumentParser(description="CUA Computer Use Agent")
    parser.add_argument("instruction", nargs="*", default=["Save an image of a cat to the desktop."],
                        help="Instruction for the agent")
    parser.add_argument("--provider", choices=["anthropic", "gemini"], default="anthropic",
                        help="AI provider (default: anthropic)")
    args = parser.parse_args()

    instruction = " ".join(args.instruction)

    # Select API key and model based on provider
    if args.provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set")
            sys.exit(1)
        from computer_use_demo.gemini_loop import GEMINI_MODEL
        model = GEMINI_MODEL
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
        if api_key == "YOUR_API_KEY_HERE":
            raise ValueError(
                "Please first set your API key in the ANTHROPIC_API_KEY environment variable"
            )
        model = "claude-opus-4-6"

    print(
        f"Starting Computer Use ({args.provider}).\nModel: {model}\nPress ctrl+c to stop.\nInstructions: '{instruction}'"
    )

    # Set up the initial messages
    messages = [
        {
            "role": "user",
            "content": instruction,
        }
    ]

    # Define callbacks
    def output_callback(content_block):
        if hasattr(content_block, "type") and content_block.type == "text":
            print("Assistant:", content_block.text if hasattr(content_block, "text") else "")
        elif isinstance(content_block, dict) and content_block.get("type") == "text":
            print("Assistant:", content_block.get("text"))

    def tool_output_callback(result: ToolResult, tool_use_id: str):
        if result.output:
            print(f"> Tool Output [{tool_use_id}]:", result.output)
        if result.error:
            print(f"!!! Tool Error [{tool_use_id}]:", result.error)
        if result.base64_image:
            os.makedirs("screenshots", exist_ok=True)
            with open(f"screenshots/screenshot_{tool_use_id}.png", "wb") as f:
                f.write(base64.b64decode(result.base64_image))
            print(f"Took screenshot screenshot_{tool_use_id}.png")

    def api_response_callback(response: APIResponse[BetaMessage]):
        print(
            "\n---------------\nAPI Response:\n",
            json.dumps(json.loads(response.text)["content"], indent=4),
            "\n",
        )

    # Run the appropriate sampling loop
    if args.provider == "gemini":
        from computer_use_demo.gemini_loop import sampling_loop_gemini
        messages, token_usage = await sampling_loop_gemini(
            model=model,
            system_prompt_suffix="",
            messages=messages,
            output_callback=output_callback,
            tool_output_callback=tool_output_callback,
            api_key=api_key,
        )
    else:
        messages, token_usage = await sampling_loop(
            model=model,
            provider=APIProvider.ANTHROPIC,
            system_prompt_suffix="",
            messages=messages,
            output_callback=output_callback,
            tool_output_callback=tool_output_callback,
            api_response_callback=api_response_callback,
            api_key=api_key,
            only_n_most_recent_images=10,
            max_tokens=4096,
        )

    from test_runner import calculate_cost
    cost = calculate_cost(token_usage["input_tokens"], token_usage["output_tokens"], token_usage["model"])
    print(f"\nToken usage: {token_usage['input_tokens']:,} in / {token_usage['output_tokens']:,} out (${cost:.4f})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Encountered Error:\n{e}")
