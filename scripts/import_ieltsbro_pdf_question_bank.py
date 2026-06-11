from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from import_ieltsbro_question_bank import (
    OUTPUT_DIR,
    ROOT,
    SEASON_CODE,
    SEASON_ENDS_ON,
    SEASON_STARTS_ON,
    SEASON_TITLE,
    TOKEN_RE,
    hash_embedding,
    slugify,
    sql_json,
    sql_text,
    sql_text_array,
    sql_uuid,
    stable_key,
    stable_uuid,
    vector_literal,
)


PDF_PATH = ROOT / "docs" / "2026年5-8月最新雅思口语题库-0525.pdf"
SOURCE_NAME = "IELTSBRO PDF"
SOURCE_TITLE = "2026年5-8月最新雅思口语题库-0525"
SOURCE_REVISION = "截止 5.25 18:00"
SOURCE_FILE = "docs/2026年5-8月最新雅思口语题库-0525.pdf"
LICENSE_NOTE = "IELTSBRO PDF 2026年5-8月; local research use, verify rights before redistribution"

REGION_LABELS = {
    "mainland": "大陆地区",
    "non_mainland": "非大陆地区",
}

SECTION_LABELS = {
    "new": "新题",
    "reused": "老题沿用",
    "evergreen": "万年老题",
}

QUESTION_TYPE_KEYS = {
    "新题": "new",
    "老题沿用": "reused",
    "万年老题": "evergreen",
}

QUESTION_LINE_TERMINAL_RE = re.compile(r"[?？.!。]$")
QUESTION_HEADER_RE = re.compile(r"^(\d+)\s+P([12])\s+(.+)$")
EVERGREEN_HEADER_RE = re.compile(r"^万年老题\s*(.+)$")
BULLET_START_RE = re.compile(
    r"^(What|Where|When|Who|Whom|Why|How|Whether|Which|And|If|To whom|With whom)\b",
    re.IGNORECASE,
)
PLACEHOLDER_NUMBERING_RE = re.compile(r"^\d+[\.\):：、-]*\s*")
PLACEHOLDER_LABEL_RE = re.compile(r"^(question|follow-?up(?: question)?|part \d+)\s*[:：-]\s*", re.IGNORECASE)
PLACEHOLDER_WHITESPACE_RE = re.compile(r"\s+")
PLACEHOLDER_EXACT = {
    "待补充",
    "待完善",
    "待填写",
    "待确认",
    "todo",
    "tbd",
    "placeholder",
    "to be added",
    "to be completed",
    "to be filled",
}
PLACEHOLDER_PREFIX = ("待补充", "待完善", "todo", "tbd", "placeholder")


@dataclass
class PdfTopicGroup:
    source_group_id: str
    part: int
    topic_name: str
    region_key: str
    section_key: str
    question_type_label: str
    source_order: int
    topic_number: int | None
    is_evergreen: bool = False
    pages: set[int] = field(default_factory=set)
    raw_questions: list[str] = field(default_factory=list)
    raw_cue_card: list[str] = field(default_factory=list)
    raw_part3: list[str] = field(default_factory=list)
    mode: str = "questions"


