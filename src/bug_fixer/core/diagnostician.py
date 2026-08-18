"""Diagnostician agent responsible for root-cause localization and fix strategy."""
from typing import Dict, Any, Optional
from bug_fixer.llm.client import LLMClient
from bug_fixer.models.state import TestCaseResult, RootCauseAnalysis


DIAGNOSIS_SYSTEM_PROMPT = """You are an expert Python Diagnostician and Software Bug Investigator.
Your task is to analyze failing pytest test outputs, stacktraces, and target source code to identify the exact root cause of a software bug.

Strict Guidelines:
1. Do NOT guess blindly. Base your diagnosis strictly on the stacktrace, assertion message, and code context.
2. Identify the EXACT file (e.g. app/services/catalog.py) and function/class where the bug is planted.
3. Formulate a clear, actionable fix strategy that will resolve the failing test without breaking any existing functionality.
4. Output your response strictly in the requested JSON format.
"""

DIAGNOSIS_USER_PROMPT = """Analyze the following test failure and repository context:

### Failing Test ID:
{test_id}

### Assertion Error Message:
{error_message}

### Traceback:
```text
{traceback}
```

### Relevant Test Code:
```python
{test_code}
```

### Suspected Source Files in Repository:
{source_files_context}

### Prior Failed Attempts for this Bug (if any):
{prior_attempts}

Output a JSON object with EXACTLY the following structure:
```json
{{
    "hypothesis": "Concise summary of the root cause flaw",
    "root_cause_file": "relative/path/to/buggy_file.py",
    "root_cause_symbol": "function_or_class_name",
    "line_range": "approximate line range like 10-25",
    "explanation": "Detailed explanation of why the failure occurs",
    "proposed_strategy": "Concrete step-by-step instructions on what to change in the code",
    "confidence_score": 0.95
}}
```
"""


class Diagnostician:
    """Agent that performs root cause analysis on test failures."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def diagnose(
        self,
        failure: TestCaseResult,
        code_context: Dict[str, Any],
        prior_attempts_info: str = "None"
    ) -> RootCauseAnalysis:
        """Diagnose root cause from test failure and targeted code context."""
        # Format source files context
        source_context_parts = []
        for file_path, content in code_context.get("suspected_source_files", {}).items():
            source_context_parts.append(f"--- File: {file_path} ---\n{content}\n")
        
        sources_str = "\n".join(source_context_parts) if source_context_parts else "No specific source file identified in traceback."

        prompt = DIAGNOSIS_USER_PROMPT.format(
            test_id=failure.test_id,
            error_message=failure.message or "Assertion failed",
            traceback=failure.traceback or "No traceback",
            test_code=code_context.get("test_code", "Not available")[:2500],
            source_files_context=sources_str[:6000],
            prior_attempts=prior_attempts_info
        )

        raw_resp = self.llm.generate(
            prompt=prompt,
            system_instruction=DIAGNOSIS_SYSTEM_PROMPT,
            temperature=0.1
        )

        data = self.llm.extract_json(raw_resp)
        return RootCauseAnalysis(**data)
