"""Deterministic test execution and pytest output parser tool."""
import os
import re
import subprocess
import time
from typing import Optional, List
from bug_fixer.config.logger_config import logger
from bug_fixer.models.state import TestCaseResult, TestSuiteReport


class TestRunner:
    """Runs pytest against target repository and parses results into structured models."""
    __test__ = False

    def __init__(self, repo_path: str, timeout_seconds: int = 30):
        self.repo_path = os.path.abspath(repo_path)
        self.timeout_seconds = timeout_seconds

    def run_all_tests(self) -> TestSuiteReport:
        """Execute the entire test suite and return structured report."""
        return self._run_pytest([])

    def run_single_test(self, test_id: str) -> TestSuiteReport:
        """Execute a single targeted test case by its test_id."""
        return self._run_pytest([test_id])

    def _run_pytest(self, extra_args: List[str]) -> TestSuiteReport:
        """Invoke pytest via subprocess in the target repository directory."""
        cmd = ["uv", "run", "pytest", "-v", "--tb=short"] + extra_args
        sub_env = os.environ.copy()
        sub_env.pop("VIRTUAL_ENV", None)
        
        start_time = time.time()
        try:
            process = subprocess.run(
                cmd,
                cwd=self.repo_path,
                env=sub_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_seconds,
                shell=True
            )
            duration = time.time() - start_time
            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            duration = self.timeout_seconds
            stdout = ""
            stderr = f"Pytest execution timed out after {self.timeout_seconds} seconds."
            exit_code = 124
            logger.error(stderr)
        except Exception as e:
            duration = time.time() - start_time
            stdout = ""
            stderr = str(e)
            exit_code = 1
            logger.error(f"Failed to execute pytest: {e}")

        report = self._parse_output(stdout, stderr, exit_code, duration)
        logger.debug(f"Test run completed: {report.passed} passed, {report.failed} failed, {report.errors} errors (exit code: {exit_code}) in {duration:.2f}s")
        return report

    def _parse_output(self, stdout: str, stderr: str, exit_code: int, duration: float) -> TestSuiteReport:
        """Parse pytest console output into structured TestSuiteReport and TestCaseResults."""
        results: List[TestCaseResult] = []
        
        # Support both verbose (tests/test_foo.py::test_bar FAILED) and summary (FAILED tests/test_foo.py::test_bar)
        test_line_regex = re.compile(
            r"^(?:(tests[/\\][^\s:]+\.py::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)|(FAILED|ERROR|PASSED)\s+(tests[/\\][^\s:]+\.py::\S+))",
            re.MULTILINE
        )
        
        seen_test_ids = set()
        for match in test_line_regex.finditer(stdout):
            if match.group(1):
                test_id = match.group(1).replace("\\", "/")
                status_str = match.group(2).lower()
            else:
                status_str = match.group(3).lower()
                test_id = match.group(4).replace("\\", "/")

            if test_id in seen_test_ids:
                continue
            seen_test_ids.add(test_id)
            
            # Extract specific failure snippet for this test if failed
            tb = ""
            msg = ""
            file_p = None
            line_n = None
            
            if status_str in ["failed", "error"]:
                tb, msg, file_p, line_n = self._extract_traceback(stdout, test_id)
            
            results.append(TestCaseResult(
                test_id=test_id,
                status=status_str,
                duration=0.0,
                message=msg,
                traceback=tb,
                file_path=file_p,
                line_number=line_n
            ))

        # Parse summary line e.g. "6 failed, 18 passed in 1.20s"
        passed = 0
        failed = 0
        errors = 0
        
        passed_match = re.search(r"(\d+)\s+passed", stdout)
        if passed_match:
            passed = int(passed_match.group(1))
            
        failed_match = re.search(r"(\d+)\s+failed", stdout)
        if failed_match:
            failed = int(failed_match.group(1))
            
        error_match = re.search(r"(\d+)\s+error", stdout)
        if error_match:
            errors = int(error_match.group(1))

        # If summary was not found, count from results list
        if passed == 0 and failed == 0 and errors == 0 and results:
            passed = sum(1 for r in results if r.status == "passed")
            failed = sum(1 for r in results if r.status == "failed")
            errors = sum(1 for r in results if r.status == "error")

        total = passed + failed + errors

        return TestSuiteReport(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            duration=round(duration, 3),
            results=results,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code
        )

    def _extract_traceback(self, stdout: str, test_id: str):
        """Extract failure traceback, assertion message, and source file line references."""
        # Find test function name
        test_fn = test_id.split("::")[-1]
        
        # Look for section `____ test_name ____`
        pattern = rf"_{{3,}}\s+{re.escape(test_fn)}\s+_{{3,}}(.*?)(?=\n_{{3,}}|\n=+ short test summary info =+|$)"
        match = re.search(pattern, stdout, re.DOTALL)
        
        tb = ""
        msg = ""
        file_path = None
        line_num = None
        
        if match:
            tb = match.group(1).strip()
            # Extract assertion message line (starts with E )
            error_lines = [line.strip() for line in tb.splitlines() if line.strip().startswith("E ")]
            if error_lines:
                msg = " \n ".join(error_lines)
            
            # Extract source file / line reference e.g. tests\test_catalog.py:31: AssertionError
            loc_match = re.search(r"(?:tests[/\\]|app[/\\])([^\s:]+\.py):(\d+):", tb)
            if loc_match:
                file_path = loc_match.group(1).replace("\\", "/")
                line_num = int(loc_match.group(2))
        else:
            tb = stdout[-1500:]  # fallback to tail
            msg = "Test failed. See traceback."

        return tb, msg, file_path, line_num
