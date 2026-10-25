# GitFavs

Bookmarks manager da riga di comando (Python ≥ 3.9, nessuna dipendenza). I bookmarks stanno in un unico
file JSON (`~/.gitfavs/bookmarks.json`, cambiabile con `gf path --set <cartella>`, salvato in `~/.gitfavs/config.json`) dentro un repository git:
**ogni modifica fa commit e, se c'è un remote, push in automatico.**

## Installazione

```bash
pip install -e .        # crea il comando `gf`
# oppure, senza installare: python3 -m gitfavs <comando>
```

## Uso

| Comando | Descrizione |
|---|---|
| `gf add <url> [-t titolo] [-T tag,tag] [-n nota]` | salva un indirizzo (titolo letto dalla pagina) |
| `gf find <testo…> [-T tag] [-a] [-r]` | cerca in nome e indirizzo (`-a` anche tag/note, `-r` regex) |
| `gf list [-T tag] [-s id\|title\|date]` | elenca tutto |
| `gf show <id>` / `open <id…>` | dettagli / apri nel browser |
| `gf edit <id> [--title --url --note --add-tag --rm-tag]` | modifica |
| `gf rm <id…> [-y]` | elimina |
| `gf tags` | tag e conteggi |
| `gf export <file.html> [-f netscape]` | pagina HTML pulita divisa in sezioni per tag, con filtro live, o formato importabile dai browser |
| `gf refresh` | rigenera `bookmarks.html` in `~/.gitfavs` (commit e push se cambia) |
| `gf import <file.json\|.html>` | importa da JSON o dai preferiti di Chrome/Firefox/Safari (le cartelle diventano tag) |
| `gf check [-T tag]` | trova i link non raggiungibili |
| `gf remote [url]` | imposta il repository remoto per il push |
| `gf sync` | pull + push (più computer) |
| `gf log` / `path` | cronologia git / percorso dei file JSON e HTML (`path json\|html` per un solo percorso, `path --set <cartella>` / `--reset` per cambiarlo) |

## Backup su GitHub

```bash
gf remote git@github.com:utente/miei-bookmarks.git
```
Da quel momento ogni `add`/`edit`/`rm` fa push. Su un altro computer: `git clone <url> ~/.gitfavs`.
Se il push fallisce (offline) il commit resta locale e viene inviato al prossimo salvataggio o con `sync`.
