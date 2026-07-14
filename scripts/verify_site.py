#!/usr/bin/env python3
"""Fail closed on broken navigation, i18n drift, and stale release claims."""

from __future__ import annotations

import json
import hashlib
import re
import struct
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://jikji-labs.com"
LOCALES = ("en", "ko", "ja", "zh", "zh-tw", "fr", "de", "es", "pt", "it", "ru", "vi", "id")
STALE = (
    "coming soon", "source is not yet public", "source code is not yet public", "1.8m+",
    "nothing leaks to a third party", "raw pii and secrets never reach",
    "exactly-once resume", "tools are never re-executed", "region- & os-free",
    "no separate api bill", "gpt-5.5",
)
KEY_RE = re.compile(r'^\s*"([^"]+)"\s*:', re.MULTILINE)
ENTRY_RE = re.compile(r'^\s*("(?:\\.|[^"])*")\s*:\s*("(?:\\.|[^"])*")\s*,?$', re.MULTILINE)
REVISION_RE = re.compile(r'window\.JIKJI_I18N_REVISION\s*=\s*"(sha256:[0-9a-f]{64})"')
SOURCE_REVISION_RE = re.compile(r'window\.JIKJI_I18N_SOURCE\["([^"]+)"\]\s*=\s*"(sha256:[0-9a-f]{64})"')
HTML_TOKEN_RE = re.compile(r'</?[^>]+>')
NUMBER_RE = re.compile(r'(?<![A-Za-z0-9_.])\d+(?:[.,]\d+)*(?![A-Za-z0-9_.])')
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
NAVIGATION = (
    ("use-cases.html", "nav.usecases"), ("architecture.html", "nav.arch"),
    ("agent-loop.html", "nav.loop"), ("jikjicode.html", "nav.code"),
    ("tools.html", "nav.tools"), ("orchestration.html", "nav.orch"),
    ("memory.html", "nav.memory"), ("ontology.html", "nav.ontology"),
    ("enterprise.html", "nav.enterprise"),
)
DETAIL_HEROES = {
    "architecture.html": "architecture.webp", "agent-loop.html": "agent-loop.webp",
    "tools.html": "tools.webp", "orchestration.html": "orchestration.webp",
    "memory.html": "memory.webp", "ontology.html": "ontology.webp",
    "enterprise.html": "enterprise.webp", "use-cases.html": "use-cases.webp",
    "jikjicode.html": "jikjicode.webp",
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
    "loop.act.note": {
        locale: ("1024", "4096") for locale in LOCALES
    },
    "onto.foresight.2p": {
        "en": ("four", "six", "one", "two"), "ko": ("4", "6", "1", "2"),
        "ja": ("4", "6", "1", "2"), "zh": ("四", "六", "一", "两"),
        "zh-tw": ("四", "六", "一", "兩"), "fr": ("quatre", "six", "un", "deux"),
        "de": ("vier", "sechs", "ein", "zwei"), "es": ("cuatro", "seis", "una", "dos"),
        "pt": ("quatro", "seis", "uma", "duas"), "it": ("quattro", "sei", "uno", "due"),
        "ru": ("четыр", "шест", "одн", "дв"), "vi": ("bốn", "sáu", "một", "hai"),
        "id": ("empat", "enam", "satu", "dua"),
    },
}
PROOF_KEYS = ("ent.pii.p", "ent.pii.flow", "ent.pii.1.p")
PROOF_CONDITIONAL_TOKENS = {
    "en": ("unmatched", "path"), "ko": ("일치하지", "경로"),
    "ja": ("一致しない", "経路"), "zh": ("未匹配", "路径"),
    "zh-tw": ("未匹配", "路徑"), "fr": ("non", "chemin"),
    "de": ("nicht", "pfad"), "es": ("no", "ruta"),
    "pt": ("não", "caminho"), "it": ("non", "percors"),
    "ru": ("не", "пут"), "vi": ("không", "đường"),
    "id": ("tidak", "jalur"),
}
PRIVATE_EXAMPLE_PREFIX = "https://github.com/jikji-labs/jikji/tree/main/examples/"
EXAMPLE_EVIDENCE = {
    "agent-cli-backbone": "examples/agent-cli-backbone/README.md",
    "trinity-council": "examples/trinity-council/README.md",
    "taskgraph-orchestration": "examples/taskgraph-orchestration/artifacts/worked_run.md",
    "dispatch-queue-worker": "examples/dispatch-queue-worker/artifacts/worked_run.md",
    "production-hardening": "examples/production-hardening/README.md",
    "ha-multi-node": "examples/ha-multi-node/README.md",
    "coding-debugging": "examples/coding-debugging/artifacts/worked_run.md",
    "observability-tracing": "examples/observability-tracing/README.md",
    "approval-gates": "examples/approval-gates/README.md",
    "backup-restore": "examples/backup-restore/README.md",
    "audit-tamper-evidence": "examples/audit-tamper-evidence/README.md",
    "relay-secure-cluster": "examples/relay-secure-cluster/README.md",
}
ALERT_CONTRACTS = {
    "jikjitargetdown": ("JikjiTargetDown", "/health"),
    "jikjihttperrorbudgetburn": ("JikjiHTTPErrorBudgetBurn", "jikji_http_route_responses_total"),
    "jikjihttpp99latency": ("JikjiHTTPP99Latency", "jikji_http_request_duration_seconds_bucket"),
    "jikjirunadmissionshedding": ("JikjiRunAdmissionShedding", "queue depth"),
    "jikjidispatchqueuebacklog": ("JikjiDispatchQueueBacklog", "jikji_dispatch_queue_depth", "jikji_dispatch_saturated_targets"),
    "jikjigalleyerrors": ("JikjiGalleyErrors", "/ready"),
    "jikjibackupfailed": ("JikjiBackupFailed", "backup.error_class", "SQLite"),
    "jikjibackupstale": ("JikjiBackupStale", "jikji_backup_last_success_timestamp_seconds", "RPO", "RTO"),
    "jikjiproviderfailureratio": ("JikjiProviderFailureRatio", "provider"),
    "jikjicircuitbreakerrejecting": ("JikjiCircuitBreakerRejecting", "breaker"),
    "jikjirelayauthenticationfailures": ("JikjiRelayAuthenticationFailures", "jikji_relay_operations_total"),
    "jikjirelayupstreamconnectfailures": ("JikjiRelayUpstreamConnectFailures", "jikji_relay_operations_total"),
    "jikjitraceexporterfailures": (
        "JikjiTraceExporterFailures", "jikji_trace_exporter_health",
        "jikji_trace_exporter_consecutive_failures", "jikji_trace_exporter_exports_total",
    ),
    "jikjicomponentunhealthy": ("JikjiComponentUnhealthy", "component"),
    "jikjimemorynearlimit": ("JikjiMemoryNearLimit", "resident memory"),
    "jikjimetriccardinalityoverflow": (
        "JikjiMetricCardinalityOverflow", "jikji_metric_cardinality_overflow_total", "family", "other",
    ),
}


