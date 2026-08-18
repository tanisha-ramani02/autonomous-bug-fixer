"""Code context and AST inspection tool for targeted source retrieval."""
import ast
import os
from typing import Dict, Any, List, Optional


class CodeInspector:
    """Targeted static analysis and file inspection for the target repository."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def read_file(self, relative_path: str) -> str:
        """Read full contents of a file relative to the target repository."""
        full_path = os.path.join(self.repo_path, relative_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {relative_path}")
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
        context: Dict[str, Any] = {
            "test_file": test_file,
            "test_code": "",
            "suspected_source_files": {}
        }

        # 1. Read the test file content
        try:
            test_content = self.read_file(test_file)
            context["test_code"] = test_content
        except Exception:
            pass

        # 2. Extract referenced app/ source files from traceback
        import re
        app_files = re.findall(r"(?:app[/\\][^\s:]+\.py)", traceback_str)
        # Also check imports in test file
        test_imports = re.findall(r"from\s+(app\.[^\s]+)\s+import", context.get("test_code", ""))
        
        for imp in test_imports:
            rel = imp.replace(".", "/") + ".py"
            if os.path.exists(os.path.join(self.repo_path, rel)):
                app_files.append(rel)

        # Normalize paths
        unique_files = list(set([f.replace("\\", "/") for f in app_files]))
        
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
            if ".venv" in root or ".git" in root or "__pycache__" in root:
                continue
            for file in files:
                if file.endswith(".py"):
                    rel = os.path.relpath(os.path.join(root, file), self.repo_path).replace("\\", "/")
                    py_files.append(rel)
        return sorted(py_files)
