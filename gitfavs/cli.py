"""Interfaccia da riga di comando di GitFavs."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__, colors, exporters, gitsync
from .colors import paint
from .store import (FILE_NAME, WEB_SCHEMES, Bookmark, GitFavsError, Library, clean, default_home, is_safe_href,
                    normalize_tags, normalize_url, read_config, write_config, CONFIG_FILE)

EXPORT_NAME = "bookmarks.html"  # export automatico accanto al JSON
UA = {"User-Agent": "Mozilla/5.0 (compatible; GitFavs)"}


# -- helper ------------------------------------------------------------------
def fetch_title(url: str) -> str:
    if not is_safe_href(url, WEB_SCHEMES):
        return ""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=6) as r:
            if "html" not in r.headers.get("Content-Type", "html"):
                return ""
            charset = r.headers.get_content_charset() or "utf-8"
            html = r.read(131072).decode(charset, errors="replace")
    except Exception:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    from html import unescape
    return clean(unescape(m.group(1)))


def persist(lib: Library, message: str) -> None:
    """Salva il JSON, esporta l'HTML, poi commit + push automatici."""
    lib.save()
    (lib.home / EXPORT_NAME).write_text(exporters.export_html(lib.items, "Bookmarks"), encoding="utf-8")
    colors.info(f"  export · {paint(str(lib.home / EXPORT_NAME), 'cyan')}")
    res = gitsync.autosave(lib.home, message, (FILE_NAME, EXPORT_NAME))
    parts = []
    if res.commit:
        parts.append(f"commit {res.commit}")
    if res.pushed:
        parts.append("push ok")
    elif res.pushed is None:
        parts.append("solo locale (nessun remote: `gf remote <url>`)")
    if parts:
        colors.info("  git · " + " · ".join(parts))
    if res.pushed is False:
        colors.warn(f"push non riuscito, i dati sono al sicuro nel commit locale ({res.error})")


def term_width() -> int:
    return max(40, shutil.get_terminal_size((100, 24)).columns)


def clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def print_bookmark(b: Bookmark, terms=None, regex=False, everywhere=False) -> None:
    terms = terms or []
    w = term_width() - 8
    idtxt = paint(f"{b.id:>4}", "yellow", "bold")
    title = colors.highlight(clip(b.title, w), terms, "bold", "white", regex=regex)
    print(f"{idtxt}  {paint(title, 'bold', 'white')}")
    url = colors.highlight(clip(b.url, w), terms, "cyan", "underline", regex=regex)
    print(f"      {paint(url, 'cyan', 'underline')}")
    meta = []
    if b.tags:
        meta.append(paint(" ".join("#" + t for t in b.tags), "magenta"))
    if b.date:
        meta.append(paint(b.date, "gray"))
    if meta:
        print("      " + paint("  ·  ", "gray").join(meta))
    if b.note:
        note = colors.highlight(clip(b.note, w), terms if everywhere else [], "dim", regex=regex)
        print("      " + paint(note, "dim"))
    print()