@dataclass(frozen=True)
class QuestionRecord:
    record_key: str
    part: int
    text: str
    topic_group: PdfTopicGroup
    sort_order: int
    source_pages: tuple[int, ...]
    cue_prompt: str | None = None
    cue_bullet_points: tuple[str, ...] = ()
    followup_texts: tuple[str, ...] = ()
    linked_part2_record_key: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="解析雅思哥 PDF 题库并导入本地题库/知识库")
    parser.add_argument("--pdf", type=Path, default=PDF_PATH, help="题库 PDF 路径")
    parser.add_argument("--apply", action="store_true", help="生成文件后直接写入 Docker Postgres")
    parser.add_argument(
        "--keep-public-web-active",
        action="store_true",
        help="保留此前公开网页首题版 active 记录；默认会归档以避免重复练习题",
    )
    parser.add_argument("--container", default="ielts_speaking-postgres-1")
    parser.add_argument("--db-user", default="ielts")
    parser.add_argument("--db-name", default="ielts_speaking")
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    groups = parse_pdf_groups(pdf_path)
    records = build_question_records(groups)
    if not groups or not records:
        raise RuntimeError("未能从 PDF 解析出题库内容")

    generated_at = datetime.now(timezone.utc).isoformat()
    json_path = OUTPUT_DIR / "ieltsbro_2026_05_08_pdf_question_bank.json"
    md_path = OUTPUT_DIR / "ieltsbro_2026_05_08_pdf_question_bank.md"
    sql_path = OUTPUT_DIR / "ieltsbro_2026_05_08_pdf_question_bank.sql"

    payload = {
        "source": {
            "name": SOURCE_NAME,
            "title": SOURCE_TITLE,
            "revision": SOURCE_REVISION,
            "file": SOURCE_FILE,
            "pdf_path": str(pdf_path),
            "generated_at": generated_at,
            "coverage": "full_pdf_extraction",
            "coverage_note": "解析 PDF 正文中的 Part 1 子题、Part 2 题卡和 Part 3 追问；不把使用指南和 Q&A 当作题库题目导入。",
        },
        "season": {
            "code": SEASON_CODE,
            "title": SEASON_TITLE,
            "starts_on": SEASON_STARTS_ON,
            "ends_on": SEASON_ENDS_ON,
        },
        "summary": summarize(groups, records),
        "groups": [group_to_json(group) for group in groups],
        "records": [record_to_json(record) for record in records],
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(groups, payload), encoding="utf-8")
    sql_path.write_text(
        build_sql(records, generated_at, archive_public_web=not args.keep_public_web_active),
        encoding="utf-8",
    )

    print(f"生成 JSON: {json_path}")
    print(f"生成 Markdown: {md_path}")
    print(f"生成 SQL: {sql_path}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))

    if args.apply:
        apply_sql(sql_path, args.container, args.db_user, args.db_name)
        print("数据库导入完成")

    return 0


def parse_pdf_groups(pdf_path: Path) -> list[PdfTopicGroup]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("缺少 PyMuPDF，请先安装 pymupdf 后再解析 PDF") from exc

    groups: list[PdfTopicGroup] = []
    current_group: PdfTopicGroup | None = None
    current_region = ""
    current_section = ""
    current_question_type = ""
    source_order = 0
    evergreen_order = 0

    document = fitz.open(pdf_path)
    for page_number, page in enumerate(document, start=1):
        if page_number < 6:
            continue
        for line in extract_page_lines(page, page_number):
            region = detect_region_heading(line)
            if region is not None:
                current_region, current_section, current_question_type = region
                continue
            if re.match(r"^Part\s+1\b", line) or re.match(r"^Part\s+2&3\b", line):
                continue

            question_header = QUESTION_HEADER_RE.match(line)
            evergreen_header = EVERGREEN_HEADER_RE.match(line)
            if question_header or evergreen_header:
                if evergreen_header:
                    evergreen_order += 1
                    part = 1
                    topic_number = None
                    topic_name = evergreen_header.group(1).strip()
                    section_key = "evergreen"
                    question_type_label = "万年老题"
                    group_order = evergreen_order
                else:
                    topic_number = int(question_header.group(1))
                    part = int(question_header.group(2))
                    topic_name = question_header.group(3).strip()
                    section_key = current_section
                    question_type_label = current_question_type
                    group_order = topic_number

                source_order += 1
                current_group = PdfTopicGroup(
                    source_group_id=build_group_id(
                        region_key=current_region,
                        section_key=section_key,
                        part=part,
                        order=group_order,
                        topic_name=topic_name,
                    ),
                    part=part,
                    topic_name=topic_name,
                    region_key=current_region,
                    section_key=section_key,
                    question_type_label=question_type_label,
                    source_order=source_order,
                    topic_number=topic_number,
                    is_evergreen=evergreen_header is not None,
                    mode="cue_card" if part == 2 else "questions",
                )
                current_group.pages.add(page_number)
                groups.append(current_group)
                continue

            if line == "P3" and current_group and current_group.part == 2:
                current_group.mode = "part3"
                current_group.pages.add(page_number)
                continue

            if current_group is None:
                continue
            current_group.pages.add(page_number)
            if current_group.part == 1:
                current_group.raw_questions.append(line)
            elif current_group.mode == "part3":
                current_group.raw_part3.append(line)
            else:
                current_group.raw_cue_card.append(line)

    validate_groups(groups)
    return groups


def extract_page_lines(page: Any, page_number: int) -> list[str]:
    lines: list[str] = []
    text = page.get_text("text").replace("\r", "")
    for raw_line in text.split("\n"):
        line = normalize_line(raw_line)
        if not line:
            continue
        if line == str(page_number):
            continue
        lines.append(line)
    return lines


def normalize_line(value: str) -> str:
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value.strip())


