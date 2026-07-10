#!/usr/bin/env python3
"""Fail closed on broken navigation, i18n drift, and stale release claims."""

from __future__ import annotations

import json
import re
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://jikji-labs.com"
LOCALES = ("en", "ko", "ja", "zh", "zh-tw", "fr", "de", "es", "pt", "it", "ru", "vi", "id")
STALE = ("coming soon", "source is not yet public", "source code is not yet public", "1.8m+")
KEY_RE = re.compile(r'^\s*"([^"]+)"\s*:', re.MULTILINE)
ENTRY_RE = re.compile(r'^\s*("(?:\\.|[^"])*")\s*:\s*("(?:\\.|[^"])*")\s*,?$', re.MULTILINE)
HTML_TOKEN_RE = re.compile(r'</?[^>]+>')
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
DETAIL_HEROES = {
    "architecture.html": "architecture.webp", "agent-loop.html": "agent-loop.webp",
    "tools.html": "tools.webp", "orchestration.html": "orchestration.webp",
    "memory.html": "memory.webp", "ontology.html": "ontology.webp",
    "enterprise.html": "enterprise.webp", "use-cases.html": "use-cases.webp",
}
CARDINALITY_TOKENS = {
    "exp.h2": {
        "en": ("seven", "7"), "ko": ("일곱", "7"), "ja": ("7", "七"),
        "zh": ("七", "7"), "zh-tw": ("七", "7"), "fr": ("sept", "7"),
        "de": ("sieben", "7"), "es": ("siete", "7"), "pt": ("sete", "7"),
        "it": ("sette", "7"), "ru": ("сем", "7"), "vi": ("bảy", "7"),
        "id": ("tujuh", "7"),
    },
    "ent.perm.p": {
        "en": ("four", "4"), "ko": ("네", "4"), "ja": ("4", "四"),
        "zh": ("四", "4"), "zh-tw": ("四", "4"), "fr": ("quatre", "4"),
        "de": ("vier", "4"), "es": ("cuatro", "4"), "pt": ("quatro", "4"),
        "it": ("quattro", "4"), "ru": ("четыр", "4"), "vi": ("bốn", "4"),
        "id": ("empat", "4"),
    },
}
NUMBER_TOKEN_GROUPS = {
    "onto.foresight.2p": {
        "en": ("four", "six", "one", "two"), "ko": ("4", "6", "1", "2"),
        "ja": ("4", "6", "1", "2"), "zh": ("四", "六", "一", "两"),
        "zh-tw": ("四", "六", "一", "兩"), "fr": ("quatre", "six", "un", "deux"),
        "de": ("vier", "sechs", "ein", "zwei"), "es": ("cuatro", "seis", "una", "dos"),
        "pt": ("quatro", "seis", "uma", "duas"), "it": ("quattro", "sei", "uno", "due"),
        "ru": ("четыр", "шест", "одн", "дв"), "vi": ("bốn", "sáu", "một", "hai"),
        "id": ("empat", "enam", "satu", "dua"),
    },
    "onto.foresight.3p": {
        "en": ("three", "one"), "ko": ("3", "단일"), "ja": ("3", "1"),
        "zh": ("三", "一个"), "zh-tw": ("三", "單一"), "fr": ("trois", "un"),
        "de": ("drei", "ein"), "es": ("tres", "un"), "pt": ("três", "um"),
        "it": ("tre", "un"), "ru": ("тремя", "одного"), "vi": ("ba", "một"),
        "id": ("tiga", "satu"),
    },
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []
        self.i18n_keys: set[str] = set()
        self.scripts: list[str] = []
        self.canonicals: list[str] = []
        self.images_without_alt: list[str] = []
        self.images: list[dict[str, str]] = []
        self.cardinality_results: list[tuple[int, int, str]] = []
        self._cardinality_stack: list[dict[str, object]] = []
        self._depth = 0
        self.english_notice_count = 0
        self.title_count = 0
        self.description_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        for frame in self._cardinality_stack:
            if values.get("data-cardinality"):
                continue
            selector_class = frame.get("selector_class")
            selector_tag = frame.get("selector_tag")
            if (selector_class and selector_class in classes) or (selector_tag and selector_tag == tag):
                frame["count"] = int(frame["count"]) + 1
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if values.get("data-i18n"):
            self.i18n_keys.add(values["data-i18n"] or "")
        if values.get("data-i18n-alt"):
            self.i18n_keys.add(values["data-i18n-alt"] or "")
        if "data-english-notice" in values:
            self.english_notice_count += 1
        for attr in ("href", "src"):
            if values.get(attr):
                self.refs.append((attr, values[attr] or ""))
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
        if tag == "link" and values.get("rel") == "canonical":
            self.canonicals.append(values.get("href") or "")
        if tag == "img":
            self.images.append({key: value or "" for key, value in values.items()})
            if not (values.get("alt") or "").strip():
                self.images_without_alt.append(values.get("src") or "<inline>")
        if tag == "title":
            self.title_count += 1
        if tag == "meta" and values.get("name") == "description" and values.get("content"):
            self.description_count += 1
        if values.get("data-cardinality"):
            self._cardinality_stack.append({
                "tag": tag, "depth": self._depth, "expected": int(values["data-cardinality"] or "0"),
                "selector_class": values.get("data-cardinality-class"),
                "selector_tag": values.get("data-cardinality-tag"), "count": 0,
                "label": values.get("id") or values.get("class") or tag,
            })
        if tag not in VOID_TAGS:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID_TAGS:
            self._depth = max(0, self._depth - 1)
        for frame in list(reversed(self._cardinality_stack)):
            if frame["tag"] == tag and frame["depth"] == self._depth:
                self.cardinality_results.append((int(frame["expected"]), int(frame["count"]), str(frame["label"])))
                self._cardinality_stack.remove(frame)
                break


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


def dictionary(locale: str, errors: list[str]) -> dict[str, str]:
    path = ROOT / "assets" / "i18n" / f"{locale}.js"
    if not path.is_file() or path.stat().st_size == 0:
        errors.append(f"missing locale asset: {path.relative_to(ROOT)}")
        return {}
    text = path.read_text(encoding="utf-8")
    keys = KEY_RE.findall(text)
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        errors.append(f"{path.name}: duplicate keys {', '.join(duplicates)}")
    values = {json.loads(key): json.loads(value) for key, value in ENTRY_RE.findall(text)}
    if set(keys) != set(values):
        errors.append(f"{path.name}: dictionary values could not be parsed")
    return values


def webp_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:32]
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP" or data[12:16] != b"VP8 ":
        return None
    width, height = struct.unpack_from("<HH", data, 26)
    return width & 0x3FFF, height & 0x3FFF


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
        for expected, actual, label in parser.cardinality_results:
            if actual != expected:
                errors.append(f"{page.name}: cardinality {label!r} expected {expected}, found {actual}")
        relative_name = page.relative_to(ROOT).as_posix()
        if relative_name in DETAIL_HEROES:
            expected_src = "assets/detail/" + DETAIL_HEROES[relative_name]
            matches = [image for image in parser.images if image.get("src") == expected_src]
            if len(matches) != 1:
                errors.append(f"{page.name}: requires one detail hero {expected_src}")
            else:
                image = matches[0]
                if image.get("width") != "1600" or image.get("height") != "666" or not image.get("data-i18n-alt"):
                    errors.append(f"{page.name}: detail hero requires 1600x666 dimensions and translated alt")
                asset = ROOT / expected_src
                if not asset.is_file() or asset.stat().st_size < 50_000 or webp_dimensions(asset) != (1600, 666):
                    errors.append(f"{page.name}: invalid or blank-sized detail hero {expected_src}")
        if relative_name in {"licensing.html", "contact.html", "docs/operations/alerting/index.html"} and parser.english_notice_count != 1:
            errors.append(f"{page.name}: requires one authoritative-English locale notice")

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

    dictionaries = {locale: dictionary(locale, errors) for locale in LOCALES}
    english = dictionaries["en"]
    missing_english = sorted(site_keys - set(english))
    if missing_english:
        errors.append("English canonical dictionary misses: " + ", ".join(missing_english))
    for locale in LOCALES[1:]:
        unknown = sorted(set(dictionaries[locale]) - set(english))
        if unknown:
            errors.append(f"{locale}: keys absent from English canonical: {', '.join(unknown)}")
        missing = sorted(site_keys - set(dictionaries[locale]))
        if missing:
            errors.append(f"{locale}: missing current translations: {', '.join(missing)}")
        for key in site_keys & set(dictionaries[locale]) & set(english):
            if HTML_TOKEN_RE.findall(dictionaries[locale][key]) != HTML_TOKEN_RE.findall(english[key]):
                errors.append(f"{locale}: {key} does not preserve canonical HTML tokens")
        for key, locale_tokens in CARDINALITY_TOKENS.items():
            value = dictionaries[locale].get(key, "").casefold()
            if not any(token.casefold() in value for token in locale_tokens[locale]):
                errors.append(f"{locale}: {key} does not express required cardinality")
        for key, locale_tokens in NUMBER_TOKEN_GROUPS.items():
            value = dictionaries[locale].get(key, "").casefold()
            if not all(token.casefold() in value for token in locale_tokens[locale]):
                errors.append(f"{locale}: {key} changes a required numeric bound")

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

    coverage = min(len(site_keys & set(dictionaries[locale])) / len(site_keys) for locale in LOCALES[1:])
    print(
        f"site verification passed: {len(pages)} pages, {len(LOCALES)} locales, "
        f"{len(site_keys)} canonical keys, minimum translated-key coverage {coverage:.1%}"
    )


if __name__ == "__main__":
    main()
