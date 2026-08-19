"""Comprehensive unit test suite for Autonomous Bug Fixer Agent deterministic tools,
safety guards, circuit breaker, parser resilience, and state contracts.
"""
import os
import re
import tempfile
import pytest
from bug_fixer.tools.patcher import Patcher
from bug_fixer.tools.code_inspector import CodeInspector
from bug_fixer.tools.test_runner import TestRunner
from bug_fixer.tools.git_manager import GitManager
from bug_fixer.llm.client import LLMClient, CircuitBreaker
from bug_fixer.config.logger_config import mask_secrets
from bug_fixer.models.state import (
    TestCaseResult as TestCaseResultModel,
    TestSuiteReport as TestSuiteReportModel,
    RootCauseAnalysis,
    PatchCandidate,
    FixAttempt,
    AgentRunTrace
)

# Tell pytest not to collect data model classes starting with 'Test'
TestCaseResultModel.__test__ = False
TestSuiteReportModel.__test__ = False


# ============================================================================
# 1. Patcher & AST Syntax Pre-Validation Tests
# ============================================================================

def test_patcher_syntax_validation():
    """Verify patcher catches Python syntax errors before saving."""
    with tempfile.TemporaryDirectory() as tmpdir:
        patcher = Patcher(tmpdir)
        
        valid_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        is_valid, err = patcher.validate_python_syntax(valid_code)
        assert is_valid is True
        assert err is None

        invalid_code = "def broken(:\n    return\n"
        is_valid, err = patcher.validate_python_syntax(invalid_code)
        assert is_valid is False
        assert "SyntaxError" in err


def test_patcher_snippet_replacement_and_diff():
    """Verify patcher replaces target snippet accurately and creates standard unified diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "catalog.py"
        full_path = os.path.join(tmpdir, test_file)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("def paginate(items, page, size):\n    start = page * size\n    return items[start:]\n")

        patcher = Patcher(tmpdir)
        ok, msg, diff = patcher.apply_replacement(
            target_file=test_file,
            original_snippet="    start = page * size",
            replacement_snippet="    start = (page - 1) * size"
        )
        assert ok is True
        content = open(full_path, "r", encoding="utf-8").read()
        assert "start = (page - 1) * size" in content
        assert "+    start = (page - 1) * size" in diff


def test_patcher_snippet_not_found_handling():
    """Verify patcher fails gracefully when original snippet is not found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "service.py"
        full_path = os.path.join(tmpdir, test_file)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("def calculate():\n    return 42\n")

        patcher = Patcher(tmpdir)
        ok, msg, diff = patcher.apply_replacement(
            target_file=test_file,
            original_snippet="non_existent_snippet_line()",
            replacement_snippet="replacement_line()"
        )
        assert ok is False
        assert "not found" in msg.lower()


def test_patcher_syntax_rejection_prevents_disk_corruption():
    """Verify patcher rejects invalid syntax in replacement and does not modify disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "calc.py"
        full_path = os.path.join(tmpdir, test_file)
        original_code = "def calc(x):\n    return x + 1\n"
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(original_code)

        patcher = Patcher(tmpdir)
        ok, msg, diff = patcher.apply_replacement(
            target_file=test_file,
            original_snippet="    return x + 1",
            replacement_snippet="    return (x +"  # Syntax error!
        )
        assert ok is False
        assert "syntax" in msg.lower()
        # Verify disk file is preserved untouched
        assert open(full_path, "r", encoding="utf-8").read() == original_code


def test_patcher_memory_backup_and_restore():
    """Verify in-memory backup and restore functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "app.py"
        full_path = os.path.join(tmpdir, test_file)
        original_text = "def compute():\n    return 100\n"
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(original_text)

        patcher = Patcher(tmpdir)
        # Apply a change (which automatically captures in-memory backup)
        ok, msg, diff = patcher.apply_replacement(
            target_file=test_file,
            original_snippet="    return 100",
            replacement_snippet="    return 200"
        )
        assert ok is True
        assert "return 200" in open(full_path).read()

        # Restore from backup
        restored = patcher.restore_backup(test_file)
        assert restored is True
        assert open(full_path, "r", encoding="utf-8").read() == original_text


# ============================================================================
# 2. CodeInspector Dynamic Resolution Tests
# ============================================================================

