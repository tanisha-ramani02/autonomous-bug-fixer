"""Unit tests for Autonomous Bug Fixer Agent deterministic tools."""
import os
import tempfile
import pytest
from bug_fixer.tools.patcher import Patcher
from bug_fixer.tools.test_runner import TestRunner
from bug_fixer.llm.client import LLMClient


def test_patcher_syntax_validation():
    """Verify patcher catches Python syntax errors before saving."""
    with tempfile.TemporaryDirectory() as tmpdir:
        patcher = Patcher(tmpdir)
        
        valid_code = "def add(a, b):\n    return a + b\n"
        is_valid, err = patcher.validate_python_syntax(valid_code)
        assert is_valid is True
        assert err is None

        invalid_code = "def broken(:\n    return\n"
        is_valid, err = patcher.validate_python_syntax(invalid_code)
        assert is_valid is False
        assert "SyntaxError" in err


def test_patcher_snippet_replacement():
    """Verify patcher replaces target snippet accurately and creates diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = "service.py"
        full_path = os.path.join(tmpdir, test_file)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("def calculate(x):\n    return x // 2\n")

        patcher = Patcher(tmpdir)
        ok, msg, diff = patcher.apply_replacement(
            target_file=test_file,
            original_snippet="return x // 2",
            replacement_snippet="return (x + 1) // 2"
        )
        assert ok is True
        assert "return (x + 1) // 2" in open(full_path).read()
        assert "+    return (x + 1) // 2" in diff


def test_llm_client_json_extraction():
    """Verify robust JSON extraction from markdown fences and raw text."""
    client = LLMClient()
    
    raw_markdown = '```json\n{"hypothesis": "Off by one error", "confidence_score": 0.95}\n```'
    parsed = client.extract_json(raw_markdown)
    assert parsed["hypothesis"] == "Off by one error"
    assert parsed["confidence_score"] == 0.95

    raw_text = 'Here is the diagnosis: {"hypothesis": "Missing await", "confidence_score": 0.90} hope this helps'
    parsed2 = client.extract_json(raw_text)
    assert parsed2["hypothesis"] == "Missing await"


def test_cost_calculation():
    """Verify USD cost computation according to token pricing."""
    client = LLMClient()
    cost = client._calculate_cost("gemini-flash-latest", prompt_tokens=1000, completion_tokens=500)
    assert cost > 0
    assert cost < 0.001
