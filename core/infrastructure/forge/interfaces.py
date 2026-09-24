"""Forge adapter interfaces for repository intelligence and context retrieval."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class ForgeFile:
    path: str
    content: str
    language: str
    size_bytes: int
    sha256: str


@dataclass
class ForgeSymbol:
    name: str
    kind: str  # function, class, method, variable, etc.
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str]
    docstring: Optional[str]


@dataclass
class ForgeFileReference:
    file_path: str
    symbol_name: str
    line: int
    context: str  # surrounding code context


@dataclass
class ForgeSearchResult:
    file: ForgeFile
    symbols: List[ForgeSymbol]
    references: List[ForgeFileReference]
    relevance_score: float
    match_type: str  # semantic, lexical, symbol, path


@dataclass
class ForgeContextBundle:
    query: str
    mission_id: UUID
    task_id: Optional[UUID]
    results: List[ForgeSearchResult]
    total_tokens: int
    retrieved_at: datetime
    metadata: Dict[str, Any]


@dataclass
class ForgeRepositoryInfo:
    repository_id: str
    name: str
    default_branch: str
    languages: List[str]
    total_files: int
    total_lines: int
    last_indexed: datetime


class ForgeContextProvider(ABC):
    """Interface for Forge repository context retrieval."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if Forge service is available."""
        pass

    @abstractmethod
    async def get_repository_info(
        self, repository_id: str
    ) -> Optional[ForgeRepositoryInfo]:
        """Get repository metadata."""
        pass

    @abstractmethod
    async def search_semantic(
        self,
        query: str,
        repository_id: str,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[ForgeSearchResult]:
        """Semantic search using embeddings."""
        pass

    @abstractmethod
    async def search_lexical(
        self,
        query: str,
        repository_id: str,
        limit: int = 20,
        file_patterns: Optional[List[str]] = None,
    ) -> List[ForgeSearchResult]:
        """Lexical/keyword search."""
        pass

    @abstractmethod
    async def search_symbols(
        self,
        symbol_name: str,
        repository_id: str,
        symbol_kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[ForgeSearchResult]:
        """Search for symbols (functions, classes, etc.)."""
        pass

    @abstractmethod
    async def get_file_content(
        self, repository_id: str, file_path: str, branch: Optional[str] = None
    ) -> Optional[ForgeFile]:
        """Get full file content."""
        pass

    @abstractmethod
    async def get_symbol_references(
        self,
        symbol_name: str,
        repository_id: str,
        file_path: Optional[str] = None,
    ) -> List[ForgeFileReference]:
        """Find all references to a symbol."""
        pass

    @abstractmethod
    async def get_dependencies(
        self, file_path: str, repository_id: str, depth: int = 1
    ) -> Dict[str, List[str]]:
        """Get import/dependency graph for a file."""
        pass

    @abstractmethod
    async def get_callers(
        self, symbol_name: str, file_path: str, repository_id: str
    ) -> List[ForgeFileReference]:
        """Find all callers of a function/method."""
        pass

    @abstractmethod
    async def get_git_history(
        self, file_path: str, repository_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get git history for a file."""
        pass

    @abstractmethod
    async def get_blame(
        self, file_path: str, repository_id: str, branch: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get git blame for a file."""
        pass


class ForgeIndexer(ABC):
    """Interface for Forge repository indexing."""

    @abstractmethod
    async def index_repository(
        self, repository_id: str, repository_path: str, branch: str = "main"
    ) -> bool:
        """Index a repository for semantic search."""
        pass

    @abstractmethod
    async def update_file(
        self, repository_id: str, file_path: str, content: str, branch: str = "main"
    ) -> bool:
        """Update a single file in the index."""
        pass

    @abstractmethod
    async def delete_file(self, repository_id: str, file_path: str) -> bool:
        """Remove a file from the index."""
        pass

    @abstractmethod
    async def reindex_repository(self, repository_id: str) -> bool:
        """Full reindex of a repository."""
        pass

    @abstractmethod
    async def get_index_status(self, repository_id: str) -> Dict[str, Any]:
        """Get indexing status for a repository."""
        pass