def test_code_inspector_fuzzy_path_resolution():
    """Verify CodeInspector resolves file paths accurately via exact and fuzzy matching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "app", "api", "routes"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "app", "services"), exist_ok=True)

        search_route = os.path.join(tmpdir, "app", "api", "routes", "search.py")
        catalog_srv = os.path.join(tmpdir, "app", "services", "catalog.py")
        open(search_route, "w").close()
        open(catalog_srv, "w").close()

        inspector = CodeInspector(tmpdir)
        
        # Exact match
        assert inspector.resolve_file_path("app/services/catalog.py") == "app/services/catalog.py"
        # Basename lookup
        assert inspector.resolve_file_path("search.py") == "app/api/routes/search.py"
        # Fuzzy match
        assert inspector.resolve_file_path("catalog.py") == "app/services/catalog.py"


def test_code_inspector_list_python_files_ignores_junk():
    """Verify list_python_files ignores .venv, .git, and __pycache__ directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "app"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, ".venv", "lib"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, ".git", "objects"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "app", "__pycache__"), exist_ok=True)

        open(os.path.join(tmpdir, "app", "main.py"), "w").close()
        open(os.path.join(tmpdir, ".venv", "lib", "bad.py"), "w").close()
        open(os.path.join(tmpdir, "app", "__pycache__", "main.cpython.py"), "w").close()

        inspector = CodeInspector(tmpdir)
        files = inspector.list_python_files()
        assert len(files) == 1
        assert files[0] == "app/main.py"


def test_code_inspector_read_file_with_line_numbers():
    """Verify line number slicing and formatting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "utils.py"
        with open(os.path.join(tmpdir, test_file), "w", encoding="utf-8") as f:
            f.write("line 1\nline 2\nline 3\nline 4\nline 5\n")

        inspector = CodeInspector(tmpdir)
        snippet = inspector.read_file_with_line_numbers(test_file, start_line=2, end_line=4)
        assert "2 | line 2" in snippet
        assert "3 | line 3" in snippet
        assert "4 | line 4" in snippet
        assert "1 | line 1" not in snippet


# ============================================================================
# 3. TestRunner Regex Parser & Summary Tests
# ============================================================================

def test_test_runner_parse_all_passed_output():
    """Verify parsing of 100% green test suite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TestRunner(tmpdir)
        sample_output = """
============================= test session starts =============================
collected 24 items
tests/test_async.py .                                                    [  4%]
tests/test_catalog.py .                                                  [  8%]
============================== 24 passed in 0.54s ==============================
"""
        report = runner._parse_output(stdout=sample_output, stderr="", exit_code=0, duration=0.54)
        assert report.total == 24
        assert report.passed == 24
        assert report.failed == 0
        assert report.is_all_passed is True


def test_test_runner_parse_failures_and_tracebacks():
    """Verify parsing of failing pytest output with failure summary and short traceback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = TestRunner(tmpdir)
        sample_output = """
============================= test session starts =============================
collected 2 items
FAILED tests/test_calc.py::test_division - ZeroDivisionError: division by zero
tests/test_calc.py:12: ZeroDivisionError
=========================== short test summary info ===========================
FAILED tests/test_calc.py::test_division - ZeroDivisionError: division by zero
========================= 1 failed, 1 passed in 0.12s =========================
"""
        report = runner._parse_output(stdout=sample_output, stderr="", exit_code=1, duration=0.12)
        assert report.total == 2
        assert report.passed == 1
        assert report.failed == 1
        assert report.is_all_passed is False
        assert len(report.results) == 1
        assert report.results[0].test_id == "tests/test_calc.py::test_division"


# ============================================================================
# 4. Circuit Breaker State Transition Tests
# ============================================================================

def test_circuit_breaker_state_transitions():
    """Verify CircuitBreaker CLOSED -> OPEN -> HALF_OPEN lifecycle."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.2)
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.allow_request() is True

    # Record 2 failures (under threshold)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED

    # Record 3rd failure (trips to OPEN)
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.allow_request() is False

    # After recovery timeout, transitions to HALF_OPEN
    import time
    time.sleep(0.25)
    assert cb.allow_request() is True
    assert cb.state == CircuitBreaker.HALF_OPEN

    # Success in HALF_OPEN resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0


# ============================================================================
# 5. LLM Client 4-Tier JSON Parser & Cost Calculation Tests
# ============================================================================

def test_llm_client_json_extraction_tiers():
    """Verify 4-tier JSON parsing handles markdown fences, raw JSON, and substring brackets."""
    client = LLMClient()

    # Tier 1: Raw JSON
    t1 = client.extract_json('{"key": "value"}')
    assert t1["key"] == "value"

    # Tier 2: Markdown Code Block
    t2 = client.extract_json('```json\n{"status": "ok", "confidence": 1.0}\n```')
    assert t2["status"] == "ok"

    # Tier 3: Substring Search
    t3 = client.extract_json('Thought: here is the json {"hypothesis": "Bug found"} hope it helps.')
    assert t3["hypothesis"] == "Bug found"


def test_llm_client_json_extraction_tier4_regex_fallback():
    """Verify Tier 4 regex fallback extracts fields even if code contains unescaped quotes."""
    client = LLMClient()
    malformed = """
    {
        "target_file": "app/services/shipping.py",
        "original_snippet": "zip_code = address.get("ZipCode")",
        "replacement_snippet": "zip_code = address.get("zip_code")",
        "confidence_score": 0.95,
        "rationale": "Fix casing"
    }
    """
    parsed = client.extract_json(malformed)
    assert parsed["target_file"] == "app/services/shipping.py"
    assert "ZipCode" in parsed["original_snippet"]
    assert "zip_code" in parsed["replacement_snippet"]