def normalize_question_text(value: str) -> str:
    text = PLACEHOLDER_WHITESPACE_RE.sub(" ", value.strip())
    if not text:
        return ""
    text = text.strip("\"'`“”‘’《》「」『』()[]{}")
    text = PLACEHOLDER_LABEL_RE.sub("", text)
    text = PLACEHOLDER_NUMBERING_RE.sub("", text)
    text = text.strip("\"'`“”‘’《》「」『』()[]{}")
    text = text.rstrip(" .?!？！。,:：;；\"'`“”‘’")
    return PLACEHOLDER_WHITESPACE_RE.sub(" ", text).strip().lower()


def is_placeholder_question_text(value: str) -> bool:
    normalized = normalize_question_text(value)
    if not normalized:
        return False
    if normalized in PLACEHOLDER_EXACT:
        return True
    return any(
        normalized.startswith(f"{prefix}:") or normalized.startswith(f"{prefix} ")
        for prefix in PLACEHOLDER_PREFIX
    )


def detect_region_heading(line: str) -> tuple[str, str, str] | None:
    if re.match(r"^一、", line):
        return "mainland", "new", "新题"
    if re.match(r"^二、", line):
        return "mainland", "reused", "老题沿用"
    if re.match(r"^三、", line):
        return "non_mainland", "new", "新题"
    return None


def build_group_id(*, region_key: str, section_key: str, part: int, order: int, topic_name: str) -> str:
    text_part = re.sub(r"[^a-zA-Z0-9]+", "-", topic_name.lower()).strip("-")
    if not text_part:
        text_part = stable_key("pdf-topic", topic_name)
    return f"pdf-{region_key}-{section_key}-p{part}-{order:02d}-{text_part[:48]}"


def validate_groups(groups: list[PdfTopicGroup]) -> None:
    if len(groups) != 108:
        raise RuntimeError(f"PDF 题组数量异常，期望 108，实际 {len(groups)}")
    part1 = [group for group in groups if group.part == 1]
    part2 = [group for group in groups if group.part == 2]
    if len(part1) != 46 or len(part2) != 62:
        raise RuntimeError(f"PDF 题组结构异常，Part 1={len(part1)}，Part 2={len(part2)}")


def build_question_records(groups: list[PdfTopicGroup]) -> list[QuestionRecord]:
    records: list[QuestionRecord] = []
    for group in groups:
        if group.part == 1:
            questions = merge_question_lines(group.raw_questions)
            for index, question in enumerate(questions, start=1):
                records.append(
                    QuestionRecord(
                        record_key=f"{group.source_group_id}-q{index:02d}",
                        part=1,
                        text=question,
                        topic_group=group,
                        sort_order=index,
                        source_pages=tuple(sorted(group.pages)),
                    )
                )
            continue

        cue_prompt, cue_bullet_points = parse_cue_card(group.raw_cue_card)
        followups = filter_followup_questions(group.raw_part3)
        part2_key = f"{group.source_group_id}-part2"
        records.append(
            QuestionRecord(
                record_key=part2_key,
                part=2,
                text=cue_prompt,
                topic_group=group,
                sort_order=1,
                source_pages=tuple(sorted(group.pages)),
                cue_prompt=cue_prompt,
                cue_bullet_points=tuple(cue_bullet_points),
                followup_texts=tuple(followups),
            )
        )
        for index, followup in enumerate(followups, start=1):
            records.append(
                QuestionRecord(
                    record_key=f"{group.source_group_id}-p3-q{index:02d}",
                    part=3,
                    text=followup,
                    topic_group=group,
                    sort_order=index,
                    source_pages=tuple(sorted(group.pages)),
                    linked_part2_record_key=part2_key,
                )
            )

    validate_records(records, groups)
    return records


