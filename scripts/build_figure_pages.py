#!/usr/bin/env python3
"""Stage the standalone figure and its downloads for GitHub Pages."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "models" / "imx477-hq"


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs
                          if key in ("href", "src") and value)


def build(output: Path) -> None:
    # Require a new directory so staging cannot overwrite existing work.
    output.mkdir(parents=True)
    figure = output / "figure"
    figure.mkdir()
    for source in sorted((KIT / "figure").iterdir()):
        if source.is_file() and source.suffix in (".html", ".svg", ".png"):
            shutil.copy2(source, figure / source.name)
    shutil.copytree(KIT / "print", output / "print")
    for name in ("README.zh-CN.md", "validation.json"):
        shutil.copy2(KIT / name, output / name)
    shutil.copy2(ROOT / "models" / "IMX477-HQ-print-kit.zip", output)
    (output / ".nojekyll").touch()
    (output / "index.html").write_text(
        '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="refresh" content="0; url=figure/">'
        '<title>IMX477 居中云台 · CyberVisual</title></head><body>'
        '<p><a href="figure/">打开 IMX477 居中云台示意图</a></p>'
        '<p><a href="IMX477-HQ-print-kit.zip">下载完整打印套件</a></p>'
        '</body></html>\n', encoding="utf-8")

    # Relative links must work below /CyberVisual/, not just at a domain root.
    checked = 0
    for page in output.rglob("*.html"):
        parser = PageLinks()
        parser.feed(page.read_text(encoding="utf-8"))
        for link in parser.links:
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path:
                continue
            if url.path.startswith("/"):
                raise ValueError(f"Domain-root link in {page.name}: {link}")
            target = (page.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(output) or not target.exists():
                raise ValueError(f"Missing local link in {page.name}: {link}")
            checked += 1
    count = sum(path.is_file() for path in output.rglob("*"))
    print(f"GitHub Pages: {count} files, {checked} local links verified: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site",
                        help="New output directory (default: _site)")
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
