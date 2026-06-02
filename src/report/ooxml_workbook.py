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
_REL_COMMENTS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
_REL_VML = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing"
)
_CT_WORKSHEET = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)
_CT_COMMENTS = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"
)
_CT_VML = "application/vnd.openxmlformats-officedocument.vmlDrawing"

_Q_WORKSHEET = f"{{{_NS_MAIN}}}worksheet"
_Q_ROW = f"{{{_NS_MAIN}}}row"
_Q_C = f"{{{_NS_MAIN}}}c"
_Q_IS = f"{{{_NS_MAIN}}}is"
_Q_T = f"{{{_NS_MAIN}}}t"
_Q_SHEETDATA = f"{{{_NS_MAIN}}}sheetData"
_Q_HYPERLINKS = f"{{{_NS_MAIN}}}hyperlinks"
_Q_HYPERLINK = f"{{{_NS_MAIN}}}hyperlink"
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
_REL_TAG_RE = re.compile(r"<Relationship\s+[^>]*/>", re.IGNORECASE)
_REL_ID_RE = re.compile(r'\bId="rId(\d+)"')
_SHEET_ID_RE = re.compile(r'\bsheetId="(\d+)"')
_WORKSHEET_PART_RE = re.compile(r"worksheets/sheet(\d+)\.xml")
_COMMENTS_PART_RE = re.compile(r"comments/comment(\d+)\.xml")
_VML_PART_RE = re.compile(r"drawings/vmlDrawing(\d+)\.vml")


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
    hyperlinks: dict[tuple[int, int], str] | None = None,
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

    if hyperlinks:
        links_el = ET.SubElement(root, _Q_HYPERLINKS)
        for (row_idx, col_idx), location in sorted(hyperlinks.items()):
            if row_idx < 1 or col_idx < 1 or not location:
                continue
            ref = f"{_col_letter(col_idx)}{row_idx}"
            ET.SubElement(
                links_el,
                _Q_HYPERLINK,
                attrib={"ref": ref, "location": location},
            )

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


def _append_relationships(
    rels_xml: bytes,
    pairs: list[tuple[str, str, str]],
) -> bytes:
    """追加任意 Relationship，``pairs`` = (rId, Type, Target)。"""
    text = rels_xml.decode("utf-8")
    lines = [
        f'<Relationship Id="{rid}" Type="{typ}" Target="{target}"/>'
        for rid, typ, target in pairs
    ]
    close = "</Relationships>"
    pos = text.rfind(close)
    if pos < 0:
        raise ValueError("rels 缺少 </Relationships>")
    return (text[:pos] + "".join(lines) + text[pos:]).encode("utf-8")


def _empty_relationships_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_NS_PKG}"></Relationships>'
    ).encode("utf-8")


def _max_rid(rels_xml: bytes) -> int:
    text = rels_xml.decode("utf-8", errors="replace")
    return max((int(m.group(1)) for m in _REL_ID_RE.finditer(text)), default=0)


def _relationship_target_by_type(rels_xml: bytes, rel_type: str) -> str | None:
    text = rels_xml.decode("utf-8", errors="replace")
    for m in _REL_TAG_RE.finditer(text):
        tag = m.group(0)
        if f'Type="{rel_type}"' not in tag:
            continue
        tm = re.search(r'\bTarget="([^"]+)"', tag)
        if tm:
            return tm.group(1)
    return None


def _sheet_rels_path(sheet_path: str) -> str:
    directory, name = sheet_path.rsplit("/", 1)
    return f"{directory}/_rels/{name}.rels"


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


def _ensure_override(ct_xml: bytes, part_name: str, content_type: str) -> bytes:
    text = ct_xml.decode("utf-8")
    if part_name in text:
        return ct_xml
    override = f'<Override PartName="{part_name}" ContentType="{content_type}"/>'
    close = "</Types>"
    pos = text.rfind(close)
    if pos < 0:
        raise ValueError("[Content_Types].xml 缺少 </Types>")
    return (text[:pos] + override + text[pos:]).encode("utf-8")


def _ensure_vml_default(ct_xml: bytes) -> bytes:
    text = ct_xml.decode("utf-8")
    if 'Extension="vml"' in text:
        return ct_xml
    default = f'<Default Extension="vml" ContentType="{_CT_VML}"/>'
    close = "</Types>"
    pos = text.rfind(close)
    if pos < 0:
        raise ValueError("[Content_Types].xml 缺少 </Types>")
    return (text[:pos] + default + text[pos:]).encode("utf-8")