def merge_question_lines(lines: list[str]) -> list[str]:
    questions: list[str] = []
    current = ""
    for line in lines:
        current = f"{current} {line}".strip() if current else line
        if QUESTION_LINE_TERMINAL_RE.search(current):
            questions.append(current)
            current = ""
    if current:
        questions.append(current)
    return questions


def filter_followup_questions(lines: list[str]) -> list[str]:
    return [item for item in merge_question_lines(lines) if not is_placeholder_question_text(item)]


def parse_cue_card(lines: list[str]) -> tuple[str, list[str]]:
    marker = "You should say:"
    marker_index = lines.index(marker) if marker in lines else 1
    prompt = " ".join(lines[:marker_index]).strip()
    bullets: list[str] = []
    for line in lines[marker_index + 1 :]:
        if not bullets or BULLET_START_RE.match(line):
            bullets.append(line)
        else:
            bullets[-1] = f"{bullets[-1]} {line}".strip()
    if not prompt or not bullets:
        raise RuntimeError(f"题卡解析异常: prompt={prompt!r}, bullets={bullets!r}, raw={lines!r}")
    return prompt, bullets


def validate_records(records: list[QuestionRecord], groups: list[PdfTopicGroup]) -> None:
    part_counts = {1: 0, 2: 0, 3: 0}
    for record in records:
        part_counts[record.part] += 1
    skipped_placeholder_part3 = count_placeholder_part3_questions(groups)
    if part_counts[1] != 273 or part_counts[2] != 62 or part_counts[3] + skipped_placeholder_part3 != 351:
        raise RuntimeError(
            f"PDF 题目数量异常: kept={part_counts}, skipped_placeholder_part3={skipped_placeholder_part3}"
        )


def summarize(groups: list[PdfTopicGroup], records: list[QuestionRecord]) -> dict[str, Any]:
    group_counts: dict[str, int] = {}
    for group in groups:
        key = f"{REGION_LABELS[group.region_key]}-{SECTION_LABELS[group.section_key]}-Part {group.part}"
        group_counts[key] = group_counts.get(key, 0) + 1

    part_counts: dict[str, int] = {}
    for record in records:
        key = f"part{record.part}_question_count"
        part_counts[key] = part_counts.get(key, 0) + 1

    skipped_placeholder_part3 = count_placeholder_part3_questions(groups)
    return {
        "topic_group_count": len(groups),
        "part1_topic_group_count": sum(1 for group in groups if group.part == 1),
        "part2_topic_group_count": sum(1 for group in groups if group.part == 2),
        "question_record_count": len(records),
        **part_counts,
        "part3_placeholder_skipped_count": skipped_placeholder_part3,
        "group_counts": group_counts,
        "coverage_note": "PDF 题库正文全量解析；Part 2 题卡保留为 Part 2 题目，同时将 P3 追问作为 followup_templates 和独立 Part 3 题目入库。",
    }


def count_placeholder_part3_questions(groups: list[PdfTopicGroup]) -> int:
    return sum(
        1
        for group in groups
        if group.part == 2
        for question in merge_question_lines(group.raw_part3)
        if is_placeholder_question_text(question)
    )


def group_to_json(group: PdfTopicGroup) -> dict[str, Any]:
    return {
        "source_group_id": group.source_group_id,
        "part": group.part,
        "topic_name": group.topic_name,
        "region_key": group.region_key,
        "region_label": REGION_LABELS[group.region_key],
        "section_key": group.section_key,
        "section_label": SECTION_LABELS[group.section_key],
        "question_type_label": group.question_type_label,
        "source_order": group.source_order,
        "topic_number": group.topic_number,
        "is_evergreen": group.is_evergreen,
        "pages": sorted(group.pages),
        "p1_question_count": len(merge_question_lines(group.raw_questions)) if group.part == 1 else None,
        "p3_question_count": len(merge_question_lines(group.raw_part3)) if group.part == 2 else None,
    }