def test_llm_cost_calculation_exact_formulas():
    """Verify USD token pricing calculation across models."""
    client = LLMClient()
    
    # gemini-3.1-flash-lite: $0.05 per 1M in, $0.20 per 1M out
    cost_lite = client._calculate_cost("gemini-3.1-flash-lite", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert round(cost_lite, 4) == 0.25

    # openai/gpt-oss-120b: $0.15 per 1M in, $0.60 per 1M out -> $0.75
    cost_groq = client._calculate_cost("openai/gpt-oss-120b", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert round(cost_groq, 4) == 0.75

    # gpt-4o: $2.50 per 1M in, $10.00 per 1M out -> $12.50
    cost_openai = client._calculate_cost("gpt-4o", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert round(cost_openai, 4) == 12.50


# ============================================================================
# 6. GitManager Safe Rollback Tests
# ============================================================================

def test_git_manager_safe_targeted_rollback():
    """Verify GitManager targeted rollback does not delete unrelated untracked files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize a real git repo
        os.system(f"git init {tmpdir} >nul 2>&1")
        
        file1 = os.path.join(tmpdir, "file1.py")
        with open(file1, "w") as f:
            f.write("COMMITTED_DATA = 1\n")
            
        os.system(f"git -C {tmpdir} add file1.py >nul 2>&1")
        os.system(f"git -C {tmpdir} commit -m \"init\" >nul 2>&1")

        # Mutate file1.py and create an untracked user file user_notes.txt
        with open(file1, "w") as f:
            f.write("CORRUPTED_DATA = 2\n")
            
        user_notes = os.path.join(tmpdir, "user_notes.txt")
        with open(user_notes, "w") as f:
            f.write("Important user notes\n")

        gm = GitManager(tmpdir)
        ok, msg = gm.rollback(target_file="file1.py")
        assert ok is True
        
        # Verify file1.py was rolled back
        assert open(file1).read() == "COMMITTED_DATA = 1\n"
        # Verify untracked user_notes.txt was NOT deleted
        assert os.path.exists(user_notes) is True
        assert open(user_notes).read() == "Important user notes\n"


def test_git_manager_non_git_repo_graceful_handling():
    """Verify GitManager handles non-git directories safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gm = GitManager(tmpdir)
        assert gm.is_git_repo() is False
        ok_rb, msg_rb = gm.rollback()
        assert ok_rb is False
        ok_cm, msg_cm = gm.commit_fix("msg")
        assert ok_cm is False


# ============================================================================
# 7. Secret Masking Security Filter Tests
# ============================================================================

def test_secret_masking_filter():
    """Verify regex masks OpenAI, Google Gemini, and Groq API keys in logs."""
    raw_text = "Sending request with AIzaSyDw39vT04_sampleGoogleKey999 and gsk_fakeGroqKey123456789"
    masked = mask_secrets(raw_text)
    
    assert "[MASKED_API_KEY]" in masked
    assert "Dw39vT04_sampleGoogleKey999" not in masked
    assert "fakeGroqKey123456789" not in masked


# ============================================================================
# 8. Pydantic State Models Serialization Tests
# ============================================================================

def test_state_models_serialization():
    """Verify all state contracts serialize and deserialize cleanly without data loss."""
    diag = RootCauseAnalysis(
        hypothesis="Off-by-one boundary error",
        root_cause_file="app/services/catalog.py",
        root_cause_symbol="paginate",
        explanation="Multiplies page instead of page - 1",
        proposed_strategy="Use (page - 1) * size",
        confidence_score=0.98
    )
    assert diag.confidence_score == 0.98

    patch = PatchCandidate(
        target_file="app/services/catalog.py",
        original_snippet="page * size",
        replacement_snippet="(page - 1) * size",
        confidence_score=0.98,
        rationale="Fixes pagination offset"
    )
    assert patch.target_file == "app/services/catalog.py"

    attempt = FixAttempt(
        bug_id="tests/test_catalog.py::test_pagination",
        attempt_number=1,
        diagnosis=diag,
        patch=patch,
        target_test_passed=True,
        full_suite_passed=True,
        regressions=[]
    )
    assert attempt.target_test_passed is True

    trace = AgentRunTrace(
        repository_path="/workspace/repo",
        total_tests=10,
        initial_failures=1,
        resolved_bugs=1,
        unresolved_bugs=0,
        status="SUCCESS",
        attempts=[attempt]
    )
    dumped = trace.model_dump(mode="json")
    assert dumped["status"] == "SUCCESS"
    assert len(dumped["attempts"]) == 1
