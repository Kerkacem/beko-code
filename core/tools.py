#!/usr/bin/env python3
"""
BEKO CODE - Tool Engine
All tools available to the agent: bash, python, web, files, git, skills
"""

import os
import json
import subprocess
import sys
import traceback
import requests
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


class ToolEngine:
    """Unified tool executor for BEKO Agent"""
    
    def __init__(self):
        self.workspace = Path("workspace")
        self.workspace.mkdir(exist_ok=True)
        self.skills_dir = Path("skills")
        self.skills_dir.mkdir(exist_ok=True)
        
        self.tool_map = {
            "bash":        self.bash,
            "python":      self.python_exec,
            "write_file":  self.write_file,
            "read_file":   self.read_file,
            "list_files":  self.list_files,
            "web_search":  self.web_search,
            "web_fetch":   self.web_fetch,
            "git_commit":  self.git_commit,
            "build_skill": self.build_skill,
            "load_skill":  self.load_skill,
            "install":     self.install_package,
            "test":        self.run_tests,
            "delete_file": self.delete_file,
            "done":        lambda x: "Task complete.",
        }
    
    def execute(self, tool: str, inputs: Dict) -> str:
        """Route to correct tool"""
        fn = self.tool_map.get(tool)
        if not fn:
            return f"Unknown tool: {tool}. Available: {list(self.tool_map.keys())}"
        return fn(inputs)
    
    # ----------------------------------------------------------
    # BASH
    # ----------------------------------------------------------
    def bash(self, inputs: Dict) -> str:
        cmd = inputs.get("cmd", inputs.get("command", ""))
        timeout = inputs.get("timeout", 30)
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=str(Path.cwd())
            )
            output = result.stdout + result.stderr
            return output[:3000] if output else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Bash error: {e}"
    
    # ----------------------------------------------------------
    # PYTHON EXECUTOR
    # ----------------------------------------------------------
    def python_exec(self, inputs: Dict) -> str:
        code = inputs.get("code", "")
        if not code:
            return "No code provided"
        
        # Write to temp file and execute
        tmp = Path("_beko_tmp.py")
        tmp.write_text(code)
        try:
            result = subprocess.run(
                [sys.executable, str(tmp)],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout + result.stderr
            return output[:3000] or "(no output)"
        except subprocess.TimeoutExpired:
            return "Python execution timed out"
        except Exception as e:
            return f"Python error: {e}"
        finally:
            tmp.unlink(missing_ok=True)
    
    # ----------------------------------------------------------
    # FILE OPERATIONS
    # ----------------------------------------------------------
    def write_file(self, inputs: Dict) -> str:
        path = inputs.get("path", "")
        content = inputs.get("content", "")
        if not path:
            return "No path provided"
        
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written: {path} ({len(content)} chars)"
    
    def read_file(self, inputs: Dict) -> str:
        path = inputs.get("path", "")
        if not path:
            return "No path provided"
        
        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        
        content = p.read_text(encoding="utf-8", errors="ignore")
        return content[:5000]  # Limit for context
    
    def list_files(self, inputs: Dict) -> str:
        dir_path = inputs.get("path", ".")
        try:
            p = Path(dir_path)
            if not p.exists():
                return f"Directory not found: {dir_path}"
            
            items = []
            for item in sorted(p.iterdir()):
                prefix = "[DIR]" if item.is_dir() else "[FILE]"
                size = item.stat().st_size if item.is_file() else ""
                items.append(f"{prefix} {item.name} {size}")
            
            return "\n".join(items) or "(empty directory)"
        except Exception as e:
            return f"List error: {e}"
    
    def delete_file(self, inputs: Dict) -> str:
        path = inputs.get("path", "")
        try:
            Path(path).unlink(missing_ok=True)
            return f"Deleted: {path}"
        except Exception as e:
            return f"Delete error: {e}"
    
    # ----------------------------------------------------------
    # WEB SEARCH
    # ----------------------------------------------------------
    def web_search(self, inputs: Dict) -> str:
        query = inputs.get("query", "")
        if not query:
            return "No query provided"
        
        try:
            # Use DuckDuckGo Instant Answer API (free, no key)
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            
            results = []
            
            # Abstract
            if data.get("AbstractText"):
                results.append(f"SUMMARY: {data['AbstractText'][:500]}")
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:5]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append(f"- {topic['Text'][:200]}")
            
            if results:
                return "\n".join(results)
            
            # Fallback: search via HTML scraping
            return self._ddg_html_search(query)
            
        except Exception as e:
            return f"Search error: {e}"
    
    def _ddg_html_search(self, query: str) -> str:
        """Fallback HTML search"""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(
                f"https://html.duckduckgo.com/html/?q={query}",
                headers=headers, timeout=10
            )
            # Extract text snippets (simple)
            from html.parser import HTMLParser
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.texts = []
                    self.in_result = False
                def handle_starttag(self, tag, attrs):
                    attrs_dict = dict(attrs)
                    if attrs_dict.get("class") == "result__snippet":
                        self.in_result = True
                def handle_data(self, data):
                    if self.in_result and data.strip():
                        self.texts.append(data.strip())
                        self.in_result = False
            
            parser = TextExtractor()
            parser.feed(resp.text)
            return "\n".join(parser.texts[:5]) or "No results found"
        except Exception as e:
            return f"Fallback search error: {e}"
    
    def web_fetch(self, inputs: Dict) -> str:
        """Fetch content from a URL"""
        url = inputs.get("url", "")
        if not url:
            return "No URL provided"
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=15)
            # Strip HTML tags simply
            text = resp.text
            import re
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:3000]
        except Exception as e:
            return f"Fetch error: {e}"
    
    # ----------------------------------------------------------
    # GIT
    # ----------------------------------------------------------
    def git_commit(self, inputs: Dict) -> str:
        message = inputs.get("message", f"BEKO auto commit {datetime.now().strftime('%Y%m%d-%H%M')}")
        files = inputs.get("files", ".")  # "." = all
        
        cmds = [
            f"git add {files}",
            f'git commit -m "{message}"',
            "git push"
        ]
        
        results = []
        for cmd in cmds:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            results.append(f"{cmd}: {r.stdout or r.stderr}")
        
        return "\n".join(results)
    
    # ----------------------------------------------------------
    # SKILL BUILDER
    # ----------------------------------------------------------
    def build_skill(self, inputs: Dict) -> str:
        """Create a new reusable skill file"""
        name    = inputs.get("name", "")
        code    = inputs.get("code", "")
        desc    = inputs.get("description", "")
        
        if not name or not code:
            return "Need 'name' and 'code'"
        
        skill_path = self.skills_dir / f"{name}.py"
        
        header = f'''# BEKO Skill: {name}
# Description: {desc}
# Created: {datetime.now().isoformat()}
# Auto-generated by BEKO CODE agent

'''
        skill_path.write_text(header + code)
        
        # Auto-generate test
        test_path = Path("tests") / f"test_{name}.py"
        test_path.parent.mkdir(exist_ok=True)
        test_code = f'''import pytest
from skills.{name} import *

def test_{name}_exists():
    assert True  # Skill loaded successfully
'''
        test_path.write_text(test_code)
        
        return f"Skill '{name}' created at {skill_path} with test at {test_path}"
    
    def load_skill(self, inputs: Dict) -> str:
        """Load and execute a skill"""
        name = inputs.get("name", "")
        skill_path = self.skills_dir / f"{name}.py"
        
        if not skill_path.exists():
            available = [f.stem for f in self.skills_dir.glob("*.py")]
            return f"Skill '{name}' not found. Available: {available}"
        
        return self.python_exec({"code": skill_path.read_text()})
    
    # ----------------------------------------------------------
    # PACKAGE INSTALLER
    # ----------------------------------------------------------
    def install_package(self, inputs: Dict) -> str:
        package = inputs.get("package", inputs.get("name", ""))
        if not package:
            return "No package name provided"
        
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "-q"],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout + result.stderr or f"Installed {package}"
    
    # ----------------------------------------------------------
    # TEST RUNNER
    # ----------------------------------------------------------
    def run_tests(self, inputs: Dict) -> str:
        path = inputs.get("path", "tests/")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-v", "--tb=short"],
            capture_output=True, text=True, timeout=60
        )
        return (result.stdout + result.stderr)[:3000]
