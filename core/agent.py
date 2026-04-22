#!/usr/bin/env python3
"""
BEKO CODE - Core Agent Engine
ReAct (Reasoning + Acting) Loop - Unlimited Steps
Self-improving, web-searching, error-recovering autonomous agent
"""

import os
import json
import time
import traceback
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from groq import Groq

from core.tools import ToolEngine
from core.memory import Memory

# ============================================================
# CONFIG
# ============================================================
class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    MODEL_FAST   = "llama-3.1-8b-instant"        # Quick reasoning
    MODEL_SMART  = "llama-3.3-70b-versatile"     # Deep thinking
    MODEL_CODE   = "llama-3.3-70b-versatile"     # Code generation
    MAX_STEPS    = 50                             # Unlimited in production
    MAX_RETRIES  = 3
    WORKSPACE    = Path("workspace")
    LOGS_DIR     = Path("logs")
    SKILLS_DIR   = Path("skills")
    MEMORY_FILE  = Path("memory/beko_memory.json")

    def __post_init__(self):
        self.WORKSPACE.mkdir(exist_ok=True)
        self.LOGS_DIR.mkdir(exist_ok=True)
        self.SKILLS_DIR.mkdir(exist_ok=True)
        Path("memory").mkdir(exist_ok=True)

cfg = Config()

# ============================================================
# SYSTEM PROMPT - The Brain
# ============================================================
SYSTEM_PROMPT = """
You are BEKO CODE - an elite autonomous AI agent more powerful than Claude Code.

Your capabilities:
- Execute bash commands and Python code
- Read, write, create, delete any file
- Search the web for latest information
- Fix your own errors automatically
- Build new skills and tools for yourself
- Run tests and validate your work
- Git commit and push changes
- Install packages as needed

You operate in a ReAct loop:
1. THINK: Analyze the task deeply
2. ACT: Use a tool
3. OBSERVE: Read the result
4. REFLECT: Did it work? If not, why?
5. REPEAT until task is 100% complete

ALWAYS respond with valid JSON:
{
  "thought": "Your deep reasoning here",
  "action": "tool_name",
  "action_input": {"param": "value"},
  "status": "working" | "done" | "error"
}

Available tools:
- bash: Run any shell command
- python: Execute Python code
- write_file: Write content to file
- read_file: Read file content
- web_search: Search the internet
- git_commit: Commit and push changes
- build_skill: Create a new reusable skill
- list_files: List directory contents
- install: Install Python packages
- test: Run pytest on a file

If you hit an error: think why -> fix -> retry. Never give up.
Always verify your work before marking as done.
"""

# ============================================================
# REACT ENGINE
# ============================================================
class BekoAgent:
    def __init__(self, task: str = "", session_id: str = ""):
        if not cfg.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set")
        
        self.client   = Groq(api_key=cfg.GROQ_API_KEY)
        self.tools    = ToolEngine()
        self.memory   = Memory()
        self.task     = task
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.steps    = []
        self.logs     = []
        self.errors   = []
        self.skills_built = []
        
        # Load task from file if not provided
        if not self.task:
            goal_file = Path("goal.txt")
            if goal_file.exists():
                self.task = goal_file.read_text().strip()
            else:
                self.task = "Analyze the project, find improvements, and implement them."
        
        self._log(f"BEKO CODE started | Task: {self.task}")

    def _log(self, msg: str, level: str = "INFO"):
        entry = f"[{datetime.now().strftime('%H:%M:%S')}][{level}] {msg}"
        print(entry)
        self.logs.append(entry)
        
        # Persist logs
        log_file = cfg.LOGS_DIR / f"session_{self.session_id}.log"
        with open(log_file, "a") as f:
            f.write(entry + "\n")

    def _think(self, messages: List[Dict]) -> Dict:
        """Call LLM with retry logic"""
        for attempt in range(cfg.MAX_RETRIES):
            try:
                resp = self.client.chat.completions.create(
                    model=cfg.MODEL_SMART,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4096,
                )
                raw = resp.choices[0].message.content.strip()
                
                # Extract JSON from response
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                
                return json.loads(raw)
            except json.JSONDecodeError as e:
                self._log(f"JSON parse error (attempt {attempt+1}): {e}", "WARN")
                if attempt == cfg.MAX_RETRIES - 1:
                    return {"thought": "Parse error", "action": "bash", 
                            "action_input": {"cmd": "echo 'retry'"}, "status": "working"}
            except Exception as e:
                self._log(f"LLM error (attempt {attempt+1}): {e}", "ERROR")
                time.sleep(2 ** attempt)
        
        return {"thought": "LLM unavailable", "action": "done", 
                "action_input": {}, "status": "error"}

    def _execute(self, action: str, action_input: Dict) -> str:
        """Execute tool and return result"""
        try:
            result = self.tools.execute(action, action_input)
            return str(result)[:3000]  # Truncate for context window
        except Exception as e:
            err = f"Tool error [{action}]: {traceback.format_exc()}"
            self._log(err, "ERROR")
            self.errors.append(err)
            return err

    def run(self) -> Dict:
        """Main ReAct loop"""
        self._log(f"Starting ReAct loop | Max steps: {cfg.MAX_STEPS}")
        
        # Load relevant memories
        context = self.memory.get_relevant(self.task)
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {self.task}\n\nContext from memory:\n{context}"}
        ]
        
        for step in range(cfg.MAX_STEPS):
            self._log(f"Step {step+1}/{cfg.MAX_STEPS}")
            
            # Think
            decision = self._think(messages)
            thought = decision.get("thought", "")
            action  = decision.get("action", "bash")
            inputs  = decision.get("action_input", {})
            status  = decision.get("status", "working")
            
            self._log(f"THOUGHT: {thought}")
            self._log(f"ACTION: {action} | INPUT: {inputs}")
            
            # Check if done
            if status == "done" or action == "done":
                self._log("Task completed successfully!")
                break
            
            # Execute
            observation = self._execute(action, inputs)
            self._log(f"OBSERVATION: {observation[:200]}")
            
            # Track skill building
            if action == "build_skill":
                self.skills_built.append(inputs.get("name", ""))
            
            # Update conversation
            messages.append({"role": "assistant", "content": json.dumps(decision)})
            messages.append({"role": "user", "content": f"Observation: {observation}"})
            
            # Save step
            self.steps.append({
                "step": step+1,
                "thought": thought,
                "action": action,
                "input": inputs,
                "observation": observation,
                "timestamp": datetime.now().isoformat()
            })
            
            # Auto-save progress
            if step % 5 == 0:
                self._save_session()
        
        # Final save
        result = self._save_session()
        self.memory.save(self.task, self.steps)
        return result

    def _save_session(self) -> Dict:
        """Save session results"""
        result = {
            "session_id": self.session_id,
            "task": self.task,
            "steps_count": len(self.steps),
            "steps": self.steps,
            "skills_built": self.skills_built,
            "errors": self.errors,
            "timestamp": datetime.now().isoformat()
        }
        
        # Save to files
        Path("session_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Update plan.json for compatibility
        Path("plan.json").write_text(json.dumps({
            "task": self.task,
            "steps": len(self.steps),
            "last_action": self.steps[-1]["action"] if self.steps else "",
            "skills_built": self.skills_built
        }, indent=2))
        
        return result


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    agent = BekoAgent(task=task)
    result = agent.run()
    print(f"\n=== BEKO CODE DONE ===")
    print(f"Steps: {result['steps_count']}")
    print(f"Skills built: {result['skills_built']}")
    print(f"Errors: {len(result['errors'])}")
