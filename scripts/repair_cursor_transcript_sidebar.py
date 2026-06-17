"""Repair/register imported agent transcripts in Cursor sidebar index.

Run with Cursor fully closed.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

APP = Path(os.environ["APPDATA"]) / "Cursor" / "User"
GLOBAL_DB = APP / "globalStorage" / "state.vscdb"
WS_ID = "3bfced73905b25feccd3f25ddd8399f1"
WS_DB = APP / "workspaceStorage" / WS_ID / "state.vscdb"
TRANSCRIPT_ROOT = Path(r"E:\AI file\agent-transcripts")
LOCAL_SESSION_IDS = {
    "637a9452-f7c4-4d43-807d-9825b05ce062",
    "6a53a677-1880-4bf4-8690-d026c303881b",
}


def _load(con: sqlite3.Connection, table: str, key: str):
    row = con.execute(f"SELECT value FROM {table} WHERE key = ?", (key,)).fetchone()
    if not row or row[0] is None:
        return None
    val = row[0]
    if isinstance(val, bytes):
        val = val.decode("utf-8")
    return json.loads(val)


def _set(con: sqlite3.Connection, table: str, key: str, obj: dict) -> None:
    con.execute(
        f"INSERT OR REPLACE INTO {table} (key, value) VALUES (?, ?)",
        (key, json.dumps(obj, ensure_ascii=False)),
    )


def _workspace_identifier() -> dict:
    return {
        "id": WS_ID,
        "uri": {
            "$mid": 1,
            "fsPath": "e:\\AI file",
            "_sep": 1,
            "external": "file:///e%3A/AI%20file",
            "path": "/e:/AI file",
            "scheme": "file",
        },
    }


def _header_template(composer_id: str, name: str, created_at: int, last_updated_at: int, subtitle: str) -> dict:
    return {
        "type": "head",
        "composerId": composer_id,
        "name": name,
        "createdAt": created_at,
        "lastUpdatedAt": last_updated_at,
        "unifiedMode": "agent",
        "forceMode": "edit",
        "hasUnreadMessages": False,
        "totalLinesAdded": 0,
        "totalLinesRemoved": 0,
        "isArchived": False,
        "isDraft": False,
        "isWorktree": False,
        "worktreeStartedReadOnly": False,
        "isSpec": False,
        "isProject": False,
        "isBestOfNSubcomposer": False,
        "numSubComposers": 0,
        "referencedPlans": [],
        "trackedGitRepos": [],
        "workspaceIdentifier": _workspace_identifier(),
        "hasBlockingPendingActions": False,
        "hasPendingPlan": False,
        "subtitle": subtitle[:160],
        "conversationCheckpointLastUpdatedAt": last_updated_at,
        "contextUsagePercent": 0,
        "filesChangedCount": 0,
    }


def _discover_import_ids(gcon: sqlite3.Connection) -> list[str]:
    ids: list[str] = []
    for jsonl in sorted(TRANSCRIPT_ROOT.glob("*/*.jsonl")):
        cid = jsonl.parent.name
        if cid in LOCAL_SESSION_IDS:
            continue
        if gcon.execute(
            "SELECT 1 FROM cursorDiskKV WHERE key = ?",
            (f"composerData:{cid}",),
        ).fetchone():
            ids.append(cid)
    return ids


def repair() -> int:
    if not GLOBAL_DB.exists() or not WS_DB.exists():
        raise SystemExit("Cursor databases not found.")

    backup = GLOBAL_DB.with_suffix(".vscdb.bak-repair")
    ws_backup = WS_DB.with_suffix(".vscdb.bak-repair")
    shutil.copy2(GLOBAL_DB, backup)
    shutil.copy2(WS_DB, ws_backup)

    gcon = sqlite3.connect(GLOBAL_DB)
    wcon = sqlite3.connect(WS_DB)
    registered = 0
    try:
        import_ids = _discover_import_ids(gcon)
        headers_doc = _load(gcon, "ItemTable", "composer.composerHeaders") or {"allComposers": []}
        all_headers: list[dict] = [
            h for h in headers_doc.get("allComposers", []) if isinstance(h, dict)
        ]
        import_set = set(import_ids)
        new_import_headers: list[dict] = []
        for cid in import_ids:
            composer = _load(gcon, "cursorDiskKV", f"composerData:{cid}")
            if not composer:
                continue
            name = composer.get("name") or f"Imported {cid[:8]}"
            created_at = int(composer.get("createdAt") or 0)
            last_updated_at = int(composer.get("lastUpdatedAt") or created_at)
            new_import_headers.append(
                _header_template(cid, name, created_at, last_updated_at, name)
            )
            registered += 1
            print(f"registered: {cid[:8]}... | {name[:50]}")

        kept = [
            h
            for h in all_headers
            if h.get("composerId") not in import_set
        ]
        headers_doc["allComposers"] = kept + new_import_headers
        _set(gcon, "ItemTable", "composer.composerHeaders", headers_doc)

        ws_doc = _load(wcon, "ItemTable", "composer.composerData") or {}
        selected = list(ws_doc.get("selectedComposerIds") or [])
        for cid in import_ids:
            if cid not in selected:
                selected.append(cid)
        ws_doc["selectedComposerIds"] = selected
        ws_doc["lastFocusedComposerIds"] = selected[:3]
        ws_doc.setdefault("hasMigratedComposerData", True)
        ws_doc.setdefault("hasMigratedMultipleComposers", True)
        _set(wcon, "ItemTable", "composer.composerData", ws_doc)

        # Ensure composerData has minimal fields Cursor expects
        for cid in import_ids:
            composer = _load(gcon, "cursorDiskKV", f"composerData:{cid}")
            if not composer:
                continue
            composer.setdefault("status", "completed")
            composer.setdefault("isAgentic", True)
            composer.setdefault("forceMode", "edit")
            composer.setdefault("unifiedMode", "agent")
            composer.setdefault("conversationMap", {})
            composer.setdefault("context", {})
            composer.setdefault("_v", 13)
            _set(gcon, "cursorDiskKV", f"composerData:{cid}", composer)

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

    print(f"\nRegistered {registered} imported chat(s) in composer.composerHeaders.")
    print(f"Backups: {backup}")
    print("Fully quit Cursor, reopen E:\\AI file, then check Agent sidebar.")
    return registered


if __name__ == "__main__":
    try:
        n = repair()
    except sqlite3.OperationalError as exc:
        if "database is locked" in str(exc).lower():
            raise SystemExit("Cursor is running. Fully quit Cursor and retry.") from exc
        raise
    sys.exit(0)
