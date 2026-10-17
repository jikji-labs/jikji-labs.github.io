#!/usr/bin/env python3
"""Validate publication boundaries, local links, HTML structure and archive contracts."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())

class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.path, self.refs, self.ids, self.stack, self.errors = path, [], set(), [], []
        self.robots, self.lang, self.title = '', '', 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html': self.lang = a.get('lang', '')
        if tag == 'title': self.title += 1
        if tag == 'meta' and a.get('name') == 'robots': self.robots = a.get('content', '')
        if 'id' in a:
            if a['id'] in self.ids: self.errors.append('duplicate id '+a['id'])
            self.ids.add(a['id'])
        for attr in ('href', 'src', 'action', 'poster'):
            if attr in a: self.refs.append((tag, attr, a[attr]))
        if tag not in VOID: self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in VOID: return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append('unexpected closing '+tag)
        else: self.stack.pop()


def target(page, ref):
    u = urlsplit(ref)
    if u.netloc and u.netloc != 'jikji-labs.com': return None, ''
    if u.scheme and u.scheme not in ('http', 'https'): return None, ''
    path = unquote(u.path)
    dest = (ROOT / path.lstrip('/') if path.startswith('/') else page.parent / path).resolve() if path else page
    if dest.is_dir(): dest = dest / 'index.html'
    return dest, unquote(u.fragment)


def main():
    errors, parsed = [], {}
    for path in sorted(ROOT.rglob('*.html')):
        if '.git' in path.parts: continue
        p = Page(path); p.feed(path.read_text()); parsed[path] = p
        if not p.lang or p.title != 1: errors.append(f'{path.relative_to(ROOT)}: missing language or unique title')
        # Archived markup keeps the historical HTML; new pages use strict explicit nesting.
        if 'v1' not in path.relative_to(ROOT).parts:
            errors.extend(f'{path.relative_to(ROOT)}: {e}' for e in p.errors)
            if p.stack: errors.append(f'{path.relative_to(ROOT)}: unclosed {p.stack}')
    for path, p in parsed.items():
        rel = path.relative_to(ROOT)
        for tag, attr, ref in p.refs:
            dest, fragment = target(path, ref)
            if dest is None: continue
            if not dest.is_relative_to(ROOT) or not dest.is_file():
                errors.append(f'{rel}: broken {attr}={ref}')
            elif fragment and dest.suffix == '.html' and fragment not in parsed[dest].ids:
                errors.append(f'{rel}: missing fragment {ref}')
            if rel.parts[0] != 'v2' and dest.is_relative_to(ROOT / 'v2'):
                errors.append(f'{rel}: reveals hidden edition through {attr}')
        if rel.parts[0] == 'v2':
            if p.robots != 'noindex,nofollow': errors.append(f'{rel}: wrong robots metadata')
            text = path.read_text()
            badge = 'Design stage — before implementation' if p.lang == 'en' else '설계 단계 — 구현 전'
            if badge not in text: errors.append(f'{rel}: missing design badge')
            peer = ROOT / 'v2' / (path.name if p.lang == 'en' else 'en/'+path.name)
            if not peer.exists(): errors.append(f'{rel}: missing translation peer')
    sitemap = (ROOT/'sitemap.xml').read_text()
    for loc in ET.fromstring(sitemap).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
        dest, _ = target(ROOT/'index.html', loc.text)
        if not dest or not dest.is_file() or dest.is_relative_to(ROOT/'v2'): errors.append('invalid sitemap URL')
    if '/v2' in (ROOT/'robots.txt').read_text() or '/v2' in sitemap: errors.append('hidden path disclosed to crawler files')
    if (ROOT/'CNAME').read_text().strip() != 'jikji-labs.com': errors.append('CNAME changed')
    # All previous HTML paths remain represented by either the landing page or redirects.
    for archived in (ROOT/'v1').rglob('*.html'):
        previous = ROOT / archived.relative_to(ROOT/'v1')
        if not previous.is_file(): errors.append(f'missing legacy route {previous.relative_to(ROOT)}')
        elif previous != ROOT/'index.html':
            text = previous.read_text()
            if 'http-equiv="refresh"' not in text or 'location.hash' not in text: errors.append('redirect contract missing')
    if errors: raise SystemExit('\n'.join(errors))
    subprocess.run([sys.executable, str(ROOT/'scripts/verify_v1.py')], check=True)
    print(f'Publication validation passed: {len(parsed)} HTML pages; links, fragments, redirects, bilingual peers, noindex, sitemap and CNAME.')

if __name__ == '__main__': main()
