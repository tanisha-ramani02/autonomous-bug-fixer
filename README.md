# Autonomous Bug Fixer Agent

An autonomous agentic engineering system that observes failing tests, diagnoses root causes, generates precision patches, validates syntax, verifies fixes against regressions, and recovers gracefully on errors.

---

## Architecture Overview
```text
                    ┌─────────────────────────┐
                    │       Coordinator       │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       ┌──────────────────┐            ┌───────────────────┐
       │   TestRunner     │            │   CodeInspector   │
       │ (Subprocess/AST) │            │ (Targeted Context)│
       └─────────┬────────┘            └─────────┬─────────┘
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │      Diagnostician      │
                    │  (Root Cause Analysis)  │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │      Coder Agent        │
                    │  (Diff & Confidence)    │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   Patcher / Validator   │
                    │   (AST Syntax Check)    │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │        Verifier         │
                    │  (Dual-Stage & Regress) │
                    └────────────┬────────────┘
                                 │
                   Pass? ────────┴──────── Fail?
                     │                      │
                     ▼                      ▼
           ┌──────────────────┐   ┌──────────────────┐
           │   Git Commit     │   │   Git Rollback   │
           │  & Next Failure  │   │     & Retry      │
           └──────────────────┘   └──────────────────┘
```

---

## Features
- **Deterministic Tools vs. LLM Reasoning**: Fast, reliable subprocess test running, AST inspection, and git rollback coupled with targeted LLM reasoning.
- **Multi-Provider Key Rotation**: Seamless failover across Gemini and Groq API keys.
- **Zero Regressions**: Dual-stage verification runs the target failing test first, followed by the complete test suite.
- **Observability**: Live Rich console UI with diff inspection, token accounting, and serializable `run_trace.json`.
- **Generalization**: Zero hard-coded bug rules or file paths. Operates dynamically on any Python repository with pytest.

---

## Setup & Installation

### Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- `uv` package manager (`pip install uv` or via standalone installer)

### Installation
```bash
cd autonomous-bug-fixer
uv sync
```

### Environment Configuration (`.env`)
Create a `.env` file in `autonomous-bug-fixer/`:
```env
# Gemini Configuration (Supported)
GOOGLE_API_KEY1=your_gemini_api_key
GOOGLE_API_KEY2=optional_backup_gemini_key

# Groq Configuration (Optional)
GROQ_API_KEY1=your_groq_api_key

# Default Settings
GEMINI_MODEL1=gemini-flash-latest
PRIMARY_PROVIDER=gemini
MAX_ATTEMPTS_PER_BUG=3
MAX_COST_BUDGET_USD=5.00
AUTO_GIT_ROLLBACK=true
```

---

## Execution Guide

### Run against the target testbed repository:
```bash
uv run python main.py --repo ../buggy-repo-python-fastapi --verbose
```

### Options:
- `--repo <path>`: Path to the target repository (required).
- `--provider <gemini|groq>`: Choose LLM provider (default: `gemini`).
- `--budget <float>`: Dollar spend ceiling (default: `$5.00`).
- `--max-retries <int>`: Maximum retry attempts per bug (default: `3`).
- `--verbose`: Render live terminal diffs and diagnostic panels.

---

## Running Agent Unit Tests
```bash
uv run pytest -v
```
