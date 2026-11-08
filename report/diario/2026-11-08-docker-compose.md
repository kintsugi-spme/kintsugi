# 2026-11-08 — Docker Compose per V1, V2 e V3

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 2 h · **Issue:** #35

## Cosa abbiamo fatto

Le tre versioni dell'app partono sul computer con un comando ciascuno, con Docker Compose, in `deploy/compose/`:

| File | Cosa fa |
|---|---|
| `base.yaml` | il database PostgreSQL 18.6, comune a tutte; carica `deploy/k8s/base/schema.sql` (lo stesso schema di Kubernetes) la prima volta |
| `v1.yaml` | una copia dell'API sincrona |
| `v2.yaml` | tre copie dell'API sincrona dietro un bilanciatore (`nginx`) |
| `v3.yaml` | coda RabbitMQ 4.4.0, API asincrona e tre worker |
| `nginx.conf` | il bilanciatore di V2: distribuisce a turno sulle tre copie |
| `Makefile` | `make v1`, `make v2`, `make v3` e `make giu` |
| `README.md` | uso, cosa parte, cose da sapere |

Nella rete Docker i container si chiamano `api`, `worker`, `db` e `coda`, come nella relazione di sintesi. Verso il computer si apre solo la porta 8000.

## Perché

- **Un file per versione sopra una base comune,** non i profili: così in ogni versione i servizi hanno gli stessi nomi.
- **La deadline non è riscritta:** `make` legge `tempi.deadline_api_s` da `config/parametri.yaml` e la passa come `DEADLINE_S`. Senza, `docker compose` si ferma con un errore (coerente con la regola della #62: obbligatoria per ogni API).
- **L'immagine si costruisce una volta sola,** nel Makefile; i file la usano e basta (`pull_policy: never`).
- **Controllo di RabbitMQ sulla porta,** non con `rabbitmq-diagnostics`: lanciato prima dell'avvio crea `.erlang.cookie` come root e il server non parte (limite già registrato nel diario del worker). Controllo del database con `-h 127.0.0.1`, perché durante la creazione del volume PostgreSQL risponde solo sul socket locale.
- **Due volumi** (`db-dati`, `coda-dati`): `docker compose stop db` e `start db` conservano i dati, `make giu` li cancella. Il nome del nodo di RabbitMQ è fisso (`coda`), così i dati si ritrovano anche dopo che il container è stato ricreato.
- **`stop_grace_period: 10s` su ogni servizio:** `docker stop` su Docker Desktop concede meno dei 10 s documentati (circa 1,5 s su un Mac, 3,2 s su un altro) e un'altra prova aveva lasciato PostgreSQL ucciso a metà dell'arresto. Con 10 s, `docker compose stop db` impiega 0,3 s e il database esce con codice 0.
- **Versioni fissate** delle immagini (`postgres:18.6-alpine`, `rabbitmq:4.4.0-alpine`, `nginx:1.29.8-alpine`), come Python e le librerie.

## Comandi e configurazione

```bash
cd deploy/compose
make v3                      # oppure v1, v2; riparte sempre da zero
python3 ../../harness/client/cliente.py --url http://localhost:8000/ordini --richieste 100 --ritmo 25
make v3 SERVICE_TIME_S=0.05  # tempo di servizio (predefinito 0)
make giu                     # ferma tutto e cancella i dati
```

## Risultato

Provato con il codice di `main` (che contiene #60 e #62) e con il client della #36:

| Prova | Risultato |
|---|---|
| V1: 100 ordini a 25/s | 100 × `201`, 100 salvati |
| V2: 100 ordini a 25/s | 100 × `201`, 100 salvati, **33 + 33 + 34** richieste sulle tre copie |
| V2: lo stesso ID 6 volte | 6 × `201`, 5 doppi registrati da 3 copie diverse (provato con il codice della #62 prima della fusione) |
| V3: 100 ordini a 25/s | 100 × `202`, 100 salvati, 3 worker collegati |
| V3, criterio 3: lo stesso ordine due volte | 1 ordine e 1 doppio (stesso codice della #62) |
| V3, criterio 4: database fermo 60 s con 600 ordini a 10/s | 600 × `202`, **700 su 700 salvati, 0 persi**, 0 nei falliti, coda vuota |
| Partenza a freddo senza immagine: V3, V1, V2 | tutte e tre partono; `make giu` non lascia container né volumi (4 s) |

## Problemi e soluzioni

- **V3 si fermava alla prima partenza** con «image already exists»: `api` e `worker` costruivano insieme la stessa immagine. Ora la costruisce il Makefile una volta sola.
- **`make giu` non cancellava il volume della coda,** perché `down -v` toglie solo i volumi dei servizi che conosce. Ora include `v3.yaml`.
- **Un messaggio di errore con «: » dentro un valore YAML senza virgolette** rendeva il file non valido: il valore è ora tra virgolette.
- **Stesso prefisso di kind:** i container del cluster kind si chiamano `kintsugi-control-plane` e `kintsugi-worker`, come il progetto Compose (`kintsugi`). `make giu` toglie solo i container con l'etichetta di Compose e non tocca quelli di kind (verificato).

## Limiti dello strumento emersi

- **Docker Desktop:** `docker stop` senza `-t` concede meno dei 10 s documentati prima di SIGKILL (voce già nella tabella con la PR #63); in Compose il limite si aggira con `stop_grace_period`.
- **Il worker gestisce ancora in modo provvisorio l'errore del database** (rimette l'ordine in coda): la prova del database fermo 60 s è stata fatta così. La riprova di D0003 (attese da 0,5 a 10 s, falliti dopo 120 s) è la #34, non ancora fatta; Compose userà il worker nuovo senza modifiche, perché l'immagine è la stessa.
- **Il bilanciatore di V2 è solo per provare l'app:** distribuisce a turno ma non riproduce il Service di Kubernetes (esclusione delle copie non pronte). Le prove sui guasti di V2 si fanno su Kubernetes, nella fase F3.
