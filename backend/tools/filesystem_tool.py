"""
FileSystem Tool - Safe sandboxed file reading for code analysis.
"""

import os
from pathlib import Path

from .registry import BaseTool, ToolResult

# Sandboxed to only read from allowed directories
ALLOWED_BASE_DIRS = [
    os.getenv("CODE_ROOT", "./sample_data"),
    "./docs",
    "./tests",
]
ALLOWED_EXTENSIONS = {".py", ".ts", ".js", ".go", ".java", ".md", ".txt", ".yaml", ".yml", ".json", ".toml"}


class FileSystemTool(BaseTool):
    name = "filesystem"
    description = "Read source code files and search within files (sandboxed to project directories)"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read_file", "list_files", "search_in_files"],
            },
            "path": {"type": "string", "description": "File or directory path"},
            "pattern": {"type": "string", "description": "Search pattern (for search action)"},
            "file_extension": {"type": "string", "description": "Filter by extension (e.g., .py)"},
        },
        "required": ["action"],
    }

    def _is_safe_path(self, path: str) -> bool:
        """Check path is within allowed directories."""
        abs_path = os.path.abspath(path)
        for base in ALLOWED_BASE_DIRS:
            if abs_path.startswith(os.path.abspath(base)):
                return True
        return False

    async def run(self, action: str, path: str = "", pattern: str = "", file_extension: str = "", **kwargs) -> ToolResult:
        if action == "read_file":
            if not path:
                return ToolResult(tool_name=self.name, success=False, data=None, error="path required")
            if not self._is_safe_path(path):
                return ToolResult(tool_name=self.name, success=False, data=None, error="Access denied: path outside sandbox")

            p = Path(path)
            if not p.exists():
                return ToolResult(tool_name=self.name, success=False, data=None, error=f"File not found: {path}")
            if p.suffix not in ALLOWED_EXTENSIONS:
                return ToolResult(tool_name=self.name, success=False, data=None, error=f"File type {p.suffix} not allowed")

            content = p.read_text(encoding="utf-8", errors="replace")
            return ToolResult(tool_name=self.name, success=True, data=content, metadata={"path": path, "size": len(content)})

        elif action == "list_files":
            base = path or ALLOWED_BASE_DIRS[0]
            if not self._is_safe_path(base):
                return ToolResult(tool_name=self.name, success=False, data=None, error="Access denied")

            files = []
            for root, dirs, filenames in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules" and d != "__pycache__"]
                for f in filenames:
                    fp = os.path.join(root, f)
                    ext = Path(f).suffix
                    if not file_extension or ext == file_extension:
                        if ext in ALLOWED_EXTENSIONS:
                            files.append(fp)

            return ToolResult(tool_name=self.name, success=True, data=files[:50])  # Cap at 50

        elif action == "search_in_files":
            if not pattern:
                return ToolResult(tool_name=self.name, success=False, data=None, error="pattern required")

            base = path or ALLOWED_BASE_DIRS[0]
            matches = []
            for root, dirs, filenames in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in filenames:
                    if Path(f).suffix not in ALLOWED_EXTENSIONS:
                        continue
                    fp = os.path.join(root, f)
                    try:
                        content = Path(fp).read_text(encoding="utf-8", errors="replace")
                        for i, line in enumerate(content.splitlines(), 1):
                            if pattern.lower() in line.lower():
                                matches.append({"file": fp, "line": i, "content": line.strip()})
                    except Exception:
                        continue

            return ToolResult(tool_name=self.name, success=True, data=matches[:30])

        return ToolResult(tool_name=self.name, success=False, data=None, error=f"Unknown action: {action}")
