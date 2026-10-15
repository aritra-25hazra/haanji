#!/usr/bin/env python3
"""research/REPORT.md -> research/REPORT.pdf, through a headless browser.

No LaTeX, no pandoc: the Markdown is rendered to HTML with a small print
stylesheet and Chromium (already installed for the visual checks) prints it.

    python research/harness/report_pdf.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "research" / "REPORT.md"
HTML = ROOT / "research" / "REPORT.html"
PDF = ROOT / "research" / "REPORT.pdf"

CSS = """
@page { size: A4; margin: 22mm 20mm 24mm 20mm; }
html { font-family: Georgia, "Times New Roman", serif; font-size: 10.5pt; line-height: 1.45; color: #1d2433; }
body { max-width: 170mm; margin: 0 auto; }
h1 { font-size: 20pt; line-height: 1.2; margin: 0 0 4pt; }
h2 { font-size: 13.5pt; margin: 20pt 0 6pt; border-bottom: 1px solid #c9cdd6; padding-bottom: 2pt; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; }
p { margin: 0 0 7pt; text-align: justify; hyphens: auto; }
.byline { color: #555b66; margin-bottom: 14pt; }
blockquote { margin: 8pt 0; padding: 6pt 12pt; border-left: 3px solid #1f4fd8; background: #f4f6fb; }
blockquote p { margin: 0; }
code { font-family: Menlo, Consolas, monospace; font-size: 9pt; background: #f1f2f5; padding: 0 2px; }
pre { font-family: Menlo, Consolas, monospace; font-size: 8.4pt; background: #f1f2f5; padding: 8pt; overflow: hidden; white-space: pre-wrap; border-radius: 3px; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; font-size: 8.2pt; margin: 6pt 0 10pt; page-break-inside: avoid; table-layout: auto; }
th, td { border: 1px solid #c9cdd6; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #eef1f7; font-weight: 700; white-space: normal !important; }
td:not(:first-child), th:not(:first-child) { text-align: right; white-space: nowrap; }
table.text td, table.text th { text-align: left; white-space: normal; }
img { max-width: 100%; display: block; margin: 8pt auto; page-break-inside: avoid; }
figure { margin: 10pt 0; page-break-inside: avoid; }
figcaption, .caption { font-size: 9pt; color: #555b66; text-align: center; margin-top: 2pt; }
ul, ol { margin: 0 0 8pt 18pt; padding: 0; }
li { margin-bottom: 2pt; }
hr { border: 0; border-top: 1px solid #c9cdd6; margin: 14pt 0; }
.refs p { font-size: 9.3pt; text-align: left; padding-left: 2em; text-indent: -2em; margin-bottom: 4pt; }
h2.break { page-break-before: always; }
a { color: #1f4fd8; text-decoration: none; }
"""


MERMAID_JS = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/11.4.1/mermaid.min.js"


def build_html(md_text: str, paper: bool = False) -> str:
    # Mermaid fences are handed to mermaid.js in the page rather than to the Markdown renderer.
    blocks: list[str] = []

    def stash(m):
        blocks.append(m.group(1))
        return f"\n\nMERMAIDBLOCK{len(blocks) - 1}\n\n"
    md_text = re.sub(r"```mermaid\n(.*?)```", stash, md_text, flags=re.S)
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc", "attr_list", "md_in_html"])
    for i, code in enumerate(blocks):
        body = body.replace(f"<p>MERMAIDBLOCK{i}</p>", f'<pre class="mermaid">{code}</pre>')
    # Figures are referenced as research-relative paths; the HTML sits in research/.
    body = body.replace('src="figures/', 'src="figures/')
    title = re.search(r"<h1[^>]*>(.*?)</h1>", body)
    t = re.sub("<.*?>", "", title.group(1)) if title else "HaanJi report"
    css = CSS + (PAPER_CSS if paper else "")
    script = (f"<script src='{MERMAID_JS}'></script><script>mermaid.initialize({{startOnLoad: true, theme: 'neutral', "
              f"securityLevel: 'loose'}});</script>" if blocks else "")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{t}</title>"
            f"<style>{css}</style></head><body>{body}{script}</body></html>")


PAPER_CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
html { font-size: 9.6pt; line-height: 1.32; }
body { max-width: 178mm; }
h1 { font-size: 17pt; text-align: center; }
.byline { text-align: center; }
.abstract { font-size: 9pt; margin: 8pt 14mm 10pt; }
.cols { column-count: 2; column-gap: 7mm; column-fill: auto; }
.cols h2 { break-after: avoid; font-size: 11pt; margin-top: 12pt; }
.cols h3 { break-after: avoid; font-size: 10pt; }
.cols p, .cols li { text-align: justify; }
.cols table { font-size: 7.6pt; }
.cols figure, .cols table, .cols pre { break-inside: avoid; }
.cols img { max-width: 100%; }
.refs p { font-size: 8.4pt; }
"""


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", action="store_true", help="two-column IEEE-style layout of research/PAPER.md")
    args = ap.parse_args(argv)
    src, html, pdf, footer = (SRC, HTML, PDF, "HaanJi — evaluation report")
    if args.paper:
        src, html, pdf, footer = (ROOT / "research" / "PAPER.md", ROOT / "research" / "PAPER.html",
                                  ROOT / "research" / "PAPER.pdf", "HaanJi — paper draft")
    html.write_text(build_html(src.read_text(encoding="utf-8"), paper=args.paper), encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html.resolve().as_uri(), wait_until="networkidle")
        page.wait_for_timeout(1500)                        # mermaid renders after load
        page.pdf(path=str(pdf), format="A4", print_background=True,
                 display_header_footer=True,
                 header_template="<div></div>",
                 footer_template=f"<div style='font-size:8px;color:#8a8f99;width:100%;text-align:center;font-family:Georgia,serif'>"
                                 f"{footer} · page <span class='pageNumber'></span> of <span class='totalPages'></span></div>",
                 margin={"top": "22mm", "bottom": "24mm", "left": "20mm", "right": "20mm"})
        browser.close()
    print(f"wrote {pdf.relative_to(ROOT)} ({pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
