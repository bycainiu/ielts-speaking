from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.rag.chunk_schema import normalize_chunk_metadata


KnowledgeDocType = Literal["question_bank", "rubric", "user_profile", "topic_knowledge", "review_history"]
KnowledgeStatus = Literal["draft", "reviewing", "active", "archived"]
KnowledgeBackend = Literal["memory", "pgvector"]
MetadataValue = str | int | float | bool | None | list[str | int | float | bool]

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class KnowledgeServiceError(RuntimeError):
    pass


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str | None = None
    doc_type: KnowledgeDocType
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_id: str | None = None
    owner_user_id: str | None = None
    status: KnowledgeStatus = "active"


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    doc_type: KnowledgeDocType
    chunk_index: int = Field(ge=0)
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int = Field(ge=0)


class KnowledgeIngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    doc_type: KnowledgeDocType
    chunk_count: int = Field(ge=0)
    content_hash: str


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    doc_type: KnowledgeDocType
    title: str
    content: str
    metadata: dict[str, Any]
    score: float = Field(ge=0, le=1)
    source: str = "knowledge_chunks"


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, gt=0, le=50)
    filters: dict[str, MetadataValue] = Field(default_factory=dict)


class HashEmbeddingProvider:
    def __init__(self, dimension: int = 1536, model_name: str = "hash-embedding-v1") -> None:
        if dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        self.dimension = dimension
        self.model_name = model_name

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class KnowledgeStore:
    def ingest_documents(
        self,
        documents: Sequence[KnowledgeDocument],
        *,
        embedding_provider: HashEmbeddingProvider,
        chunk_max_chars: int,
        chunk_overlap_chars: int,
    ) -> list[KnowledgeIngestResult]:
        raise NotImplementedError

    def retrieve(
        self,
        query: KnowledgeQuery,
        *,
        embedding_provider: HashEmbeddingProvider,
    ) -> list[KnowledgeSearchResult]:
        raise NotImplementedError

    def delete_documents(self, doc_ids: Sequence[str]) -> int:
        raise NotImplementedError

    def delete_by_filters(self, filters: Mapping[str, MetadataValue]) -> int:
        raise NotImplementedError


