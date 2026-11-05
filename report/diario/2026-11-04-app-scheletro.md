# 2026-11-04 — App: scheletro con modalità sync/async

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 3 h · **Issue:** #25

## Cosa abbiamo fatto

Primo passo di M2 (app minima, scade l'11/11/2026). In `app/` c'è ora un solo programma Python/FastAPI (D0011, D0012) che si avvia in tre modi:

| Come si avvia | Che cosa è | Versioni |
|---|---|---|
| `MODE=sync` | API che salverà l'ordine nel database prima di rispondere | V1 (1 istanza), V2 (3 copie), V4 (3 copie e database replicato, nelle due modalità V4a asincrona e V4s sincrona) |
| `MODE=async` | API che metterà l'ordine in coda | V3 (con coda), V5 (V3 con scalatura automatica dei worker) |
| `MODE=async ROLE=worker` | worker che prende gli ordini dalla coda | V3 (3 worker), V5 (da 1 a 10 worker) |

Il codice è lo stesso in tutte e cinque le versioni (D0012). Ciò che distingue V1 da V2, V3 da V5 e V4a da V4s non è nel programma: sono il numero di copie e la scalatura con KEDA (nei manifest di Kubernetes) e la modalità di replica di PostgreSQL (nell'impostazione di CloudNativePG).

File: `app/config.py` (lettura e controllo delle variabili d'ambiente), `app/main.py` (fabbrica `crea_app`, che all'avvio scrive in una riga la configurazione letta), `app/test_config.py` (11 test), `app/requirements.txt` e `app/requirements-dev.txt` (versioni fisse). Tolte le cartelle vuote `app/api` e `app/worker`: con un codice unico non servono (lo diceva la stessa issue). Una riga del README aggiornata.

Variabili: `MODE` (obbligatoria), `ROLE` (predefinita `api`), `SERVICE_TIME_S` (predefinita 0), `DEADLINE_S`, `DATABASE_URL`, `BROKER_URL`. Per ora nessun endpoint e nessuna connessione: arrivano con le issue successive (#26, #30-#34).

## Perché

**`ROLE` in più rispetto a `MODE`.** La #25 diceva «API o worker a seconda di `MODE`», ma in V3 e V5 l'API e il worker sono entrambi `MODE=async` (lo dicono la #32 e la #33). Serviva un secondo interruttore. `MODE` resta quello di D0001 (come si riceve un ordine); `ROLE` dice solo quale dei due processi è. `MODE=sync` con `ROLE=worker` è rifiutato all'avvio: in V1, V2 e V4 non c'è nessuna coda.

**Nessun valore predefinito per la deadline.** I 1,5 s stanno già in `config/parametri.yaml` (`tempi.deadline_api_s`): ricopiarli nel codice li metterebbe in un terzo posto, proprio quello che la #41 vuole evitare. La deadline la passano docker-compose e i manifest; la #31 la renderà obbligatoria.

**Avvio con `--factory`.** La configurazione si legge quando parte il programma, non quando si importa il file: così i test non dipendono dall'ambiente.

## Struttura prevista del codice

Concordata il 04/11/2026: tre strati (API, servizio, accesso ai dati), senza mapper, con il SQL scritto a mano (servono `INSERT … ON CONFLICT DO NOTHING` di D0004 e `clock_timestamp()` di D0005, che un ORM nasconderebbe). Questi moduli non esistono ancora: nascono con la prima issue che li usa.

| Modulo | Cosa fa | Issue |
|---|---|---|
| `api.py` | riceve la richiesta HTTP e risponde 201, 202 o 503; le sonde | #26, #30, #32 |
| `modelli.py` | l'ordine ricevuto (`OrdineIn`, identificativo UUID), validato da FastAPI | #30 o #32, chi arriva per primo |
| `servizio.py` | la logica: sceglie con `MODE` se salvare o pubblicare, applica la deadline; la funzione di salvataggio è la stessa dell'API sincrona e del worker | #30, #31, #32 |
| `db.py` | pool di 5 connessioni (D0010) e SQL | #28, #29 |
| `broker.py` | pubblicazione con conferma e consumo dalla coda | #32, #33 |
| `worker.py` | ciclo del worker: salva, riprova, coda dei falliti | #33, #34 |

Non essendoci PR impilate (`CONTRIBUTING.md`), chi arriva per secondo su un file lo riusa dopo la fusione della PR dell'altro.

## Comandi e configurazione

```bash
cd app
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
MODE=sync uvicorn --factory main:crea_app
MODE=async uvicorn --factory main:crea_app
MODE=async ROLE=worker uvicorn --factory main:crea_app
```

## Risultato

11 test passati. Provato l'avvio nei tre modi: ognuno scrive la configurazione letta (`avvio: mode=sync role=api …`) e risponde 200 su `/openapi.json` (la pagina che FastAPI genera da sola; le sonde vere sono nella #26). Senza `MODE`, con un valore sbagliato o con `MODE=sync ROLE=worker` il programma non parte e dice quale variabile è sbagliata. Le password negli indirizzi non finiscono nel log.

## Problemi e soluzioni

- **Python locale diverso da quello della CI:** provato con Python 3.11 (su questo computer ci sono 3.11, 3.14 e 3.15). La CI usa 3.12 e l'immagine Docker (#27) userà la stessa: il codice usa solo funzioni presenti da 3.10.
- **Docker non usato:** per questa issue non serve; l'immagine arriva con la #27.

## Limiti dello strumento emersi

- **Nessun controllo automatico sul codice:** la CI (#41) oggi compila solo i documenti; i test dell'app non girano su GitHub finché non si aggiunge il passo per il codice (parte 2 della #41 sul codice).
