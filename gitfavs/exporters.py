"""Export (HTML pulito, Netscape) e import (JSON, HTML dei browser)."""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from .store import GitFavsError, Bookmark, is_safe_href, normalize_tags, normalize_url

_CSS = """
:root{--bg:#161514;--fg:#ece9e6;--mut:#b6afa6;--line:#45413c;--acc:#8cb4ff}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow:hidden}
main{height:100vh;max-width:84rem;margin:0 auto;padding:1.5rem 1.25rem 1.25rem;display:flex;flex-direction:column}
h1{font-size:1.5rem;margin:0 0 .25rem;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:.875rem;margin:0 0 .75rem}
input{width:100%;max-width:28rem;padding:.6rem .8rem;font:inherit;color:inherit;background:transparent;border:1px solid var(--line);border-radius:8px;margin-bottom:.75rem}
input:focus{outline:2px solid var(--acc);outline-offset:1px}
nav{display:flex;flex-wrap:wrap;align-items:center;gap:.4rem;margin-bottom:.9rem}
nav button{cursor:pointer;font:inherit;font-size:.8125rem;color:#d6d1cb;background:#242220;border:1px solid var(--line);border-radius:999px;padding:.3rem .75rem}
nav button:hover{color:var(--fg)}
nav button.on{background:var(--fg);border-color:var(--fg);color:var(--bg)}
nav button small{margin-left:.4em;opacity:.75}
section{flex:1;min-height:0;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:10px;background:hsl(var(--h,220) 32% 22% / .55)}
h2{display:flex;align-items:baseline;gap:.5rem;margin:0;padding:.75rem 1rem .5rem;font-size:.9375rem}
h2 small{color:var(--mut);font-size:.75rem;font-weight:400}
.none{color:var(--mut)}
ul{list-style:none;margin:0;padding:0 1rem 1rem;overflow-y:auto;min-height:0}
li{padding:.4rem 0}
a{color:var(--acc);text-decoration:none;font-weight:600;overflow-wrap:anywhere}
a:hover{text-decoration:underline}
.url{display:block;color:var(--mut);font-size:.75rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.note{margin:.2rem 0 0;font-size:.8125rem}
.tag{display:inline-block;margin:.3rem .3rem 0 0;padding:0 .45rem;border:1px solid var(--line);border-radius:6px;color:var(--mut);font-size:.6875rem}
[hidden]{display:none}
"""

_JS = """
const pages=[...document.querySelectorAll('section')],btns=[...document.querySelectorAll('nav [data-i]')],
q=document.getElementById('q'),n=document.getElementById('n'),total=+n.textContent;
let cur=0;
function show(i){cur=(i+pages.length)%pages.length;
pages.forEach((s,j)=>s.hidden=j!==cur);
btns.forEach((b,j)=>b.classList.toggle('on',j===cur));}
btns.forEach((b,j)=>b.onclick=()=>show(j));
document.addEventListener('keydown',e=>{if(e.target===q)return;
if(e.key==='ArrowRight')show(cur+1);if(e.key==='ArrowLeft')show(cur-1);});
function apply(){const t=q.value.toLowerCase().split(/\\s+/).filter(Boolean);const seen=new Set();
pages.forEach((s,j)=>{let vis=0;
s.querySelectorAll('li').forEach(r=>{const ok=t.every(x=>r.dataset.s.includes(x));r.hidden=!ok;
if(ok){vis++;if(t.length)seen.add(r.dataset.id)}});
btns[j].querySelector('small').textContent=t.length?vis:s.dataset.total;
btns[j].hidden=!!t.length&&vis===0});
if(t.length&&btns[cur].hidden){const f=btns.findIndex(b=>!b.hidden);show(f>=0?f:0);}
n.textContent=t.length?seen.size:total;}
q.addEventListener('input',apply);
apply();show(0);
"""


def _hue(name: str) -> int:
    """Tonalità 0-359 deterministica per assegnare un colore diverso a ogni tag."""
    h = 0
    for c in name.lower():
        h = (h * 31 + ord(c)) % 997
    return h % 360


def _row(b: Bookmark, section: str | None = None) -> str:
    tags = "".join(f'<span class="tag">#{escape(t)}</span>' for t in b.tags if t != section)
    note = f'<p class="note">{escape(b.note)}</p>' if b.note else ""
    search = escape(" ".join([b.title, b.url, *b.tags, b.note]).lower(), quote=True)
    href = escape(b.url if is_safe_href(b.url) else "#", quote=True)
    return (
        f'<li data-id="{b.id}" data-s="{search}"><a href="{href}" rel="noopener noreferrer">{escape(b.title)}</a>'
        f'<span class="url">{escape(b.url)}</span>{note}<div>{tags}</div></li>'
    )


