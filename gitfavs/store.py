"""Archivio dei bookmarks: un unico file JSON."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

FILE_NAME = "bookmarks.json"
VERSION = 1


class GitFavsError(Exception):
    """Errore atteso, mostrato all'utente senza traceback."""


CONFIG_FILE = Path.home() / ".gitfavs" / "config.json"


def read_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_home() -> Path:
    """Cartella dati dal file di configurazione, altrimenti ~/.gitfavs (o ~/.bukmarks se esiste gia': vecchia versione)."""
    if home := read_config().get("home"):
        return Path(home).expanduser()
    new, legacy = Path.home() / ".gitfavs", Path.home() / ".bukmarks"
    return legacy if legacy.exists() and not new.exists() else new


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


SAFE_SCHEMES = ("http", "https", "ftp", "mailto")
WEB_SCHEMES = ("http", "https")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


def clean(text: str) -> str:
    """Rimuove i caratteri di controllo (es. sequenze ESC) per non pilotare il terminale."""
    return _CONTROL.sub(" ", str(text)).strip()


def is_safe_href(url: str, schemes=SAFE_SCHEMES) -> bool:
    return urlsplit(url).scheme.lower() in schemes


def normalize_url(url: str) -> str:
    url = clean(url)
    if not url:
        raise GitFavsError("indirizzo vuoto")
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(//)?", url)
    if m and (m.group(2) or not re.match(r"^[^:/]+:\d", url)):
        # schema esplicito: solo quelli sicuri (niente javascript:, data:, file:, ...)
        if m.group(1).lower() not in SAFE_SCHEMES:
            raise GitFavsError(f"schema non consentito: {m.group(1)}:")
    else:
        url = "https://" + url
    parts = urlsplit(url)
    if not parts.netloc and parts.scheme != "mailto":
        raise GitFavsError(f"indirizzo non valido: {url}")
    return url


def normalize_tags(raw) -> list[str]:
    tags: list[str] = []
    for chunk in raw or []:
        for t in str(chunk).split(","):
            t = re.sub(r"\s+", "-", t.strip().lstrip("#").lower())
            if t and t not in tags:
                tags.append(t)
    return tags


@dataclass
class Bookmark:
    id: int
    url: str
    title: str
    tags: list[str] = field(default_factory=list)
    note: str = ""
    created: str = ""
    updated: str = ""

    def __post_init__(self):
        self.title, self.note, self.url = clean(self.title), clean(self.note), clean(self.url)
        self.tags = [clean(t) for t in self.tags]

    @property
    def date(self) -> str:
        return (self.created or "")[:10]


class Library:
    def __init__(self, home: Path):
        self.home = home
        self.path = home / FILE_NAME
        self.items: list[Bookmark] = []
        self.next_id = 1

    # -- persistenza ---------------------------------------------------------
    def load(self) -> "Library":
        if not self.path.exists():
            return self
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.items = [Bookmark(**b) for b in data.get("bookmarks", [])]
            self.next_id = int(data.get("next_id", 0)) or 1
        except (ValueError, TypeError, AttributeError) as e:
            raise GitFavsError(f"file dei bookmarks corrotto ({self.path}): {e}") from e
        self.next_id = max([self.next_id] + [b.id + 1 for b in self.items])
        return self

    def save(self) -> None:
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        data = {
            "version": VERSION,
            "next_id": self.next_id,
            "bookmarks": [asdict(b) for b in sorted(self.items, key=lambda b: b.id)],
        }
        fd, tmp = tempfile.mkstemp(dir=self.home, prefix=".bookmarks-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- operazioni ----------------------------------------------------------
    def by_url(self, url: str) -> Bookmark | None:
        key = url.rstrip("/").lower()
        return next((b for b in self.items if b.url.rstrip("/").lower() == key), None)

    def get(self, bid: int) -> Bookmark:
        for b in self.items:
            if b.id == bid:
                return b
        raise GitFavsError(f"nessun bookmark con id {bid}")

    def add(self, url: str, title: str, tags=None, note: str = "") -> Bookmark:
        ts = now()
        b = Bookmark(self.next_id, url, clean(title) or url, normalize_tags(tags), note, ts, ts)
        self.next_id += 1
        self.items.append(b)
        return b

    def remove(self, bid: int) -> Bookmark:
        b = self.get(bid)
        self.items.remove(b)
        return b

    def tag_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for b in self.items:
            for t in b.tags:
                counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def search(self, terms: list[str], tags=None, everywhere=False, regex=False) -> list[Bookmark]:
        """Tutti i termini devono comparire (AND) nel nome o nell'indirizzo.
        Con `everywhere` si cerca anche in tag e note."""
        tags = normalize_tags(tags)
        if regex:
            try:
                rxs = [re.compile(t, re.IGNORECASE) for t in terms]
            except re.error as e:
                raise GitFavsError(f"espressione regolare non valida: {e}") from e
            hit = lambda t, text: rxs[t].search(text) is not None  # noqa: E731
        else:
            low = [t.lower() for t in terms]
            hit = lambda t, text: low[t] in text.lower()  # noqa: E731

        scored: list[tuple[int, Bookmark]] = []
        for b in self.items:
            if any(t not in b.tags for t in tags):
                continue
            score = 0
            for i in range(len(terms)):
                s = 0
                if hit(i, b.title):
                    s += 3
                if hit(i, b.url):
                    s += 2
                if everywhere and (hit(i, " ".join(b.tags)) or hit(i, b.note)):
                    s += 1
                if not s:
                    break
                score += s
            else:
                scored.append((score, b))
        scored.sort(key=lambda sb: (-sb[0], sb[1].title.lower()))
        return [b for _, b in scored]
