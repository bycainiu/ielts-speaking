from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "knowledge" / "question_bank"
SEASON_CODE = "IELTSBRO-2026-05-08"
SEASON_TITLE = "雅思哥口语题库 2026年5-8月"
SEASON_STARTS_ON = "2026-05-01"
SEASON_ENDS_ON = "2026-08-31"
SOURCE_URL = "https://www.ieltsbro.com/question-bank/"
API_BASE = "https://hcp-server.ieltsbro.com"
NAMESPACE = UUID("3e67c6f5-35c4-523b-9f0e-1e9e3f4d3e6b")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


QUESTION_TYPE_LABELS = {
    0: "疑似新题",
    1: "确定新题",
    2: "老题沿用",
}

CATEGORY_LABELS = {
    "1": "人物",
    "2": "事物",
    "3": "事件",
    "4": "地点",
}


@dataclass(frozen=True)
class TopicRecord:
    source_topic_id: str
    topic_name: str
    part_group: str
    part: int
    observed_question_id: str
    observed_question_text: str
    question_count: int
    question_type: int | None
    question_type_label: str | None
    is_new: bool | None
    time_tag: str | None
    oral_nums: str | None
    recent_exam_count: int | None
    category_ids: tuple[str, ...]
    category_labels: tuple[str, ...]
    question_pic: str | None
    topic_create_date: str | None
    create_date: str | None
    update_date: str | None
    update_flag: bool | None


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取雅思哥当季口语题库并导入本地库")
    parser.add_argument("--apply", action="store_true", help="生成文件后直接写入 Docker Postgres")
    parser.add_argument("--container", default="ielts_speaking-postgres-1")
    parser.add_argument("--db-user", default="ielts")
    parser.add_argument("--db-name", default="ielts_speaking")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_bundle = fetch_raw_bundle()
    records = build_records(raw_bundle)
    if not records:
        raise RuntimeError("未抓取到题库记录")

    generated_at = datetime.now(timezone.utc).isoformat()
    json_path = OUTPUT_DIR / "ieltsbro_2026_05_08_question_bank.json"
    md_path = OUTPUT_DIR / "ieltsbro_2026_05_08_question_bank.md"
    sql_path = OUTPUT_DIR / "ieltsbro_2026_05_08_question_bank.sql"

    payload = {
        "source": {
            "name": "IELTSBRO",
            "url": SOURCE_URL,
            "api_base": API_BASE,
            "generated_at": generated_at,
            "coverage": "公开网页接口可见数据：当季主题、首题、题量、分类、热度与更新时间；完整子题需 App 侧接口补齐。",
        },
        "season": {
            "code": SEASON_CODE,
            "title": SEASON_TITLE,
            "starts_on": SEASON_STARTS_ON,
            "ends_on": SEASON_ENDS_ON,
        },
        "summary": summarize(records),
        "raw": raw_bundle,
        "records": [record_to_json(record) for record in records],
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(records, payload), encoding="utf-8")
    sql_path.write_text(build_sql(records, generated_at), encoding="utf-8")

    print(f"生成 JSON: {json_path}")
    print(f"生成 Markdown: {md_path}")
    print(f"生成 SQL: {sql_path}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))

    if args.apply:
        apply_sql(sql_path, args.container, args.db_user, args.db_name)
        print("数据库导入完成")

    return 0


def fetch_raw_bundle() -> dict[str, Any]:
    topic_change = request_json("/hcp/qsBank/topicChange/getDataV2/1", method="GET")
    newest_time = request_json("/hcp/qsBank/topicChange/getNewestTime", method="GET")

    oral_lists: dict[str, Any] = {}
    for part in (0, 1):
        for category_id in ("all", "1", "2", "3", "4"):
            key = f"part{part}_{category_id}"
            oral_lists[key] = request_json(
                "/hcp/qsBank/oralTopic/listV3",
                method="POST",
                body={"oralTopCatalog": category_id, "part": part},
            )

    return {
        "topic_change_v2": topic_change,
        "newest_time": newest_time,
        "oral_lists": oral_lists,
    }


def request_json(path: str, *, method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {
        "source": "2",
        "version": "0.0.0",
        "User-Agent": "Mozilla/5.0 Codex IELTS speaking importer",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"请求失败: {path}: {exc}") from exc
    if payload.get("status") != 0:
        raise RuntimeError(f"接口返回异常: {path}: {payload}")
    return payload


def build_records(raw_bundle: dict[str, Any]) -> list[TopicRecord]:
    topic_change = raw_bundle["topic_change_v2"]["content"]
    topic_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for part_group, key in (("p1", "p1List"), ("p23", "p23List")):
        for item in topic_change.get(key) or []:
            source_topic_id = normalize_topic_id(item)
            if source_topic_id:
                topic_meta[(part_group, source_topic_id)] = item

    category_map: dict[tuple[str, str], set[str]] = {}
    for key, payload in raw_bundle["oral_lists"].items():
        _, category_id = key.split("_", 1)
        if category_id == "all":
            continue
        content = payload.get("content") or {}
        part_group = "p1" if key.startswith("part0_") else "p23"
        for item in content.get("list") or []:
            source_topic_id = normalize_topic_id(item)
            if source_topic_id:
                category_map.setdefault((part_group, source_topic_id), set()).add(category_id)

    records: list[TopicRecord] = []
    seen: set[tuple[str, str]] = set()
    for key in ("part0_all", "part1_all"):
        payload = raw_bundle["oral_lists"][key]
        content = payload.get("content") or {}
        part_group = "p1" if key.startswith("part0_") else "p23"
        part = 1 if part_group == "p1" else 2
        for item in content.get("list") or []:
            source_topic_id = normalize_topic_id(item)
            topic_name = normalize_text(item.get("oralTopicName"))
            observed_text = normalize_question_text(item.get("oralQuestion"))
            if not source_topic_id or not topic_name or not observed_text:
                continue

            record_key = (part_group, source_topic_id)
            if record_key in seen:
                continue
            seen.add(record_key)

            meta = topic_meta.get(record_key, {})
            category_ids = tuple(sorted(category_map.get(record_key, set())))
            category_labels = tuple(CATEGORY_LABELS[value] for value in category_ids if value in CATEGORY_LABELS)
            question_type = int_or_none(meta.get("questionType", item.get("questionType")))

            records.append(
                TopicRecord(
                    source_topic_id=source_topic_id,
                    topic_name=topic_name,
                    part_group=part_group,
                    part=part,
                    observed_question_id=str(item.get("oralQuestionId") or stable_key("observed-question", part_group, source_topic_id)),
                    observed_question_text=observed_text,
                    question_count=int(item.get("questionCount") or 1),
                    question_type=question_type,
                    question_type_label=QUESTION_TYPE_LABELS.get(question_type),
                    is_new=ieltsbro_is_new(meta.get("ifNew", item.get("ifNew"))),
                    time_tag=normalize_optional_text(item.get("timeTag")),
                    oral_nums=normalize_optional_text(item.get("oralNums")),
                    recent_exam_count=int_or_none(item.get("recentExamCount")),
                    category_ids=category_ids,
                    category_labels=category_labels,
                    question_pic=normalize_optional_text(meta.get("questionPic")),
                    topic_create_date=normalize_optional_text(meta.get("topicCreateDate")),
                    create_date=normalize_optional_text(meta.get("createDate")),
                    update_date=normalize_optional_text(meta.get("updateDate")),
                    update_flag=bool_or_none(meta.get("updateFlag")),
                )
            )

    records.sort(key=lambda item: (item.part, item.question_type_label or "", item.topic_name.lower()))
    return records


def record_to_json(record: TopicRecord) -> dict[str, Any]:
    return {
        "source_topic_id": record.source_topic_id,
        "topic_name": record.topic_name,
        "part_group": record.part_group,
        "part": record.part,
        "observed_question_id": record.observed_question_id,
        "observed_question_text": record.observed_question_text,
        "question_count": record.question_count,
        "question_type": record.question_type,
        "question_type_label": record.question_type_label,
        "is_new": record.is_new,
        "time_tag": record.time_tag,
        "oral_nums": record.oral_nums,
        "recent_exam_count": record.recent_exam_count,
        "category_ids": list(record.category_ids),
        "category_labels": list(record.category_labels),
        "question_pic": record.question_pic,
        "topic_create_date": record.topic_create_date,
        "create_date": record.create_date,
        "update_date": record.update_date,
        "update_flag": record.update_flag,
    }


def summarize(records: list[TopicRecord]) -> dict[str, Any]:
    part1 = [record for record in records if record.part == 1]
    part2 = [record for record in records if record.part == 2]
    return {
        "record_count": len(records),
        "part1_topic_count": len(part1),
        "part2_topic_count": len(part2),
        "observed_question_count": len(records),
        "declared_question_count_total": sum(record.question_count for record in records),
        "coverage_note": "每条记录包含公开页面可见的首题；question_count 表示网页声明的该主题题量，不代表本次已抓到全部子题文本。",
    }


def build_markdown(records: list[TopicRecord], payload: dict[str, Any]) -> str:
    lines = [
        f"# {SEASON_TITLE}",
        "",
        f"- 来源：{SOURCE_URL}",
        f"- 生成时间：{payload['source']['generated_at']}",
        f"- 覆盖范围：{payload['source']['coverage']}",
        f"- 记录数：{payload['summary']['record_count']}",
        f"- Part 1 主题数：{payload['summary']['part1_topic_count']}",
        f"- Part 2/3 主题数：{payload['summary']['part2_topic_count']}",
        f"- 网页声明题量合计：{payload['summary']['declared_question_count_total']}",
        "",
        "> 注意：公开网页接口只暴露主题卡片和首题。完整 Part 1 子题、Part 3 追问需要 App 侧题目详情接口补齐。",
        "",
    ]
    for part, title in ((1, "Part 1"), (2, "Part 2&3")):
        lines.extend([f"## {title}", ""])
        for record in [item for item in records if item.part == part]:
            labels = "、".join(filter(None, [record.question_type_label, *record.category_labels]))
            suffix = f"（{labels}）" if labels else ""
            lines.append(f"### {record.topic_name}{suffix}")
            lines.append("")
            lines.append(f"- 主题 ID：`{record.source_topic_id}`")
            lines.append(f"- 网页声明题量：{record.question_count}")
            if record.time_tag:
                lines.append(f"- 时间标签：{record.time_tag}")
            if record.recent_exam_count is not None:
                lines.append(f"- 近期考试人数：{record.recent_exam_count}")
            lines.append("")
            lines.append(record.observed_question_text)
            lines.append("")
    return "\n".join(lines)


def build_sql(records: list[TopicRecord], generated_at: str) -> str:
    season_id = stable_uuid("season", SEASON_CODE)
    values = []
    values.append("begin;")
    values.append("set constraints all immediate;")
    values.append("update seasons set is_active = false where is_active = true and deleted_at is null;")
    values.append(
        f"""
insert into seasons (id, code, title, starts_on, ends_on, status, is_active)
values ({sql_uuid(season_id)}, {sql_text(SEASON_CODE)}, {sql_text(SEASON_TITLE)}, {sql_text(SEASON_STARTS_ON)}::date, {sql_text(SEASON_ENDS_ON)}::date, 'active', true)
on conflict (code) do update set
    title = excluded.title,
    starts_on = excluded.starts_on,
    ends_on = excluded.ends_on,
    status = 'active',
    is_active = true,
    updated_at = now(),
    deleted_at = null;
""".strip()
    )

    categories = {
        ("ieltsbro-part1", "Part 1"),
        ("ieltsbro-p23", "Part 2&3"),
        *{(f"ieltsbro-category-{key}", value) for key, value in CATEGORY_LABELS.items()},
    }
    for slug, name in sorted(categories):
        values.append(
            f"""
insert into topic_categories (id, name, slug)
values ({sql_uuid(stable_uuid("topic-category", slug))}, {sql_text(name)}, {sql_text(slug)})
on conflict (slug) do update set
    name = excluded.name,
    updated_at = now();
""".strip()
        )

    for record in records:
        topic_id = stable_uuid("topic", record.part_group, record.source_topic_id)
        question_id = stable_uuid("question", record.part_group, record.source_topic_id, record.observed_question_id)
        doc_id = stable_uuid("knowledge-doc", str(question_id))
        category_slug = category_slug_for(record)
        category_id = stable_uuid("topic-category", category_slug)
        topic_slug = slugify(f"ieltsbro-{record.part_group}-{record.source_topic_id}-{record.topic_name}")
        metadata = metadata_for(record, generated_at)
        question_content = knowledge_content(record)
        content_hash = hashlib.sha256(question_content.encode("utf-8")).hexdigest()
        embedding = vector_literal(hash_embedding(question_content))
        chunk_id = stable_uuid("knowledge-chunk", str(doc_id), "0")

        values.append(
            f"""
insert into topics (id, category_id, name, slug, status)
values ({sql_uuid(topic_id)}, {sql_uuid(category_id)}, {sql_text(record.topic_name)}, {sql_text(topic_slug)}, 'active')
on conflict (slug) do update set
    category_id = excluded.category_id,
    name = excluded.name,
    status = 'active',
    updated_at = now(),
    deleted_at = null;
""".strip()
        )
        values.append(
            f"""
insert into questions
    (id, season_id, topic_id, part, text, source_type, license, review_status, metadata)
values
    ({sql_uuid(question_id)}, {sql_uuid(season_id)}, {sql_uuid(topic_id)}, {record.part}, {sql_text(record.observed_question_text)},
     'user_recall', {sql_text("IELTSBRO public web page; local research use, verify rights before redistribution")}, 'active', {sql_json(metadata)}::jsonb)
on conflict (id) do update set
    season_id = excluded.season_id,
    topic_id = excluded.topic_id,
    part = excluded.part,
    text = excluded.text,
    source_type = excluded.source_type,
    license = excluded.license,
    review_status = 'active',
    metadata = excluded.metadata,
    updated_at = now(),
    deleted_at = null;
""".strip()
        )
        if record.part == 2:
            prompt, bullets = parse_cue_card(record.observed_question_text)
            values.append(
                f"""
insert into cue_cards (question_id, prompt, bullet_points, preparation_seconds, speaking_seconds)
values ({sql_uuid(question_id)}, {sql_text(prompt)}, {sql_text_array(bullets)}, 60, 120)
on conflict (question_id) do update set
    prompt = excluded.prompt,
    bullet_points = excluded.bullet_points,
    preparation_seconds = excluded.preparation_seconds,
    speaking_seconds = excluded.speaking_seconds,
    updated_at = now();
""".strip()
            )

        doc_metadata = {
            **metadata,
            "season_id": str(season_id),
            "part": str(record.part),
            "topic": record.topic_name,
            "topic_id": str(topic_id),
            "source_type": "user_recall",
            "question_id": str(question_id),
            "review_status": "active",
        }
        if record.part == 2:
            prompt, bullets = parse_cue_card(record.observed_question_text)
            doc_metadata.update(
                {
                    "has_cue_card": True,
                    "cue_card_prompt": prompt,
                    "cue_card_bullet_points": bullets,
                    "cue_card_preparation_seconds": 60,
                    "cue_card_speaking_seconds": 120,
                }
            )
        values.append(
            f"""
insert into knowledge_docs
    (id, doc_type, source_id, title, content_hash, metadata, status)
values
    ({sql_uuid(doc_id)}, 'question_bank', {sql_uuid(question_id)}, {sql_text(knowledge_title(record))},
     {sql_text(content_hash)}, {sql_json(doc_metadata)}::jsonb, 'active')
on conflict (id) do update set
    doc_type = excluded.doc_type,
    source_id = excluded.source_id,
    title = excluded.title,
    content_hash = excluded.content_hash,
    metadata = excluded.metadata,
    status = 'active',
    updated_at = now(),
    deleted_at = null;
delete from knowledge_chunks where doc_id = {sql_uuid(doc_id)};
insert into knowledge_chunks
    (id, doc_id, chunk_index, content, metadata, embedding, embedding_model, token_count)
values
    ({sql_uuid(chunk_id)}, {sql_uuid(doc_id)}, 0, {sql_text(question_content)}, {sql_json(doc_metadata)}::jsonb,
     {sql_text(embedding)}::vector, 'hash-embedding-v1', {len(TOKEN_RE.findall(question_content))});
""".strip()
        )

    values.append("commit;")
    return "\n\n".join(values) + "\n"


def metadata_for(record: TopicRecord, generated_at: str) -> dict[str, Any]:
    return {
        "source": "ieltsbro",
        "source_url": SOURCE_URL,
        "source_topic_id": record.source_topic_id,
        "source_question_id": record.observed_question_id,
        "part_group": record.part_group,
        "topic_name": record.topic_name,
        "question_type": record.question_type,
        "question_type_label": record.question_type_label,
        "is_new": record.is_new,
        "time_tag": record.time_tag,
        "question_count_declared": record.question_count,
        "coverage": "first_public_question_only",
        "coverage_note": "公开网页接口只暴露该主题首题；完整子题和 Part 3 追问需 App 侧接口补齐。",
        "category_ids": list(record.category_ids),
        "category_labels": list(record.category_labels),
        "oral_nums": record.oral_nums,
        "recent_exam_count": record.recent_exam_count,
        "question_pic": record.question_pic,
        "topic_create_date": record.topic_create_date,
        "create_date": record.create_date,
        "update_date": record.update_date,
        "update_flag": record.update_flag,
        "imported_at": generated_at,
    }


def knowledge_title(record: TopicRecord) -> str:
    return f"Part {record.part} {record.topic_name}: {record.observed_question_text[:72]}"


def knowledge_content(record: TopicRecord) -> str:
    lines = [
        f"Topic: {record.topic_name}",
        f"Part: {record.part}",
        f"Question: {record.observed_question_text}",
        f"Declared question count for this topic: {record.question_count}",
        "Coverage: first public question only; full sub-question list requires App-side detail data.",
    ]
    if record.question_type_label:
        lines.append(f"Question type: {record.question_type_label}")
    if record.category_labels:
        lines.append("Categories: " + ", ".join(record.category_labels))
    return "\n".join(lines)


def parse_cue_card(text: str) -> tuple[str, list[str]]:
    normalized = normalize_question_text(text)
    marker = "You should say:"
    if marker not in normalized:
        return normalized, []
    prompt, rest = normalized.split(marker, 1)
    bullets = [line.strip(" -") for line in rest.splitlines() if line.strip()]
    return prompt.strip(), bullets


def category_slug_for(record: TopicRecord) -> str:
    if record.part == 1:
        return "ieltsbro-part1"
    if record.category_ids:
        return f"ieltsbro-category-{record.category_ids[0]}"
    return "ieltsbro-p23"


def stable_uuid(*parts: str) -> UUID:
    return uuid5(NAMESPACE, ":".join(parts))


def stable_key(*parts: str) -> str:
    return hashlib.sha1(":".join(parts).encode("utf-8")).hexdigest()[:16]


def normalize_topic_id(item: dict[str, Any]) -> str:
    value = item.get("oralTopicId") or item.get("oralTopicCode")
    return normalize_text(value)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_question_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def normalize_optional_text(value: Any) -> str | None:
    text = normalize_text(value)
    return text or None


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def ieltsbro_is_new(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value == 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"0", "false", "no"}:
            return True
        if lowered in {"1", "true", "yes"}:
            return False
    return None


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:118] or hashlib.sha1(value.encode("utf-8")).hexdigest()[:24]


def sql_text(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_uuid(value: UUID) -> str:
    return f"{sql_text(str(value))}::uuid"


def sql_json(value: dict[str, Any]) -> str:
    return sql_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def sql_text_array(values: list[str]) -> str:
    if not values:
        return "'{}'::text[]"
    escaped = ",".join('"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' for value in values)
    return sql_text("{" + escaped + "}") + "::text[]"


def hash_embedding(text: str, dimension: int = 1536) -> list[float]:
    vector = [0.0] * dimension
    for token in TOKEN_RE.findall(text.lower()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def apply_sql(sql_path: Path, container: str, db_user: str, db_name: str) -> None:
    sql = sql_path.read_bytes()
    command = ["docker", "exec", "-i", container, "psql", "-U", db_user, "-d", db_name, "-v", "ON_ERROR_STOP=1"]
    completed = subprocess.run(command, input=sql, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.stdout:
        sys.stdout.write(completed.stdout.decode("utf-8", errors="replace"))
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr.decode("utf-8", errors="replace"))
        raise RuntimeError(f"psql 导入失败，退出码 {completed.returncode}")
    if completed.stderr:
        sys.stderr.write(completed.stderr.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    raise SystemExit(main())
