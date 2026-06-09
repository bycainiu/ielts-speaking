from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.rag.llamaindex_service import KnowledgeDocument, KnowledgeIngestResult, LlamaIndexKnowledgeService


KnowledgeKind = Literal["idea", "example", "vocabulary", "expression", "structure"]


class TopicKnowledgeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    knowledge_type: KnowledgeKind
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


def build_default_topic_knowledge_items() -> list[TopicKnowledgeItem]:
    items: list[TopicKnowledgeItem] = []
    for topic, idea, example, vocabulary in [
        (
            "technology",
            "Technology is useful when it solves a real problem, but it still needs human guidance.",
            "Online learning apps can give students flexible access, while teachers keep discussion focused.",
            "digital tools, online learning, screen time, human guidance, access to information",
        ),
        (
            "travel",
            "Travel answers work best when they include a concrete route, a person, and one small memorable detail.",
            "A short train trip can show planning, local culture, food, and a personal feeling of independence.",
            "itinerary, local culture, memorable, flexible plan, travel companion",
        ),
        (
            "hometown",
            "Hometown answers should connect place, routine, and personal feeling instead of listing features.",
            "A local library, park, or market can show community, convenience, and a familiar daily routine.",
            "neighbourhood, convenient, local community, public space, daily routine",
        ),
        (
            "work_or_study",
            "Work or study answers need a clear role, one responsibility, and one reason it matters.",
            "A project deadline can explain teamwork, pressure, communication, and practical learning.",
            "deadline, teamwork, responsibility, practical skills, communication",
        ),
        (
            "public_places",
            "Public places can be discussed through access, safety, cost, and community value.",
            "A park or library gives people a low-cost place to rest, study, meet others, and feel included.",
            "accessible, safe, low-cost, community value, shared space",
        ),
    ]:
        items.extend(
            [
                TopicKnowledgeItem(topic=topic, knowledge_type="idea", title=f"{topic} ideas", content=idea),
                TopicKnowledgeItem(topic=topic, knowledge_type="example", title=f"{topic} examples", content=example),
                TopicKnowledgeItem(topic=topic, knowledge_type="vocabulary", title=f"{topic} vocabulary", content=vocabulary),
            ]
        )
    return items


def build_default_topic_knowledge_documents() -> list[KnowledgeDocument]:
    return [
        KnowledgeDocument(
            doc_id=stable_topic_doc_id(item),
            doc_type="topic_knowledge",
            title=item.title,
            content=item.content,
            metadata={
                "topic": item.topic,
                "knowledge_type": item.knowledge_type,
                "source_type": "internal",
            },
            status="active",
        )
        for item in build_default_topic_knowledge_items()
    ]


def ingest_default_topic_knowledge(service: LlamaIndexKnowledgeService) -> list[KnowledgeIngestResult]:
    return service.ingest_documents(build_default_topic_knowledge_documents())


def stable_topic_doc_id(item: TopicKnowledgeItem) -> str:
    import hashlib
    from uuid import UUID

    digest = hashlib.md5(f"topic:{item.topic}:{item.knowledge_type}:{item.title}".encode("utf-8")).hexdigest()
    return str(UUID(digest))