def group_by_tag(items: list[Bookmark]) -> list[tuple[str | None, list[Bookmark]]]:
    """Sezioni ordinate per tag; un link con piu' tag compare in ognuna. I senza tag (None) vanno in fondo."""
    groups: dict[str, list[Bookmark]] = {}
    untagged: list[Bookmark] = []
    for b in sorted(items, key=lambda b: b.title.lower()):
        for t in b.tags or []:
            groups.setdefault(t, []).append(b)
        if not b.tags:
            untagged.append(b)
    out: list[tuple[str | None, list[Bookmark]]] = sorted(groups.items(), key=lambda kv: kv[0].lower())
    if untagged:
        out.append((None, untagged))
    return out


def export_html(items: list[Bookmark], title: str = "Bookmarks") -> str:
    """Pagina a schede: un tag per pagina (navigabile con le frecce o i tasti ←/→),
    ogni tag con il proprio colore di sfondo, nessuna scroll della pagina."""
    groups = group_by_tag(items)
    sections, chips = [], []
    for i, (tag, group) in enumerate(groups):
        heading = f"#{escape(tag)}" if tag else '<span class="none">Senza tag</span>'
        hue = _hue(tag if tag else "senza tag")
        hidden = " hidden" if i else ""
        sections.append(
            f'<section data-total="{len(group)}" style="--h:{hue}"{hidden}>'
            f"<h2>{heading}<small>{len(group)}</small></h2>"
            f"<ul>{''.join(_row(b, tag) for b in group)}</ul></section>"
        )
        on = " class='on'" if i == 0 else ""
        chips.append(f'<button data-i="{i}"{on}>{heading}<small>{len(group)}</small></button>')
    nav = "".join(chips)
    stamp = datetime.now().strftime("%d/%m/%Y")
    return (
        f'<!doctype html>\n<html lang="it"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{escape(title)}</h1>"
        f'<p class="sub"><span id="n">{len(items)}</span> link · {len(groups)} sezioni · aggiornato il {stamp}</p>'
        f'<input id="q" type="search" placeholder="Cerca per nome, indirizzo o tag…" autofocus>'
        f"<nav>{nav}</nav>{''.join(sections)}<script>{_JS}</script></main></body></html>\n"
    )


def export_netscape(items: list[Bookmark]) -> str:
    """Formato importabile da Chrome, Firefox, Safari."""
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>", "<H1>Bookmarks</H1>", "<DL><p>",
    ]
    for b in sorted(items, key=lambda b: b.id):
        try:
            ts = int(datetime.fromisoformat(b.created).timestamp())
        except ValueError:
            ts = 0
        tags = escape(",".join(b.tags), quote=True)
        lines.append(
            f'    <DT><A HREF="{escape(b.url, quote=True)}" ADD_DATE="{ts}" TAGS="{tags}">{escape(b.title)}</A>'
        )
        if b.note:
            lines.append(f"    <DD>{escape(b.note)}")
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


class _NetscapeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[dict] = []
        self.folders: list[str] = []
        self._cur: dict | None = None
        self._in_h3 = False
        self._h3 = ""
        self._pending_folder: str | None = None
        self._dd_for: dict | None = None
        self._in_dd = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h3":
            self._in_h3, self._h3 = True, ""
        elif tag == "dl":
            self.folders.append(self._pending_folder or "")
            self._pending_folder = None
        elif tag == "a" and a.get("href"):
            self._cur = {"url": a["href"], "title": "", "tags": (a.get("tags") or "").split(","),
                         "folders": [f for f in self.folders if f], "note": ""}
        elif tag == "dd":
            self._in_dd = True

    def handle_endtag(self, tag):
        if tag == "h3":
            self._in_h3, self._pending_folder = False, self._h3.strip()
        elif tag == "dl" and self.folders:
            self.folders.pop()
        elif tag == "a" and self._cur:
            self._cur["title"] = self._cur["title"].strip()
            self.found.append(self._cur)
            self._dd_for, self._cur = self._cur, None

    def handle_data(self, data):
        if self._in_h3:
            self._h3 += data
        elif self._cur is not None:
            self._cur["title"] += data
        elif self._in_dd and self._dd_for is not None:
            self._dd_for["note"] += data.strip()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def read_import(path: Path) -> list[dict]:
    """Ritorna dict con url, title, tags, note da un JSON o da un HTML dei browser."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise GitFavsError(f"impossibile leggere {path}: {e}") from e
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as e:
            raise GitFavsError(f"JSON non valido: {e}") from e
        rows = data.get("bookmarks", []) if isinstance(data, dict) else data
        return [
            {"url": r["url"], "title": r.get("title", ""), "tags": r.get("tags", []), "note": r.get("note", "")}
            for r in rows if isinstance(r, dict) and r.get("url")
        ]
    parser = _NetscapeParser()
    parser.feed(text)
    out = []
    for r in parser.found:
        if r["url"].startswith(("javascript:", "place:")):
            continue
        out.append({"url": r["url"], "title": r["title"], "tags": [*r["tags"], *r["folders"]], "note": r["note"]})
    return out


__all__ = ["export_html", "export_netscape", "read_import", "normalize_tags", "normalize_url"]