def record_to_json(record: QuestionRecord) -> dict[str, Any]:
    return {
        "question_id": str(question_id_for(record)),
        "record_key": record.record_key,
        "part": record.part,
        "text": record.text,
        "topic_group_id": record.topic_group.source_group_id,
        "topic_id": str(topic_id_for(record.topic_group)),
        "topic_name": record.topic_group.topic_name,
        "sort_order": record.sort_order,
        "source_pages": list(record.source_pages),
        "cue_prompt": record.cue_prompt,
        "cue_bullet_points": list(record.cue_bullet_points),
        "followup_texts": list(record.followup_texts),
        "linked_part2_question_id": linked_part2_question_id(record),
        "metadata": metadata_for(record, imported_at=None),
    }


def build_markdown(groups: list[PdfTopicGroup], payload: dict[str, Any]) -> str:
    lines = [
        f"# {SEASON_TITLE} PDF 全量题库",
        "",
        f"- 来源：{SOURCE_NAME}《{SOURCE_TITLE}》",
        f"- 版本：{SOURCE_REVISION}",
        f"- 文件：`{SOURCE_FILE}`",
        f"- 生成时间：{payload['source']['generated_at']}",
        f"- 题组数：{payload['summary']['topic_group_count']}",
        f"- 题目记录数：{payload['summary']['question_record_count']}",
        f"- Part 1 子题：{payload['summary']['part1_question_count']}",
        f"- Part 2 题卡：{payload['summary']['part2_question_count']}",
        f"- Part 3 追问：{payload['summary']['part3_question_count']}",
        "",
        "> 说明：使用指南与 Q&A 未作为题目导入；Part 3 追问同时挂到对应 Part 2 题卡，并作为独立 Part 3 题目保存。",
        "",
    ]

    for region_key, section_key in (
        ("mainland", "new"),
        ("mainland", "reused"),
        ("mainland", "evergreen"),
        ("non_mainland", "new"),
    ):
        selected = [group for group in groups if group.region_key == region_key and group.section_key == section_key]
        if not selected:
            continue
        lines.extend([f"## {REGION_LABELS[region_key]} {SECTION_LABELS[section_key]}", ""])
        for group in selected:
            title_prefix = "P1" if group.part == 1 else "P2&3"
            lines.extend([f"### {title_prefix} {group.topic_name}", ""])
            if group.part == 1:
                for index, question in enumerate(merge_question_lines(group.raw_questions), start=1):
                    lines.append(f"{index}. {question}")
                lines.append("")
                continue

            prompt, bullets = parse_cue_card(group.raw_cue_card)
            lines.append(prompt)
            lines.append("")
            lines.append("You should say:")
            for bullet in bullets:
                lines.append(f"- {bullet}")
            lines.append("")
            lines.append("Part 3:")
            for index, question in enumerate(merge_question_lines(group.raw_part3), start=1):
                lines.append(f"{index}. {question}")
            lines.append("")
    return "\n".join(lines)


