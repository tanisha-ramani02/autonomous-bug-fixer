"""Verifier tool implementing dual-phase validation and regression guard."""
from typing import Tuple, List, Optional
from bug_fixer.models.state import TestSuiteReport
from bug_fixer.tools.test_runner import TestRunner


class Verifier:
    """Verifies that a patch resolves the target failure without introducing regressions."""

    def __init__(self, test_runner: TestRunner):
        self.runner = test_runner

    def verify_patch(
        self,
        target_test_id: str,
        initial_passing_tests: List[str]
    ) -> Tuple[bool, bool, List[str], TestSuiteReport, Optional[str]]:
        """
        Two-stage verification:
        Stage 1: Verify the targeted failing test now passes.
        Stage 2: Run full test suite to ensure 0 regressions on previously passing tests.

        Returns: (target_passed, no_regressions, regressions, full_report, error_message)
        """
        # 1. Run targeted test
        target_report = self.runner.run_single_test(target_test_id)
        target_passed = (target_report.failed == 0 and target_report.errors == 0 and target_report.passed > 0)
        
        if not target_passed:
            err_msg = target_report.stdout or target_report.stderr
            return False, False, [], target_report, f"Target test still fails: {err_msg[-400:].strip()}"

        # 2. Run full suite to check for regressions on previously passing tests
        full_report = self.runner.run_all_tests()
        
        # Check if any previously passing test is now failing
        current_failed_ids = [r.test_id for r in full_report.results if r.status in ["failed", "error"]]
        regressions = [tid for tid in current_failed_ids if tid in initial_passing_tests]

        no_regressions = (len(regressions) == 0)
        err_msg = None
        if not no_regressions:
            err_msg = f"Regressions detected in previously passing tests: {', '.join(regressions)}"

        return target_passed, no_regressions, regressions, full_report, err_msg
