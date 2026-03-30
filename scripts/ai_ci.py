#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys


def run_command(
    command: list[str],
    description: str,
    continue_on_failure: bool = False,
    env: dict | None = None,
) -> bool:
    """Runs a command and prints a compressed summary if it fails."""
    print(f"🚀 Running {description}...")
    try:
        # Use a pseudo-terminal or just capture output to avoid interactive prompts
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=env if env else os.environ.copy(),
        )

        if result.returncode == 0:
            print(f"✅ {description} passed.")
            # If it's ruff, maybe mention if it fixed anything?
            # For now, just keep it quiet.
            return True
        else:
            print(f"❌ {description} failed (exit code {result.returncode}).")
            output = (result.stdout + "\n" + result.stderr).strip()
            if not output:
                print("   (No output captured)")
                return False

            lines = output.splitlines()

            # Special handling for different tools to keep it "AI friendly"
            if "pytest" in command:
                process_pytest_failure(lines)
            elif "ruff" in command:
                process_ruff_failure(lines)
            else:
                process_generic_failure(lines)

            return continue_on_failure
    except Exception as e:  # noqa: BLE001
        print(f"💥 Error running {description}: {e}")
        return False


def process_pytest_failure(lines: list[str]):
    """Compresses pytest output to show only relevant failures."""
    print("   [Compressed Pytest Output]")
    failure_mode = False
    captured_lines = []

    for line in lines:
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            print(f"   {line}")
        if "=== FAILURES ===" in line or "=== ERRORS ===" in line:
            failure_mode = True
        if failure_mode:
            captured_lines.append(line)

    if captured_lines:
        if len(captured_lines) > 40:
            print("   [Truncated Failure Detail]")
            for line in captured_lines[:20]:
                print(f"   {line}")
            print("   ...")
            for line in captured_lines[-10:]:
                print(f"   {line}")
        else:
            for line in captured_lines:
                print(f"   {line}")
    else:
        # If we didn't find the FAILURES section, just show the last 20 lines
        print("   [Recent output lines]")
        for line in lines[-20:]:
            print(f"   {line}")


def process_ruff_failure(lines: list[str]):
    """Compresses ruff output."""
    print("   [Compressed Ruff Output]")
    # Ruff usually outputs one line per error if not using --fix
    if len(lines) > 30:
        for line in lines[:15]:
            print(f"   {line}")
        print(f"   ... ({len(lines) - 25} more errors truncated) ...")
        for line in lines[-10:]:
            print(f"   {line}")
    else:
        for line in lines:
            print(f"   {line}")


def process_generic_failure(lines: list[str]):
    """Generic failure compressor."""
    if len(lines) > 30:
        print("   [Showing first 15 lines of failure]")
        for line in lines[:15]:
            print(f"   {line}")
        print("   ...")
        print("   [Showing last 10 lines of failure]")
        for line in lines[-10:]:
            print(f"   {line}")
    else:
        for line in lines:
            print(f"   {line}")


def main():
    parser = argparse.ArgumentParser(description="AI-friendly CI checks")
    parser.add_argument("--int", action="store_true", help="Run integration checks")
    args = parser.parse_args()

    # Change to project root if script is run from elsewhere
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)

    # Add local deps and src to environment
    deps_dir = os.path.join(project_root, "deps")
    os.path.join(project_root, "src")

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = "./tmp/pycache"

    # Update PATH to include deps/bin
    deps_bin = os.path.join(deps_dir, "bin")
    env["PATH"] = f"{deps_bin}:{env.get('PATH', '')}"

    def get_bin(name):
        # Some are in bin, some are in root of deps
        bin_path = os.path.join(deps_bin, name)
        if not os.path.exists(bin_path):
            bin_path = os.path.join(deps_dir, name)
        return bin_path

    steps = [
        (["uv", "sync", "--extra", "dev"], "uv sync", False),
        (
            [
                "uv",
                "run",
                "ruff",
                "format",
                "--no-cache",
                "--exclude",
                "deps,.venv,.worktrees,.worktrees.bak",
                ".",
            ],
            "ruff format",
            True,
        ),
        (
            [
                "uv",
                "run",
                "ruff",
                "check",
                "--no-cache",
                "--fix",
                "--unsafe-fixes",
                "--exclude",
                "deps,.venv,.worktrees,.worktrees.bak",
                ".",
            ],
            "ruff check",
            True,
        ),
        (["uv", "run", "ty", "check"], "type check", True),
        (
            [
                "uv",
                "run",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-o",
                "cache_dir=./tmp/pytest_cache",
                "--ignore",
                "deps",
                "--ignore",
                ".worktrees",
                "--disable-warnings",
                "--tb=short",
            ],
            "pytest",
            False,
        ),
    ]

    if args.int:
        steps.append(
            (
                ["uv", "run", "python", "scripts/check_integration_workflow.py"],
                "integration checks",
                False,
            )
        )

    print("🤖 Starting AI-friendly CI checks...")
    overall_success = True
    for cmd, desc, can_continue in steps:
        step_success = run_command(cmd, desc, can_continue, env=env)
        if not step_success:
            overall_success = False
            if not can_continue:
                print(f"\n🛑 Stopping CI due to critical failure in {desc}.")
                break

    if overall_success:
        print("\n✨ All AI CI checks passed!")
        sys.exit(0)
    else:
        print("\n❌ AI CI checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