def build_sql(records: list[QuestionRecord], generated_at: str, *, archive_public_web: bool) -> str:
    season_id = stable_uuid("season", SEASON_CODE)
    values: list[str] = []
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
    if archive_public_web:
        values.append(archive_public_web_sql(season_id))
    values.append(archive_placeholder_question_sql(season_id))

    for slug, name in sorted(categories_for_records(records).items()):
        values.append(
            f"""
insert into topic_categories (id, name, slug)
values ({sql_uuid(stable_uuid("topic-category", slug))}, {sql_text(name)}, {sql_text(slug)})
on conflict (slug) do update set
    name = excluded.name,
    updated_at = now();
""".strip()
        )

    inserted_topics: set[str] = set()
    part2_records = {record.record_key: record for record in records if record.part == 2}
    for record in records:
        group = record.topic_group
        topic_id = topic_id_for(group)
        if group.source_group_id not in inserted_topics:
            inserted_topics.add(group.source_group_id)
            values.append(topic_sql(group))

        question_id = question_id_for(record)
        metadata = metadata_for(record, imported_at=generated_at)
        values.append(question_sql(record, season_id, topic_id, question_id, metadata))

        if record.part == 2:
            values.append(cue_card_sql(question_id, record))
            values.append(f"delete from followup_templates where question_id = {sql_uuid(question_id)};")
            for index, followup in enumerate(record.followup_texts, start=1):
                values.append(followup_template_sql(question_id, followup, index))

        doc_metadata = knowledge_metadata_for(record, season_id, topic_id, metadata, part2_records)
        values.append(knowledge_sql(record, question_id, doc_metadata))

    values.append("commit;")
    return "\n\n".join(values) + "\n"


def archive_public_web_sql(season_id: UUID) -> str:
    return f"""
update questions
set review_status = 'archived', updated_at = now()
where season_id = {sql_uuid(season_id)}
  and deleted_at is null
  and metadata->>'source' = 'ieltsbro'
  and metadata->>'coverage' = 'first_public_question_only';

update knowledge_docs kd
set status = 'archived', updated_at = now()
from questions q
where kd.source_id = q.id
  and kd.doc_type = 'question_bank'
  and kd.deleted_at is null
  and q.season_id = {sql_uuid(season_id)}
  and q.metadata->>'source' = 'ieltsbro'
  and q.metadata->>'coverage' = 'first_public_question_only';

update topics t
set status = 'archived',
    deleted_at = coalesce(t.deleted_at, now()),
    updated_at = now()
where t.deleted_at is null
  and t.status = 'active'
  and (t.slug like 'ieltsbro-p1-%' or t.slug like 'ieltsbro-p23-%')
  and not exists (
      select 1
      from questions q
      where q.topic_id = t.id
        and q.deleted_at is null
        and q.review_status = 'active'
  );
""".strip()


def archive_placeholder_question_sql(season_id: UUID) -> str:
    placeholder_values = ", ".join(
        sql_text(value)
        for value in (
            "待补充",
            "待完善",
            "todo",
            "tbd",
            "placeholder",
            "to be added",
            "to be completed",
            "to be filled",
        )
    )
    return f"""
update knowledge_docs kd
set status = 'archived', updated_at = now()
from questions q
where kd.source_id = q.id
  and kd.doc_type = 'question_bank'
  and kd.deleted_at is null
  and q.season_id = {sql_uuid(season_id)}
  and q.deleted_at is null
  and q.review_status = 'active'
  and q.metadata->>'source' = 'ieltsbro_pdf'
  and q.metadata->>'coverage' = 'full_pdf_extraction'
  and lower(btrim(q.text)) in ({placeholder_values});

update questions
set review_status = 'archived', updated_at = now()
where season_id = {sql_uuid(season_id)}
  and deleted_at is null
  and review_status = 'active'
  and metadata->>'source' = 'ieltsbro_pdf'
  and metadata->>'coverage' = 'full_pdf_extraction'
  and lower(btrim(text)) in ({placeholder_values});
""".strip()


def categories_for_records(records: list[QuestionRecord]) -> dict[str, str]:
    categories: dict[str, str] = {}
    for record in records:
        slug = category_slug_for(record.topic_group)
        group = record.topic_group
        categories[slug] = f"{REGION_LABELS[group.region_key]} {SECTION_LABELS[group.section_key]}"
    return categories


def topic_sql(group: PdfTopicGroup) -> str:
    return f"""
insert into topics (id, category_id, name, slug, status)
values ({sql_uuid(topic_id_for(group))}, {sql_uuid(stable_uuid("topic-category", category_slug_for(group)))}, {sql_text(group.topic_name)}, {sql_text(topic_slug_for(group))}, 'active')
on conflict (slug) do update set
    category_id = excluded.category_id,
    name = excluded.name,
    status = 'active',
    updated_at = now(),
    deleted_at = null;
""".strip()


