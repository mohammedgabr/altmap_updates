import yaml
import os
import re
from typing import List, Dict, Any, Optional

class MimicStep:
    def __init__(self, request_data: Dict[str, Any]):
        self.method = request_data.get("method", "GET").upper()
        self.paths = request_data.get("path", [])
        self.matchers = request_data.get("matchers", [])
        self.raw = request_data.get("raw", [])
        self.extractors = request_data.get("extractors", [])

    def get_response_content(self) -> str:
        # Find a word matcher to mimic
        for matcher in self.matchers:
            if matcher.get("type") == "word" and "words" in matcher:
                return matcher["words"][0]
        return "Target Matched"

class MimicEngine:
    def __init__(self, template_path: str):
        self.template_path = template_path
        self.template_id = ""
        self.steps: List[MimicStep] = []
        self.current_step_index = 0
        self.load_template()

    def load_template(self):
        with open(self.template_path, 'r') as f:
            data = yaml.safe_load(f)
            self.template_id = data.get("id", "unknown")
            
            # Nuclei templates can have 'http' or 'requests'
            requests = data.get("http", []) or data.get("requests", [])
            for req in requests:
                self.steps.append(MimicStep(req))

    def reset(self):
        self.current_step_index = 0

    def get_current_step(self) -> Optional[MimicStep]:
        if self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def process_request(self, method: str, path: str) -> Dict[str, Any]:
        step = self.get_current_step()
        if not step:
            return {"status": 404, "content": "No active step"}

        # Basic path matching (ignoring {{BaseURL}})
        # In a real scenario, we might want to be more precise
        matched = False
        for p in step.paths:
            clean_p = p.replace("{{BaseURL}}", "").split("?")[0]
            if clean_p == path or path.endswith(clean_p):
                matched = True
                break
        
        if matched and method.upper() == step.method:
            content = step.get_response_content()
            self.current_step_index += 1
            return {"status": 200, "content": content, "step": self.current_step_index}
        
        return {"status": 404, "content": f"Path {path} not expected for current step"}

def find_templates(root_dir: str) -> List[Dict[str, str]]:
    templates = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".yaml"):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, 'r') as f:
                        data = yaml.safe_load(f)
                        if "id" in data:
                            templates.append({
                                "id": data["id"],
                                "name": data.get("info", {}).get("name", "Unnamed"),
                                "severity": data.get("info", {}).get("severity", "unknown"),
                                "path": full_path
                            })
                except Exception:
                    continue
    return templates
