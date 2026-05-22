"""在不整本 openpyxl.save 的前提下向 xlsx 注入工作表（保留外部链接）。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"

_REL_WORKSHEET = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
)
_CT_WORKSHEET = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)

_Q_WORKSHEET = f"{{{_NS_MAIN}}}worksheet"
_Q_ROW = f"{{{_NS_MAIN}}}row"
_Q_C = f"{{{_NS_MAIN}}}c"
_Q_IS = f"{{{_NS_MAIN}}}is"
_Q_T = f"{{{_NS_MAIN}}}t"
_Q_SHEETDATA = f"{{{_NS_MAIN}}}sheetData"
_Q_OVERRIDE = f"{{{_NS_CT}}}Override"

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_SHEET_TAG_RE = re.compile(
    r"<sheet\s+[^>]*name=\"([^\"]*)\"[^>]*/>",
    re.IGNORECASE,
)
_SHEETS_BLOCK_RE = re.compile(
    r"(<sheets>)(.*?)(</sheets>)",
    re.DOTALL | re.IGNORECASE,
)
_REL_WORKSHEET_RE = re.compile(
    r'<Relationship\s+[^>]*Type="[^"]*relationships/worksheet"[^>]*/>',
    re.IGNORECASE,
)
_REL_ID_RE = re.compile(r'\bId="rId(\d+)"')
_SHEET_ID_RE = re.compile(r'\bsheetId="(\d+)"')
_WORKSHEET_PART_RE = re.compile(r"worksheets/sheet(\d+)\.xml")


def workbook_has_external_links(path: str | Path) -> bool:
    with zipfile.ZipFile(path, "r") as zf:
        return any(
            n.startswith("xl/externalLinks/") and n.endswith(".xml")
            for n in zf.namelist()
        )


def _col_letter(col: int) -> str:
    letters = ""
    n = col
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def build_worksheet_xml(
    headers: tuple[str, ...],
    rows: list[tuple],
    *,
    footer: str | None = None,
) -> bytes:
    """生成仅含 inlineStr 的最小 worksheet XML。"""
    root = ET.Element(
        _Q_WORKSHEET,
        attrib={
            "xmlns": _NS_MAIN,
            "xmlns:r": _NS_REL_DOC,
        },
    )
    sheet_data = ET.SubElement(root, _Q_SHEETDATA)

    def add_row(row_idx: int, values: tuple) -> None:
        row_el = ET.SubElement(
            sheet_data,
            _Q_ROW,
            attrib={"r": str(row_idx), "spans": f"1:{len(headers)}"},
        )
        for col_idx, val in enumerate(values, start=1):
            if val is None or val == "":
                continue
            ref = f"{_col_letter(col_idx)}{row_idx}"
            cell = ET.SubElement(
                row_el,
                _Q_C,
                attrib={"r": ref, "t": "inlineStr"},
            )
            is_el = ET.SubElement(cell, _Q_IS)
            t_el = ET.SubElement(is_el, _Q_T)
            t_el.text = str(val)

    add_row(1, headers)
    if not rows:
        add_row(2, ("（本区无 findings）",) + (None,) * (len(headers) - 1))
    else:
        for r_idx, row in enumerate(rows, start=2):
            padded = tuple(row) + (None,) * max(0, len(headers) - len(row))
            add_row(r_idx, padded[: len(headers)])
    if footer:
        footer_row = (len(rows) + 3) if rows else 3
        add_row(footer_row, (footer,) + (None,) * (len(headers) - 1))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _sheet_name_to_rid(workbook_xml: bytes, rels_xml: bytes, name: str) -> str | None:
    text = workbook_xml.decode("utf-8", errors="replace")
    rid: str | None = None
    for m in _SHEET_TAG_RE.finditer(text):
        if m.group(1) == name:
            tag = m.group(0)
            rm = re.search(r'\br:id="(rId\d+)"', tag)
            if rm:
                rid = rm.group(1)
                break
    return rid


def _rid_to_worksheet_path(rels_xml: bytes, rid: str) -> str | None:
    text = rels_xml.decode("utf-8", errors="replace")
    for m in _REL_WORKSHEET_RE.finditer(text):
        tag = m.group(0)
        if f'Id="{rid}"' not in tag:
            continue
        tm = re.search(r'\bTarget="([^"]+)"', tag)
        if tm:
            target = tm.group(1)
            return f"xl/{target}" if not target.startswith("/") else target.lstrip("/")
    return None


def _new_sheet_tag(sheet_name: str, sheet_id: int, rid: str) -> str:
    return (
        f'<sheet xmlns:r="{_R_NS}" name="{sheet_name}" '
        f'sheetId="{sheet_id}" r:id="{rid}"/>'
    )


def _patch_workbook_sheets(
    workbook_xml: bytes,
    *,
    remove_names: set[str],
    new_sheet_tags: list[str],
) -> bytes:
    """仅改写 ``<sheets>`` 内层，保留 ``externalReference`` 等其余字节结构。"""
    text = workbook_xml.decode("utf-8")
    m = _SHEETS_BLOCK_RE.search(text)
    if not m:
        raise ValueError("workbook.xml 缺少 <sheets> 块")
    open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
    inner_text = inner
    for sm in list(_SHEET_TAG_RE.finditer(inner_text)):
        if sm.group(1) in remove_names:
            inner_text = inner_text.replace(sm.group(0), "", 1)
    new_inner = "".join(new_sheet_tags) + inner_text
    new_text = text[: m.start()] + open_tag + new_inner + close_tag + text[m.end() :]
    return new_text.encode("utf-8")


def _remove_worksheet_relationships(rels_xml: bytes, targets: set[str]) -> bytes:
    text = rels_xml.decode("utf-8")
    for m in list(_REL_WORKSHEET_RE.finditer(text)):
        tag = m.group(0)
        tm = re.search(r'\bTarget="([^"]+)"', tag)
        if tm and tm.group(1) in targets:
            text = text.replace(tag, "", 1)
    return text.encode("utf-8")


def _append_worksheet_relationships(rels_xml: bytes, pairs: list[tuple[str, str]]) -> bytes:
    """追加 worksheet Relationship，``pairs`` = (rId, Target)。"""
    text = rels_xml.decode("utf-8")
    lines = []
    for rid, target in pairs:
        lines.append(
            f'<Relationship Id="{rid}" Type="{_REL_WORKSHEET}" Target="{target}"/>'
        )
    insert = "".join(lines)
    close = "</Relationships>"
    pos = text.rfind(close)
    if pos < 0:
        raise ValueError("workbook.xml.rels 缺少 </Relationships>")
    return (text[:pos] + insert + text[pos:]).encode("utf-8")


def _ensure_content_types(ct_xml: bytes, sheet_nums: list[int]) -> bytes:
    text = ct_xml.decode("utf-8")
    for num in sheet_nums:
        part = f"/xl/worksheets/sheet{num}.xml"
        if part in text:
            continue
        override = (
            f'<Override PartName="{part}" ContentType="{_CT_WORKSHEET}"/>'
        )
        close = "</Types>"
        pos = text.rfind(close)
        if pos < 0:
            raise ValueError("[Content_Types].xml 缺少 </Types>")
        text = text[:pos] + override + text[pos:]
    return text.encode("utf-8")


def _rewrite_zip(
    path: Path,
    *,
    updates: dict[str, bytes],
    remove: set[str],
) -> None:
    """按原 ZipInfo 复制未改条目，避免破坏 OOXML 结构。"""
    tmp = path.with_name(path.stem + "._qc_tmp" + path.suffix)
    try:
        with zipfile.ZipFile(path, "r") as zin:
            with zipfile.ZipFile(tmp, "w") as zout:
                seen: set[str] = set()
                for info in zin.infolist():
                    if info.filename in remove:
                        continue
                    data = updates.pop(info.filename, zin.read(info.filename))
                    zout.writestr(info, data)
                    seen.add(info.filename)
                for name, data in updates.items():
                    if name not in seen:
                        zout.writestr(
                            name, data, compress_type=zipfile.ZIP_DEFLATED
                        )
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def inject_worksheets_at_front(
    workbook_path: str | Path,
    sheet_plans: list[tuple[str, bytes]],
    *,
    remove_sheet_names: tuple[str, ...] = (),
) -> None:
    """
    将工作表插入最前；**不**用 ElementTree 重写 workbook.xml（避免破坏 ``r:id`` 外链）。
    """
    path = Path(workbook_path)
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        archive = {n: zf.read(n) for n in names}

    wb_key = "xl/workbook.xml"
    rels_key = "xl/_rels/workbook.xml.rels"
    ct_key = "[Content_Types].xml"
    if wb_key not in archive or rels_key not in archive:
        raise ValueError("非标准 xlsx：缺少 workbook 或 rels")

    remove_set = set(remove_sheet_names)
    remove_targets: set[str] = set()
    rels_xml = archive[rels_key]
    wb_xml = archive[wb_key]

    for name in remove_set:
        rid = _sheet_name_to_rid(wb_xml, rels_xml, name)
        if not rid:
            continue
        target_path = _rid_to_worksheet_path(rels_xml, rid)
        if target_path:
            remove_targets.add(target_path.replace("xl/", ""))
            archive.pop(target_path, None)
            archive.pop(f"{target_path}.rels", None)

    rels_xml = _remove_worksheet_relationships(rels_xml, remove_targets)

    keys_blob = "\n".join(archive.keys())
    max_sheet_num = max(
        (int(m.group(1)) for m in _WORKSHEET_PART_RE.finditer(keys_blob)),
        default=0,
    )
    rels_text = rels_xml.decode("utf-8", errors="replace")
    max_rid = max(
        (int(m.group(1)) for m in _REL_ID_RE.finditer(rels_text)),
        default=0,
    )
    wb_text = wb_xml.decode("utf-8", errors="replace")
    max_sheet_id = max(
        (int(m.group(1)) for m in _SHEET_ID_RE.finditer(wb_text)),
        default=0,
    )

    new_sheet_tags: list[str] = []
    new_rels: list[tuple[str, str]] = []
    new_sheet_nums: list[int] = []

    for offset, (sheet_name, ws_xml) in enumerate(sheet_plans, start=1):
        sheet_num = max_sheet_num + offset
        rid_num = max_rid + offset
        sheet_id = max_sheet_id + offset
        ws_path = f"xl/worksheets/sheet{sheet_num}.xml"
        target = f"worksheets/sheet{sheet_num}.xml"
        archive[ws_path] = ws_xml
        new_sheet_nums.append(sheet_num)
        new_rels.append((f"rId{rid_num}", target))
        new_sheet_tags.append(_new_sheet_tag(sheet_name, sheet_id, f"rId{rid_num}"))

    archive[wb_key] = _patch_workbook_sheets(
        wb_xml,
        remove_names=remove_set,
        new_sheet_tags=new_sheet_tags,
    )
    archive[rels_key] = _append_worksheet_relationships(rels_xml, new_rels)
    if ct_key in archive:
        archive[ct_key] = _ensure_content_types(archive[ct_key], new_sheet_nums)

    remove_paths: set[str] = set()
    for t in remove_targets:
        remove_paths.add(f"xl/{t}")
        remove_paths.add(f"xl/{t}.rels")

    patch: dict[str, bytes] = {
        wb_key: archive[wb_key],
        rels_key: archive[rels_key],
    }
    if ct_key in archive:
        patch[ct_key] = archive[ct_key]
    for offset, (_, ws_xml) in enumerate(sheet_plans, start=1):
        sheet_num = max_sheet_num + offset
        patch[f"xl/worksheets/sheet{sheet_num}.xml"] = ws_xml

    _rewrite_zip(path, updates=patch, remove=remove_paths)