class InMemoryKnowledgeStore(KnowledgeStore):
    def __init__(self) -> None:
        self._chunks: dict[str, tuple[KnowledgeChunk, list[float]]] = {}
        self._doc_chunks: dict[str, set[str]] = defaultdict(set)

    def ingest_documents(
        self,
        documents: Sequence[KnowledgeDocument],
        *,
        embedding_provider: HashEmbeddingProvider,
        chunk_max_chars: int,
        chunk_overlap_chars: int,
    ) -> list[KnowledgeIngestResult]:
        results: list[KnowledgeIngestResult] = []
        for document in documents:
            doc_id = document.doc_id or str(uuid4())
            content_hash = hash_content(document.content)
            self._delete_doc_chunks(doc_id)

            chunks = build_chunks(
                document,
                doc_id=doc_id,
                chunk_max_chars=chunk_max_chars,
                chunk_overlap_chars=chunk_overlap_chars,
            )
            for chunk in chunks:
                embedding = embedding_provider.embed(chunk.content)
                self._chunks[chunk.chunk_id] = (chunk, embedding)
                self._doc_chunks[doc_id].add(chunk.chunk_id)

            results.append(
                KnowledgeIngestResult(
                    doc_id=doc_id,
                    doc_type=document.doc_type,
                    chunk_count=len(chunks),
                    content_hash=content_hash,
                )
            )
        return results

    def retrieve(
        self,
        query: KnowledgeQuery,
        *,
        embedding_provider: HashEmbeddingProvider,
    ) -> list[KnowledgeSearchResult]:
        query_embedding = embedding_provider.embed(query.query)
        candidates: list[KnowledgeSearchResult] = []
        for chunk, embedding in self._chunks.values():
            if chunk.metadata.get("status") != "active":
                continue
            if not metadata_matches(chunk, query.filters):
                continue
            score = cosine_similarity(query_embedding, embedding)
            candidates.append(
                KnowledgeSearchResult(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    doc_type=chunk.doc_type,
                    title=chunk.title,
                    content=chunk.content,
                    metadata=chunk.metadata,
                    score=score,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: query.top_k]

    def _delete_doc_chunks(self, doc_id: str) -> None:
        for chunk_id in self._doc_chunks.pop(doc_id, set()):
            self._chunks.pop(chunk_id, None)

    def delete_documents(self, doc_ids: Sequence[str]) -> int:
        deleted_count = 0
        for doc_id in doc_ids:
            if doc_id in self._doc_chunks:
                deleted_count += 1
            self._delete_doc_chunks(doc_id)
        return deleted_count

    def delete_by_filters(self, filters: Mapping[str, MetadataValue]) -> int:
        doc_ids = {
            chunk.doc_id
            for chunk, _ in self._chunks.values()
            if metadata_matches(chunk, filters)
        }
        return self.delete_documents(sorted(doc_ids))


class PgVectorKnowledgeStore(KnowledgeStore):
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise KnowledgeServiceError("pgvector backend requires KNOWLEDGE_DATABASE_URL")
        self.database_url = database_url

    def ingest_documents(
        self,
        documents: Sequence[KnowledgeDocument],
        *,
        embedding_provider: HashEmbeddingProvider,
        chunk_max_chars: int,
        chunk_overlap_chars: int,
    ) -> list[KnowledgeIngestResult]:
        psycopg, Jsonb = load_psycopg()
        results: list[KnowledgeIngestResult] = []
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                for document in documents:
                    doc_id = document.doc_id or str(uuid4())
                    content_hash = hash_content(document.content)
                    conn.execute(
                        """
                        insert into knowledge_docs
                            (id, doc_type, owner_user_id, source_id, title, content_hash, metadata, status)
                        values
                            (%s::uuid, %s::knowledge_doc_type, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::content_status)
                        on conflict (id) do update set
                            doc_type = excluded.doc_type,
                            owner_user_id = excluded.owner_user_id,
                            source_id = excluded.source_id,
                            title = excluded.title,
                            content_hash = excluded.content_hash,
                            metadata = excluded.metadata,
                            status = excluded.status,
                            updated_at = now(),
                            deleted_at = null
                        """,
                        (
                            doc_id,
                            document.doc_type,
                            document.owner_user_id,
                            document.source_id,
                            document.title,
                            content_hash,
                            Jsonb(document.metadata),
                            document.status,
                        ),
                    )
                    conn.execute("delete from knowledge_chunks where doc_id = %s::uuid", (doc_id,))
                    chunks = build_chunks(
                        document,
                        doc_id=doc_id,
                        chunk_max_chars=chunk_max_chars,
                        chunk_overlap_chars=chunk_overlap_chars,
                    )
                    for chunk in chunks:
                        embedding = vector_literal(embedding_provider.embed(chunk.content))
                        conn.execute(
                            """
                            insert into knowledge_chunks
                                (id, doc_id, chunk_index, content, metadata, embedding, embedding_model, token_count)
                            values
                                (%s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::vector, %s, %s)
                            """,
                            (
                                chunk.chunk_id,
                                doc_id,
                                chunk.chunk_index,
                                chunk.content,
                                Jsonb(chunk.metadata),
                                embedding,
                                embedding_provider.model_name,
                                chunk.token_count,
                            ),
                        )
                    results.append(
                        KnowledgeIngestResult(
                            doc_id=doc_id,
                            doc_type=document.doc_type,
                            chunk_count=len(chunks),
                            content_hash=content_hash,
                        )
                    )
        return results

    def retrieve(
        self,
        query: KnowledgeQuery,
        *,
        embedding_provider: HashEmbeddingProvider,
    ) -> list[KnowledgeSearchResult]:
        psycopg, Jsonb = load_psycopg()
        query_vector = vector_literal(embedding_provider.embed(query.query))
        where_sql, params = build_pgvector_filter_sql(query.filters, Jsonb)
        sql = f"""
            select
                kc.id::text,
                kd.id::text,
                kd.doc_type::text,
                kd.title,
                kc.content,
                (kd.metadata || kc.metadata)::text,
                greatest(0, least(1, 1 - (kc.embedding <=> %s::vector))) as score
            from knowledge_chunks kc
            join knowledge_docs kd on kd.id = kc.doc_id
            where kd.deleted_at is null
              and kd.status = 'active'
              and kc.embedding is not null
              {where_sql}
            order by kc.embedding <=> %s::vector
            limit %s
        """
        with psycopg.connect(self.database_url) as conn:
            rows = conn.execute(sql, [query_vector, *params, query_vector, query.top_k]).fetchall()
        results: list[KnowledgeSearchResult] = []
        for row in rows:
            metadata = row[5]
            if isinstance(metadata, str):
                import json

                metadata = json.loads(metadata)
            results.append(
                KnowledgeSearchResult(
                    chunk_id=row[0],
                    doc_id=row[1],
                    doc_type=row[2],
                    title=row[3],
                    content=row[4],
                    metadata=metadata,
                    score=float(row[6]),
                )
            )
        return results

    def delete_documents(self, doc_ids: Sequence[str]) -> int:
        if not doc_ids:
            return 0
        psycopg, _ = load_psycopg()
        normalized_doc_ids = [str(doc_id) for doc_id in doc_ids]
        with psycopg.connect(self.database_url) as conn:
            with conn.transaction():
                conn.execute("delete from knowledge_chunks where doc_id = any(%s::uuid[])", (normalized_doc_ids,))
                conn.execute(
                    """
                    update knowledge_docs
                    set status = 'archived',
                        deleted_at = now(),
                        updated_at = now()
                    where id = any(%s::uuid[])
                    """,
                    (normalized_doc_ids,),
                )
        return len(normalized_doc_ids)

    def delete_by_filters(self, filters: Mapping[str, MetadataValue]) -> int:
        psycopg, Jsonb = load_psycopg()
        where_sql, params = build_pgvector_filter_sql(filters, Jsonb)
        sql = f"""
            select distinct kd.id::text
            from knowledge_docs kd
            join knowledge_chunks kc on kc.doc_id = kd.id
            where kd.deleted_at is null
              {where_sql}
        """
        with psycopg.connect(self.database_url) as conn:
            doc_ids = [row[0] for row in conn.execute(sql, params).fetchall()]
        return self.delete_documents(doc_ids)


class LlamaIndexKnowledgeService:
    def __init__(
        self,
        *,
        store: KnowledgeStore,
        embedding_provider: HashEmbeddingProvider,
        chunk_max_chars: int = 1200,
        chunk_overlap_chars: int = 120,
        backend: KnowledgeBackend = "memory",
    ) -> None:
        if chunk_max_chars <= 0:
            raise ValueError("chunk_max_chars must be positive")
        if chunk_overlap_chars < 0 or chunk_overlap_chars >= chunk_max_chars:
            raise ValueError("chunk_overlap_chars must be >= 0 and smaller than chunk_max_chars")
        self.store = store
        self.embedding_provider = embedding_provider
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap_chars = chunk_overlap_chars
        self.backend = backend

    @classmethod
    def from_settings(cls, settings: Settings) -> "LlamaIndexKnowledgeService":
        embedding_provider = HashEmbeddingProvider(
            dimension=settings.knowledge_embedding_dimension,
            model_name=settings.knowledge_embedding_model,
        )
        if settings.knowledge_store_backend == "pgvector":
            store: KnowledgeStore = PgVectorKnowledgeStore(settings.knowledge_database_url)
        else:
            store = InMemoryKnowledgeStore()
        return cls(
            store=store,
            embedding_provider=embedding_provider,
            chunk_max_chars=settings.knowledge_chunk_max_chars,
            chunk_overlap_chars=settings.knowledge_chunk_overlap_chars,
            backend=settings.knowledge_store_backend,  # type: ignore[arg-type]
        )

    def ingest_documents(self, documents: Sequence[KnowledgeDocument]) -> list[KnowledgeIngestResult]:
        return self.store.ingest_documents(
            documents,
            embedding_provider=self.embedding_provider,
            chunk_max_chars=self.chunk_max_chars,
            chunk_overlap_chars=self.chunk_overlap_chars,
        )

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, MetadataValue] | None = None,
    ) -> list[KnowledgeSearchResult]:
        knowledge_query = KnowledgeQuery(query=query, top_k=top_k, filters=dict(filters or {}))
        return self.store.retrieve(knowledge_query, embedding_provider=self.embedding_provider)

    def delete_documents(self, doc_ids: Sequence[str]) -> int:
        return self.store.delete_documents(doc_ids)

    def delete_by_filters(self, filters: Mapping[str, MetadataValue]) -> int:
        return self.store.delete_by_filters(filters)

    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "embedding_model": self.embedding_provider.model_name,
            "embedding_dimension": self.embedding_provider.dimension,
            "chunk_max_chars": self.chunk_max_chars,
            "chunk_overlap_chars": self.chunk_overlap_chars,
        }


