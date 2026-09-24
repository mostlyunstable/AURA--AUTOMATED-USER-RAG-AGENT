"""Forge adapter implementations."""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.infrastructure.forge.interfaces import (
    ForgeContextProvider,
    ForgeFile,
    ForgeFileReference,
    ForgeIndexer,
    ForgeRepositoryInfo,
    ForgeSearchResult,
    ForgeSymbol,
)


class StubForgeContextProvider(ForgeContextProvider):
    """Stub Forge context provider for testing/local development.

    This provides a minimal implementation that reads directly from the filesystem
    when Forge is not available. In production, this should be replaced with
    a real Forge integration.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self._workspace_root_str = workspace_root or os.getenv(
            "AURA_WORKSPACE_ROOT", "/tmp"
        )

    @property
    def _workspace_root(self) -> str:
        """Get workspace root as non-optional string."""
        return self._workspace_root_str or os.getenv("AURA_WORKSPACE_ROOT") or "/tmp"

    async def health_check(self) -> bool:
        return os.path.exists(self._workspace_root)

    async def get_repository_info(
        self, repository_id: str
    ) -> Optional[ForgeRepositoryInfo]:
        repo_path = os.path.join(self._workspace_root, repository_id)
        if not os.path.exists(repo_path):
            return None

        # Count files and lines
        total_files = 0
        total_lines = 0
        languages = set()
        for root, _, files in os.walk(repo_path):
            for f in files:
                if f.startswith("."):
                    continue
                total_files += 1
                ext = os.path.splitext(f)[1].lower()
                if ext in (
                    ".py",
                    ".js",
                    ".ts",
                    ".go",
                    ".rs",
                    ".java",
                    ".cpp",
                    ".c",
                    ".h",
                ):
                    languages.add(ext[1:])
                try:
                    with open(os.path.join(root, f), "r") as fh:
                        total_lines += len(fh.readlines())
                except Exception:
                    pass

        return ForgeRepositoryInfo(
            repository_id=repository_id,
            name=repository_id,
            default_branch="main",
            languages=list(languages),
            total_files=total_files,
            total_lines=total_lines,
            last_indexed=datetime.utcnow(),
        )

    async def search_semantic(
        self,
        query: str,
        repository_id: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ForgeSearchResult]:
        # Fallback to lexical search
        return await self.search_lexical(
            query,
            repository_id,
            limit,
            filters.get("file_patterns") if filters else None,
        )

    async def search_lexical(
        self,
        query: str,
        repository_id: str,
        limit: int = 20,
        file_patterns: Optional[List[str]] = None,
    ) -> List[ForgeSearchResult]:
        repo_path = os.path.join(self._workspace_root, repository_id)
        if not os.path.exists(repo_path):
            return []

        results = []
        query_lower = query.lower()
        patterns = file_patterns or [
            "*.py",
            "*.js",
            "*.ts",
            "*.go",
            "*.rs",
            "*.java",
            "*.md",
            "*.txt",
        ]

        import fnmatch

        for root, _, files in os.walk(repo_path):
            for f in files:
                if any(fnmatch.fnmatch(f, p) for p in patterns):
                    file_path = os.path.join(root, f)
                    rel_path = os.path.relpath(file_path, repo_path)
                    try:
                        with open(file_path, "r") as fh:
                            content = fh.read()
                    except Exception:
                        continue

                    # Simple line-by-line search
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            results.append(
                                ForgeSearchResult(
                                    file=ForgeFile(
                                        path=rel_path,
                                        content=content,
                                        language=self._detect_language(rel_path),
                                        size_bytes=len(content),
                                        sha256=self._hash(content),
                                    ),
                                    symbols=[],
                                    references=[
                                        ForgeFileReference(
                                            file_path=rel_path,
                                            symbol_name="",
                                            line=i + 1,
                                            context=line.strip()[:200],
                                        )
                                    ],
                                    relevance_score=1.0,
                                    match_type="lexical",
                                )
                            )
                            if len(results) >= limit:
                                return results
        return results

    async def search_symbols(
        self,
        symbol_name: str,
        repository_id: str,
        symbol_kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[ForgeSearchResult]:
        # Simple implementation - search for symbol name in code
        return await self.search_lexical(
            symbol_name, repository_id, limit, ["*.py", "*.js", "*.ts", "*.go", "*.rs"]
        )

    async def get_file_content(
        self, repository_id: str, file_path: str, branch: Optional[str] = None
    ) -> Optional[ForgeFile]:
        repo_path = os.path.join(self._workspace_root, repository_id)
        full_path = os.path.join(repo_path, file_path)
        if not os.path.exists(full_path):
            return None

        try:
            with open(full_path, "r") as f:
                content = f.read()
        except Exception:
            return None

        return ForgeFile(
            path=file_path,
            content=content,
            language=self._detect_language(file_path),
            size_bytes=len(content),
            sha256=self._hash(content),
        )

    async def get_symbol_references(
        self,
        symbol_name: str,
        repository_id: str,
        file_path: Optional[str] = None,
    ) -> List[ForgeFileReference]:
        results = await self.search_lexical(symbol_name, repository_id, 100)
        return [
            ForgeFileReference(
                file_path=r.file.path,
                symbol_name=symbol_name,
                line=r.references[0].line if r.references else 1,
                context=r.references[0].context if r.references else "",
            )
            for r in results
        ]

    async def get_dependencies(
        self, file_path: str, repository_id: str, depth: int = 1
    ) -> Dict[str, List[str]]:
        # Simple import extraction for Python files
        file = await self.get_file_content(repository_id, file_path)
        if not file or file.language != "python":
            return {"imports": [], "imported_by": []}

        imports = []
        for line in file.content.split("\n"):
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                imports.append(line)

        return {"imports": imports, "imported_by": []}

    async def get_callers(
        self, symbol_name: str, file_path: str, repository_id: str
    ) -> List[ForgeFileReference]:
        # Simple grep for function calls
        results = await self.search_lexical(f"{symbol_name}(", repository_id, 50)
        return [
            ForgeFileReference(
                file_path=r.file.path,
                symbol_name=symbol_name,
                line=r.references[0].line if r.references else 1,
                context=r.references[0].context if r.references else "",
            )
            for r in results
        ]

    async def get_git_history(
        self, file_path: str, repository_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        # Not implemented in stub
        return []

    async def get_blame(
        self, file_path: str, repository_id: str, branch: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Not implemented in stub
        return []

    def _detect_language(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".md": "markdown",
            ".txt": "text",
        }
        return lang_map.get(ext, "text")

    def _hash(self, content: str) -> str:
        import hashlib

        return hashlib.sha256(content.encode()).hexdigest()


class StubForgeIndexer(ForgeIndexer):
    """Stub Forge indexer for testing."""

    def __init__(self):
        self.indexed: Dict[str, Any] = {}

    async def index_repository(
        self, repository_id: str, repository_path: str, branch: str = "main"
    ) -> bool:
        self.indexed[repository_id] = {"path": repository_path, "branch": branch}
        return True

    async def update_file(
        self, repository_id: str, file_path: str, content: str, branch: str = "main"
    ) -> bool:
        if repository_id not in self.indexed:
            return False
        return True

    async def delete_file(self, repository_id: str, file_path: str) -> bool:
        if repository_id not in self.indexed:
            return False
        return True

    async def reindex_repository(self, repository_id: str) -> bool:
        return repository_id in self.indexed

    async def get_index_status(self, repository_id: str) -> Dict[str, Any]:
        if repository_id not in self.indexed:
            return {"status": "not_indexed"}
        return {
            "status": "indexed",
            "path": self.indexed[repository_id]["path"],
            "branch": self.indexed[repository_id]["branch"],
        }
