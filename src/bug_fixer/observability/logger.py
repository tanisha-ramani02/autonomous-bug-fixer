"""Observability logger combining Rich live terminal UI and Loguru file persistence."""
from typing import Optional, List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from bug_fixer.config.logger_config import logger
from bug_fixer.models.state import TestSuiteReport, RootCauseAnalysis, PatchCandidate, FixAttempt, TokenCostSummary

console = Console()


class AgentLogger:
    """Provides real-time terminal UI for agent lifecycle events and metrics with file persistence."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.console = console

    def log_header(self, repo_path: str, provider: str, budget: float):
        """Log startup banner."""
        logger.info(f"Starting Autonomous Bug Fixer on repository: {repo_path} | Provider: {provider} | Budget: ${budget:.2f}")
        console.print()
        console.print(Panel(
            f"[bold cyan]Autonomous Bug Fixer Agent[/bold cyan]\n"
            f"[bold]Target Repository:[/bold] [yellow]{repo_path}[/yellow]\n"
            f"[bold]LLM Provider:[/bold] [green]{provider}[/green] | [bold]Budget:[/bold] [green]${budget:.2f}[/green]",
            title="🚀 INITIALIZATION",
            border_style="cyan"
        ))

    def log_initial_test_run(self, report: TestSuiteReport):
        """Display and log initial test suite breakdown."""
        logger.info(f"Initial test execution completed: {report.total} total, {report.passed} passed, {report.failed} failed, {report.errors} errors in {report.duration:.2f}s")
        
        table = Table(title="Initial Test Suite Execution", border_style="bright_blue")
        table.add_column("Total Tests", style="bold")
        table.add_column("Passed", style="green")
        table.add_column("Failed", style="red")
        table.add_column("Duration", style="yellow")

        table.add_row(
            str(report.total),
            str(report.passed),
            str(report.failed + report.errors),
            f"{report.duration:.2f}s"
        )
        console.print(table)

    def log_bug_start(self, bug_index: int, total_bugs: int, test_id: str):
        """Log start of bug investigation."""
        logger.info(f"--- Investigating Bug [{bug_index}/{total_bugs}]: {test_id} ---")
        console.print()
        console.rule(f"[bold yellow]Investigating Bug [{bug_index}/{total_bugs}]: {test_id}[/bold yellow]")

    def log_diagnosis(self, diagnosis: RootCauseAnalysis):
        """Display and log diagnosis hypothesis."""
        logger.info(
            f"Diagnosis for {diagnosis.root_cause_file} ({diagnosis.root_cause_symbol or 'module'}): "
            f"Confidence={diagnosis.confidence_score:.2f} | Hypothesis='{diagnosis.hypothesis}'"
        )
        logger.debug(f"Proposed strategy: {diagnosis.proposed_strategy}")

        text = Text()
        text.append(f"File: {diagnosis.root_cause_file}\n", style="bold cyan")
        if diagnosis.root_cause_symbol:
            text.append(f"Symbol: {diagnosis.root_cause_symbol}\n", style="cyan")
        text.append(f"Confidence: {diagnosis.confidence_score:.0%}\n", style="bold green")
        text.append(f"Hypothesis: {diagnosis.hypothesis}\n", style="yellow")
        text.append(f"Strategy: {diagnosis.proposed_strategy}", style="italic")
        
        console.print(Panel(text, title="🧠 ROOT CAUSE DIAGNOSIS", border_style="yellow"))

    def log_patch_candidate(self, patch: PatchCandidate, diff: Optional[str] = None):
        """Display and log patch candidate."""
        logger.info(f"Generated patch for {patch.target_file} (Confidence: {patch.confidence_score:.2f}) | Rationale: {patch.rationale}")
        if diff:
            logger.debug(f"Patch Diff:\n{diff}")

        console.print(f"[bold blue]Applying Patch to:[/bold blue] [white]{patch.target_file}[/white] (Confidence: {patch.confidence_score:.0%})")
        if diff and self.verbose:
            syntax = Syntax(diff, "diff", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, title="Candidate Unified Diff", border_style="blue"))

    def log_attempt_result(self, attempt: FixAttempt):
        """Display and log outcome of a fix attempt."""
        if attempt.target_test_passed and attempt.full_suite_passed:
            logger.info(f"Fix attempt {attempt.attempt_number} for {attempt.bug_id} SUCCEEDED. 0 regressions.")
            console.print(f"[bold green]✔ Patch Verified![/bold green] Target test passed with 0 regressions.")
        elif attempt.target_test_passed and not attempt.full_suite_passed:
            logger.warning(f"Fix attempt {attempt.attempt_number} for {attempt.bug_id} caused regressions: {attempt.regressions}")
            console.print(f"[bold red]✘ Regression Detected![/bold red] Regressions: {attempt.regressions}")
        else:
            logger.warning(f"Fix attempt {attempt.attempt_number} for {attempt.bug_id} FAILED: {attempt.error_message}")
            console.print(f"[bold red]✘ Fix Failed:[/bold red] {attempt.error_message}")

    def log_rollback(self, reason: str):
        """Display and log rollback event."""
        logger.info(f"Executing rollback: {reason}")
        console.print(f"[bold magenta]↺ Rolling back changes...[/bold magenta] Reason: {reason}")

    def log_summary(self, initial_failed: int, resolved: int, unresolved: int, token_summary: TokenCostSummary, duration: float):
        """Display and log final run summary table."""
        logger.info(
            f"Execution Finished: Initial Failed={initial_failed}, Resolved={resolved}, Unresolved={unresolved}, "
            f"Total LLM Calls={token_summary.calls_count}, Total Tokens={token_summary.total_tokens}, Total Cost=${token_summary.total_cost_usd:.4f}"
        )
        
        console.print()
        table = Table(title="🏁 EXECUTION SUMMARY & AUDIT", border_style="green")
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="cyan")

        table.add_row("Initial Failing Bugs", str(initial_failed))
        table.add_row("Resolved Bugs", f"[green]{resolved}[/green]")
        table.add_row("Unresolved Bugs", f"[red]{unresolved}[/red]")
        table.add_row("Total LLM Calls", str(token_summary.calls_count))
        table.add_row("Prompt Tokens", f"{token_summary.prompt_tokens:,}")
        table.add_row("Completion Tokens", f"{token_summary.completion_tokens:,}")
        table.add_row("Total Tokens", f"{token_summary.total_tokens:,}")
        table.add_row("Total Cost (USD)", f"[bold green]${token_summary.total_cost_usd:.4f}[/bold green]")
        table.add_row("Total Duration", f"{duration:.2f}s")

        console.print(table)
