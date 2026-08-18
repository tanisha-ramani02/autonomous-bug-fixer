"""Trace recorder that saves complete execution audit trails to JSON."""
import json
import os
from datetime import datetime
from bug_fixer.models.state import AgentRunTrace


class TraceRecorder:
    """Serializes execution trace into structured JSON format."""

    def __init__(self, output_dir: str = "."):
        self.output_dir = os.path.abspath(output_dir)

    def save_trace(self, trace: AgentRunTrace, filename: str = "run_trace.json") -> str:
        """Save AgentRunTrace to json file."""
        os.makedirs(self.output_dir, exist_ok=True)
        file_path = os.path.join(self.output_dir, filename)
        
        # Serialize model to json dict
        data = trace.model_dump(mode="json")
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        return file_path
