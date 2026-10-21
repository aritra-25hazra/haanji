# The paper, in LaTeX

`haanji.tex` is generated from [`../PAPER.md`](../PAPER.md) by
`research/harness/paper_tex.py` — edit the Markdown, re-run the script, and
the LaTeX follows. It uses the IEEE conference class (`IEEEtran`, two columns)
with `booktabs` tables and numeric citations.

## Compile

Locally, with [Tectonic](https://tectonic-typesetting.github.io/) (one binary,
fetches packages on demand):

```bash
python research/harness/paper_tex.py
cd research/paper-latex && tectonic haanji.tex       # → haanji.pdf
```

Or with a TeX Live install: `pdflatex haanji.tex` twice (the second pass
resolves the citation numbers).

## Overleaf

1. New Project → *Upload Project* → zip this folder (`haanji.tex` is enough;
   `IEEEtran.cls` is in Overleaf's TeX Live).
2. Set the compiler to **pdfLaTeX** (Menu → Compiler); `inputenc` and
   `fontenc` are already declared.
3. Recompile twice so the reference numbers appear.

## A different venue

The body is plain `\section`/`\subsection` text, tables and `\cite`s, so
switching class is a matter of the preamble and the author block:

* **ACL / ICON** (`acl.sty`): `\documentclass[11pt]{article}`,
  `\usepackage[final]{acl}`, and replace the `\IEEEauthorblock*` lines with
  `\author{...\\ \texttt{email}}`.
* **Springer LNCS**: `\documentclass{llncs}`, `\institute{}` for the
  affiliation, and `\begin{abstract}` stays as is.

Keep the Markdown as the source of truth: every number in it is produced by a
script in `research/harness/`, and the report says which one.
