#!/usr/bin/env python3
"""
BEKO CODE - Long-Term Memory System
Stores and retrieves relevant context across sessions
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class Memory:
    """Persistent memory for BEKO agent across sessions"""
    
    def __init__(self, memory_file: str = "memory/beko_memory.json"):
        self.path = Path(memory_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
    
    def _load(self) -> Dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except:
                pass
        return {
            "sessions": [],
            "skills_learned": [],
            "errors_seen": [],
            "knowledge_base": {},
            "task_history": []
        }
    
    def _save(self):
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
    
    def save(self, task: str, steps: List[Dict]):
        """Save a completed session to memory"""
        session = {
            "task": task,
            "steps_count": len(steps),
            "actions_used": list(set(s.get("action", "") for s in steps)),
            "timestamp": datetime.now().isoformat(),
            "summary": self._summarize(steps)
        }
        
        self.data["sessions"].append(session)
        self.data["task_history"].append(task)
        
        # Keep last 100 sessions only
        self.data["sessions"] = self.data["sessions"][-100:]
        self.data["task_history"] = self.data["task_history"][-200:]
        
        self._save()
    
    def _summarize(self, steps: List[Dict]) -> str:
        """Create a brief summary of what was done"""
        actions = [s.get("action", "") for s in steps]
        files_written = [
            s.get("input", {}).get("path", "")
            for s in steps if s.get("action") == "write_file"
        ]
        skills_built = [
            s.get("input", {}).get("name", "")
            for s in steps if s.get("action") == "build_skill"
        ]
        
        summary_parts = [f"Actions: {', '.join(set(actions))}"]
        if files_written:
            summary_parts.append(f"Files: {', '.join(filter(None, files_written[:5]))}")
        if skills_built:
            summary_parts.append(f"Skills: {', '.join(filter(None, skills_built))}")
        
        return " | ".join(summary_parts)
    
    def get_relevant(self, task: str, limit: int = 5) -> str:
        """Get relevant context for a new task"""
        if not self.data["sessions"]:
            return "No previous sessions found."
        
        # Simple keyword matching (can be upgraded to embeddings)
        task_words = set(task.lower().split())
        scored = []
        
        for session in self.data["sessions"][-50:]:
            session_words = set(session["task"].lower().split())
            score = len(task_words & session_words)
            if score > 0:
                scored.append((score, session))
        
        scored.sort(reverse=True)
        relevant = [s[1] for s in scored[:limit]]
        
        if not relevant:
            # Return last 3 sessions
            relevant = self.data["sessions"][-3:]
        
        lines = ["### Relevant past sessions:"]
        for s in relevant:
            lines.append(f"- [{s['timestamp'][:10]}] Task: {s['task'][:100]}")
            lines.append(f"  Summary: {s.get('summary', 'N/A')}")
        
        # Add known skills
        skills = [f.stem for f in Path("skills").glob("*.py")] if Path("skills").exists() else []
        if skills:
            lines.append(f"\n### Available skills: {', '.join(skills)}")
        
        return "\n".join(lines)
    
    def add_knowledge(self, key: str, value: str):
        """Store a piece of knowledge"""
        self.data["knowledge_base"][key] = {
            "value": value,
            "timestamp": datetime.now().isoformat()
        }
        self._save()
    
    def get_knowledge(self, key: str) -> Optional[str]:
        """Retrieve stored knowledge"""
        entry = self.data["knowledge_base"].get(key)
        return entry["value"] if entry else None
    
    def log_error(self, error: str, context: str = ""):
        """Remember errors to avoid repeating them"""
        self.data["errors_seen"].append({
            "error": error[:500],
            "context": context[:200],
            "timestamp": datetime.now().isoformat()
        })
        self.data["errors_seen"] = self.data["errors_seen"][-50:]
        self._save()
    
    def get_stats(self) -> Dict:
        """Return memory statistics"""
        return {
            "total_sessions": len(self.data["sessions"]),
            "tasks_done": len(self.data["task_history"]),
            "knowledge_entries": len(self.data["knowledge_base"]),
            "errors_logged": len(self.data["errors_seen"]),
            "skills_in_memory": self.data.get("skills_learned", [])
        }
