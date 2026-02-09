"""
CUA QA Test Runner
Executes test scripts defined in YAML format using Claude's Computer Use API.
"""

import asyncio
import os
import sys
import json
import base64
import yaml
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from jinja2 import Template
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / ".env")

from computer_use_demo.loop import sampling_loop, APIProvider
from computer_use_demo.tools import ToolResult
from anthropic.types.beta import BetaMessage, BetaMessageParam
from anthropic import APIResponse


@dataclass
class StepResult:
    """Result of a single test step."""
    step_number: int
    action: str
    expected: str
    status: str  # 'pass', 'fail', 'error'
    actual: str = ""
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TestResult:
    """Result of a complete test run."""
    name: str
    platform: str
    start_time: str
    end_time: str = ""
    status: str = "running"  # 'pass', 'fail', 'error'
    steps: list[StepResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == 'pass')

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == 'fail')

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.steps if s.status == 'error')


class TestRunner:
    """Runs CUA QA tests from YAML test scripts."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self.provider = APIProvider.ANTHROPIC
        self.screenshots_dir = Path("screenshots")
        self.reports_dir = Path("reports")
        self.screenshots_dir.mkdir(exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)
        self.current_screenshot: Optional[str] = None
        self.current_step_id: str = ""

    def load_test(self, test_path: str) -> dict:
        """Load a test script from YAML file."""
        with open(test_path, 'r') as f:
            return yaml.safe_load(f)

    async def run_test(self, test_path: str, verbose: bool = True) -> TestResult:
        """Run a complete test from a YAML file."""
        test_config = self.load_test(test_path)
        test_name = test_config.get('name', Path(test_path).stem)
        platform = test_config.get('platform', 'browser')
        steps = test_config.get('steps', [])

        result = TestResult(
            name=test_name,
            platform=platform,
            start_time=datetime.now().isoformat()
        )

        if verbose:
            print(f"\n{'='*60}")
            print(f"Running Test: {test_name}")
            print(f"Platform: {platform}")
            print(f"Steps: {len(steps)}")
            print(f"{'='*60}\n")

        for i, step in enumerate(steps, 1):
            action = step.get('action', '')
            expected = step.get('expected', '')

            if verbose:
                print(f"\n[Step {i}/{len(steps)}]")
                print(f"  Action: {action}")
                print(f"  Expected: {expected}")

            step_result = await self.run_step(i, action, expected, verbose)
            result.steps.append(step_result)

            if verbose:
                status_icon = "✓" if step_result.status == 'pass' else "✗"
                print(f"  Result: {status_icon} {step_result.status.upper()}")
                if step_result.error_message:
                    print(f"  Error: {step_result.error_message}")

        result.end_time = datetime.now().isoformat()
        result.status = 'pass' if result.failed_count == 0 and result.error_count == 0 else 'fail'

        if verbose:
            print(f"\n{'='*60}")
            print(f"Test Complete: {result.status.upper()}")
            print(f"  Passed: {result.passed_count}/{len(result.steps)}")
            print(f"  Failed: {result.failed_count}/{len(result.steps)}")
            print(f"  Errors: {result.error_count}/{len(result.steps)}")
            print(f"{'='*60}\n")

        return result

    async def run_step(self, step_num: int, action: str, expected: str, verbose: bool = True) -> StepResult:
        """Run a single test step."""
        self.current_step_id = f"step_{step_num}_{datetime.now().strftime('%H%M%S')}"
        self.current_screenshot = None

        # Build the prompt for Claude
        prompt = f"""Execute this test step and verify the result:

ACTION: {action}

After completing the action, verify if the following expected result is true:
EXPECTED: {expected}

First, take a screenshot to see the current state. Then perform the action.
After performing the action, take another screenshot and evaluate if the expected result is visible/true.

