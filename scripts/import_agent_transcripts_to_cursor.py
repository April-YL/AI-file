"""Import agent-transcript JSONL files into Cursor SQLite for sidebar visibility.

Requires Cursor to be fully closed before running.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

APP = Path(os.environ["APPDATA"]) / "Cursor" / "User"
GLOBAL_DB = APP / "globalStorage" / "state.vscdb"
WS_ID = "3bfced73905b25feccd3f25ddd8399f1"
WS_DB = APP / "workspaceStorage" / WS_ID / "state.vscdb"
WS_URI = "file:///e%3A/AI%20file"
WS_FS_PATH = r"E:\AI file"
TRANSCRIPT_ROOT = Path(r"E:\AI file\agent-transcripts")
PATH_REWRITE = re.compile(r"d:\\AI file", re.I)
def _rewrite_paths(text: str) -> str:
    return PATH_REWRITE.sub(lambda _: r"E:\AI file", text)


def _extract_text(content: list | dict) -> str:
    if isinstance(content, str):
        return _rewrite_paths(content)
    if not isinstance(content, list):
        return _rewrite_paths(str(content))
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            parts.append(_rewrite_paths(str(block["text"])))
        elif block.get("type") == "tool_use":
            name = block.get("name", "tool")
            parts.append(f"[Tool: {name}]")
    return "\n".join(parts).strip()


def _parse_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _first_user_title(rows: list[dict]) -> str:
    for row in rows:
        if row.get("role") != "user":
            continue
        msg = row.get("message", {})
        text = _extract_text(msg.get("content", []))
        m = re.search(r"<user_query>\s*(.+?)(?:\n|$)", text, re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        else:
            title = re.sub(r"\s+", " ", text).strip()
        if title:
            return title[:80]
    return "Imported chat"


def _mtime_ms(path: Path) -> int:
    ts = path.stat().st_mtime
    return int(ts * 1000)


def _load_json(con: sqlite3.Connection, table: str, key: str) -> dict | None:
    row = con.execute(f"SELECT value FROM {table} WHERE key = ?", (key,)).fetchone()
    if not row or row[0] is None:
        return None
    val = row[0]
    if isinstance(val, bytes):
        val = val.decode("utf-8")
    return json.loads(val)


def _set_json(con: sqlite3.Connection, table: str, key: str, obj: dict) -> None:
    con.execute(
        f"INSERT OR REPLACE INTO {table} (key, value) VALUES (?, ?)",
        (key, json.dumps(obj, ensure_ascii=False)),
    )


def _template_bubble(composer_id: str, bubble_id: str, msg_type: int, text: str, created_at: int) -> dict:
    return {
        "_v": 3,
        "type": msg_type,
        "bubbleId": bubble_id,
        "composerId": composer_id,
        "text": text,
        "richText": text if msg_type == 1 else "",
        "createdAt": created_at,
        "tokenCountUpUntilHere": 0,
        "tokenCount": 0,
    }


def _template_composer(
    composer_id: str,
    name: str,
    headers: list[dict],
    created_at: int,
    last_updated_at: int,
) -> dict:
    return {
        "_v": 13,
        "composerId": composer_id,
        "name": name,
        "status": "completed",
        "unifiedMode": "agent",
        "forceMode": "edit",
        "createdAt": created_at,
        "lastUpdatedAt": last_updated_at,
        "isAgentic": True,
        "hasLoaded": True,
        "fullConversationHeadersOnly": headers,
        "conversationMap": {},
        "context": {},
        "modelConfig": {"modelName": "default", "maxMode": False},
        "applied": True,
        "isDraft": False,
    }


def _header_entry(
    composer_id: str,
    name: str,
    created_at: int,
    last_updated_at: int,
    subtitle: str,
) -> dict:
    return {
        "type": "head",
        "composerId": composer_id,
        "name": name,
        "createdAt": created_at,
        "lastUpdatedAt": last_updated_at,
        "unifiedMode": "agent",
        "forceMode": "edit",
        "subtitle": subtitle[:120],
        "isArchived": False,
        "isDraft": False,
        "isWorktree": False,
        "isSpec": False,
        "workspaceIdentifier": {
            "id": WS_ID,
            "uri": {
                "$mid": 1,
                "fsPath": WS_FS_PATH,
                "external": WS_URI,
                "path": "/E:/AI file",
                "scheme": "file",
            },
        },
    }


def import_transcripts() -> int:
    if not TRANSCRIPT_ROOT.exists():
        raise SystemExit(f"Missing transcript root: {TRANSCRIPT_ROOT}")
    if not GLOBAL_DB.exists() or not WS_DB.exists():
        raise SystemExit("Cursor databases not found. Open the project in Cursor once, then close Cursor.")

    backup = GLOBAL_DB.with_suffix(".vscdb.bak-import")
    ws_backup = WS_DB.with_suffix(".vscdb.bak-import")
    shutil.copy2(GLOBAL_DB, backup)
    shutil.copy2(WS_DB, ws_backup)

    imported = 0
    gcon = sqlite3.connect(GLOBAL_DB)
    wcon = sqlite3.connect(WS_DB)
    try:
        headers_doc = _load_json(gcon, "ItemTable", "composer.composerHeaders") or {"allComposers": []}
        all_headers: list[dict] = headers_doc.setdefault("allComposers", [])
        existing_ids = {h.get("composerId") for h in all_headers if isinstance(h, dict)}

        ws_doc = _load_json(wcon, "ItemTable", "composer.composerData") or {}
        selected: list[str] = list(ws_doc.get("selectedComposerIds") or [])

        for jsonl in sorted(TRANSCRIPT_ROOT.glob("*/*.jsonl")):
            composer_id = jsonl.parent.name
            if composer_id in existing_ids:
                print(f"skip existing: {composer_id}")
                continue
            if gcon.execute(
                "SELECT 1 FROM cursorDiskKV WHERE key = ?",
                (f"composerData:{composer_id}",),
            ).fetchone():
                print(f"skip composerData exists: {composer_id}")
                continue

            rows = _parse_jsonl(jsonl)
            if not rows:
                continue

            title = _first_user_title(rows)
            created_at = _mtime_ms(jsonl)
            last_updated_at = created_at
            bubble_headers: list[dict] = []

            for i, row in enumerate(rows):
                role = row.get("role")
                if role not in {"user", "assistant"}:
                    continue
                msg_type = 1 if role == "user" else 2
                text = _extract_text(row.get("message", {}).get("content", []))
                if not text:
                    continue
                bubble_id = str(uuid.uuid4())
                bubble_headers.append({"bubbleId": bubble_id, "type": msg_type})
                bubble = _template_bubble(composer_id, bubble_id, msg_type, text, created_at + i)
                _set_json(gcon, "cursorDiskKV", f"bubbleId:{composer_id}:{bubble_id}", bubble)

            if not bubble_headers:
                continue

            composer = _template_composer(composer_id, title, bubble_headers, created_at, last_updated_at)
            _set_json(gcon, "cursorDiskKV", f"composerData:{composer_id}", composer)
            all_headers.append(_header_entry(composer_id, title, created_at, last_updated_at, title))
            if composer_id not in selected:
                selected.append(composer_id)
            existing_ids.add(composer_id)
            imported += 1
            print(f"imported: {composer_id[:8]}... | {title[:50]}")

        _set_json(gcon, "ItemTable", "composer.composerHeaders", headers_doc)
        ws_doc["selectedComposerIds"] = selected
        ws_doc["lastFocusedComposerIds"] = selected[:2]
        ws_doc.setdefault("hasMigratedComposerData", True)
        ws_doc.setdefault("hasMigratedMultipleComposers", True)
        _set_json(wcon, "ItemTable", "composer.composerData", ws_doc)

        gcon.commit()
        wcon.commit()
    except Exception:
        gcon.close()
        wcon.close()
        shutil.copy2(backup, GLOBAL_DB)
        shutil.copy2(ws_backup, WS_DB)
        raise
    finally:
        gcon.close()
        wcon.close()

    print(f"\nDone. Imported {imported} conversation(s).")
    print(f"Backups: {backup}")
    print(f"         {ws_backup}")
    print("Fully quit and reopen Cursor to refresh the sidebar.")
    return imported


if __name__ == "__main__":
    try:
        count = import_transcripts()
    except sqlite3.OperationalError as exc:
        if "database is locked" in str(exc).lower():
            raise SystemExit("Cursor appears to be running. Fully quit Cursor and retry.") from exc
        raise
    sys.exit(0 if count >= 0 else 1)
