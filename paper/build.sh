#!/bin/sh
# Builds paper.pdf from paper.md. Run from research/oscillator-paper/paper. Needs pandoc and xelatex.
set -e
cd "$(dirname "$0")"
pandoc paper.md -o paper.pdf --pdf-engine=xelatex \
  -V geometry:margin=1in -V fontsize=11pt -V mainfont="DejaVu Serif" -V monofont="DejaVu Sans Mono" \
  -V linkcolor=black -V colorlinks=true --resource-path=. -H header.tex \
  --from markdown-auto_identifiers+implicit_figures
