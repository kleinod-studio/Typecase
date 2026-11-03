"""Renders the export HTML to a PDF with WeasyPrint, without GTK.

Runs as its own process (python3 -m typecase.pdf_render …), started by the export dialog, so
a slow or failing layout never blocks the window. WeasyPrint lays out real pages: it knows page
sizes and margins, footnotes at the bottom of the page and, through CSS, page numbers.

Only local files and data: URLs are loaded; anything from the network is left out."""

import argparse
import sys
from pathlib import Path


def available() -> bool:
    import importlib.util

    return importlib.util.find_spec("weasyprint") is not None


def page_css(width_mm: float, height_mm: float, margins_mm: dict) -> str:
    """Paper and margins from template.json; they win over @page rules in the template's CSS."""
    margin = " ".join(f"{margins_mm[side]}mm" for side in ("top", "right", "bottom", "left"))
    return f"@page {{ size: {width_mm}mm {height_mm}mm; margin: {margin}; }}"


def _local_only():
    from weasyprint.urls import URLFetcher

    return URLFetcher(allowed_protocols=("file", "data"))


def render(html: Path, base_dir: Path, output: Path, css: str) -> None:
    import weasyprint

    document = weasyprint.HTML(filename=str(html), base_url=base_dir.resolve().as_uri() + "/", url_fetcher=_local_only())
    document.write_pdf(str(output), stylesheets=[weasyprint.CSS(string=css)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="typecase.pdf_render")
    parser.add_argument("html", type=Path)
    parser.add_argument("base_dir", type=Path, help="folder that relative image paths refer to")
    parser.add_argument("output", type=Path)
    parser.add_argument("--paper-mm", required=True, help="width,height")
    parser.add_argument("--margins-mm", required=True, help="top,right,bottom,left")
    args = parser.parse_args(argv)
    width, height = (float(value) for value in args.paper_mm.split(","))
    margins = dict(zip(("top", "right", "bottom", "left"), (float(v) for v in args.margins_mm.split(","))))
    try:
        render(args.html, args.base_dir, args.output, page_css(width, height, margins))
    except Exception as error:  # reported to the user by the export dialog
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
