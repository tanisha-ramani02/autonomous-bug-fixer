"""Coder / Patch Generator agent responsible for generating unified code modifications."""
from typing import Dict, Any
from bug_fixer.llm.client import LLMClient
from bug_fixer.models.state import RootCauseAnalysis, PatchCandidate


CODER_SYSTEM_PROMPT = """You are an expert Principal Python Engineer specializing in writing clean, minimal, robust bug fixes.
Your task is to produce a precise code modification to fix the diagnosed bug.

Rules:
1. Make the MINIMAL change necessary to fix the bug and satisfy API contracts.
2. Preserve existing variable names, function signatures, and unrelated behavior.
3. Ensure the replacement snippet is valid Python syntax and exact match to the original code in the file.
4. For dictionary keys (e.g. headers, addresses), support standard casing robustly (e.g. check both "Authorization" and "authorization", or use case-insensitive dict lookup).
5. If the failure is an AssertionError comparing specific string constants (e.g. CORS headers, status messages, JSON keys), ensure the replacement precisely matches the expected contract value.
6. Output your response strictly in the requested JSON format.
"""

CODER_USER_PROMPT = """You need to patch the file `{target_file}` to fix the following diagnosed issue:

### Diagnosis & Strategy:
- **Hypothesis**: {hypothesis}
- **Explanation**: {explanation}
- **Proposed Strategy**: {proposed_strategy}

### Failing Test & Assertion Context:
{test_context}

### Current Full Content of `{target_file}`:
```python
{file_content}
```

### Prior Failed Fix Attempts (if any):
{prior_attempts}

Please provide the exact original code snippet to replace, and the replacement code snippet.
Make sure `original_snippet` matches EXACT lines from the file content above.

Output a JSON object with EXACTLY the following structure:
```json
{{
    "target_file": "{target_file}",
    "original_snippet": "exact lines of code from the file to replace",
    "replacement_snippet": "the corrected lines of code",
    "confidence_score": 0.95,
    "rationale": "Brief justification of why this fix is safe and complete"
}}
```
"""


class Coder:
    """Agent that generates minimal, targeted patches."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_patch(
        self,
        diagnosis: RootCauseAnalysis,
        target_file_content: str,
        prior_attempts_info: str = "None",
        test_context_info: str = "None"
    ) -> PatchCandidate:
        """Generate a PatchCandidate based on the diagnosis, test assertions, and current file content."""
        prompt = CODER_USER_PROMPT.format(
            target_file=diagnosis.root_cause_file,
            hypothesis=diagnosis.hypothesis,
            explanation=diagnosis.explanation,
            proposed_strategy=diagnosis.proposed_strategy,
            test_context=test_context_info,
            file_content=target_file_content,
            prior_attempts=prior_attempts_info
        )

        raw_resp = self.llm.generate(
            prompt=prompt,
            system_instruction=CODER_SYSTEM_PROMPT,
            temperature=0.1
        )

        data = self.llm.extract_json(raw_resp)
        return PatchCandidate(**data)