def build_chunks(
    document: KnowledgeDocument,
    *,
    doc_id: str,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> list[KnowledgeChunk]:
    pieces = split_text(document.content, max_chars=chunk_max_chars, overlap_chars=chunk_overlap_chars)
    chunks: list[KnowledgeChunk] = []
    for index, piece in enumerate(pieces):
        metadata = {
            **document.metadata,
            "doc_type": document.doc_type,
            "title": document.title,
            "status": document.status,
        }
        if document.source_id:
            metadata["source_id"] = document.source_id
        if document.owner_user_id:
            metadata["owner_user_id"] = document.owner_user_id
        metadata = normalize_chunk_metadata(document.doc_type, metadata)

        chunks.append(
            KnowledgeChunk(
                chunk_id=str(uuid4()),
                doc_id=doc_id,
                doc_type=document.doc_type,
                chunk_index=index,
                title=document.title,
                content=piece,
                metadata=metadata,
                token_count=len(TOKEN_RE.findall(piece)),
            )
        )
    return chunks


def split_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)
    return chunks


def metadata_matches(chunk: KnowledgeChunk, filters: Mapping[str, MetadataValue]) -> bool:
    for key, expected in filters.items():
        actual = chunk.metadata.get(key)
        if not metadata_value_matches(actual, expected):
            return False
    return True


