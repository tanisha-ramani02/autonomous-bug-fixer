"""CLI Entrypoint for the Autonomous Bug Fixer Agent."""
import argparse
import os
import sys

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure src directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bug_fixer.config.logger_config import logger, setup_logger
from bug_fixer.core.coordinator import Coordinator
from bug_fixer.config.settings import settings


def parse_args():
    parser = argparse.ArgumentParser(
        description="Autonomous Bug Fixer Agent — Closed-loop software bug diagnosis, patching, and verification."
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Path to the target repository containing failing pytest tests."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=settings.primary_provider,
        choices=["gemini", "groq"],
        help="LLM provider to use (default: gemini)."
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Specific model to use (e.g. gemini-flash-latest, llama-3.3-70b-versatile)."
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=settings.max_cost_budget_usd,
        help=f"Maximum LLM cost budget in USD (default: ${settings.max_cost_budget_usd:.2f})."
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=settings.max_attempts_per_bug,
        help=f"Maximum retry attempts per bug (default: {settings.max_attempts_per_bug})."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Enable rich verbose terminal output with diffs."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    target_repo = os.path.abspath(args.repo)
    if not os.path.exists(target_repo):
        print(f"Error: Target repository path does not exist: {target_repo}", file=sys.stderr)
        sys.exit(1)

    if args.model:
        if args.provider == "groq":
            settings.groq_model1 = args.model
        else:
            settings.gemini_model1 = args.model

    # Initialize log directory
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    setup_logger(log_dir=log_dir)
    logger.info(f"Invoking CLI for repository: {target_repo}")

    coordinator = Coordinator(
        repo_path=target_repo,
        max_attempts_per_bug=args.max_retries,
        max_cost_budget=args.budget,
        provider=args.provider,
        verbose=args.verbose
    )

    trace = coordinator.run()
    
    if trace.status == "SUCCESS":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
