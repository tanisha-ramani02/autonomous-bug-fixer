"""Settings module entrypoint for autonomous-bug-fixer."""
import os
import sys

# Ensure src is in sys.path
src_path = os.path.join(os.path.dirname(__file__), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from bug_fixer.config.settings import settings, Settings

# Export keys and models for direct compatibility
GOOGLE_API_KEY1 = settings.google_api_key1
GOOGLE_API_KEY2 = settings.google_api_key2
GOOGLE_API_KEY3 = settings.google_api_key3

GROQ_API_KEY1 = settings.groq_api_key1
GROQ_API_KEY2 = settings.groq_api_key2
GROQ_API_KEY3 = settings.groq_api_key3

GEMINI_MODEL1 = settings.gemini_model1
GEMINI_MODEL2 = settings.gemini_model2

GROQ_MODEL1 = settings.groq_model1
GROQ_MODEL2 = settings.groq_model2

__all__ = [
    "settings",
    "Settings",
    "GOOGLE_API_KEY1",
    "GOOGLE_API_KEY2",
    "GOOGLE_API_KEY3",
    "GROQ_API_KEY1",
    "GROQ_API_KEY2",
    "GROQ_API_KEY3",
    "GEMINI_MODEL1",
    "GEMINI_MODEL2",
    "GROQ_MODEL1",
    "GROQ_MODEL2",
]
