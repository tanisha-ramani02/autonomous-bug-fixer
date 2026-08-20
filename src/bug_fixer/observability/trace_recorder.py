"""Trace recorder that saves complete execution audit trails to JSON."""
import json
import os
from datetime import datetime
from bug_fixer.models.state import AgentRunTrace


class TraceRecorder:
    """Serializes execution trace into structured JSON format with repository name and timestamps."""

    def __init__(self, output_dir: str = "."):
        self.output_dir = os.path.abspath(output_dir)

    def save_trace(self, trace: AgentRunTrace, filename: str = "run_trace.json") -> str:
        """Save AgentRunTrace to json file with timestamped and named copies."""
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Determine repository base name and timestamp
        repo_name = os.path.basename(os.path.normpath(trace.repository_path)) or "repo"
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Primary named file: run_trace_{repo_name}_{timestamp}.json
        named_filename = f"run_trace_{repo_name}_{ts}.json"
        named_path = os.path.join(self.output_dir, named_filename)
        standard_path = os.path.join(self.output_dir, filename)
        
        # Serialize model to json dict
        data = trace.model_dump(mode="json")
        
        with open(named_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            
        with open(standard_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        return named_path