Respond with your assessment in this format:
- VERIFICATION: PASS or FAIL
- OBSERVATION: What you actually observed
"""

        messages: list[BetaMessageParam] = [
            {"role": "user", "content": prompt}
        ]

        collected_output = []
        verification_result = None
        observation = ""

        def output_callback(content_block):
            if isinstance(content_block, dict) and content_block.get("type") == "text":
                text = content_block.get("text", "")
                collected_output.append(text)
                if verbose:
                    print(f"    Claude: {text[:100]}..." if len(text) > 100 else f"    Claude: {text}")

        def tool_output_callback(result: ToolResult, tool_use_id: str):
            if result.base64_image:
                screenshot_path = self.screenshots_dir / f"{self.current_step_id}.png"
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(result.base64_image))
                self.current_screenshot = str(screenshot_path)
                if verbose:
                    print(f"    Screenshot saved: {screenshot_path}")
            if result.output and verbose:
                print(f"    Tool output: {result.output[:80]}..." if len(result.output) > 80 else f"    Tool output: {result.output}")
            if result.error:
                print(f"    Tool error: {result.error}")

        def api_response_callback(response: APIResponse[BetaMessage]):
            pass  # Suppress API response output

        try:
            await sampling_loop(
                model=self.model,
                provider=self.provider,
                system_prompt_suffix="You are a QA testing agent. Execute actions precisely and verify results accurately.",
                messages=messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=self.api_key,
                only_n_most_recent_images=5,
                max_tokens=4096,
            )

            # Parse verification from Claude's output
            full_output = " ".join(collected_output)
            if "VERIFICATION: PASS" in full_output.upper():
                verification_result = "pass"
            elif "VERIFICATION: FAIL" in full_output.upper():
                verification_result = "fail"
            else:
                verification_result = "pass"  # Default to pass if not explicitly stated

            # Extract observation
            if "OBSERVATION:" in full_output.upper():
                obs_start = full_output.upper().find("OBSERVATION:")
                observation = full_output[obs_start + 12:].strip()
            else:
                observation = full_output[:200] if full_output else "No observation recorded"

            return StepResult(
                step_number=step_num,
                action=action,
                expected=expected,
                status=verification_result,
                actual=observation,
                screenshot_path=self.current_screenshot
            )

        except Exception as e:
            return StepResult(
                step_number=step_num,
                action=action,
                expected=expected,
                status="error",
                error_message=str(e),
                screenshot_path=self.current_screenshot
            )

    def generate_report(self, result: TestResult) -> str:
        """Generate an HTML report for the test results."""
        template = Template(HTML_REPORT_TEMPLATE)

        report_filename = f"report_{result.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_path = self.reports_dir / report_filename

        # Convert screenshots to base64 for embedding in HTML
        for step in result.steps:
            if step.screenshot_path and Path(step.screenshot_path).exists():
                with open(step.screenshot_path, 'rb') as f:
                    step.screenshot_base64 = base64.b64encode(f.read()).decode()
            else:
                step.screenshot_base64 = None

        html_content = template.render(result=result)

        with open(report_path, 'w') as f:
            f.write(html_content)

        return str(report_path)


HTML_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CUA QA Report - {{ result.name }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #1a1a2e; color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; }
        .header h1 { font-size: 24px; margin-bottom: 10px; }
        .header .meta { color: #888; font-size: 14px; }
        .summary { display: flex; gap: 20px; margin-bottom: 20px; }
        .summary-card { flex: 1; background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .summary-card.pass { border-left: 4px solid #22c55e; }
        .summary-card.fail { border-left: 4px solid #ef4444; }
        .summary-card.error { border-left: 4px solid #f59e0b; }
        .summary-card .count { font-size: 36px; font-weight: bold; }
        .summary-card .label { color: #666; font-size: 14px; }
        .step { background: white; border-radius: 10px; margin-bottom: 15px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .step-header { padding: 15px 20px; display: flex; align-items: center; gap: 15px; border-bottom: 1px solid #eee; }
        .step-number { background: #1a1a2e; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; }
        .step-status { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; text-transform: uppercase; }
        .step-status.pass { background: #dcfce7; color: #166534; }
        .step-status.fail { background: #fee2e2; color: #991b1b; }
        .step-status.error { background: #fef3c7; color: #92400e; }
        .step-body { padding: 20px; }
        .step-detail { margin-bottom: 10px; }
        .step-detail label { font-weight: 600; color: #666; font-size: 12px; text-transform: uppercase; display: block; margin-bottom: 4px; }
        .step-detail p { color: #333; }
        .screenshot { margin-top: 15px; }
        .screenshot img { max-width: 100%; border: 1px solid #ddd; border-radius: 8px; }
        .overall-status { text-align: center; padding: 20px; font-size: 18px; }
        .overall-status.pass { color: #22c55e; }
        .overall-status.fail { color: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ result.name }}</h1>
            <div class="meta">
                Platform: {{ result.platform }} |
                Started: {{ result.start_time }} |
                Ended: {{ result.end_time }}
            </div>
        </div>

        <div class="summary">
            <div class="summary-card pass">
                <div class="count">{{ result.passed_count }}</div>
                <div class="label">Passed</div>
            </div>
            <div class="summary-card fail">
                <div class="count">{{ result.failed_count }}</div>
                <div class="label">Failed</div>
            </div>
            <div class="summary-card error">
                <div class="count">{{ result.error_count }}</div>
                <div class="label">Errors</div>
            </div>
        </div>

        {% for step in result.steps %}
        <div class="step">
            <div class="step-header">
                <div class="step-number">{{ step.step_number }}</div>
                <div style="flex: 1;">
                    <strong>{{ step.action }}</strong>
                </div>
                <div class="step-status {{ step.status }}">{{ step.status }}</div>
            </div>
            <div class="step-body">
                <div class="step-detail">
                    <label>Expected</label>
                    <p>{{ step.expected }}</p>
                </div>
                <div class="step-detail">
                    <label>Actual Result</label>
                    <p>{{ step.actual or step.error_message or 'N/A' }}</p>
                </div>
                {% if step.screenshot_base64 %}
                <div class="screenshot">
                    <label>Screenshot</label>
                    <img src="data:image/png;base64,{{ step.screenshot_base64 }}" alt="Step {{ step.step_number }} screenshot">
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}

        <div class="overall-status {{ result.status }}">
            Overall Result: <strong>{{ result.status.upper() }}</strong>
        </div>
    </div>
</body>
</html>
"""


async def main():
    """Main entry point for the test runner."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Get your API key from https://console.anthropic.com/settings/keys")
        sys.exit(1)

    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python test_runner.py <test_file.yaml> [--report]")
        print("       python test_runner.py tests/example_test.yaml --report")
        sys.exit(1)

    test_path = sys.argv[1]
    generate_report = "--report" in sys.argv

    if not Path(test_path).exists():
        print(f"Error: Test file not found: {test_path}")
        sys.exit(1)

    runner = TestRunner(api_key)
    result = await runner.run_test(test_path)

    if generate_report:
        report_path = runner.generate_report(result)
        print(f"\nReport generated: {report_path}")

    # Exit with appropriate code
    sys.exit(0 if result.status == 'pass' else 1)


if __name__ == "__main__":
    asyncio.run(main())