def question_sql(
    record: QuestionRecord,
    season_id: UUID,
    topic_id: UUID,
    question_id: UUID,
    metadata: dict[str, Any],
) -> str:
    return f"""
insert into questions
    (id, season_id, topic_id, part, text, source_type, license, review_status, metadata)
values
    ({sql_uuid(question_id)}, {sql_uuid(season_id)}, {sql_uuid(topic_id)}, {record.part}, {sql_text(record.text)},
     'user_recall', {sql_text(LICENSE_NOTE)}, 'active', {sql_json(metadata)}::jsonb)
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


def cue_card_sql(question_id: UUID, record: QuestionRecord) -> str:
    return f"""
insert into cue_cards (question_id, prompt, bullet_points, preparation_seconds, speaking_seconds)
values ({sql_uuid(question_id)}, {sql_text(record.cue_prompt)}, {sql_text_array(list(record.cue_bullet_points))}, 60, 120)
on conflict (question_id) do update set
    prompt = excluded.prompt,
    bullet_points = excluded.bullet_points,
    preparation_seconds = excluded.preparation_seconds,
    speaking_seconds = excluded.speaking_seconds,
    updated_at = now();
""".strip()


def followup_template_sql(part2_question_id: UUID, text: str, sort_order: int) -> str:
    followup_id = stable_uuid("pdf-followup-template", str(part2_question_id), str(sort_order))
    return f"""
insert into followup_templates (id, question_id, part, text, sort_order, review_status)
values ({sql_uuid(followup_id)}, {sql_uuid(part2_question_id)}, 3, {sql_text(text)}, {sort_order}, 'active')
on conflict (id) do update set
    question_id = excluded.question_id,
    part = excluded.part,
    text = excluded.text,
    sort_order = excluded.sort_order,
    review_status = 'active',
    updated_at = now();
""".strip()


def knowledge_sql(record: QuestionRecord, question_id: UUID, metadata: dict[str, Any]) -> str:
    content = knowledge_content(record)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    chunk_id = stable_uuid("pdf-knowledge-chunk", str(question_id), "0")
    embedding = vector_literal(hash_embedding(content))
    return f"""
insert into knowledge_docs
    (id, doc_type, source_id, title, content_hash, metadata, status)
values
    ({sql_uuid(question_id)}, 'question_bank', {sql_uuid(question_id)}, {sql_text(knowledge_title(record))},
     {sql_text(content_hash)}, {sql_json(metadata)}::jsonb, 'active')
on conflict (id) do update set
    doc_type = excluded.doc_type,
    source_id = excluded.source_id,
    title = excluded.title,
    content_hash = excluded.content_hash,
    metadata = excluded.metadata,
    status = 'active',
    updated_at = now(),
    deleted_at = null;
delete from knowledge_chunks where doc_id = {sql_uuid(question_id)};
insert into knowledge_chunks
    (id, doc_id, chunk_index, content, metadata, embedding, embedding_model, token_count)
values
    ({sql_uuid(chunk_id)}, {sql_uuid(question_id)}, 0, {sql_text(content)}, {sql_json(metadata)}::jsonb,
     {sql_text(embedding)}::vector, 'hash-embedding-v1', {len(TOKEN_RE.findall(content))});