class PageParser(HTMLParser):
    def __init__(self, source: str = "") -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self._line_offsets = [0]
        self._line_offsets.extend(match.end() for match in re.finditer("\n", source))
        self.ids: list[str] = []
        self.refs: list[tuple[str, str]] = []
        self.i18n_keys: set[str] = set()
        self.scripts: list[str] = []
        self.canonicals: list[str] = []
        self.images_without_alt: list[str] = []
        self.images: list[dict[str, str]] = []
        self.fallbacks: dict[str, list[str]] = defaultdict(list)
        self.navigation: list[tuple[str, str]] = []
        self.detail_hero_positions: list[int] = []
        self.section_positions: list[int] = []
        self.cardinality_results: list[tuple[int, int, str]] = []
        self._cardinality_stack: list[dict[str, object]] = []
        self._i18n_stack: list[dict[str, object]] = []
        self._site_nav_depth: int | None = None
        self._detail_hero_depth: int | None = None
        self._depth = 0
        self._position = 0
        self.english_notice_count = 0
        self.title_count = 0
        self.description_count = 0
        self.main_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._position += 1
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if values.get("id") == "site-nav":
            self._site_nav_depth = self._depth
        if self._site_nav_depth is not None and tag == "a":
            self.navigation.append((values.get("href") or "", values.get("data-i18n") or ""))
        if tag == "figure" and "detail-hero-media" in classes:
            self.detail_hero_positions.append(self._position)
            self._detail_hero_depth = self._depth
        if tag == "section":
            self.section_positions.append(self._position)
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
            if tag not in VOID_TAGS:
                self._i18n_stack.append({
                    "key": values["data-i18n"] or "", "tag": tag, "depth": self._depth,
                    "start": self._absolute_position() + len(self.get_starttag_text()),
                })
        if values.get("data-i18n-alt"):
            self.i18n_keys.add(values["data-i18n-alt"] or "")
            self.fallbacks[values["data-i18n-alt"] or ""].append(values.get("alt") or "")
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
            image = {key: value or "" for key, value in values.items()}
            image["in_detail_hero"] = str(self._detail_hero_depth is not None).lower()
            self.images.append(image)
            if not (values.get("alt") or "").strip():
                self.images_without_alt.append(values.get("src") or "<inline>")
        if tag == "title":
            self.title_count += 1
        if tag == "meta" and values.get("name") == "description" and values.get("content"):
            self.description_count += 1
        if tag == "main":
            self.main_count += 1
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
        for frame in list(reversed(self._i18n_stack)):
            if frame["tag"] == tag and frame["depth"] == self._depth:
                self.fallbacks[str(frame["key"])].append(
                    self.source[int(frame["start"]):self._absolute_position()]
                )
                self._i18n_stack.remove(frame)
                break
        for frame in list(reversed(self._cardinality_stack)):
            if frame["tag"] == tag and frame["depth"] == self._depth:
                self.cardinality_results.append((int(frame["expected"]), int(frame["count"]), str(frame["label"])))
                self._cardinality_stack.remove(frame)
                break
        if self._site_nav_depth == self._depth and tag == "nav":
            self._site_nav_depth = None
        if self._detail_hero_depth == self._depth and tag == "figure":
            self._detail_hero_depth = None

    def _absolute_position(self) -> int:
        line, column = self.getpos()
        if not self.source or line > len(self._line_offsets):
            return 0
        return self._line_offsets[line - 1] + column


