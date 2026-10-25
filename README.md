# GitFavs

Gestore di bookmarks da riga di comando (comando `gf`). Python ≥ 3.9, nessuna dipendenza esterna.

- **Un solo file JSON** con tutti i bookmarks (`bookmarks.json`).
- **Git automatico**: ogni modifica fa commit e, se c'è un remote, push. Non devi mai lanciare `git` a mano.
- **Export HTML automatico**: dopo ogni modifica viene rigenerato `bookmarks.html`, una pagina minimale divisa per tag con filtro live.
- **Output a colori** (disattivabili con `NO_COLOR`), con i termini cercati evidenziati.

## Come funziona

I dati vivono in una cartella che è anche un repository git (default `~/.gitfavs`):

```
~/.gitfavs/
├── bookmarks.json   # archivio dei bookmarks
├── bookmarks.html   # export pulito, rigenerato a ogni modifica
├── config.json      # impostazioni (creato solo se cambi la cartella dati)
└── .git/
```

Ogni comando che modifica i dati (`add`, `edit`, `rm`, `import`, `refresh`) esegue in ordine: salvataggio atomico del JSON,
rigenerazione dell'HTML, commit di `bookmarks.json` e `bookmarks.html`, push se esiste un remote.
Se il push fallisce (offline) il commit resta locale e parte al salvataggio successivo o con `gf sync`.

## Installazione

```bash
pipx install .          # installa il comando `gf` (consigliato)
pip install -e .        # alternativa per sviluppare
python3 -m gitfavs <comando>   # senza installare
```

Aggiornare dopo una modifica o una nuova versione:

```bash
pipx install --force .            # reinstalla dai sorgenti
# oppure, per generare i pacchetti distribuibili (wheel + sdist in dist/):
pyproject-build
pipx install --force dist/gitfavs-<versione>-py3-none-any.whl
```

La versione si imposta in `gitfavs/__init__.py`. Con un'installazione editable (`pip install -e .`) le modifiche al codice sono subito attive.

## Uso

| Comando | Descrizione |
|---|---|
| `gf add <url> [-t titolo] [-T tag,tag] [-n nota] [--no-fetch]` | salva un indirizzo (titolo letto dalla pagina) |
| `gf find <testo…> [-T tag] [-a] [-r]` | cerca in nome e indirizzo (`-a` anche tag/note, `-r` regex) |
| `gf list [-T tag] [-s id\|title\|date]` | elenca tutto |
| `gf show <id>` / `open <id…>` | dettagli / apri nel browser |
| `gf edit <id> [--title --url --note --add-tag --rm-tag]` | modifica |
| `gf rm <id…> [-y]` | elimina |
| `gf tags` | tag e conteggi |
| `gf export <file.html> [-f netscape] [--title]` | pagina HTML pulita divisa per tag, oppure formato importabile dai browser |
| `gf refresh` | rigenera `bookmarks.html` nella cartella dati (commit e push se cambia) |
| `gf import <file.json\|.html>` | importa da JSON o dai preferiti di Chrome/Firefox/Safari (le cartelle diventano tag) |
| `gf check [-T tag] [--timeout s] [-v]` | trova i link non raggiungibili |
| `gf remote [url]` | mostra o imposta il repository remoto per il push |
| `gf sync` | pull + push (più computer) |
| `gf log [-n N]` | cronologia delle modifiche (git) |
| `gf path` | cartella dati e percorsi di JSON, HTML e configurazione |

## Posizione dei file

```bash
gf path                      # cartella, JSON, HTML e config
gf path json                 # solo il percorso del JSON (adatto a script)
gf path html                 # solo il percorso dell'HTML
gf path --set ~/Dropbox/gf   # sposta la cartella dati
gf path --reset              # torna a ~/.gitfavs
```

Il file di configurazione è sempre `~/.gitfavs/config.json`, anche se i dati sono altrove.
`--set` cambia solo il puntatore: i file esistenti non vengono spostati, copiali a mano nella nuova cartella.

## Backup su GitHub

```bash
gf remote git@github.com:utente/miei-bookmarks.git
```

Da quel momento ogni `add`/`edit`/`rm` fa push. Su un altro computer: `git clone <url> ~/.gitfavs`, poi `gf sync` per allinearsi.