def metadata_value_matches(actual: Any, expected: MetadataValue) -> bool:
    if isinstance(expected, list):
        return any(metadata_value_matches(actual, item) for item in expected)
    if isinstance(actual, list):
        return any(metadata_value_matches(item, expected) for item in actual)
    return actual == expected or str(actual) == str(expected)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def build_pgvector_filter_sql(filters: Mapping[str, MetadataValue], jsonb_type: Any) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filters.items():
        if key == "doc_type":
            clauses.append("and kd.doc_type = %s::knowledge_doc_type")
            params.append(value)
            continue
        if key == "status":
            clauses.append("and kd.status = %s::content_status")
            params.append(value)
            continue
        if isinstance(value, list):
            clauses.append(
                "and (kc.metadata ->> %s = any(%s) "
                "or (jsonb_typeof(kc.metadata -> %s) = 'array' and (kc.metadata -> %s) ?| %s))"
            )
            values = [str(item) for item in value]
            params.extend([key, values, key, key, values])
            continue
        clauses.append("and kc.metadata @> %s::jsonb")
        params.append(jsonb_type({key: value}))
    return "\n              ".join(clauses), params


def load_psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:  # pragma: no cover - 只在 pgvector backend 且缺依赖时触发
        raise KnowledgeServiceError("pgvector backend requires psycopg[binary]") from exc
    return psycopg, Jsonb
