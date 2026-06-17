"""Import Codex sessions into Cursor chat sidebar as read-only history.

Requires Cursor to be fully closed before running.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_transcript import (
    DEFAULT_CODEX_HOME,
    DEFAULT_WORKSPACE,
    display_title,
    load_workspace_sessions,
)

APP = Path(os.environ["APPDATA"]) / "Cursor" / "User"
GLOBAL_DB = APP / "globalStorage" / "state.vscdb"
WS_ID = "3bfced73905b25feccd3f25ddd8399f1"
WS_DB = APP / "workspaceStorage" / WS_ID / "state.vscdb"
WS_URI = "file:///e%3A/AI%20file"
WS_FS_PATH = r"E:\AI file"
IMPORTED_PREFIX = "[Codex] "


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
        "text": text[:50000],
        "richText": text[:2000] if msg_type == 1 else "",
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


def _cursor_rows_from_session(session) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for turn in session.turns:
        text = turn.text.strip()
        if not text:
            continue
        if turn.role == "assistant" and turn.tools:
            tool_lines = "\n".join(f"- {tool}" for tool in turn.tools)
            text = f"{text}\n\n<details><summary>工具调用（{len(turn.tools)} 次）</summary>\n\n{tool_lines}\n\n</details>"
        rows.append((turn.role, text))
    return rows


def import_sessions() -> int:
    if not GLOBAL_DB.exists() or not WS_DB.exists():
        raise SystemExit("Cursor databases not found. Open the project in Cursor once, then close Cursor.")

    sessions = load_workspace_sessions(
        codex_home=DEFAULT_CODEX_HOME,
        workspace=DEFAULT_WORKSPACE,
    )
    if not sessions:
        print("No Codex sessions found for E:\\AI file.")
        return 0

    backup = GLOBAL_DB.with_suffix(".vscdb.bak-codex-import")
    ws_backup = WS_DB.with_suffix(".vscdb.bak-codex-import")
    shutil.copy2(GLOBAL_DB, backup)
    shutil.copy2(WS_DB, ws_backup)

    imported = 0
    gcon = sqlite3.connect(GLOBAL_DB)
    wcon = sqlite3.connect(WS_DB)
    try:
        headers_doc = _load_json(gcon, "ItemTable", "composer.composerHeaders") or {"allComposers": []}
        all_headers: list[dict] = headers_doc.setdefault("allComposers", [])
        existing_ids = {h.get("composerId") for h in all_headers if isinstance(h, dict)}
        existing_names = {
            h.get("name", "")
            for h in all_headers
            if isinstance(h, dict) and str(h.get("name", "")).startswith(IMPORTED_PREFIX)
        }

        ws_doc = _load_json(wcon, "ItemTable", "composer.composerData") or {}
        selected: list[str] = list(ws_doc.get("selectedComposerIds") or [])

        for session in sessions:
            composer_id = f"codex-{session.thread_id}"
            title = f"{IMPORTED_PREFIX}{display_title(session)}"
            if composer_id in existing_ids or title in existing_names:
                print(f"skip existing: {session.thread_id[:8]}... | {title[:60]}")
                continue
            if gcon.execute(
                "SELECT 1 FROM cursorDiskKV WHERE key = ?",
                (f"composerData:{composer_id}",),
            ).fetchone():
                print(f"skip composerData exists: {composer_id}")
                continue

            rows = _cursor_rows_from_session(session)
            if not rows:
                continue

            created_at = session.updated_ms - len(rows) * 1000
            last_updated_at = session.updated_ms
            bubble_headers: list[dict] = []
            ts = created_at

            for role, text in rows:
                msg_type = 1 if role == "user" else 2
                bubble_id = str(uuid.uuid4())
                bubble_headers.append({"bubbleId": bubble_id, "type": msg_type})
                bubble = _template_bubble(composer_id, bubble_id, msg_type, text, ts)
                _set_json(gcon, "cursorDiskKV", f"bubbleId:{composer_id}:{bubble_id}", bubble)
                ts += 1000

            composer = _template_composer(
                composer_id,
                title,
                bubble_headers,
                created_at,
                last_updated_at,
            )
            _set_json(gcon, "cursorDiskKV", f"composerData:{composer_id}", composer)
            all_headers.append(
                _header_entry(composer_id, title, created_at, last_updated_at, session.title)
            )
            if composer_id not in selected:
                selected.insert(0, composer_id)
            existing_ids.add(composer_id)
            existing_names.add(title)
            imported += 1
            print(f"imported: {session.thread_id[:8]}... | {title[:60]} | turns={len(rows)}")

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

    print(f"\nDone. Imported {imported} Codex conversation(s).")
    print(f"Backups: {backup}")
    print(f"         {ws_backup}")
    print("Fully quit and reopen Cursor to refresh the sidebar.")
    return imported


if __name__ == "__main__":
    try:
        count = import_sessions()
    except sqlite3.OperationalError as exc:
        if "database is locked" in str(exc).lower():
            raise SystemExit("Cursor appears to be running. Fully quit Cursor and retry.") from exc
        raise
    sys.exit(0 if count >= 0 else 1)