def local_target(page: Path, ref: str) -> tuple[Path, str] | None:
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc or ref.startswith(("mailto:", "tel:")):
        return None
    target = page if not parsed.path else (page.parent / parsed.path).resolve()
    return target, parsed.fragment


def normalized_markup(value: str) -> str:
    """Mirror the browser runtime's stale-translation comparison."""
    value = re.sub(r"<br\s*/?\s*>", "<br>", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def numeric_literals(value: str) -> Counter[str]:
    return Counter(NUMBER_RE.findall(HTML_TOKEN_RE.sub(" ", value)))


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

        parser = PageParser(text)
        parser.feed(text)
        parsed_pages[page.resolve()] = parser
        site_keys.update(parser.i18n_keys)

        duplicate_ids = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
        if duplicate_ids:
            errors.append(f"{page.name}: duplicate ids {', '.join(duplicate_ids)}")
        if parser.title_count != 1 or parser.description_count != 1:
            errors.append(f"{page.name}: requires exactly one title and description")
        if parser.main_count != 1 or parser.ids.count("main-content") != 1:
            errors.append(f"{page.name}: requires one <main id='main-content'> landmark")
        if not any(attr == "href" and ref == "#main-content" for attr, ref in parser.refs):
            errors.append(f"{page.name}: requires a skip link to #main-content")
        if parser.canonicals != [expected_canonical(page)]:
            errors.append(f"{page.name}: canonical must be {expected_canonical(page)!r}")
        expected_scripts = expected_i18n_scripts(page)
        if parser.scripts[-2:] != expected_scripts:
            errors.append(f"{page.name}: i18n scripts missing or out of order")
        for required_id in ("site-nav", "langSel"):
            if parser.ids.count(required_id) != 1:
                errors.append(f"{page.name}: requires one #{required_id}")
        expected_navigation = [
            ((ROOT / href).resolve(), key) for href, key in NAVIGATION
        ]
        actual_navigation = [
            (((page.parent / urlsplit(href).path).resolve()), key)
            for href, key in parser.navigation
        ]
        if actual_navigation != expected_navigation:
            errors.append(f"{page.name}: primary navigation differs from the canonical page/key order")
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
                if (image.get("width") != "1600" or image.get("height") != "666"
                        or not image.get("data-i18n-alt") or image.get("in_detail_hero") != "true"
                        or image.get("loading") != "eager" or image.get("fetchpriority") != "high"
                        or image.get("decoding") != "async"):
                    errors.append(
                        f"{page.name}: detail hero requires top-band placement, 1600x666 dimensions, "
                        "translated alt, and eager high-priority async loading"
                    )
                asset = ROOT / expected_src
                if not asset.is_file() or asset.stat().st_size < 50_000 or webp_dimensions(asset) != (1600, 666):
                    errors.append(f"{page.name}: invalid or blank-sized detail hero {expected_src}")
            if (len(parser.detail_hero_positions) != 1 or not parser.section_positions
                    or parser.detail_hero_positions[0] > parser.section_positions[0]):
                errors.append(f"{page.name}: detail hero must be the first content band before sections")
        if relative_name in {"licensing.html", "contact.html", "docs/operations/alerting/index.html"} and parser.english_notice_count != 1:
            errors.append(f"{page.name}: requires one authoritative-English locale notice")

    for page, parser in list(parsed_pages.items()):
        for attr, ref in parser.refs:
            scheme = urlsplit(ref).scheme.casefold()
            allowed_schemes = {"https"}
            if attr == "href":
                allowed_schemes.update({"mailto", "tel"})
            if scheme and scheme not in allowed_schemes:
                errors.append(f"{page.name}: unsupported or insecure {attr} scheme in {ref!r}")
                continue
            if ref.startswith("//"):
                errors.append(f"{page.name}: protocol-relative {attr} is not allowed: {ref!r}")
                continue
            resolved = local_target(page, ref)
            if resolved is None:
                continue
            target, fragment = resolved
            try:
                target.relative_to(ROOT)
            except ValueError:
                errors.append(f"{page.name}: local {attr} escapes the published site: {ref!r}")
                continue
            if target.is_dir():
                target = target / "index.html"
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
    canonical_payload = json.dumps(
        english, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    expected_revision = "sha256:" + hashlib.sha256(canonical_payload).hexdigest()
    english_text = (ROOT / "assets" / "i18n" / "en.js").read_text(encoding="utf-8")
    revision_match = REVISION_RE.search(english_text)
    if revision_match is None or revision_match.group(1) != expected_revision:
        errors.append("en.js: JIKJI_I18N_REVISION does not match the canonical English dictionary")
    for locale in LOCALES[1:]:
        locale_text = (ROOT / "assets" / "i18n" / f"{locale}.js").read_text(encoding="utf-8")
        source_matches = SOURCE_REVISION_RE.findall(locale_text)
        if source_matches != [(locale, expected_revision)]:
            errors.append(f"{locale}: source revision does not match canonical English")
    missing_english = sorted(site_keys - set(english))
    if missing_english:
        errors.append("English canonical dictionary misses: " + ", ".join(missing_english))
    for locale in LOCALES[1:]:
        unknown = sorted(set(dictionaries[locale]) - set(english))
        if unknown:
            errors.append(f"{locale}: keys absent from English canonical: {', '.join(unknown)}")
        missing = sorted(set(english) - set(dictionaries[locale]))
        if missing:
            errors.append(f"{locale}: missing canonical translations: {', '.join(missing)}")
        for key in site_keys & set(dictionaries[locale]) & set(english):
            if HTML_TOKEN_RE.findall(dictionaries[locale][key]) != HTML_TOKEN_RE.findall(english[key]):
                errors.append(f"{locale}: {key} does not preserve canonical HTML tokens")
            missing_numbers = sorted((
                numeric_literals(english[key]) - numeric_literals(dictionaries[locale][key])
            ).elements())
            if missing_numbers:
                errors.append(f"{locale}: {key} drops numeric literals: {', '.join(missing_numbers)}")
        for key, locale_tokens in CARDINALITY_TOKENS.items():
            value = dictionaries[locale].get(key, "").casefold()
            if not any(token.casefold() in value for token in locale_tokens[locale]):
                errors.append(f"{locale}: {key} does not express required cardinality")
        for key, locale_tokens in NUMBER_TOKEN_GROUPS.items():
            value = dictionaries[locale].get(key, "").casefold()
            if not all(token.casefold() in value for token in locale_tokens[locale]):
                errors.append(f"{locale}: {key} changes a required numeric bound")

    for page, parser in parsed_pages.items():
        for key, fallbacks in parser.fallbacks.items():
            canonical = english.get(key)
            if canonical is None:
                continue
            for fallback in fallbacks:
                if normalized_markup(fallback) != normalized_markup(canonical):
                    errors.append(
                        f"{page.name}: embedded English for {key} differs from the canonical dictionary"
                    )

    for locale in LOCALES:
        for key in PROOF_KEYS:
            value = dictionaries[locale].get(key, "")
            folded = value.casefold()
            if "proof" not in folded or "regex" not in folded:
                errors.append(f"{locale}: {key} must identify configured Proof regex coverage")
            if not any(token.casefold() in folded for token in PROOF_CONDITIONAL_TOKENS[locale]):
                errors.append(f"{locale}: {key} must describe conditional path or unmatched-value coverage")

    enterprise = (ROOT / "enterprise.html").read_text(encoding="utf-8")
    for key in PROOF_KEYS:
        if english.get(key, "") not in enterprise:
            errors.append(f"enterprise.html: fallback copy for {key} differs from canonical English")

    for relative in ("use-cases.html", "memory.html"):
        if PRIVATE_EXAMPLE_PREFIX in (ROOT / relative).read_text(encoding="utf-8"):
            errors.append(f"{relative}: private GitHub example links are not public evidence")

    use_cases = (ROOT / "use-cases.html").read_text(encoding="utf-8")
    for slug, evidence_path in EXAMPLE_EVIDENCE.items():
        expected = f'https://github.com/jikji-labs/jikji/blob/main/{evidence_path}'
        if use_cases.count(f'href="{expected}"') != 1:
            errors.append(f"use-cases.html: {slug} must link exactly once to {evidence_path}")

    architecture = (ROOT / "architecture.html").read_text(encoding="utf-8")
    if architecture.count('<div class="name">typebackbone ') != 1:
        errors.append("architecture.html: typebackbone must be the single canonical model-plane module name")

    runtime = (ROOT / "assets" / "i18n.js").read_text(encoding="utf-8")
    for contract in ("translationIsCurrent", "localStorage.setItem", "assets/i18n/", "Escape"):
        if contract not in runtime:
            errors.append(f"i18n runtime missing contract marker {contract!r}")
    langs_match = re.search(r"var LANGS\s*=\s*\[(.*?)\];", runtime, re.DOTALL)
    runtime_locales = tuple(re.findall(r'\[\s*"([a-z-]+)"\s*,', langs_match.group(1))) if langs_match else ()
    if runtime_locales != LOCALES:
        errors.append("i18n runtime locale selector differs from the canonical locale order")

    hero = ROOT / "assets" / "jikji-hero.png"
    if not hero.is_file() or hero.stat().st_size < 100_000:
        errors.append("hero bitmap missing or unexpectedly small")

    licensing = (ROOT / "licensing.html").read_text(encoding="utf-8")
    for needle in ("GPL-3.0-only", "Apache-2.0", "section 4(d)", "originally developed as Jikji"):
        if needle not in licensing:
            errors.append(f"licensing.html: missing required text {needle!r}")

    alerting = parsed_pages.get((ROOT / "docs" / "operations" / "alerting" / "index.html").resolve())
    alert_anchors = set(ALERT_CONTRACTS)
    if alerting is None:
        errors.append("missing canonical operations alerting runbook")
    else:
        missing_anchors = sorted(alert_anchors - set(alerting.ids))
        if missing_anchors:
            errors.append("alerting runbook misses anchors: " + ", ".join(missing_anchors))
        nav_targets = {urlsplit(ref).fragment for attr, ref in alerting.refs if attr == "href" and ref.startswith("#")}
        missing_nav = sorted(alert_anchors - nav_targets)
        if missing_nav:
            errors.append("alerting runbook navigation misses: " + ", ".join(missing_nav))
        alerting_text = (ROOT / "docs" / "operations" / "alerting" / "index.html").read_text(encoding="utf-8")
        for anchor, requirements in ALERT_CONTRACTS.items():
            match = re.search(
                rf'<article[^>]+id="{re.escape(anchor)}"[^>]*>(.*?)</article>',
                alerting_text, re.DOTALL,
            )
            if match is None:
                continue
            missing = [requirement for requirement in requirements if requirement not in match.group(1)]
            if missing:
                errors.append(f"alerting runbook {anchor} misses verifier evidence: {', '.join(missing)}")

    if errors:
        raise SystemExit("site verification failed:\n- " + "\n- ".join(errors))

    coverage = min(len(site_keys & set(dictionaries[locale])) / len(site_keys) for locale in LOCALES[1:])
    print(
        f"site verification passed: {len(pages)} pages, {len(LOCALES)} locales, "
        f"{len(site_keys)} canonical keys, minimum translated-key coverage {coverage:.1%}"
    )


if __name__ == "__main__":
    main()