""".strip()


def metadata_for(record: QuestionRecord, imported_at: str | None) -> dict[str, Any]:
    group = record.topic_group
    metadata: dict[str, Any] = {
        "source": "ieltsbro_pdf",
        "source_name": SOURCE_NAME,
        "source_title": SOURCE_TITLE,
        "source_revision": SOURCE_REVISION,
        "source_file": SOURCE_FILE,
        "source_group_id": group.source_group_id,
        "source_record_key": record.record_key,
        "coverage": "full_pdf_extraction",
        "region_key": group.region_key,
        "region_label": REGION_LABELS[group.region_key],
        "section_key": group.section_key,
        "section_label": SECTION_LABELS[group.section_key],
        "question_type_label": group.question_type_label,
        "topic_name": group.topic_name,
        "topic_number": group.topic_number,
        "source_order": group.source_order,
        "sort_order": record.sort_order,
        "source_pages": list(record.source_pages),
        "is_evergreen": group.is_evergreen,
        "license_note": LICENSE_NOTE,
    }
    if imported_at is not None:
        metadata["imported_at"] = imported_at
    if record.part == 2:
        metadata.update(
            {
                "has_cue_card": True,
                "cue_card_prompt": record.cue_prompt,
                "cue_card_bullet_points": list(record.cue_bullet_points),
                "cue_card_preparation_seconds": 60,
                "cue_card_speaking_seconds": 120,
                "followup_count": len(record.followup_texts),
                "followup_templates": [
                    {
                        "followup_id": str(stable_uuid("pdf-followup-template", str(question_id_for(record)), str(index))),
                        "part": 3,
                        "text": text,
                        "trigger_hint": group.topic_name,
                        "sort_order": index,
                    }
                    for index, text in enumerate(record.followup_texts, start=1)
                ],
            }
        )
    if record.part == 3:
        metadata.update(
            {
                "linked_part2_question_id": linked_part2_question_id(record),
                "linked_part2_topic": group.topic_name,
                "discussion_level": "topic_followup",
                "discussion_focus": group.topic_name,
            }
        )
    return metadata


def knowledge_metadata_for(
    record: QuestionRecord,
    season_id: UUID,
    topic_id: UUID,
    metadata: dict[str, Any],
    part2_records: dict[str, QuestionRecord],
) -> dict[str, Any]:
    doc_metadata = {
        **metadata,
        "season_id": str(season_id),
        "part": str(record.part),
        "topic": record.topic_group.topic_name,
        "topic_id": str(topic_id),
        "source_type": "user_recall",
        "question_id": str(question_id_for(record)),
        "review_status": "active",
    }
    if record.linked_part2_record_key:
        linked = part2_records[record.linked_part2_record_key]
        doc_metadata["linked_part2_question_text"] = linked.text
    return doc_metadata


def knowledge_title(record: QuestionRecord) -> str:
    text = record.text.strip()
    if len(text) > 80:
        text = text[:77].rstrip() + "..."
    return f"Part {record.part} {record.topic_group.topic_name}: {text}"


def knowledge_content(record: QuestionRecord) -> str:
    group = record.topic_group
    lines = [
        f"Topic: {group.topic_name}",
        f"Part: {record.part}",
        f"Region: {REGION_LABELS[group.region_key]}",
        f"Section: {SECTION_LABELS[group.section_key]}",
        f"Question type: {group.question_type_label}",
        f"Source: {SOURCE_NAME} {SOURCE_TITLE} ({SOURCE_REVISION})",
        f"Question: {record.text}",
    ]
    if record.part == 2:
        lines.extend(["Cue card:", record.cue_prompt or record.text, "You should say:"])
        lines.extend(f"- {point}" for point in record.cue_bullet_points)
        if record.followup_texts:
            lines.append("Part 3 follow-up questions:")
            lines.extend(f"- {question}" for question in record.followup_texts)
    if record.part == 3:
        lines.append(f"Linked Part 2 topic: {group.topic_name}")
        if record.linked_part2_record_key:
            lines.append(f"Linked Part 2 question id: {linked_part2_question_id(record)}")
    return "\n".join(lines)


def category_slug_for(group: PdfTopicGroup) -> str:
    return f"ieltsbro-pdf-{group.region_key}-{group.section_key}"


def topic_slug_for(group: PdfTopicGroup) -> str:
    return slugify(group.source_group_id)


def topic_id_for(group: PdfTopicGroup) -> UUID:
    return stable_uuid("pdf-topic", group.source_group_id)


def question_id_for(record: QuestionRecord) -> UUID:
    return stable_uuid("pdf-question", record.record_key)


def linked_part2_question_id(record: QuestionRecord) -> str | None:
    if not record.linked_part2_record_key:
        return None
    return str(stable_uuid("pdf-question", record.linked_part2_record_key))


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