def _sheet_name_to_path_map(workbook_xml: bytes, rels_xml: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    text = workbook_xml.decode("utf-8", errors="replace")
    for m in _SHEET_TAG_RE.finditer(text):
        tag = m.group(0)
        name = m.group(1)
        rm = re.search(r'\br:id="(rId\d+)"', tag)
        if not rm:
            continue
        path = _rid_to_worksheet_path(rels_xml, rm.group(1))
        if path:
            result[name] = path
    return result


def _insert_legacy_drawing(sheet_xml: bytes, rid: str) -> bytes:
    text = sheet_xml.decode("utf-8")
    if "legacyDrawing" in text:
        return sheet_xml
    if "xmlns:r=" not in text.split(">", 1)[0]:
        text = text.replace(
            "<worksheet ",
            f'<worksheet xmlns:r="{_NS_REL_DOC}" ',
            1,
        )
    tag = f'<legacyDrawing r:id="{rid}"/>'
    ext_pos = text.find("<extLst")
    if ext_pos >= 0:
        return (text[:ext_pos] + tag + text[ext_pos:]).encode("utf-8")
    pos = text.rfind("</worksheet>")
    if pos >= 0:
        return (text[:pos] + tag + text[pos:]).encode("utf-8")
    raise ValueError("worksheet XML 缺少 </worksheet>")


def _build_comments_xml(cell_comments: list[tuple[str, str, str]]) -> bytes:
    root = ET.Element(_Q_WORKSHEET.replace("worksheet", "comments"), attrib={"xmlns": _NS_MAIN})
    authors = ET.SubElement(root, f"{{{_NS_MAIN}}}authors")
    author_by_name: dict[str, int] = {}
    for _, _, author in cell_comments:
        if author in author_by_name:
            continue
        author_by_name[author] = len(author_by_name)
        el = ET.SubElement(authors, f"{{{_NS_MAIN}}}author")
        el.text = author
    comment_list = ET.SubElement(root, f"{{{_NS_MAIN}}}commentList")
    for ref, text, author in cell_comments:
        comment = ET.SubElement(
            comment_list,
            f"{{{_NS_MAIN}}}comment",
            attrib={"ref": ref, "authorId": str(author_by_name[author])},
        )
        text_el = ET.SubElement(comment, f"{{{_NS_MAIN}}}text")
        run = ET.SubElement(text_el, f"{{{_NS_MAIN}}}r")
        t_el = ET.SubElement(run, f"{{{_NS_MAIN}}}t")
        t_el.text = text
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _build_vml_xml(cell_refs: list[str], *, shape_base: int = 1024) -> bytes:
    shapes = []
    for idx, ref in enumerate(cell_refs, start=1):
        row_num = int(re.search(r"\d+", ref).group(0)) if re.search(r"\d+", ref) else 1
        col_letters = re.sub(r"\d+", "", ref).upper()
        col_num = 0
        for ch in col_letters:
            col_num = col_num * 26 + (ord(ch) - 64)
        row_zero = max(row_num - 1, 0)
        col_zero = max(col_num - 1, 0)
        shape_id = f"_x0000_s{shape_base + idx}"
        shapes.append(
            f'<v:shape id="{shape_id}" type="#_x0000_t202" '
            'style="position:absolute;margin-left:80pt;margin-top:5pt;'
            'width:108pt;height:59.25pt;z-index:1;visibility:hidden" '
            'fillcolor="#ffffe1" o:insetmode="auto">'
            '<v:fill color2="#ffffe1"/>'
            '<v:shadow on="t" color="black" obscured="t"/>'
            '<v:path o:connecttype="none"/>'
            '<v:textbox style="mso-direction-alt:auto"><div style="text-align:left"></div></v:textbox>'
            '<x:ClientData ObjectType="Note">'
            '<x:MoveWithCells/><x:SizeWithCells/>'
            f"<x:Row>{row_zero}</x:Row><x:Column>{col_zero}</x:Column>"
            "</x:ClientData></v:shape>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<xml xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:x="urn:schemas-microsoft-com:office:excel">'
        '<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="1"/></o:shapelayout>'
        '<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" '
        'path="m,l,21600r21600,l21600,xe">'
        '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/>'
        '</v:shapetype>'
        + "".join(shapes)
        + "</xml>"
    )
    return xml.encode("utf-8")


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


def inject_cell_comments(
    workbook_path: str | Path,
    comments_by_sheet: dict[str, list[tuple[str, str, str]]],
) -> dict[str, int | list[str]]:
    """
    用 OOXML 原位注入传统 Excel 批注，避免 ``openpyxl.save`` 重写外链。

    ``comments_by_sheet``: ``{sheet_name: [(cell_ref, comment_text, author), ...]}``.
    首版只处理尚无既有 comments/vmlDrawing 的工作表；复杂既有批注表会跳过。
    """
    path = Path(workbook_path)
    with zipfile.ZipFile(path, "r") as zf:
        archive = {n: zf.read(n) for n in zf.namelist()}

    wb_key = "xl/workbook.xml"
    rels_key = "xl/_rels/workbook.xml.rels"
    ct_key = "[Content_Types].xml"
    if wb_key not in archive or rels_key not in archive or ct_key not in archive:
        raise ValueError("非标准 xlsx：缺少 workbook、rels 或 content types")

    sheet_paths = _sheet_name_to_path_map(archive[wb_key], archive[rels_key])
    keys_blob = "\n".join(archive.keys())
    max_comment_num = max(
        (int(m.group(1)) for m in _COMMENTS_PART_RE.finditer(keys_blob)),
        default=0,
    )
    max_vml_num = max(
        (int(m.group(1)) for m in _VML_PART_RE.finditer(keys_blob)),
        default=0,
    )

    updates: dict[str, bytes] = {}
    applied = 0
    skipped: list[str] = []
    new_index = 0
    ct_xml = archive[ct_key]

    for sheet_name, sheet_comments in comments_by_sheet.items():
        sheet_path = sheet_paths.get(sheet_name)
        if not sheet_path or not sheet_comments:
            skipped.append(sheet_name)
            continue
        sheet_xml = archive.get(sheet_path)
        if not sheet_xml:
            skipped.append(sheet_name)
            continue

        rel_path = _sheet_rels_path(sheet_path)
        rels_xml = archive.get(rel_path, _empty_relationships_xml())
        if (
            _relationship_target_by_type(rels_xml, _REL_COMMENTS)
            or _relationship_target_by_type(rels_xml, _REL_VML)
            or b"legacyDrawing" in sheet_xml
        ):
            skipped.append(sheet_name)
            continue

        new_index += 1
        comment_num = max_comment_num + new_index
        vml_num = max_vml_num + new_index
        comments_part = f"xl/comments/comment{comment_num}.xml"
        vml_part = f"xl/drawings/vmlDrawing{vml_num}.vml"
        comments_target = f"../comments/comment{comment_num}.xml"
        vml_target = f"../drawings/vmlDrawing{vml_num}.vml"

        max_rid = _max_rid(rels_xml)
        comments_rid = f"rId{max_rid + 1}"
        vml_rid = f"rId{max_rid + 2}"

        deduped: dict[str, list[str]] = {}
        author_by_cell: dict[str, str] = {}
        for cell_ref, text, author in sheet_comments:
            cell = cell_ref.replace("$", "").upper()
            if not cell:
                continue
            deduped.setdefault(cell, []).append(text)
            author_by_cell.setdefault(cell, author)
        merged = [
            (cell, "\n\n".join(texts), author_by_cell[cell])
            for cell, texts in sorted(deduped.items())
        ]
        if not merged:
            skipped.append(sheet_name)
            continue

        updates[comments_part] = _build_comments_xml(merged)
        updates[vml_part] = _build_vml_xml([cell for cell, _, _ in merged])
        updates[rel_path] = _append_relationships(
            rels_xml,
            [
                (comments_rid, _REL_COMMENTS, comments_target),
                (vml_rid, _REL_VML, vml_target),
            ],
        )
        updates[sheet_path] = _insert_legacy_drawing(sheet_xml, vml_rid)
        ct_xml = _ensure_override(
            ct_xml,
            f"/xl/comments/comment{comment_num}.xml",
            _CT_COMMENTS,
        )
        ct_xml = _ensure_vml_default(ct_xml)
        applied += len(merged)

    if updates:
        updates[ct_key] = ct_xml
        _rewrite_zip(path, updates=updates, remove=set())

    return {"applied": applied, "skipped_sheets": skipped}
