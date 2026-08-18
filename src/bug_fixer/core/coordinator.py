"""State-machine coordinator orchestrating the full Autonomous Bug Fixer lifecycle."""
import os
import time
from datetime import datetime
from typing import Optional, List

from bug_fixer.config.settings import settings
from bug_fixer.llm.client import LLMClient
from bug_fixer.models.state import (
    AgentRunTrace,
    FixAttempt,
    TestSuiteReport,
    TestCaseResult,
    RootCauseAnalysis,
    PatchCandidate
)
from bug_fixer.tools.test_runner import TestRunner
from bug_fixer.tools.code_inspector import CodeInspector
from bug_fixer.tools.patcher import Patcher
from bug_fixer.tools.git_manager import GitManager
from bug_fixer.core.diagnostician import Diagnostician
from bug_fixer.core.coder import Coder
from bug_fixer.core.verifier import Verifier
from bug_fixer.config.logger_config import logger
from bug_fixer.observability.logger import AgentLogger
from bug_fixer.observability.trace_recorder import TraceRecorder


class Coordinator:
    """Coordinates observation, diagnosis, patching, verification, and rollback loops."""

    def __init__(
        self,
        repo_path: str,
        max_attempts_per_bug: Optional[int] = None,
        max_cost_budget: Optional[float] = None,
        provider: Optional[str] = None,
        verbose: bool = True
    ):
        self.repo_path = os.path.abspath(repo_path)
        self.max_attempts = max_attempts_per_bug or settings.max_attempts_per_bug
        self.max_cost = max_cost_budget or settings.max_cost_budget_usd
        self.provider = provider or settings.primary_provider
        
        # Tools and Agents
        self.logger = AgentLogger(verbose=verbose)
        self.llm_client = LLMClient()
        self.test_runner = TestRunner(self.repo_path, timeout_seconds=settings.subprocess_timeout_seconds)
        self.inspector = CodeInspector(self.repo_path)
        self.patcher = Patcher(self.repo_path)
        self.git_manager = GitManager(self.repo_path)
        
        self.diagnostician = Diagnostician(self.llm_client)
        self.coder = Coder(self.llm_client)
        self.verifier = Verifier(self.test_runner)
        self.trace_recorder = TraceRecorder(self.repo_path)

    def run(self) -> AgentRunTrace:
        """Execute the autonomous bug fixing lifecycle loop."""
        start_time = time.time()
        trace = AgentRunTrace(
            repository_path=self.repo_path,
            start_time=datetime.utcnow()
        )

        self.logger.log_header(self.repo_path, self.provider, self.max_cost)

        # 1. Initial Test Suite Run
        initial_report = self.test_runner.run_all_tests()
        self.logger.log_initial_test_run(initial_report)

        trace.total_tests = initial_report.total
        trace.initial_failures = initial_report.failed + initial_report.errors

        if initial_report.is_all_passed:
            logger.info("All tests passed initially. No bugs detected.")
            self.logger.console.print("[bold green]All tests are already passing! Nothing to fix.[/bold green]")
            trace.status = "SUCCESS"
            trace.end_time = datetime.utcnow()
            trace.token_usage = self.llm_client.tracker
            trace.final_test_report = initial_report
            self.trace_recorder.save_trace(trace)
            return trace

        # Collect initial failing tests and initial passing tests
        failing_tests = [r for r in initial_report.results if r.status in ["failed", "error"]]
        initial_passing_ids = [r.test_id for r in initial_report.results if r.status == "passed"]
        logger.info(f"Target repository has {len(failing_tests)} failing tests to resolve: {[f.test_id for f in failing_tests]}")

        resolved_count = 0
        unresolved_count = 0

        # 2. Iterate through each detected failing test
        for bug_idx, failure in enumerate(failing_tests, 1):
            self.logger.log_bug_start(bug_idx, len(failing_tests), failure.test_id)
            
            # Check cost budget
            if self.llm_client.tracker.total_cost_usd >= self.max_cost:
                logger.warning(f"Budget limit of ${self.max_cost:.2f} reached. Halting investigation.")
                self.logger.console.print(f"[bold red]Budget limit of ${self.max_cost:.2f} reached. Halting.[/bold red]")
                unresolved_count += (len(failing_tests) - bug_idx + 1)
                break

            bug_resolved = False
            prior_attempts_summary: List[str] = []

            for attempt_num in range(1, self.max_attempts + 1):
                logger.info(f"Processing bug [{bug_idx}/{len(failing_tests)}] {failure.test_id} - Attempt {attempt_num}/{self.max_attempts}")
                self.logger.console.print(f"\n[bold cyan]Attempt {attempt_num}/{self.max_attempts} for:[/bold cyan] {failure.test_id}")
                
                # Check budget
                if self.llm_client.tracker.total_cost_usd >= self.max_cost:
                    logger.warning("Cost budget exceeded mid-attempt.")
                    self.logger.console.print(f"[bold red]Budget limit exceeded.[/bold red]")
                    break

                # A. Inspect Code Context
                code_context = self.inspector.get_test_and_source_context(
                    test_file=failure.test_id.split("::")[0],
                    test_id=failure.test_id,
                    traceback_str=failure.traceback or ""
                )
                logger.debug(f"Retrieved code context: test_file={code_context.get('test_file')}, suspected_sources={list(code_context.get('suspected_source_files', {}).keys())}")

                # B. Diagnose Root Cause
                prior_info_str = "\n".join(prior_attempts_summary) if prior_attempts_summary else "None"
                try:
                    diagnosis = self.diagnostician.diagnose(
                        failure=failure,
                        code_context=code_context,
                        prior_attempts_info=prior_info_str
                    )
                    self.logger.log_diagnosis(diagnosis)
                except Exception as e:
                    self.logger.console.print(f"[red]Diagnosis generation error: {e}[/red]")
                    continue

                # C. Read target file content
                try:
                    target_file_content = self.inspector.read_file(diagnosis.root_cause_file)
                except Exception as e:
                    self.logger.console.print(f"[red]Could not read target file {diagnosis.root_cause_file}: {e}[/red]")
                    continue

                # D. Generate Candidate Patch
                try:
                    patch = self.coder.generate_patch(
                        diagnosis=diagnosis,
                        target_file_content=target_file_content,
                        prior_attempts_info=prior_info_str
                    )
                except Exception as e:
                    self.logger.console.print(f"[red]Patch generation error: {e}[/red]")
                    continue

                # E. Apply Patch with Pre-Validation
                apply_ok, apply_msg, diff_str = self.patcher.apply_replacement(
                    target_file=patch.target_file,
                    original_snippet=patch.original_snippet,
                    replacement_snippet=patch.replacement_snippet
                )
                
                # If snippet replacement failed, try full replacement if needed
                if not apply_ok:
                    self.logger.console.print(f"[yellow]Snippet replacement notice: {apply_msg}. Trying full block replacement...[/yellow]")
                    # Replace in content and apply full
                    new_full = target_file_content.replace(patch.original_snippet.strip(), patch.replacement_snippet.strip())
                    if new_full != target_file_content:
                        apply_ok, apply_msg, diff_str = self.patcher.apply_full_file(patch.target_file, new_full)

                if not apply_ok:
                    self.logger.console.print(f"[red]Patch application failed: {apply_msg}[/red]")
                    prior_attempts_summary.append(f"Attempt {attempt_num}: Patch application failed - {apply_msg}")
                    continue

                patch.diff = diff_str
                self.logger.log_patch_candidate(patch, diff_str)

                # F. Verify Patch (Dual-Stage)
                target_pass, no_regressions, regressions, report, err_msg = self.verifier.verify_patch(
                    target_test_id=failure.test_id,
                    initial_passing_tests=initial_passing_ids
                )

                attempt_record = FixAttempt(
                    bug_id=failure.test_id,
                    attempt_number=attempt_num,
                    diagnosis=diagnosis,
                    patch=patch,
                    target_test_passed=target_pass,
                    full_suite_passed=no_regressions,
                    regressions=regressions,
                    error_message=err_msg
                )
                trace.attempts.append(attempt_record)
                self.logger.log_attempt_result(attempt_record)

                if target_pass and no_regressions:
                    # Fix succeeded without regressions!
                    bug_resolved = True
                    resolved_count += 1
                    if settings.auto_git_rollback and self.git_manager.is_git_repo():
                        self.git_manager.commit_fix(f"fix(auto): resolve {failure.test_id}")
                    # Update initial_passing_ids to include newly passing test
                    initial_passing_ids.append(failure.test_id)
                    break
                else:
                    # Fix failed or introduced regressions -> Rollback cleanly
                    self.logger.log_rollback(err_msg or "Verification failed")
                    if self.git_manager.is_git_repo():
                        self.git_manager.rollback()
                    else:
                        self.patcher.restore_backup(patch.target_file)

                    prior_attempts_summary.append(
                        f"Attempt {attempt_num} Failed: target_passed={target_pass}, no_regressions={no_regressions}, error={err_msg}"
                    )

            if not bug_resolved:
                unresolved_count += 1

        # 3. Final Test Suite Run
        final_report = self.test_runner.run_all_tests()
        trace.final_test_report = final_report
        trace.resolved_bugs = resolved_count
        trace.unresolved_bugs = unresolved_count
        trace.end_time = datetime.utcnow()
        trace.token_usage = self.llm_client.tracker
        
        if final_report.is_all_passed:
            trace.status = "SUCCESS"
        elif resolved_count > 0:
            trace.status = "PARTIAL"
        else:
            trace.status = "FAILED"

        # 4. Save Trace and Display Summary
        duration = time.time() - start_time
        trace_file = self.trace_recorder.save_trace(trace)
        self.logger.console.print(f"\n[bold green]📁 Run trace saved to:[/bold green] [cyan]{trace_file}[/cyan]")
        self.logger.log_summary(
            initial_failed=trace.initial_failures,
            resolved=resolved_count,
            unresolved=unresolved_count,
            token_summary=self.llm_client.tracker,
            duration=duration
        )

        return trace