def parse_id(value: str) -> int:
    try:
        return int(value.lstrip("#"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"id non valido: {value}")


def load() -> Library:
    return Library(default_home()).load()


# -- comandi -----------------------------------------------------------------
def cmd_add(a) -> None:
    lib = load()
    url = normalize_url(a.url)
    if dup := lib.by_url(url):
        raise GitFavsError(f"gia' presente come #{dup.id}: {dup.title}")
    title = a.title or ("" if a.no_fetch else fetch_title(url))
    if not title and not a.title and not a.no_fetch:
        colors.warn("titolo non recuperato, uso l'indirizzo (modificabile con `edit`)")
    b = lib.add(url, title, a.tag, a.note or "")
    colors.ok(f"aggiunto {paint('#' + str(b.id), 'yellow', 'bold')}")
    print()
    print_bookmark(b)
    persist(lib, f"add: {b.title} ({b.url})")


def cmd_find(a) -> None:
    if not a.query and not a.tag:
        raise GitFavsError("indica cosa cercare, oppure --tag")
    lib = load()
    found = lib.search(a.query, a.tag, everywhere=a.all, regex=a.regex)
    label = " ".join(a.query) + (" " if a.query and a.tag else "") + " ".join("#" + t for t in normalize_tags(a.tag))
    if not found:
        colors.warn(f"nessun risultato per «{label}»")
        raise SystemExit(1)
    print(f"{paint(str(len(found)), 'green', 'bold')} risultati per {paint('«' + label + '»', 'bold')}\n")
    for b in found:
        print_bookmark(b, a.query, regex=a.regex, everywhere=a.all)


def cmd_list(a) -> None:
    lib = load()
    items = [b for b in lib.items if all(t in b.tags for t in normalize_tags(a.tag))]
    key = {"id": lambda b: b.id, "title": lambda b: b.title.lower(), "date": lambda b: b.created}[a.sort]
    items.sort(key=key, reverse=(a.sort == "date"))
    if not items:
        colors.warn("nessun bookmark")
        return
    w = term_width()
    tw = max(20, (w - 8) // 3)
    for b in items:
        tags = paint(" ".join("#" + t for t in b.tags), "magenta")
        url = clip(b.url, max(10, w - tw - 8 - len(" ".join(b.tags)) - 3))
        print(f"{paint(f'{b.id:>4}', 'yellow')}  {paint(clip(b.title, tw).ljust(tw), 'bold', 'white')}  {paint(url, 'cyan')}  {tags}")
    print(paint(f"\n{len(items)} bookmarks", "dim"))


def cmd_show(a) -> None:
    b = load().get(a.id)
    rows = [("id", b.id), ("titolo", b.title), ("url", b.url), ("tag", " ".join("#" + t for t in b.tags) or "-"),
            ("nota", b.note or "-"), ("creato", b.created), ("modificato", b.updated)]
    for k, v in rows:
        style = ("cyan", "underline") if k == "url" else ("bold",) if k == "titolo" else ()
        print(f"{paint(k.ljust(11), 'gray')}{paint(v, *style)}")


def cmd_edit(a) -> None:
    lib = load()
    b = lib.get(a.id)
    changed = False
    if a.title is not None:
        b.title, changed = clean(a.title), True
    if a.url is not None:
        url = normalize_url(a.url)
        if (dup := lib.by_url(url)) and dup.id != b.id:
            raise GitFavsError(f"indirizzo gia' presente come #{dup.id}")
        b.url, changed = url, True
    if a.note is not None:
        b.note, changed = clean(a.note), True
    for t in normalize_tags(a.add_tag):
        if t not in b.tags:
            b.tags.append(t)
            changed = True
    for t in normalize_tags(a.rm_tag):
        if t in b.tags:
            b.tags.remove(t)
            changed = True
    if not changed:
        raise GitFavsError("nessuna modifica richiesta (--title --url --note --add-tag --rm-tag)")
    from .store import now
    b.updated = now()
    colors.ok(f"modificato #{b.id}\n")
    print_bookmark(b)
    persist(lib, f"edit: #{b.id} {b.title}")


def cmd_rm(a) -> None:
    lib = load()
    removed = []
    for bid in a.ids:
        b = lib.get(bid)
        if not a.yes and sys.stdin.isatty():
            if input(f"Eliminare #{b.id} «{b.title}»? [s/N] ").strip().lower() not in ("s", "si", "y", "yes"):
                continue
        lib.remove(bid)
        removed.append(b)
    for b in removed:
        colors.ok(f"eliminato #{b.id} {b.title}")
    if removed:
        persist(lib, "rm: " + ", ".join(f"#{b.id} {b.title}" for b in removed))


def cmd_tags(a) -> None:
    counts = load().tag_counts()
    if not counts:
        colors.warn("nessun tag")
        return
    width = max(len(t) for t in counts)
    for t, n in counts.items():
        print(f"{paint('#' + t.ljust(width), 'magenta')}  {paint(str(n), 'yellow')}")


def cmd_open(a) -> None:
    lib = load()
    for bid in a.ids:
        b = lib.get(bid)
        if not is_safe_href(b.url, WEB_SCHEMES):
            colors.warn(f"#{b.id}: apro solo http/https, saltato")
            continue
        webbrowser.open(b.url)
        colors.ok(f"aperto {b.title}")


def cmd_export(a) -> None:
    lib = load()
    if a.format == "netscape":
        content = exporters.export_netscape(lib.items)
    else:
        content = exporters.export_html(lib.items, a.title)
    out = Path(a.file).expanduser()
    out.write_text(content, encoding="utf-8")
    colors.ok(f"{len(lib.items)} bookmarks esportati in {paint(str(out), 'cyan', 'underline')}")


def cmd_refresh(a) -> None:
    lib = load()
    persist(lib, "refresh: export HTML")
    colors.ok(f"{len(lib.items)} bookmarks ri-esportati in {paint(str(lib.home / EXPORT_NAME), 'cyan', 'underline')}")


def cmd_import(a) -> None:
    lib = load()
    rows = exporters.read_import(Path(a.file).expanduser())
    added = skipped = 0
    for r in rows:
        try:
            url = normalize_url(r["url"])
        except GitFavsError:
            skipped += 1
            continue
        if lib.by_url(url):
            skipped += 1
            continue
        lib.add(url, r["title"], [*r["tags"], *(a.tag or [])], r["note"])
        added += 1
    colors.ok(f"importati {paint(str(added), 'green', 'bold')} bookmarks ({skipped} saltati: duplicati o non validi)")
    if added:
        persist(lib, f"import: {added} bookmarks da {Path(a.file).name}")


def cmd_check(a) -> None:
    lib = load()
    items = [b for b in lib.items if all(t in b.tags for t in normalize_tags(a.tag))]

    def probe(b: Bookmark):
        if not is_safe_href(b.url, WEB_SCHEMES):
            return b, None, "schema non verificabile"
        try:
            req = urllib.request.Request(b.url, headers=UA, method="HEAD")
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                return b, r.status, None
        except urllib.error.HTTPError as e:
            return b, e.code, None
        except Exception as e:
            return b, None, str(getattr(e, "reason", e))

    bad = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        for b, status, err in ex.map(probe, items):
            if status is not None and status < 400:
                if a.verbose:
                    print(f"{paint('✓', 'green')} {paint(status, 'green')}  #{b.id} {b.title}")
                continue
            bad += 1
            reason = f"HTTP {status}" if status else err
            print(f"{paint('✗', 'red', 'bold')} {paint(reason, 'red')}  #{b.id} {paint(b.title, 'bold')}\n    {paint(b.url, 'cyan')}")
    (colors.ok if not bad else colors.warn)(f"controllati {len(items)} link, {bad} non raggiungibili")
    if bad:
        raise SystemExit(1)


def cmd_remote(a) -> None:
    home = default_home()
    if a.url:
        gitsync.set_remote(home, a.url)
        colors.ok(f"remote origin = {paint(a.url, 'cyan')}")
        if (home / "bookmarks.json").exists():
            gitsync.ensure_repo(home)
            res = gitsync.autosave(home, "chore: collega il remote")
            if res.pushed:
                colors.info("  push ok")
            elif res.error:
                colors.warn(res.error)
    else:
        gitsync.ensure_repo(home)
        url = gitsync.remote_url(home)
        print(paint(url, "cyan") if url else paint("nessun remote configurato", "dim"))


def cmd_sync(a) -> None:
    home = default_home()
    colors.ok(gitsync.sync(home))


def cmd_log(a) -> None:
    entries = gitsync.log(default_home(), a.n)
    if not entries:
        colors.warn("nessuna cronologia")
    for h, d, s in entries:
        print(f"{paint(h, 'yellow')}  {paint(d, 'gray')}  {s}")


def cmd_path(a) -> None:
    if a.set or a.reset:
        old = default_home()
        cfg = read_config()
        if a.reset:
            cfg.pop("home", None)
        else:
            cfg["home"] = str(Path(a.set).expanduser().resolve())
        write_config(cfg)
        new = default_home()
        colors.ok(f"cartella dati = {paint(str(new), 'cyan', 'underline')}  (config: {CONFIG_FILE})")
        if new != old and (old / FILE_NAME).exists() and not (new / FILE_NAME).exists():
            colors.warn(f"i dati esistenti sono rimasti in {old}: copiali in {new} per continuare a usarli")
        return
    home = default_home()
    files = {"json": home / FILE_NAME, "html": home / EXPORT_NAME}
    if a.which:
        print(files[a.which])
        return
    print(f"{paint('cartella'.ljust(9), 'gray')}{paint(str(home), 'cyan')}")
    files["config"] = CONFIG_FILE
    for k, f in files.items():
        state = "" if f.exists() else paint("  (non ancora creato)", "dim")
        print(f"{paint(k.ljust(9), 'gray')}{paint(str(f), 'cyan', 'underline')}{state}")


# -- parser ------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gf",
        description="Gestore di bookmarks da terminale. Ogni modifica e' salvata con commit e push automatici.",
        epilog="Cartella dati: `gf path` (default ~/.gitfavs, cambiabile con `gf path --set`). NO_COLOR disattiva i colori.",
    )
    p.add_argument("-V", "--version", action="version", version=f"GitFavs {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="comando")

    def add(name, func, help, aliases=()):
        sp = sub.add_parser(name, help=help, description=help, aliases=list(aliases))
        sp.set_defaults(func=func)
        return sp

    s = add("add", cmd_add, "salva un indirizzo (il titolo viene letto dalla pagina)")
    s.add_argument("url")
    s.add_argument("-t", "--title", help="titolo (altrimenti recuperato dal sito)")
    s.add_argument("-T", "--tag", action="append", help="tag, ripetibile o separato da virgole")
    s.add_argument("-n", "--note", help="nota libera")
    s.add_argument("--no-fetch", action="store_true", help="non scaricare la pagina per il titolo")

    s = add("find", cmd_find, "cerca per testo nel nome e nell'indirizzo", aliases=["search", "f"])
    s.add_argument("query", nargs="*", help="termini (devono comparire tutti)")
    s.add_argument("-T", "--tag", action="append", help="filtra per tag")
    s.add_argument("-a", "--all", action="store_true", help="cerca anche in tag e note")
    s.add_argument("-r", "--regex", action="store_true", help="i termini sono espressioni regolari")

    s = add("list", cmd_list, "elenca i bookmarks", aliases=["ls"])
    s.add_argument("-T", "--tag", action="append", help="filtra per tag")
    s.add_argument("-s", "--sort", choices=["id", "title", "date"], default="id")

    s = add("show", cmd_show, "mostra i dettagli di un bookmark")
    s.add_argument("id", type=parse_id)

    s = add("edit", cmd_edit, "modifica un bookmark")
    s.add_argument("id", type=parse_id)
    s.add_argument("-t", "--title")
    s.add_argument("-u", "--url")
    s.add_argument("-n", "--note")
    s.add_argument("--add-tag", action="append")
    s.add_argument("--rm-tag", action="append")

    s = add("rm", cmd_rm, "elimina uno o piu' bookmarks", aliases=["remove", "del"])
    s.add_argument("ids", type=parse_id, nargs="+")
    s.add_argument("-y", "--yes", action="store_true", help="non chiedere conferma")

    add("tags", cmd_tags, "elenca i tag con il numero di bookmarks")

    s = add("open", cmd_open, "apre i bookmarks nel browser")
    s.add_argument("ids", type=parse_id, nargs="+")

    s = add("export", cmd_export, "esporta in un file HTML")
    s.add_argument("file", help="file di destinazione")
    s.add_argument("-f", "--format", choices=["html", "netscape"], default="html",
                   help="html = pagina pulita; netscape = importabile dai browser")
    s.add_argument("--title", default="Bookmarks", help="titolo della pagina")

    add("refresh", cmd_refresh, f"rigenera {EXPORT_NAME} nella cartella dati (con commit e push se cambia)")

    s = add("import", cmd_import, "importa da JSON GitFavs o da HTML esportato dai browser")
    s.add_argument("file")
    s.add_argument("-T", "--tag", action="append", help="tag aggiunto a tutti gli importati")

    s = add("check", cmd_check, "verifica che i link siano raggiungibili")
    s.add_argument("-T", "--tag", action="append")
    s.add_argument("--timeout", type=float, default=8)
    s.add_argument("-v", "--verbose", action="store_true", help="mostra anche i link funzionanti")

    s = add("remote", cmd_remote, "mostra o imposta il repository git remoto per il push")
    s.add_argument("url", nargs="?")

    add("sync", cmd_sync, "pull dal remote e push (utile con piu' computer)")
    s = add("log", cmd_log, "cronologia delle modifiche (git)")
    s.add_argument("-n", type=int, default=15)
    s = add("path", cmd_path, "mostra la posizione dei file JSON e HTML dei bookmarks")
    s.add_argument("which", nargs="?", choices=["json", "html"], help="stampa solo il percorso di quel file (adatto a script)")
    s.add_argument("--set", metavar="CARTELLA", help="cambia la cartella dati (salvata nel file di configurazione)")
    s.add_argument("--reset", action="store_true", help="torna alla cartella predefinita (~/.gitfavs)")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        args.func(args)
    except GitFavsError as e:
        colors.error(str(e))
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    return 0
