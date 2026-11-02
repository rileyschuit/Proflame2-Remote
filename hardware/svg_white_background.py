#!/usr/bin/env python3
"""Puts a white page behind exported schematics, so they read on GitHub's dark theme."""
import re
import sys

MARKER = '<rect id="page-background"'
BACKGROUND = MARKER + ' x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>\n'


def add_background(svg):
    if MARKER in svg:
        return svg
    opening = re.search(r"<svg\b[^>]*>\s*", svg)
    if not opening:
        raise SystemExit("no <svg> element found")
    return svg[: opening.end()] + BACKGROUND + svg[opening.end() :]


for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as handle:
        original = handle.read()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(add_background(original))
