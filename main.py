"""Root main.py entrypoint redirecting to bug_fixer CLI."""
import sys
import os

# Add src to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from bug_fixer.main import main

if __name__ == "__main__":
    main()
