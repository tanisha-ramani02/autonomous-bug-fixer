"""Pydantic data models representing the agent state, test results, diagnoses, and traces."""
from datetime import datetime
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class TestCaseResult(BaseModel):
    """Represents the execution outcome of a single test case."""
    test_id: str
    status: str  # "passed" | "failed" | "error" | "skipped"
    duration: float = 0.0
    message: Optional[str] = None
    traceback: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None


class TestSuiteReport(BaseModel):
    """Summary of a full or partial test suite execution."""
    total: int
    passed: int
    failed: int
    errors: int = 0
    duration: float
    results: List[TestCaseResult] = []
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0

    @property
    def is_all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.passed > 0


class RootCauseAnalysis(BaseModel):
    """Structured hypothesis produced by the Diagnostician agent."""
    hypothesis: str = Field(description="Summary hypothesis of what caused the bug")
    root_cause_file: str = Field(description="Relative path to the source file where the bug exists")
    root_cause_symbol: Optional[str] = Field(default=None, description="Function or class name containing the bug")
    line_range: Optional[str] = Field(default=None, description="Estimated line range e.g. '15-28'")
    explanation: str = Field(description="In-depth explanation of why the failure occurred")
    proposed_strategy: str = Field(description="Proposed modification to fix the bug without regressions")
    confidence_score: float = Field(default=0.8, ge=0.0, le=1.0)


class PatchCandidate(BaseModel):
    """Proposed code patch produced by the Coder agent."""
    target_file: str
    original_snippet: str
    replacement_snippet: str
    diff: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    rationale: str


class FixAttempt(BaseModel):
    """Record of a single attempt to resolve a specific bug."""
    bug_id: str
    attempt_number: int
    diagnosis: Optional[RootCauseAnalysis] = None
    patch: Optional[PatchCandidate] = None
    target_test_passed: bool = False
    full_suite_passed: bool = False
    regressions: List[str] = []
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TokenCostSummary(BaseModel):
    """Tracks token usage and exact USD expenditures."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    calls_count: int = 0

    def add_usage(self, prompt: int, completion: int, cost: float):
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += (prompt + completion)
        self.total_cost_usd += cost
        self.calls_count += 1


class AgentRunTrace(BaseModel):
    """Audit log capturing the end-to-end execution of the Autonomous Bug Fixer."""
    repository_path: str
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    total_tests: int = 0
    initial_failures: int = 0
    resolved_bugs: int = 0
    unresolved_bugs: int = 0
    status: str = "IN_PROGRESS"  # "SUCCESS" | "PARTIAL" | "FAILED"
    token_usage: TokenCostSummary = Field(default_factory=TokenCostSummary)
    attempts: List[FixAttempt] = []
    final_test_report: Optional[TestSuiteReport] = None
