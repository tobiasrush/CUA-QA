"""
CUA QA Test Runner
Executes test scripts defined in YAML format using Claude's Computer Use API.
"""

import asyncio
import os
import sys
import json
import base64
import time
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
    screenshot_paths: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0
    state_before: str = ""
    state_after: str = ""
    test_name: str = ""
    grouping: str = ""


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

    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        self.api_key = api_key
        self.model = model
        self.provider = APIProvider.ANTHROPIC
        self.screenshots_dir = Path("screenshots")
        self.reports_dir = Path("reports")
        self.screenshots_dir.mkdir(exist_ok=True)
        self.reports_dir.mkdir(exist_ok=True)
        self.current_step_screenshots: list[str] = []
        self.current_step_id: str = ""
        # Conversation context carried across steps within a test
        self.messages: list[BetaMessageParam] = []

    def load_test(self, test_path: str) -> dict:
        """Load a test script from YAML file."""
        with open(test_path, 'r') as f:
            return yaml.safe_load(f)

    async def run_test(self, test_input, verbose: bool = True) -> TestResult:
        """Run a complete test from a YAML file path or a pre-built test dict."""
        if isinstance(test_input, dict):
            test_config = test_input
        else:
            test_config = self.load_test(test_input)

        test_name = test_config.get('name', Path(test_input).stem if isinstance(test_input, str) else 'unnamed')
        platform = test_config.get('platform', 'browser')
        grouping = test_config.get('grouping', '')
        steps = test_config.get('steps', [])

        result = TestResult(
            name=test_name,
            platform=platform,
            start_time=datetime.now().isoformat()
        )

        # Reset conversation context for this test
        self.messages = []

        if verbose:
            print(f"\n{'='*60}")
            print(f"Running Test: {test_name}")
            print(f"Platform: {platform}")
            print(f"Steps: {len(steps)}")
            print(f"{'='*60}\n")

        for i, step in enumerate(steps, 1):
            action = step.get('action', '')
            expected = step.get('expected', '')
            state_before = step.get('state_before', '')
            state_after = step.get('state_after', '')

            if verbose:
                print(f"\n[Step {i}/{len(steps)}]")
                print(f"  Action: {action}")
                if state_before:
                    print(f"  Precondition: {state_before}")
                print(f"  Expected: {expected}")
                if state_after:
                    print(f"  Postcondition: {state_after}")

            step_result = await self.run_step(i, action, expected, verbose,
                                              state_before=state_before, state_after=state_after)
            step_result.test_name = test_name
            step_result.grouping = grouping
            result.steps.append(step_result)

            if verbose:
                status_icon = "PASS" if step_result.status == 'pass' else "FAIL"
                print(f"  Result: {status_icon}")
                print(f"  Duration: {step_result.duration_seconds:.1f}s")
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

    async def run_step(self, step_num: int, action: str, expected: str, verbose: bool = True,
                       state_before: str = "", state_after: str = "") -> StepResult:
        """Run a single test step, carrying conversation context from prior steps."""
        self.current_step_id = f"step_{step_num}_{datetime.now().strftime('%H%M%S')}"
        self.current_step_screenshots = []
        screenshot_counter = 0
        step_start = time.monotonic()

        # Build the prompt for this step
        prompt_parts = [f"Execute this test step and verify the result:\n\nACTION: {action}"]

        if state_before:
            prompt_parts.append(f"PRECONDITION: {state_before}")

        prompt_parts.append(f"\nAfter completing the action, verify if the following expected result is true:\nEXPECTED OUTCOME: {expected}")

        if state_after:
            prompt_parts.append(f"POSTCONDITION: {state_after}")

        prompt_parts.append(
            "\nFirst, take a screenshot to see the current state. Then perform the action.\n"
            "After performing the action, take another screenshot and evaluate if the expected result is visible/true.\n\n"
            "Respond with your assessment in this format:\n"
            "- VERIFICATION: PASS or FAIL\n"
            "- OBSERVATION: What you actually observed"
        )

        prompt = "\n".join(prompt_parts)

        # Append to existing conversation context (not a fresh list)
        self.messages.append({"role": "user", "content": prompt})

        collected_output = []

        def output_callback(content_block):
            if hasattr(content_block, 'type') and content_block.type == "text":
                text = content_block.text
                collected_output.append(text)
                if verbose:
                    print(f"    Claude: {text[:100]}..." if len(text) > 100 else f"    Claude: {text}")
            elif isinstance(content_block, dict) and content_block.get("type") == "text":
                text = content_block.get("text", "")
                collected_output.append(text)
                if verbose:
                    print(f"    Claude: {text[:100]}..." if len(text) > 100 else f"    Claude: {text}")

        def tool_output_callback(result: ToolResult, tool_use_id: str):
            nonlocal screenshot_counter
            if result.base64_image:
                screenshot_counter += 1
                screenshot_path = self.screenshots_dir / f"{self.current_step_id}_{screenshot_counter}.png"
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(result.base64_image))
                self.current_step_screenshots.append(str(screenshot_path))
                if verbose:
                    print(f"    Screenshot saved: {screenshot_path}")
            if result.output and verbose:
                print(f"    Tool output: {result.output[:80]}..." if len(result.output) > 80 else f"    Tool output: {result.output}")
            if result.error:
                print(f"    Tool error: {result.error}")

        def api_response_callback(response: APIResponse[BetaMessage]):
            pass

        try:
            # Pass the accumulated messages — sampling_loop mutates in place
            await sampling_loop(
                model=self.model,
                provider=self.provider,
                system_prompt_suffix="You are a QA testing agent. Execute actions precisely and verify results accurately.",
                messages=self.messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=self.api_key,
                only_n_most_recent_images=10,
                max_tokens=4096,
            )

            step_duration = time.monotonic() - step_start

            # Parse verification from Claude's output
            full_output = " ".join(collected_output)
            if "VERIFICATION: PASS" in full_output.upper():
                verification_result = "pass"
            elif "VERIFICATION: FAIL" in full_output.upper():
                verification_result = "fail"
            else:
                verification_result = "fail"  # Default to FAIL when unclear

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
                screenshot_paths=list(self.current_step_screenshots),
                duration_seconds=step_duration,
                state_before=state_before,
                state_after=state_after,
            )

        except Exception as e:
            step_duration = time.monotonic() - step_start
            return StepResult(
                step_number=step_num,
                action=action,
                expected=expected,
                status="error",
                error_message=str(e),
                screenshot_paths=list(self.current_step_screenshots),
                duration_seconds=step_duration,
                state_before=state_before,
                state_after=state_after,
            )

    def generate_report(self, result: TestResult) -> str:
        """Generate an HTML report for the test results."""
        template = Template(HTML_REPORT_TEMPLATE)

        report_filename = f"report_{result.name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_path = self.reports_dir / report_filename

        # Convert screenshots to base64 for embedding in HTML
        for step in result.steps:
            step.screenshots_base64 = []
            for spath in step.screenshot_paths:
                if Path(spath).exists():
                    with open(spath, 'rb') as f:
                        step.screenshots_base64.append(base64.b64encode(f.read()).decode())

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
        .step-duration { color: #888; font-size: 13px; }
        .screenshots { margin-top: 15px; }
        .screenshots-grid { display: flex; gap: 10px; flex-wrap: wrap; }
        .screenshots-grid .screenshot-item { flex: 1; min-width: 300px; }
        .screenshots-grid .screenshot-item img { max-width: 100%; border: 1px solid #ddd; border-radius: 8px; }
        .screenshots-grid .screenshot-item .screenshot-label { font-size: 11px; color: #888; margin-bottom: 4px; }
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
                    <span class="step-duration">({{ "%.1f"|format(step.duration_seconds) }}s)</span>
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
                {% if step.screenshots_base64 %}
                <div class="screenshots">
                    <label style="font-weight: 600; color: #666; font-size: 12px; text-transform: uppercase; display: block; margin-bottom: 8px;">Screenshots</label>
                    <div class="screenshots-grid">
                        {% for screenshot_b64 in step.screenshots_base64 %}
                        <div class="screenshot-item">
                            <div class="screenshot-label">{% if loop.first %}Before{% elif loop.last and not loop.first %}After{% else %}During ({{ loop.index }}){% endif %}</div>
                            <img src="data:image/png;base64,{{ screenshot_b64 }}" alt="Step {{ step.step_number }} screenshot {{ loop.index }}">
                        </div>
                        {% endfor %}
                    </div>
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
    import argparse

    parser = argparse.ArgumentParser(description="CUA QA Test Runner")
    parser.add_argument("test_file", nargs="?", help="YAML test file path")
    parser.add_argument("--sheet", metavar="SHEET_ID", help="Google Sheet ID to load tests from")
    parser.add_argument("--test", metavar="TEST_NAME", help="Run a single test by name (requires --sheet)")
    parser.add_argument("--group", metavar="GROUP_NAME", help="Run all tests in a group (requires --sheet)")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    parser.add_argument("--dry-run", action="store_true", help="List tests without executing CUA")
    args = parser.parse_args()

    if not args.sheet and not args.test_file:
        parser.print_help()
        sys.exit(1)

    # Sheets mode
    if args.sheet:
        from sheets_loader import load_tests_from_sheet, write_results_to_sheet

        print(f"Loading tests from Google Sheet: {args.sheet}")
        all_tests = load_tests_from_sheet(args.sheet)
        print(f"Found {len(all_tests)} tests")

        # Filter by --test or --group
        if args.test:
            tests = [t for t in all_tests if t["name"] == args.test]
            if not tests:
                print(f"Error: No test found with name '{args.test}'")
                print("Available tests:")
                for t in all_tests:
                    print(f"  [{t['grouping']}] {t['name']}")
                sys.exit(1)
        elif args.group:
            tests = [t for t in all_tests if t["grouping"] == args.group]
            if not tests:
                print(f"Error: No tests found in group '{args.group}'")
                print("Available groups:")
                groups = sorted(set(t["grouping"] for t in all_tests))
                for g in groups:
                    count = sum(1 for t in all_tests if t["grouping"] == g)
                    print(f"  {g} ({count} tests)")
                sys.exit(1)
        else:
            tests = all_tests

        # Dry run — just list tests
        if args.dry_run:
            print(f"\nDry run — {len(tests)} tests would be executed:\n")
            for i, t in enumerate(tests, 1):
                step = t["steps"][0]
                print(f"  {i}. [{t['grouping']}] {t['name']}")
                print(f"     Action: {step['action']}")
                print(f"     Expected: {step['expected']}")
                if step.get("state_before"):
                    print(f"     Precondition: {step['state_before']}")
                if step.get("state_after"):
                    print(f"     Postcondition: {step['state_after']}")
                print()
            sys.exit(0)

        # Run tests
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable not set")
            sys.exit(1)

        runner = TestRunner(api_key)
        all_results = []
        sheet_results = []

        for test_config in tests:
            result = await runner.run_test(test_config)
            all_results.append(result)

            # Collect results for writing back to sheet
            for step in result.steps:
                sheet_results.append({
                    "grouping": step.grouping,
                    "test_name": step.test_name,
                    "expected": step.expected,
                    "actual": step.actual or step.error_message or "",
                })

            if args.report:
                report_path = runner.generate_report(result)
                print(f"Report generated: {report_path}")

        # Write results back to Google Sheet
        if sheet_results:
            rows_written = write_results_to_sheet(args.sheet, sheet_results)
            print(f"\nWrote {rows_written} result(s) to Google Sheet Results tab")

        # Exit with appropriate code
        any_failed = any(r.status != "pass" for r in all_results)
        sys.exit(1 if any_failed else 0)

    # YAML mode (existing behavior)
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable not set")
            sys.exit(1)

        test_path = args.test_file
        if not Path(test_path).exists():
            print(f"Error: Test file not found: {test_path}")
            sys.exit(1)

        runner = TestRunner(api_key)
        result = await runner.run_test(test_path)

        if args.report:
            report_path = runner.generate_report(result)
            print(f"\nReport generated: {report_path}")

        sys.exit(0 if result.status == "pass" else 1)


if __name__ == "__main__":
    asyncio.run(main())
