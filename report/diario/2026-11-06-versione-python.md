# 2026-11-06 — Stessa versione di Python in tutti gli ambienti

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 0,5 h · **Issue:** #55

## Cosa abbiamo fatto

La versione di Python è la **3.14**, scritta in un solo posto e uguale in locale, nella CI e nell'immagine Docker (D0011).

| File | Cosa fa |
|---|---|
| `.python-version` | contiene `3.14`; lo legge `pyenv`, che cambia versione da solo entrando nella cartella |
| `.github/workflows/controlli.yml` | i tre job che usano Python leggono la versione da `.python-version` (`python-version-file`) invece di avere `"3.12"` scritto a mano |
| `.github/workflows/controlli.yml` | nuovo passo nel job «Test dell'app»: fallisce se il `FROM` del Dockerfile non è `python:<versione di .python-version>-slim` |
| `app/Dockerfile` | `FROM python:3.14-slim@sha256:…` (indice multi-architettura, 3.14.10 al momento) |
| `README.md` | prerequisito e badge dicono 3.14; comandi per preparare l'ambiente e controllare la versione |

## Perché

- **3.14 e non 3.12.** La issue proponeva la 3.12 solo perché era già in CI e nell'immagine. Sulle macchine di Gianmarco e Francesco c'è già la 3.14, quindi nessuno deve installare niente. Le librerie di oggi funzionano tutte sulla 3.14 (provato, vedi sotto).
- **Un solo file.** Se la versione fosse scritta in tre posti (CI, Dockerfile, README) prima o poi uno resterebbe indietro. In `.python-version` sta l'unica copia che si modifica a mano; il Dockerfile non può leggerla, e per questo c'è il controllo in CI.
- **`requirements.txt` non cambia.** Rigenerato dentro la nuova base, l'elenco è identico a quello fatto con la 3.12 (a parte `pip`, che il file stesso dice di togliere). Perciò nessun conflitto con le PR della coda (#32) e dei doppi (#29), che aggiungono righe allo stesso file.

## Comandi e configurazione

```bash
# controllo che il FROM coincida con .python-version (lo stesso della CI)
versione=$(cat .python-version)
grep -q "^FROM python:${versione}-slim@" app/Dockerfile && echo ok

# per preparare l'ambiente in locale
pyenv install 3.14
python --version          # 3.14.x
python -m venv .venv && source .venv/bin/activate
pip install -r app/requirements-dev.txt
```

## Risultato

- **Test:** 19 superati su Python 3.14.10, in un container `python:3.14-slim`.
- **Librerie delle altre PR:** `psycopg` 3.3.6 con `psycopg-binary` (implementazione `binary`) e `aio-pika` 10.1.1 si installano già compilate (`--only-binary`) e si importano sulla 3.14.
- **`requirements.txt`:** l'elenco rigenerato nella base con l'hash del nuovo `FROM` coincide con quello esistente.
- **Immagine:** si costruisce; avviata come API sincrona e come worker risponde `200` su `/openapi.json`, il processo 1 è `uvicorn` e Python è 3.14.10.
- **Controllo del `FROM`:** passa con 3.14 e fallisce simulando un'altra versione.

## Problemi e soluzioni

- **Solo la versione «minore» è uguale.** Nel `FROM` il codice di verifica blocca la patch (3.14.10), mentre `pyenv` sul Mac ha la 3.14.3 e la CI prende l'ultima 3.14.x. Per le misure non cambia nulla (gira sempre l'immagine); la differenza va solo ricordata.
- **Ambiente virtuale locale da ricreare.** Il `.venv` nella radice usa Python 3.15: chi l'ha creato con un'altra versione deve rifarlo.
- **Rigenerazione dell'elenco:** la prima volta il comando con sostituzione di processo (`<(...)`) non funzionava nella shell del container (`sh`); ho confrontato l'elenco fuori dal container.

## Limiti dello strumento emersi

- **La CI controlla solo che il `FROM` abbia la stessa versione minore di `.python-version`,** non che l'hash dell'immagine sia aggiornato né che `pyenv` sia installato sulle macchine di chi lavora.
- **Le librerie future non sono garantite:** la 3.14 è uscita da meno tempo della 3.12, quindi un aggiornamento di libreria potrebbe richiedere una verifica in più. Quelle fissate oggi funzionano.
