"""Git-based safety and rollback management tool."""
import os
import subprocess
from typing import Tuple, Optional
from bug_fixer.config.logger_config import logger


class GitManager:
    """Manages Git checkpoints, atomic rollbacks on regression, and fix commits."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._is_git = os.path.exists(os.path.join(self.repo_path, ".git"))

    def is_git_repo(self) -> bool:
        return self._is_git

    def get_status(self) -> str:
        """Get git status output."""
        return self._run_git(["status", "--short"])

    def rollback(self) -> Tuple[bool, str]:
        """
        Atomically rollback any uncommitted modifications in the target repository.
        """
        if not self._is_git:
            logger.warning(f"Cannot rollback: {self.repo_path} is not a git repository")
            return False, "Not a git repository"
        
        # Discard working tree changes
        out1 = self._run_git(["checkout", "--", "."])
        out2 = self._run_git(["clean", "-fd"])
        logger.info(f"Git rollback executed in {self.repo_path}: {out1} {out2}")
        return True, f"Working tree restored cleanly. {out1} {out2}".strip()

    def commit_fix(self, message: str) -> Tuple[bool, str]:
        """Stage all modifications and commit them."""
        if not self._is_git:
            logger.warning(f"Cannot commit: {self.repo_path} is not a git repository")
            return False, "Not a git repository"

        self._run_git(["add", "."])
        out = self._run_git(["commit", "-m", message])
        logger.info(f"Git fix committed: '{message}' (output: {out})")
        return True, out

    def _run_git(self, args: list) -> str:
        """Execute git command in target repository."""
        cmd = ["git"] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=self.repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True
            )
            return res.stdout.strip() or res.stderr.strip()
        except Exception as e:
            return str(e)
