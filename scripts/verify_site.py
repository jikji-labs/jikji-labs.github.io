#!/usr/bin/env python3
"""Fail closed on broken links and stale release claims in the static site."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
STALE = (
    "coming soon",
    "source is not yet public",
    "source code is not yet public",
    "1.8m+",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        for attr in ("href", "src"):
            if values.get(attr):
                self.refs.append((attr, values[attr] or ""))


def local_target(page: Path, ref: str) -> tuple[Path, str] | None:
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc or ref.startswith(("mailto:", "tel:")):
        return None
    path = parsed.path
    target = page if not path else (page.parent / path).resolve()
    return target, parsed.fragment


def main() -> None:
    pages = sorted(ROOT.glob("*.html"))
    errors: list[str] = []
    parsed_pages: dict[Path, PageParser] = {}

    for page in pages:
        text = page.read_text(encoding="utf-8")
        lower = text.lower()
        for phrase in STALE:
            if phrase in lower:
                errors.append(f"{page.name}: stale claim {phrase!r}")
        parser = PageParser()
        parser.feed(text)
        parsed_pages[page.resolve()] = parser

    for page, parser in parsed_pages.items():
        for attr, ref in parser.refs:
            resolved = local_target(page, ref)
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.exists():
                errors.append(f"{page.name}: broken {attr}={ref!r}")
                continue
            if fragment and target.suffix == ".html":
                target_parser = parsed_pages.get(target)
                if target_parser is None:
                    target_parser = PageParser()
                    target_parser.feed(target.read_text(encoding="utf-8"))
                    parsed_pages[target] = target_parser
                if fragment not in target_parser.ids:
                    errors.append(f"{page.name}: missing fragment {ref!r}")

    index = (ROOT / "index.html").read_text(encoding="utf-8")
    licensing = (ROOT / "licensing.html").read_text(encoding="utf-8")
    required = {
        "index.html": ("Jikji", "github.com/jikji-labs", "licensing.html"),
        "licensing.html": ("GPL-3.0-only", "Apache-2.0", "section 4(d)", "originally developed as Jikji"),
    }
    for name, needles in required.items():
        text = index if name == "index.html" else licensing
        for needle in needles:
            if needle not in text:
                errors.append(f"{name}: missing required text {needle!r}")

    if errors:
        raise SystemExit("site verification failed:\n- " + "\n- ".join(errors))
    print(f"site verification passed: {len(pages)} HTML pages")


if __name__ == "__main__":
    main()
