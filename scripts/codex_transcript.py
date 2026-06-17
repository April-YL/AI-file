"""Parse Codex rollout JSONL sessions for export / Cursor sidebar import."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_WORKSPACE = Path(r"E:\AI file")
PATH_RE = re.compile(r"d:\\AI file", re.I)
THREAD_ID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.I,
)
INJECTED_MARKERS = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<permissions instructions>",
    "<app-context>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<plugins_instructions>",
)


def rewrite_paths(text: str) -> str:
    return PATH_RE.sub(lambda _: r"E:\AI file", text)


def normalize_workspace(path: str | Path) -> str:
    return str(Path(path)).replace("/", "\\").rstrip("\\").lower()


def load_thread_names(codex_home: Path) -> dict[str, str]:
    index_path = codex_home / "session_index.jsonl"
    names: dict[str, str] = {}
    if not index_path.exists():
        return names
    for line in index_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        thread_id = row.get("id")
        thread_name = row.get("thread_name")
        if thread_id and thread_name:
            names[str(thread_id)] = str(thread_name)
    return names


def discover_rollout_files(codex_home: Path) -> list[Path]:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return []
    return sorted(sessions_root.rglob("rollout-*.jsonl"))


def thread_id_from_path(path: Path) -> str | None:
    match = THREAD_ID_RE.search(path.stem)
    return match.group(1) if match else None


def is_injected_user_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if any(stripped.startswith(marker) for marker in INJECTED_MARKERS):
        return True
    if "<INSTRUCTIONS>" in stripped and "project-doc" in stripped:
        return True
    return False


def _parse_timestamp_ms(value: str | None, fallback_ms: int) -> int:
    if not value:
        return fallback_ms
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError:
        return fallback_ms


def _assistant_text_from_response(payload: dict) -> str | None:
    if payload.get("type") != "message" or payload.get("role") != "assistant":
        return None
    parts: list[str] = []
    for block in payload.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") in {"output_text", "text"} and block.get("text"):
            parts.append(str(block["text"]))
    text = "\n\n".join(parts).strip()
    return rewrite_paths(text) if text else None


def _tool_brief(payload: dict) -> str | None:
    if payload.get("type") != "function_call":
        return None
    name = payload.get("name", "tool")
    args_raw = payload.get("arguments") or "{}"
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        return f"`{name}`"
    brief_parts: list[str] = []
    for key in ("command", "path", "query", "description", "file_path", "pattern"):
        if key in args and args[key]:
            brief_parts.append(f"{key}={args[key]!r}")
            break
    if not brief_parts:
        brief_parts = [f"{k}={v!r}" for k, v in list(args.items())[:2]]
    brief = ", ".join(brief_parts)
    if len(brief) > 160:
        brief = brief[:157] + "..."
    return f"`{name}`({brief})" if brief else f"`{name}`"


@dataclass
class CodexTurn:
    role: str
    text: str
    tools: list[str] = field(default_factory=list)
    timestamp_ms: int = 0
    phase: str | None = None


@dataclass
class CodexSession:
    thread_id: str
    title: str
    cwd: str
    source_files: list[Path] = field(default_factory=list)
    turns: list[CodexTurn] = field(default_factory=list)
    updated_ms: int = 0

    @property
    def size_kb(self) -> float:
        total = sum(path.stat().st_size for path in self.source_files if path.exists())
        return round(total / 1024, 1)


def parse_rollout_file(path: Path, workspace: Path) -> CodexSession | None:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    if not rows:
        return None

    thread_id = thread_id_from_path(path)
    cwd = ""
    title = ""
    fallback_ms = int(path.stat().st_mtime * 1000)
    workspace_norm = normalize_workspace(workspace)

    for row in rows:
        if row.get("type") != "session_meta":
            continue
        payload = row.get("payload") or {}
        thread_id = str(payload.get("id") or thread_id or "")
        cwd = str(payload.get("cwd") or cwd)
        if not title:
            title = str(payload.get("thread_name") or "")
        break

    if not thread_id:
        return None
    if cwd and normalize_workspace(cwd) != workspace_norm:
        return None

    turns: list[CodexTurn] = []
    pending_tools: list[str] = []
    seen_assistant: set[str] = set()
    max_ts = fallback_ms

    for row in rows:
        ts = _parse_timestamp_ms(row.get("timestamp"), fallback_ms)
        max_ts = max(max_ts, ts)
        row_type = row.get("type")
        payload = row.get("payload") or {}

        if row_type == "response_item":
            tool_brief = _tool_brief(payload)
            if tool_brief:
                pending_tools.append(tool_brief)
                continue

            if payload.get("type") == "message" and payload.get("role") == "user":
                content = payload.get("content") or []
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "input_text":
                        text_parts.append(str(block.get("text") or ""))
                text = rewrite_paths("\n".join(text_parts).strip())
                if text and not is_injected_user_text(text):
                    turns.append(
                        CodexTurn(role="user", text=text, timestamp_ms=ts)
                    )
                continue

            assistant_text = _assistant_text_from_response(payload)
            if assistant_text:
                phase = payload.get("phase")
                key = f"{phase}:{assistant_text}"
                if key in seen_assistant:
                    continue
                seen_assistant.add(key)
                if phase == "commentary" and turns and turns[-1].role == "assistant":
                    if turns[-1].phase == "final_answer":
                        continue
                turn = CodexTurn(
                    role="assistant",
                    text=assistant_text,
                    tools=list(pending_tools),
                    timestamp_ms=ts,
                    phase=phase,
                )
                turns.append(turn)
                pending_tools = []
            continue

        if row_type != "event_msg":
            continue

        event_type = payload.get("type")
        if event_type == "user_message":
            text = rewrite_paths(str(payload.get("message") or "").strip())
            if text:
                turns.append(CodexTurn(role="user", text=text, timestamp_ms=ts))
            pending_tools = []
            continue

        if event_type == "agent_message":
            text = rewrite_paths(str(payload.get("message") or "").strip())
            if not text:
                continue
            phase = payload.get("phase")
            key = f"{phase}:{text}"
            if key in seen_assistant:
                continue
            seen_assistant.add(key)
            if phase == "commentary" and turns and turns[-1].role == "assistant":
                if turns[-1].phase == "final_answer" and turns[-1].text == text:
                    continue
            turns.append(
                CodexTurn(
                    role="assistant",
                    text=text,
                    tools=list(pending_tools),
                    timestamp_ms=ts,
                    phase=phase,
                )
            )
            pending_tools = []

    if not turns:
        return None

    cleaned: list[CodexTurn] = []
    for turn in turns:
        if (
            cleaned
            and cleaned[-1].role == turn.role
            and cleaned[-1].text == turn.text
            and cleaned[-1].phase == turn.phase
        ):
            continue
        cleaned.append(turn)

    return CodexSession(
        thread_id=thread_id,
        title=title or "Codex 会话",
        cwd=cwd or str(workspace),
        source_files=[path],
        turns=cleaned,
        updated_ms=max_ts,
    )


def merge_sessions(sessions: list[CodexSession], thread_names: dict[str, str]) -> list[CodexSession]:
    grouped: dict[str, list[CodexSession]] = {}
    for session in sessions:
        grouped.setdefault(session.thread_id, []).append(session)

    merged: list[CodexSession] = []
    for thread_id, items in grouped.items():
        items = sorted(items, key=lambda s: s.updated_ms)
        turns: list[CodexTurn] = []
        source_files: list[Path] = []
        cwd = items[-1].cwd
        updated_ms = items[-1].updated_ms
        title = thread_names.get(thread_id) or items[-1].title or "Codex 会话"

        for item in items:
            source_files.extend(item.source_files)
            for turn in item.turns:
                if (
                    turns
                    and turns[-1].role == turn.role
                    and turns[-1].text == turn.text
                    and turns[-1].phase == turn.phase
                ):
                    continue
                turns.append(turn)

        if not turns:
            continue
        if turns[0].role != "user":
            for turn in turns:
                if turn.role == "user":
                    title = title or turn.text[:80]
                    break

        merged.append(
            CodexSession(
                thread_id=thread_id,
                title=title,
                cwd=cwd,
                source_files=source_files,
                turns=turns,
                updated_ms=updated_ms,
            )
        )

    merged.sort(key=lambda s: s.updated_ms, reverse=True)
    return merged


def load_workspace_sessions(
    *,
    codex_home: Path = DEFAULT_CODEX_HOME,
    workspace: Path = DEFAULT_WORKSPACE,
) -> list[CodexSession]:
    thread_names = load_thread_names(codex_home)
    parsed = [
        session
        for path in discover_rollout_files(codex_home)
        if (session := parse_rollout_file(path, workspace)) is not None
    ]
    return merge_sessions(parsed, thread_names)


def slugify(title: str, max_len: int = 40) -> str:
    s = re.sub(r"<[^>]+>", "", title)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:max_len] or "codex-session").strip("-")


def display_title(session: CodexSession) -> str:
    for turn in session.turns:
        if turn.role == "user" and turn.text.strip():
            text = re.sub(r"\s+", " ", turn.text.strip())
            return text[:100]
    return session.title or "Codex 会话"
