#!/usr/bin/env python3
"""Adjust the styles of a Pandoc reference.docx (the Word part of a Typecase template).

Pandoc copies only the *look* of a reference document into exported Word files: the paragraph
styles (Normal, Body Text, Heading 1-3, Title, Block Text, ...), the page size and margins.
This script edits those settings directly in the DOCX (a ZIP with XML), so no word processor
is needed. Only the Python standard library is used.

Example:
    python3 style_docx.py assets/reference.docx out/reference.docx \
        --body-font "Liberation Serif" --body-size 12 --heading-font "Liberation Sans" \
        --line-spacing 2 --first-line-indent 1.25 --paper a4 --margins 25,50,25,25

Every option is optional; whatever you leave out stays as it is.
--page-numbers and --header-lines add a footer/header part to the document; Pandoc carries
headers and footers of the reference document over into every exported Word file.
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
HEADER_ID, FOOTER_ID = "rIdTypecaseHeader", "rIdTypecaseFooter"
PAPER_TWIPS = {  # width, height in twentieths of a point
    "a3": (16838, 23811),
    "a4": (11906, 16838),
    "a5": (8391, 11906),
    "letter": (12240, 15840),
    "legal": (12240, 20160),
}
TWIPS_PER_MM = 56.6929
TWIPS_PER_CM = 566.929


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def child(parent: ET.Element, tag: str, before: tuple[str, ...] = ()) -> ET.Element:
    """Find or create a direct child. `before` lists tags the new element must precede
    (Word is picky about element order inside pPr/rPr)."""
    found = parent.find(w(tag))
    if found is not None:
        return found
    element = ET.Element(w(tag))
    for index, existing in enumerate(list(parent)):
        if existing.tag in {w(t) for t in before}:
            parent.insert(index, element)
            return element
    parent.append(element)
    return element


# Order of the elements we touch inside w:pPr and w:rPr (subset of the OOXML schema order).
PPR_ORDER = ("keepNext", "keepLines", "pageBreakBefore", "widowControl", "numPr", "pBdr", "shd", "tabs",
             "spacing", "ind", "contextualSpacing", "jc", "outlineLvl", "rPr")
RPR_ORDER = ("rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "color", "spacing",
             "sz", "szCs", "u", "lang")


def after(tag: str, order: tuple[str, ...]) -> tuple[str, ...]:
    return order[order.index(tag) + 1 :]


def set_font(rpr: ET.Element, family: str) -> None:
    fonts = child(rpr, "rFonts", after("rFonts", RPR_ORDER))
    fonts.attrib.clear()
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(w(attribute), family)


def set_size(rpr: ET.Element, points: float) -> None:
    half_points = str(round(points * 2))
    child(rpr, "sz", after("sz", RPR_ORDER)).set(w("val"), half_points)
    child(rpr, "szCs", after("szCs", RPR_ORDER)).set(w("val"), half_points)


def set_color(rpr: ET.Element, color: str) -> None:
    element = child(rpr, "color", after("color", RPR_ORDER))
    element.attrib.clear()
    element.set(w("val"), color)


def style(styles: ET.Element, style_id: str) -> ET.Element | None:
    for element in styles.findall(w("style")):
        if element.get(w("styleId")) == style_id:
            return element
    return None


def ppr(element: ET.Element) -> ET.Element:
    return child(element, "pPr", ("rPr",))


def rpr(element: ET.Element) -> ET.Element:
    return child(element, "rPr")


def edit_styles(root: ET.Element, args) -> None:
    defaults = child(root, "docDefaults", ("latentStyles", "style"))
    default_rpr = child(child(defaults, "rPrDefault"), "rPr")
    default_ppr = child(child(defaults, "pPrDefault"), "pPr")

    if args.body_font:
        set_font(default_rpr, args.body_font)
    if args.body_size:
        set_size(default_rpr, args.body_size)
    if args.line_spacing:
        spacing = child(default_ppr, "spacing", after("spacing", PPR_ORDER))
        spacing.set(w("line"), str(round(240 * args.line_spacing)))
        spacing.set(w("lineRule"), "auto")
    if args.paragraph_spacing is not None:
        twips = str(round(args.paragraph_spacing * 20))
        for target in [default_ppr] + [ppr(s) for s in (style(root, "BodyText"),) if s is not None]:
            spacing = child(target, "spacing", after("spacing", PPR_ORDER))
            spacing.set(w("before"), "0")
            spacing.set(w("after"), twips)

    body = style(root, "BodyText")
    if body is not None:
        if args.first_line_indent is not None:
            ind = child(ppr(body), "ind", after("ind", PPR_ORDER))
            ind.set(w("firstLine"), str(round(args.first_line_indent * TWIPS_PER_CM)))
            # The first paragraph after a heading traditionally has no indent.
            first = style(root, "FirstParagraph")
            if first is not None:
                child(ppr(first), "ind", after("ind", PPR_ORDER)).set(w("firstLine"), "0")
        if args.align:
            child(ppr(body), "jc", after("jc", PPR_ORDER)).set(w("val"), "both" if args.align == "justify" else "left")

    heading_sizes = [float(x) for x in args.heading_sizes.split(",")] if args.heading_sizes else []
    for level in range(1, 10):
        heading = style(root, f"Heading{level}")
        if heading is None:
            continue
        properties = rpr(heading)
        if args.heading_font:
            set_font(properties, args.heading_font)
        if args.heading_color:
            set_color(properties, args.heading_color)
        if level <= len(heading_sizes):
            set_size(properties, heading_sizes[level - 1])
        if args.chapter_page_break and level == 1:
            child(ppr(heading), "pageBreakBefore", after("pageBreakBefore", PPR_ORDER))

    for style_id in ("Title", "Subtitle"):
        element = style(root, style_id)
        if element is None:
            continue
        if args.heading_font:
            set_font(rpr(element), args.heading_font)
        if args.title_align:
            child(ppr(element), "jc", after("jc", PPR_ORDER)).set(w("val"), "center" if args.title_align == "center" else "left")


def edit_document(root: ET.Element, args) -> None:
    body = root.find(w("body"))
    section = body.find(w("sectPr")) if body is not None else None
    if section is None:
        section = ET.SubElement(body, w("sectPr"))
    order = ("headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz", "pgMar",
             "cols", "titlePg", "docGrid")
    first_only = args.header_lines and args.header_first_page_only
    for kind, enabled, rid in (("header", args.header_lines, HEADER_ID), ("footer", args.page_numbers, FOOTER_ID)):
        if not enabled:
            continue
        for old in section.findall(w(f"{kind}Reference")):
            section.remove(old)
        reference = ET.Element(w(f"{kind}Reference"))
        # Header only on page 1 ("first"); page numbers from page 2 on when page 1 is special.
        reference.set(w("type"), "first" if kind == "header" and first_only else "default")
        reference.set(f"{{{R}}}id", rid)
        section.insert(0, reference)
    if first_only:
        child(section, "titlePg", after("titlePg", order))
    if args.paper:
        width, height = PAPER_TWIPS[args.paper]
        size = child(section, "pgSz", after("pgSz", order))
        size.set(w("w"), str(width))
        size.set(w("h"), str(height))
    if args.margins:
        top, right, bottom, left = (float(x) for x in args.margins.split(","))
        margins = child(section, "pgMar", after("pgMar", order))
        for name, value in (("top", top), ("right", right), ("bottom", bottom), ("left", left)):
            margins.set(w(name), str(round(value * TWIPS_PER_MM)))
        for name, value in (("header", "720"), ("footer", "720"), ("gutter", "0")):
            margins.attrib.setdefault(w(name), value)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def header_part(lines: list[str], font: str | None) -> str:
    fonts = f'<w:rFonts w:ascii="{_escape(font)}" w:hAnsi="{_escape(font)}" w:cs="{_escape(font)}"/>' if font else ""
    paragraphs = "".join(
        f'<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/><w:jc w:val="right"/></w:pPr>'
        f'<w:r><w:rPr>{fonts}{"<w:b/>" if index == 0 else ""}<w:sz w:val="{20 if index == 0 else 18}"/></w:rPr>'
        f'<w:t xml:space="preserve">{_escape(line)}</w:t></w:r></w:p>'
        for index, line in enumerate(lines)
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:hdr xmlns:w="{W}" xmlns:r="{R}">{paragraphs}</w:hdr>'


def footer_part(alignment: str) -> str:
    def run(inner: str) -> str:
        return f"<w:r>{inner}</w:r>"

    field = (
        run('<w:fldChar w:fldCharType="begin"/>')
        + run('<w:instrText xml:space="preserve"> PAGE </w:instrText>')
        + run('<w:fldChar w:fldCharType="separate"/>')
        + run("<w:t>1</w:t>")
        + run('<w:fldChar w:fldCharType="end"/>')
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:ftr xmlns:w="{W}" xmlns:r="{R}">'
        f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="{alignment}"/></w:pPr>{field}</w:p></w:ftr>'
    )


def add_relationship(rels: str, rid: str, kind: str, target: str) -> str:
    rels = re.sub(rf'<Relationship [^>]*Id="{rid}"[^>]*/>', "", rels)
    entry = f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}" Target="{target}"/>'
    return rels.replace("</Relationships>", entry + "</Relationships>")


def add_content_type(types: str, part: str, content_type: str) -> str:
    types = re.sub(rf'<Override [^>]*PartName="{re.escape(part)}"[^>]*/>', "", types)
    return types.replace("</Types>", f'<Override PartName="{part}" ContentType="{content_type}"/></Types>')


def rewrite_xml(data: bytes, edit, args) -> bytes:
    """Parse, edit and serialize while keeping every namespace declaration of the original root
    (ElementTree would drop unused ones, which can break mc:Ignorable)."""
    text = data.decode("utf-8")
    for prefix, uri in re.findall(r'xmlns:(\w+)="([^"]+)"', text):
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(data)
    edit(root, args)
    output = ET.tostring(root, encoding="unicode")
    original_root = re.search(r"<(\w+:\w+)\s[^>]*>", text.split("?>", 1)[-1])
    new_root = re.match(r"<(\w+:\w+)(\s[^>]*)?>", output)
    if original_root and new_root:
        declared = dict(re.findall(r'(xmlns(?::\w+)?)="([^"]+)"', original_root.group(0)))
        present = dict(re.findall(r'(xmlns(?::\w+)?)="([^"]+)"', new_root.group(0)))
        missing = "".join(f' {key}="{value}"' for key, value in declared.items() if key not in present)
        others = re.findall(r'\s((?:\w+:)?\w+)="([^"]*)"', original_root.group(0))
        extra = "".join(f' {k}="{v}"' for k, v in others if k.startswith("mc:") and k not in new_root.group(0))
        output = output[: new_root.end() - 1] + missing + extra + output[new_root.end() - 1 :]
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + output).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="reference.docx to start from (e.g. assets/reference.docx)")
    parser.add_argument("output", type=Path, help="where to write the adjusted reference.docx")
    parser.add_argument("--body-font", help='font family for normal text, e.g. "Liberation Serif"')
    parser.add_argument("--body-size", type=float, help="font size of normal text in points")
    parser.add_argument("--heading-font", help="font family for headings, title and subtitle")
    parser.add_argument("--heading-color", help='heading colour as hex without "#", e.g. 000000')
    parser.add_argument("--heading-sizes", help='sizes of heading 1,2,3,... in points, e.g. "18,14,12"')
    parser.add_argument("--line-spacing", type=float, help="1 = single, 1.5, 2 = double")
    parser.add_argument("--paragraph-spacing", type=float, help="space after each paragraph in points (0 for none)")
    parser.add_argument("--first-line-indent", type=float, help="first-line indent of body paragraphs in cm")
    parser.add_argument("--align", choices=("left", "justify"), help="alignment of body paragraphs")
    parser.add_argument("--title-align", choices=("left", "center"), help="alignment of title and subtitle")
    parser.add_argument("--chapter-page-break", action="store_true", help="start every heading 1 on a new page")
    parser.add_argument("--paper", choices=sorted(PAPER_TWIPS), help="page size")
    parser.add_argument("--margins", help="page margins in mm: top,right,bottom,left (e.g. 25,50,25,25)")
    parser.add_argument("--page-numbers", choices=("center", "right"), help="page number in the footer")
    parser.add_argument("--header-lines", help='small right-aligned header, lines separated by "|" (first line bold), e.g. a letterhead')
    parser.add_argument("--header-first-page-only", action="store_true", help="show the header on page 1 only (page numbers then start on page 2)")
    args = parser.parse_args()

    if args.margins and len(args.margins.split(",")) != 4:
        parser.error("--margins needs four numbers: top,right,bottom,left")
    if args.heading_color and not re.fullmatch(r"[0-9A-Fa-f]{6}", args.heading_color):
        parser.error("--heading-color must be six hex digits, e.g. 1F3864")

    try:
        source = zipfile.ZipFile(args.source)
    except (OSError, zipfile.BadZipFile) as error:
        print(f"Cannot read {args.source}: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix=".docx", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        ns = "application/vnd.openxmlformats-officedocument.wordprocessingml"
        extra_parts = {}
        if args.header_lines:
            lines = [line.strip() for line in args.header_lines.split("|") if line.strip()]
            extra_parts["word/typecase-header.xml"] = (header_part(lines, args.body_font), "header", HEADER_ID, f"{ns}.header+xml")
        if args.page_numbers:
            extra_parts["word/typecase-footer.xml"] = (footer_part(args.page_numbers), "footer", FOOTER_ID, f"{ns}.footer+xml")
        with source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                if item.filename in extra_parts:
                    continue  # replaced below
                data = source.read(item.filename)
                if item.filename == "word/styles.xml":
                    data = rewrite_xml(data, edit_styles, args)
                elif item.filename == "word/document.xml":
                    data = rewrite_xml(data, edit_document, args)
                elif item.filename == "word/_rels/document.xml.rels":
                    text = data.decode("utf-8")
                    for part, (_xml, kind, rid, _type) in extra_parts.items():
                        text = add_relationship(text, rid, kind, part.removeprefix("word/"))
                    data = text.encode("utf-8")
                elif item.filename == "[Content_Types].xml":
                    text = data.decode("utf-8")
                    for part, (_xml, _kind, _rid, content_type) in extra_parts.items():
                        text = add_content_type(text, "/" + part, content_type)
                    data = text.encode("utf-8")
                target.writestr(item, data)
            for part, (xml, *_rest) in extra_parts.items():
                target.writestr(part, xml.encode("utf-8"))
        shutil.move(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
