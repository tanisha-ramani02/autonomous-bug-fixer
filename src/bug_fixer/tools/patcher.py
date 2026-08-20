"""Safe code patching and syntax validation tool."""
import ast
import os
import difflib
from typing import Tuple, Optional
from bug_fixer.config.logger_config import logger


class Patcher:
    """Applies code patches to target repository files with AST syntax pre-validation."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._backups = {}

    def validate_python_syntax(self, code_str: str) -> Tuple[bool, Optional[str]]:
        """Pre-validate that modified code is valid Python syntax before applying."""
        try:
            ast.parse(code_str)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}, offset {e.offset}: {e.msg}"
        except Exception as e:
            return False, f"Invalid code: {str(e)}"

    def apply_replacement(
        self,
        target_file: str,
        original_snippet: str,
        replacement_snippet: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Apply a snippet replacement to a file in the target repo.
        Returns (success, message, unified_diff).
        """
        full_path = os.path.join(self.repo_path, target_file)
        if not os.path.exists(full_path):
            return False, f"Target file does not exist: {target_file}", None

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            current_content = f.read()

        # Backup current content
        self._backups[target_file] = current_content

        # Check if original_snippet is present
        clean_orig = original_snippet.strip()
        if clean_orig not in current_content:
            # Try normalized line endings / whitespace
            norm_current = "\n".join(line.rstrip() for line in current_content.splitlines())
            norm_orig = "\n".join(line.rstrip() for line in clean_orig.splitlines())
            if norm_orig not in norm_current:
                return False, f"Original snippet not found in {target_file}", None
            # Replace using normalized
            new_content = norm_current.replace(norm_orig, replacement_snippet.strip(), 1)
        else:
            new_content = current_content.replace(clean_orig, replacement_snippet.strip(), 1)

        # Pre-validate Python syntax
        if target_file.endswith(".py"):
            is_valid, err = self.validate_python_syntax(new_content)
            if not is_valid:
                logger.warning(f"Patch rejected: Syntax error detected in {target_file}: {err}")
                return False, f"Patch produces invalid Python syntax: {err}", None

        # Generate unified diff
        diff_lines = list(difflib.unified_diff(
            current_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}"
        ))
        diff_str = "".join(diff_lines)

        # Write patch
        with open(full_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)

        logger.info(f"Applied snippet patch to {target_file} ({len(diff_lines)} diff lines)")
        return True, f"Successfully applied patch to {target_file}", diff_str

    def apply_full_file(self, target_file: str, new_content: str) -> Tuple[bool, str, Optional[str]]:
        """Replace full file content with syntax validation."""
        full_path = os.path.join(self.repo_path, target_file)
        if not os.path.exists(full_path):
            logger.error(f"Target file does not exist: {target_file}")
            return False, f"Target file does not exist: {target_file}", None

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            current_content = f.read()

        self._backups[target_file] = current_content

        if target_file.endswith(".py"):
            is_valid, err = self.validate_python_syntax(new_content)
            if not is_valid:
                logger.warning(f"Full file patch rejected: Syntax error in {target_file}: {err}")
                return False, f"Invalid Python syntax: {err}", None

        diff_lines = list(difflib.unified_diff(
            current_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}"
        ))
        diff_str = "".join(diff_lines)

        with open(full_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_content)

        logger.info(f"Applied full file patch to {target_file}")
        return True, f"Successfully updated {target_file}", diff_str

    def restore_backup(self, target_file: str) -> bool:
        """Restore file from in-memory backup."""
        if target_file in self._backups:
            full_path = os.path.join(self.repo_path, target_file)
            with open(full_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self._backups[target_file])
            logger.info(f"Restored in-memory backup for {target_file}")
            return True
        return False
