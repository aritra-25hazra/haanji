"""research/PAPER.md -> research/paper-latex/haanji.tex (IEEEtran, two columns).

The Markdown draft stays the source; this script is the typesetter. Inline
markup, tables, bracketed citations and the reference list are converted; the
rest is the venue's class. Run:

    python research/harness/paper_tex.py
    cd research/paper-latex && tectonic haanji.tex    # or upload to Overleaf
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "research" / "PAPER.md"
OUT = ROOT / "research" / "paper-latex" / "haanji.tex"

UNICODE = {"→": r"$\rightarrow$", "≤": r"$\leq$", "≥": r"$\geq$", "×": r"$\times$", "‖": r"$\,\|\,$",
           "–": "--", "—": "---", "§": r"\S{}", "·": r"$\cdot$", "≈": r"$\approx$", "±": r"$\pm$",
           "…": r"\ldots{}", "₹": "Rs.\\,", "∅": r"$\emptyset$", "“": "``", "”": "''", "‘": "`", "’": "'"}
SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def esc(text: str) -> str:
    out = []
    for ch in text:
        if ch in SPECIAL:
            out.append(SPECIAL[ch])
        elif ch in UNICODE:
            out.append(UNICODE[ch])
        else:
            out.append(ch)
    return "".join(out)


def inline(text: str, keys: dict[str, str]) -> str:
    """Markdown inline markup -> LaTeX, with escaping done on the plain runs only."""
    pieces: list[str] = []
    pattern = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[A-Z][^\]]*?\d{4}[a-z]?\])")
    pos = 0
    for m in pattern.finditer(text):
        pieces.append(esc(text[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith("`"):
            pieces.append(r"\texttt{" + esc(tok[1:-1]) + "}")
        elif tok.startswith("**"):
            pieces.append(r"\textbf{" + esc(tok[2:-2]) + "}")
        elif tok.startswith("*"):
            pieces.append(r"\emph{" + esc(tok[1:-1]) + "}")
        else:                                   # [Pundak 2018; Zhao 2019]
            found, missing = [], []
            for part in tok[1:-1].split(";"):
                part = part.strip()                      # "Philips 1990, 2000" cites two entries
                surname = part.split()[0].rstrip(",").lower()
                years = re.findall(r"\d{4}[a-z]?", part)
                for year in years or [""]:
                    key = surname + year
                    if key in keys:
                        if keys[key] not in found:
                            found.append(keys[key])
                    else:
                        missing.append(part)
            if found and not missing:
                pieces.append(r"\cite{" + ",".join(found) + "}")
            else:
                pieces.append(esc(tok))
        pos = m.end()
    pieces.append(esc(text[pos:]))
    return "".join(pieces)


def table(lines: list[str], caption: str, label: str, keys: dict[str, str]) -> str:
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if not re.match(r"^\|\s*-", l)]
    ncol = len(rows[0])
    spec = "l" + "r" * (ncol - 1)
    body = [" & ".join(inline(c, keys) for c in rows[0]) + r" \\", r"\midrule"]
    body += [" & ".join(inline(c, keys) for c in r) + r" \\" for r in rows[1:]]
    return ("\\begin{table}[t]\n\\caption{%s}\n\\label{%s}\n\\centering\\small\n\\begin{tabular}{%s}\n\\toprule\n%s\n\\bottomrule\n\\end{tabular}\n\\end{table}\n"
            % (inline(caption, keys), label, spec, "\n".join(body)))


def references(block: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    entries = [e.strip() for e in block.split(" · ") if e.strip()]
    items, keys = [], {}          # keys: every "surnameYEAR" alias -> the bibitem key
    for n, e in enumerate(entries, 1):
        ym = re.search(r"\(([^)]*\d{4}[^)]*)\)", e)       # "(1990, 2000)" cites as either year
        years = re.findall(r"\d{4}[a-z]?", ym.group(1)) if ym else []
        surname = re.split(r"[,\s]", e, 1)[0].lower()
        key = f"{surname}{years[0] if years else n}"
        while key in {k for k, _ in items}:
            key += "x"
        for year in years or [""]:
            keys.setdefault(surname + year, key)
        items.append((key, e))
    return items, keys


def main() -> int:
    md = SRC.read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", md, re.M).group(1)
    byline = re.search(r'<p class="byline">(.*?)</p>', md, re.S).group(1)
    abstract = re.search(r'<div class="abstract" markdown="1">\s*\*\*Abstract\*\*\s*—\s*(.*?)</div>', md, re.S).group(1).strip()
    refs_block = re.search(r'<div class="refs" markdown="1">(.*?)</div>', md, re.S).group(1).strip()
    items, keys = references(refs_block)
    body_md = md[md.index('<div class="cols" markdown="1">') + len('<div class="cols" markdown="1">'):md.index("## References")]

    out: list[str] = []
    lines = body_md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            out.append("\\section{" + inline(re.sub(r"^[IVX]+\.\s*", "", line[3:]), keys) + "}")
        elif line.startswith("### "):
            out.append("\\subsection{" + inline(re.sub(r"^[A-Z]\.\s*", "", line[4:]), keys) + "}")
        elif line.startswith("**Table ") and i + 1 < len(lines) and lines[i + 2].startswith("|") if i + 2 < len(lines) else False:
            cap = re.sub(r"^\*\*Table [IVX]+\.\*\*\s*", "", line)
            num = re.search(r"Table ([IVX]+)", line).group(1)
            j = i + 2
            tbl = []
            while j < len(lines) and lines[j].startswith("|"):
                tbl.append(lines[j]); j += 1
            out.append(table(tbl, cap, f"tab:{num}", keys))
            i = j
            continue
        elif line.strip() == "" or line.startswith("<"):
            out.append("")
        else:
            out.append(inline(line, keys))
        i += 1
    body = "\n".join(out)
    body = re.sub(r"\n{3,}", "\n\n", body)

    authors = byline.split(" — ")[0]
    affil = byline.split(" — ")[1].split(" · ")[0] if " — " in byline else ""
    author_tex = " \\and ".join(
        "\\IEEEauthorblockN{%s}\\IEEEauthorblockA{%s}" % (esc(a.strip()), esc(affil)) for a in authors.split(","))

    bib = "\n".join("\\bibitem{%s} %s" % (k, inline(e, {})) for k, e in items)
    tex = f"""% Generated from research/PAPER.md by research/harness/paper_tex.py — edit the Markdown, not this file.
\\documentclass[conference]{{IEEEtran}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{booktabs}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{url}}
\\usepackage{{microtype}}
\\hyphenation{{Hing-lish Beng-lish Ma-ra-thing-lish}}

\\title{{{esc(title)}}}
\\author{{{author_tex}}}

\\begin{{document}}
\\maketitle

\\begin{{abstract}}
{inline(abstract, keys)}
\\end{{abstract}}

\\begin{{IEEEkeywords}}
voice agents, speech recognition, code-mixed Hindi-English, phonetic matching, contextual biasing, speculative execution, verifiable receipts
\\end{{IEEEkeywords}}

{body}

\\begin{{thebibliography}}{{{len(items)}}}
{bib}
\\end{{thebibliography}}

\\end{{document}}
"""
    OUT.write_text(tex, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(tex.splitlines())} lines, {len(items)} references)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
