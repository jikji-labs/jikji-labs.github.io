#!/usr/bin/env python3
"""Fail closed on broken navigation, i18n drift, and stale release claims."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://jikji-labs.com"
LOCALES = ("en", "ko", "ja", "zh", "zh-tw", "fr", "de", "es", "pt", "it", "ru", "vi", "id")
STALE = ("coming soon", "source is not yet public", "source code is not yet public", "1.8m+")
KEY_RE = re.compile(r'^\s*"([^"]+)"\s*:', re.MULTILINE)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []
        self.i18n_keys: set[str] = set()
        self.scripts: list[str] = []
        self.canonicals: list[str] = []
        self.images_without_alt: list[str] = []
        self.title_count = 0
        self.description_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if values.get("data-i18n"):
            self.i18n_keys.add(values["data-i18n"] or "")
        for attr in ("href", "src"):
            if values.get(attr):
                self.refs.append((attr, values[attr] or ""))
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
        if tag == "link" and values.get("rel") == "canonical":
            self.canonicals.append(values.get("href") or "")
        if tag == "img" and not (values.get("alt") or "").strip():
            self.images_without_alt.append(values.get("src") or "<inline>")
        if tag == "title":
            self.title_count += 1
        if tag == "meta" and values.get("name") == "description" and values.get("content"):
            self.description_count += 1


def local_target(page: Path, ref: str) -> tuple[Path, str] | None:
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc or ref.startswith(("mailto:", "tel:")):
        return None
    target = page if not parsed.path else (page.parent / parsed.path).resolve()
    return target, parsed.fragment


def expected_canonical(page: Path) -> str:
    relative = page.relative_to(ROOT)
    if relative == Path("index.html"):
        return f"{CANONICAL}/"
    if page.name == "index.html":
        return f"{CANONICAL}/{relative.parent.as_posix()}"
    return f"{CANONICAL}/{relative.as_posix()}"


def expected_i18n_scripts(page: Path) -> list[str]:
    depth = len(page.relative_to(ROOT).parent.parts)
    prefix = "../" * depth
    return [f"{prefix}assets/i18n/en.js", f"{prefix}assets/i18n.js"]


def dictionary_keys(locale: str, errors: list[str]) -> set[str]:
    path = ROOT / "assets" / "i18n" / f"{locale}.js"
    if not path.is_file() or path.stat().st_size == 0:
        errors.append(f"missing locale asset: {path.relative_to(ROOT)}")
        return set()
    text = path.read_text(encoding="utf-8")
    keys = KEY_RE.findall(text)
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        errors.append(f"{path.name}: duplicate keys {', '.join(duplicates)}")
    return set(keys)


def main() -> None:
    pages = sorted(ROOT.rglob("*.html"))
    errors: list[str] = []
    parsed_pages: dict[Path, PageParser] = {}
    site_keys: set[str] = set()

    if not pages:
        errors.append("no HTML pages found")

    for page in pages:
        text = page.read_text(encoding="utf-8")
        lower = text.lower()
        for phrase in STALE:
            if phrase in lower:
                errors.append(f"{page.name}: stale claim {phrase!r}")
        if "jikji-labs.github.io" in lower or "http://jikji-labs.com" in lower:
            errors.append(f"{page.name}: non-canonical domain or insecure canonical link")

        parser = PageParser()
        parser.feed(text)
        parsed_pages[page.resolve()] = parser
        site_keys.update(parser.i18n_keys)

        duplicate_ids = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
        if duplicate_ids:
            errors.append(f"{page.name}: duplicate ids {', '.join(duplicate_ids)}")
        if parser.title_count != 1 or parser.description_count != 1:
            errors.append(f"{page.name}: requires exactly one title and description")
        if parser.canonicals != [expected_canonical(page)]:
            errors.append(f"{page.name}: canonical must be {expected_canonical(page)!r}")
        expected_scripts = expected_i18n_scripts(page)
        if parser.scripts[-2:] != expected_scripts:
            errors.append(f"{page.name}: i18n scripts missing or out of order")
        for required_id in ("site-nav", "langSel"):
            if parser.ids.count(required_id) != 1:
                errors.append(f"{page.name}: requires one #{required_id}")
        if parser.images_without_alt:
            errors.append(f"{page.name}: images without alt: {', '.join(parser.images_without_alt)}")

    for page, parser in list(parsed_pages.items()):
        for attr, ref in parser.refs:
            resolved = local_target(page, ref)
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.exists() or (target.is_file() and target.stat().st_size == 0):
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

    dictionaries = {locale: dictionary_keys(locale, errors) for locale in LOCALES}
    english = dictionaries["en"]
    missing_english = sorted(site_keys - english)
    if missing_english:
        errors.append("English canonical dictionary misses: " + ", ".join(missing_english))
    for locale in LOCALES[1:]:
        unknown = sorted(dictionaries[locale] - english)
        if unknown:
            errors.append(f"{locale}: keys absent from English canonical: {', '.join(unknown)}")
        coverage = len(site_keys & dictionaries[locale]) / max(1, len(site_keys))
        if coverage < 0.95:
            errors.append(f"{locale}: key coverage {coverage:.1%} is below 95% fallback contract")

    runtime = (ROOT / "assets" / "i18n.js").read_text(encoding="utf-8")
    for contract in ("translationIsCurrent", "localStorage.setItem", "assets/i18n/", "Escape"):
        if contract not in runtime:
            errors.append(f"i18n runtime missing contract marker {contract!r}")

    hero = ROOT / "assets" / "jikji-hero.png"
    if not hero.is_file() or hero.stat().st_size < 100_000:
        errors.append("hero bitmap missing or unexpectedly small")

    licensing = (ROOT / "licensing.html").read_text(encoding="utf-8")
    for needle in ("GPL-3.0-only", "Apache-2.0", "section 4(d)", "originally developed as Jikji"):
        if needle not in licensing:
            errors.append(f"licensing.html: missing required text {needle!r}")

    alerting = parsed_pages.get((ROOT / "docs" / "operations" / "alerting" / "index.html").resolve())
    alert_anchors = {
        "jikjitargetdown", "jikjihttperrorbudgetburn", "jikjirunadmissionshedding",
        "jikjigalleyerrors", "jikjiproviderfailureratio", "jikjicircuitbreakerrejecting",
        "jikjicomponentunhealthy", "jikjimemorynearlimit",
    }
    if alerting is None:
        errors.append("missing canonical operations alerting runbook")
    else:
        missing_anchors = sorted(alert_anchors - set(alerting.ids))
        if missing_anchors:
            errors.append("alerting runbook misses anchors: " + ", ".join(missing_anchors))

    if errors:
        raise SystemExit("site verification failed:\n- " + "\n- ".join(errors))

    coverage = min(len(site_keys & dictionaries[locale]) / len(site_keys) for locale in LOCALES[1:])
    print(
        f"site verification passed: {len(pages)} pages, {len(LOCALES)} locales, "
        f"{len(site_keys)} canonical keys, minimum translated-key coverage {coverage:.1%}"
    )


if __name__ == "__main__":
    main()
