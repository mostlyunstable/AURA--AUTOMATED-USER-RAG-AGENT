"""RAG Engine - Context Retrieval Service for engineering context."""

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from core.application.interfaces import UnitOfWork
from core.domain.agents.entities import Agent
from core.domain.agents.enums import AgentCapability
from core.domain.tasks.entities import Task
from core.domain.tasks.enums import TaskType
from core.infrastructure.forge.interfaces import (
    ForgeContextProvider,
    ForgeFile,
    ForgeSearchResult,
)
from core.infrastructure.metrics.execution import (
    aura_rag_latency_seconds,
    aura_rag_retrievals_total,
    aura_rag_tokens_total,
)


@dataclass
class RetrievalQuery:
    """Structured query for context retrieval."""

    mission_id: UUID
    task_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    query_text: str = ""
    task_type: Optional[str] = None
    acceptance_criteria: List[str] = field(default_factory=list)
    changed_files: List[str] = field(default_factory=list)
    error_context: Optional[str] = None
    max_results: int = 20
    token_budget: int = 8000
    retrieval_strategies: List[str] = field(
        default_factory=lambda: ["semantic", "lexical", "symbol", "path"]
    )
    metadata_filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedContext:
    """A single piece of retrieved context with metadata."""

    content: str
    source: str  # file path, symbol, etc.
    source_type: str  # file, symbol, path, git_history, etc.
    relevance_score: float
    tokens: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBundle:
    """Assembled context bundle for agent consumption."""

    mission_id: UUID
    task_id: Optional[UUID]
    query: str
    contexts: List[RetrievedContext]
    total_tokens: int
    token_budget: int
    retrieved_at: datetime
    retrieval_strategies_used: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class TokenCounter:
    """Simple token counter using character approximation."""

    # Rough approximation: 1 token ≈ 4 characters for English code
    CHARS_PER_TOKEN = 4

    @classmethod
    def count_tokens(cls, text: str) -> int:
        return max(1, len(text) // cls.CHARS_PER_TOKEN)

    @classmethod
    def count_tokens_list(cls, texts: List[str]) -> int:
        return sum(cls.count_tokens(t) for t in texts)


class ContextRetrievalService:
    """Service for retrieving relevant engineering context for agents.

    Coordinates multiple retrieval strategies:
    - Semantic search (embeddings via Forge)
    - Lexical/keyword search
    - Symbol/function search
    - Path/dependency search
    - Git history/recent changes
    - Test file relevance

    Applies token budgeting and deduplication to assemble compact,
    high-relevance context bundles.
    """

    def __init__(
        self,
        forge_provider: ForgeContextProvider,
        token_budget: int = 8000,
        max_results_per_strategy: int = 10,
        min_relevance_threshold: float = 0.3,
    ):
        self.forge = forge_provider
        self.token_budget = token_budget
        self.max_results_per_strategy = max_results_per_strategy
        self.min_relevance_threshold = min_relevance_threshold
        self._cache: Dict[str, List[RetrievedContext]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def retrieve_context(self, query: RetrievalQuery) -> ContextBundle:
        """Retrieve and assemble context for an agent task."""
        start_time = datetime.utcnow()

        # Check cache
        cache_key = self._cache_key(query)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if (datetime.utcnow() - start_time).total_seconds() < self._cache_ttl:
                return self._assemble_bundle(query, cached, start_time)

        # Run retrieval strategies in parallel
        all_results: List[ForgeSearchResult] = []

        if "semantic" in query.retrieval_strategies:
            results = await self._semantic_search(query)
            all_results.extend(results)

        if "lexical" in query.retrieval_strategies:
            results = await self._lexical_search(query)
            all_results.extend(results)

        if "symbol" in query.retrieval_strategies:
            results = await self._symbol_search(query)
            all_results.extend(results)

        if "path" in query.retrieval_strategies:
            results = await self._path_search(query)
            all_results.extend(results)

        if "dependency" in query.retrieval_strategies:
            results = await self._dependency_search(query)
            all_results.extend(results)

        if "git_history" in query.retrieval_strategies:
            results = await self._git_history_search(query)
            all_results.extend(results)

        # Convert to RetrievedContext, deduplicate, filter, rank
        contexts = self._process_results(all_results, query)

        # Apply token budget
        contexts = self._apply_token_budget(contexts, query.token_budget)

        # Cache results
        self._cache[cache_key] = contexts

        # Record metrics
        aura_rag_retrievals_total.inc()
        aura_rag_tokens_total.inc(sum(c.tokens for c in contexts))
        aura_rag_latency_seconds.observe(
            (datetime.utcnow() - start_time).total_seconds()
        )

        return self._assemble_bundle(query, contexts, start_time)

    async def _semantic_search(self, query: RetrievalQuery) -> List[ForgeSearchResult]:
        """Semantic search using Forge embeddings."""
        try:
            return await self.forge.search_semantic(
                query=query.query_text,
                repository_id=str(query.mission_id),
                limit=self.max_results_per_strategy,
                filters=query.metadata_filters,
            )
        except Exception:
            return []

    async def _lexical_search(self, query: RetrievalQuery) -> List[ForgeSearchResult]:
        """Lexical/keyword search."""
        try:
            return await self.forge.search_lexical(
                query=query.query_text,
                repository_id=str(query.mission_id),
                limit=self.max_results_per_strategy,
                file_patterns=query.metadata_filters.get("file_patterns"),
            )
        except Exception:
            return []

    async def _symbol_search(self, query: RetrievalQuery) -> List[ForgeSearchResult]:
        """Search for symbols (functions, classes, methods)."""
        symbols: set[str] = set()
        # Extract symbols from query and acceptance criteria
        for text in [query.query_text] + query.acceptance_criteria:
            symbols.update(self._extract_symbols(text))

        all_results = []
        for symbol in symbols:
            try:
                results = await self.forge.search_symbols(
                    symbol_name=symbol,
                    repository_id=str(query.mission_id),
                    limit=5,
                )
                all_results.extend(results)
            except Exception:
                continue
        return all_results[: self.max_results_per_strategy]

    async def _path_search(self, query: RetrievalQuery) -> List[ForgeSearchResult]:
        """Search by file path relevance."""
        results = []
        for changed_file in query.changed_files:
            try:
                file = await self.forge.get_file_content(
                    str(query.mission_id), changed_file
                )
                if file:
                    results.append(
                        ForgeSearchResult(
                            file=file,
                            symbols=[],
                            references=[],
                            relevance_score=1.0,
                            match_type="path",
                        )
                    )
            except Exception:
                continue
        return results

    async def _dependency_search(
        self, query: RetrievalQuery
    ) -> List[ForgeSearchResult]:
        """Search for dependency-related files."""
        results = []
        for changed_file in query.changed_files:
            try:
                deps = await self.forge.get_dependencies(
                    str(query.mission_id), changed_file
                )
                for imp in deps.get("imports", []):
                    # Search for the imported module
                    dep_results = await self.forge.search_lexical(
                        query=imp,
                        repository_id=str(query.mission_id),
                        limit=3,
                    )
                    results.extend(dep_results)
            except Exception:
                continue
        return results[: self.max_results_per_strategy]

    async def _git_history_search(
        self, query: RetrievalQuery
    ) -> List[ForgeSearchResult]:
        """Search recent git history for relevant changes."""
        results = []
        for changed_file in query.changed_files:
            try:
                history = await self.forge.get_git_history(
                    str(query.mission_id), changed_file, limit=20
                )
                for commit in history:
                    if query.query_text.lower() in commit.get("message", "").lower():
                        results.append(
                            ForgeSearchResult(
                                file=ForgeFile(
                                    path=changed_file,
                                    content=commit.get("message", ""),
                                    language="git",
                                    size_bytes=len(commit.get("message", "")),
                                    sha256="",
                                ),
                                symbols=[],
                                references=[],
                                relevance_score=0.8,
                                match_type="git_history",
                            )
                        )
            except Exception:
                continue
        return results[: self.max_results_per_strategy]

    def _extract_symbols(self, text: str) -> Set[str]:
        """Extract potential symbol names from text."""
        import re

        # Match function names, class names, method calls
        patterns = [
            r"\b([A-Z][a-zA-Z0-9]*)\b",  # PascalCase (classes)
            r"\b([a-z_][a-z0-9_]*)\s*\(",  # function calls
            r"\b(self\.[a-z_][a-z0-9_]*)",  # method calls
        ]
        symbols: set[str] = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                if isinstance(m, tuple):
                    symbols.update(m)
                else:
                    symbols.add(m)
        return symbols

    def _process_results(
        self, results: List[ForgeSearchResult], query: RetrievalQuery
    ) -> List[RetrievedContext]:
        """Process, deduplicate, filter, and rank search results."""
        # Convert to RetrievedContext
        contexts = []
        seen_sources: Set[str] = set()

        for result in results:
            if result.relevance_score < self.min_relevance_threshold:
                continue

            source_key = result.file.path
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)

            # Extract content based on match type
            if result.match_type == "git_history":
                content = f"Git history for {result.file.path}:\n{result.file.content}"
            elif result.references:
                content = "\n".join(r.context for r in result.references[:5])
            else:
                content = result.file.content[:5000]  # Truncate

            tokens = TokenCounter.count_tokens(content)

            contexts.append(
                RetrievedContext(
                    content=content,
                    source=result.file.path,
                    source_type=result.match_type,
                    relevance_score=result.relevance_score,
                    tokens=tokens,
                    metadata={
                        "match_type": result.match_type,
                        "file_language": result.file.language,
                        "file_size": result.file.size_bytes,
                    },
                    provenance={
                        "forge_result": True,
                        "match_type": result.match_type,
                        "sha256": result.file.sha256,
                    },
                )
            )

        # Sort by relevance
        contexts.sort(key=lambda c: c.relevance_score, reverse=True)

        return contexts

    def _apply_token_budget(
        self, contexts: List[RetrievedContext], budget: int
    ) -> List[RetrievedContext]:
        """Apply token budget, keeping highest relevance contexts."""
        if not contexts:
            return []

        total = sum(c.tokens for c in contexts)
        if total <= budget:
            return contexts

        # Greedy: keep highest relevance until budget exhausted
        selected = []
        total_tokens = 0
        for ctx in contexts:
            if total_tokens + ctx.tokens <= budget:
                selected.append(ctx)
                total_tokens += ctx.tokens
            else:
                # Try to truncate this context to fit
                remaining = budget - total_tokens
                if remaining > 100:  # Minimum viable context
                    truncated = RetrievedContext(
                        content=ctx.content[: remaining * 4],  # Approx chars
                        source=ctx.source,
                        source_type=ctx.source_type,
                        relevance_score=ctx.relevance_score * 0.8,
                        tokens=remaining,
                        metadata={**ctx.metadata, "truncated": True},
                        provenance=ctx.provenance,
                    )
                    selected.append(truncated)
                break

        return selected

    def _assemble_bundle(
        self,
        query: RetrievalQuery,
        contexts: List[RetrievedContext],
        start_time: datetime,
    ) -> ContextBundle:
        return ContextBundle(
            mission_id=query.mission_id,
            task_id=query.task_id,
            query=query.query_text,
            contexts=contexts,
            total_tokens=sum(c.tokens for c in contexts),
            token_budget=query.token_budget,
            retrieved_at=datetime.utcnow(),
            retrieval_strategies_used=query.retrieval_strategies,
            metadata={
                "task_type": query.task_type,
                "agent_id": str(query.agent_id) if query.agent_id else None,
                "retrieval_time_ms": (datetime.utcnow() - start_time).total_seconds()
                * 1000,
            },
        )

    def _cache_key(self, query: RetrievalQuery) -> str:
        """Generate cache key for query."""
        parts = (
            str(query.mission_id),
            str(query.task_id) if query.task_id else "",
            query.query_text[:100],
            ",".join(sorted(query.retrieval_strategies)),
        )
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

    def clear_cache(self) -> None:
        self._cache.clear()


class ContextAssemblyService:
    """Assembles final context bundles for different agent types."""

    def __init__(self, retrieval_service: ContextRetrievalService):
        self.retrieval = retrieval_service

    async def build_planner_context(
        self,
        mission_id: UUID,
        repository_id: str,
        requirements: str,
    ) -> ContextBundle:
        """Build context for the Planner agent."""
        query = RetrievalQuery(
            mission_id=mission_id,
            query_text=requirements,
            task_type="planning",
            retrieval_strategies=["semantic", "lexical", "path", "dependency"],
            token_budget=12000,
            metadata_filters={
                "file_patterns": [
                    "*.py",
                    "*.js",
                    "*.ts",
                    "*.go",
                    "*.rs",
                    "*.md",
                    "*.yaml",
                    "*.yml",
                ]
            },
        )
        return await self.retrieval.retrieve_context(query)

    async def build_coder_context(
        self,
        mission_id: UUID,
        task_id: UUID,
        task_description: str,
        acceptance_criteria: List[str],
        changed_files: List[str],
    ) -> ContextBundle:
        """Build context for the Coding agent."""
        query = RetrievalQuery(
            mission_id=mission_id,
            task_id=task_id,
            query_text=task_description,
            task_type="implementation",
            acceptance_criteria=acceptance_criteria,
            changed_files=changed_files,
            retrieval_strategies=[
                "semantic",
                "lexical",
                "symbol",
                "path",
                "dependency",
            ],
            token_budget=8000,
        )
        return await self.retrieval.retrieve_context(query)

    async def build_debugger_context(
        self,
        mission_id: UUID,
        task_id: UUID,
        error_context: str,
        changed_files: List[str],
    ) -> ContextBundle:
        """Build context for the Debugger agent."""
        query = RetrievalQuery(
            mission_id=mission_id,
            task_id=task_id,
            query_text=error_context,
            task_type="debugging",
            error_context=error_context,
            changed_files=changed_files,
            retrieval_strategies=[
                "semantic",
                "lexical",
                "symbol",
                "git_history",
                "dependency",
            ],
            token_budget=8000,
        )
        return await self.retrieval.retrieve_context(query)

    async def build_tester_context(
        self,
        mission_id: UUID,
        task_id: UUID,
        test_requirements: str,
        changed_files: List[str],
    ) -> ContextBundle:
        """Build context for the Tester agent."""
        query = RetrievalQuery(
            mission_id=mission_id,
            task_id=task_id,
            query_text=test_requirements,
            task_type="testing",
            changed_files=changed_files,
            retrieval_strategies=["semantic", "lexical", "symbol", "path"],
            token_budget=8000,
        )
        return await self.retrieval.retrieve_context(query)

    async def build_reviewer_context(
        self,
        mission_id: UUID,
        task_id: UUID,
        diff: str,
        changed_files: List[str],
        review_type: str,  # "code" or "security"
    ) -> ContextBundle:
        """Build context for Code/Security Reviewer agent."""
        strategies = ["semantic", "lexical", "symbol", "path", "git_history"]
        if review_type == "security":
            strategies.append("dependency")

        query = RetrievalQuery(
            mission_id=mission_id,
            task_id=task_id,
            query_text=f"{review_type} review: {diff[:2000]}",
            task_type="review",
            changed_files=changed_files,
            retrieval_strategies=strategies,
            token_budget=10000,
        )
        return await self.retrieval.retrieve_context(query)
