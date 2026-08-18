"""Code context and AST inspection tool for targeted source retrieval."""
import ast
import os
import re
from typing import Dict, Any, List, Optional
from difflib import get_close_matches


class CodeInspector:
    """Targeted static analysis and file inspection for the target repository."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def resolve_file_path(self, relative_path: str) -> Optional[str]:
        """Resolve a relative file path, with intelligent fuzzy-matching if needed."""
        norm_path = relative_path.replace("\\", "/").strip().lstrip("/")
        full_path = os.path.join(self.repo_path, norm_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            return norm_path

        # Search existing python files in repository
        all_files = self.list_python_files()
        
        # Exact basename match (e.g. schemas.py or search.py)
        req_base = os.path.basename(norm_path)
        for f in all_files:
            if os.path.basename(f) == req_base:
                return f

        # Fuzzy match on relative path or basename
        matches = get_close_matches(norm_path, all_files, n=1, cutoff=0.5)
        if matches:
            return matches[0]

        # Base name fuzzy match (e.g. item.py -> items.py)
        for f in all_files:
            f_base = os.path.splitext(os.path.basename(f))[0]
            req_name = os.path.splitext(req_base)[0]
            if req_name in f_base or f_base in req_name:
                return f

        return None

    def read_file(self, relative_path: str) -> str:
        """Read full contents of a file relative to the target repository with auto-resolution."""
        resolved = self.resolve_file_path(relative_path)
        if not resolved:
            raise FileNotFoundError(f"File not found: {relative_path} (Available files: {self.list_python_files()})")
        
        full_path = os.path.join(self.repo_path, resolved)
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def read_file_with_line_numbers(self, relative_path: str, start_line: int = 1, end_line: Optional[int] = None) -> str:
        """Read specific line slice formatted with line numbers."""
        content = self.read_file(relative_path)
        lines = content.splitlines()
        
        end = end_line if end_line is not None else len(lines)
        start = max(1, start_line)
        end = min(len(lines), end)

        formatted = []
        for i in range(start - 1, end):
            formatted.append(f"{i + 1:4d} | {lines[i]}")
        return "\n".join(formatted)

    def get_test_and_source_context(self, test_file: str, test_id: str, traceback_str: str) -> Dict[str, Any]:
        """
        Dynamically locate and extract the relevant test implementation and suspected source files.
        """
        all_py_files = self.list_python_files()
        context: Dict[str, Any] = {
            "test_file": test_file,
            "test_code": "",
            "available_files": all_py_files,
            "suspected_source_files": {}
        }

        # 1. Read the test file content
        try:
            test_content = self.read_file(test_file)
            context["test_code"] = test_content
        except Exception:
            test_content = ""

        # 2. Extract referenced app/ source files from traceback
        app_files = re.findall(r"(?:app[/\\][^\s:]+\.py)", traceback_str)
        
        # 3. Check direct imports in test file
        test_imports = re.findall(r"from\s+(app\.[^\s]+)\s+import", test_content)
        for imp in test_imports:
            rel = imp.replace(".", "/") + ".py"
            resolved = self.resolve_file_path(rel)
            if resolved:
                app_files.append(resolved)

        # 4. Check API endpoint paths in test (e.g. client.get("/search/?q=...") -> app/api/routes/search.py)
        url_matches = re.findall(r'["\']/(items|search|orders|catalog|reports)/?', test_content)
        for endpoint in url_matches:
            candidate_route = f"app/api/routes/{endpoint}.py"
            resolved = self.resolve_file_path(candidate_route)
            if resolved:
                app_files.append(resolved)
            candidate_service = f"app/services/{endpoint}.py"
            resolved_s = self.resolve_file_path(candidate_service)
            if resolved_s:
                app_files.append(resolved_s)

        # 5. Extract schemas and models if test mentions schemas/models
        if "schemas" in test_content or "schema" in test_content or "create" in test_id:
            for cand in ["app/schemas.py", "app/models.py"]:
                if cand in all_py_files:
                    app_files.append(cand)

        # Normalize and deduplicate
        unique_files = []
        for f in app_files:
            norm = f.replace("\\", "/")
            resolved = self.resolve_file_path(norm)
            if resolved and resolved not in unique_files:
                unique_files.append(resolved)

        # If nothing matched, include relevant app files
        if not unique_files:
            unique_files = [f for f in all_py_files if not f.startswith("tests/")]

        for rel_file in unique_files:
            try:
                content = self.read_file(rel_file)
                context["suspected_source_files"][rel_file] = content
            except Exception:
                pass

        return context

    def list_python_files(self) -> List[str]:
        """List all Python files in the application source tree."""
        py_files = []
        for root, _, files in os.walk(self.repo_path):
            if any(ignore in root for ignore in [".venv", ".git", "__pycache__", "site-packages", ".pytest_cache"]):
                continue
            for file in files:
                if file.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, file), self.repo_path).replace("\\", "/")
                    py_files.append(rel)
        return sorted(py_files)
