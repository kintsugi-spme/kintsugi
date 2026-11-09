# 2026-11-09 — CI con PostgreSQL e RabbitMQ veri

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 1 h · **Issue:** #41

## Cosa abbiamo fatto

Il job «Test dell'app» di `.github/workflows/controlli.yml` avvia PostgreSQL e RabbitMQ come servizi, così le prove che hanno bisogno di loro girano nella CI invece di saltarsi:

| Parte | Cosa fa |
|---|---|
| `services:` | `postgres:18.6-alpine` e `rabbitmq:4.4.0-alpine`, le stesse versioni di `deploy/compose` |
| `env:` | `TEST_DATABASE_URL` e `TEST_BROKER_URL`, gli indirizzi che le prove leggono (utente e password di RabbitMQ sono valori di prova) |
| Passo «Aspetta PostgreSQL e RabbitMQ e carica lo schema» | si collega davvero a entrambi, riprovando fino a 60 s, e carica `deploy/k8s/base/schema.sql` |

Nelle prime righe di `test_db.py`, `test_api_sincrona.py`, `test_broker.py` e `test_worker.py` la frase «non girano nella CI» è sostituita da quella che dice che ci girano. Il codice dell'app non cambia.

## Perché

- **Le prove si saltavano senza dirlo.** Senza gli indirizzi, 15 prove (database, API sincrona, broker, worker) erano «saltate» e la CI risultava verde lo stesso: una PR che rompeva la scrittura nel database o la coda non diventava rossa.
- **Stesse versioni di Compose.** Le immagini sono fissate come in `deploy/compose` (D0011). Non c'è un controllo che le tenga allineate: se se ne cambia una, va cambiata anche l'altra.
- **Nessun `health-cmd` su RabbitMQ.** Un comando lanciato prima dell'avvio del server crea `.erlang.cookie` come root e il server non parte (limite già nella tabella di `report/diario/README.md`). La prontezza si controlla con un collegamento vero.
- **Non basta una porta aperta.** Docker pubblica la porta prima che il servizio sia pronto e accetta la connessione anche allora: il passo di attesa fa un login vero (PostgreSQL) e una connessione AMQP (RabbitMQ).
- **PostgreSQL con `trust`,** senza password: il servizio esiste solo per la durata del job.

## Comandi e configurazione

Il passo di attesa, in sintesi:

```bash
python - <<'PY'
# riprova per 60 s: psycopg.connect(TEST_DATABASE_URL) + schema.sql, poi aio_pika.connect(TEST_BROKER_URL)
PY
pytest -q
```

Per provare le stesse prove sul proprio computer, i comandi per avviare i due servizi sono nelle prime righe dei file di prova.

## Risultato

Sulla CI della PR (09/11/2026):

| Passo | Risultato |
|---|---|
| Servizi avviati e pronti | PostgreSQL con lo schema e RabbitMQ pronti, in circa 1 s dopo l'installazione delle librerie |
| `pytest -q` nell'app | **68 passate, 0 saltate**, in 4,8 s (prima della modifica: 53 passate e 15 saltate) |
| Prove del client (`harness/client`) | 7 passate |
| Intero job «Test dell'app» | 36 s |
| Tutti i controlli della PR | 6 su 6 verdi |

Sul Mac le stesse prove con i servizi veri erano già 68 su 68.

## Problemi e soluzioni

- **Il caso «il servizio non risponde» è provato; quello «risponde» solo sulla CI.** In locale Docker Desktop era spento, quindi ho provato che il passo di attesa fallisce con un messaggio chiaro (`::error::PostgreSQL non risponde dopo 60 s`), e il caso in cui i servizi rispondono l'ha provato la CI stessa.
- **La CI su `main` dopo la fusione della #66 è fallita per un'interruzione di GitHub Actions,** non per questa modifica (vedi i limiti).

## Limiti dello strumento emersi

- **GitHub Actions:** il 09/11/2026 un'interruzione del servizio ha fatto partire la CI su `main` senza job («workflow file issue», senza che il file avesse errori). Con «Re-run all jobs» è passata. Nessun effetto sulle misure.
- **Possibili oscillazioni:** `test_api_sincrona.py` controlla un tempo di servizio con margini di pochi ms e su una macchina di GitHub più lenta potrebbe oscillare. Con un solo run non si può escludere; se succede si allarga il margine o si sposta la prova tra quelle da lanciare solo in locale.
- **I controlli sui manifest Kubernetes** (previsti dalla #41) non sono fatti: in `deploy/k8s` c'è solo lo schema. La #41 resta aperta per aggiungerli.
