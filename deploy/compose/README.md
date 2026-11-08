# Docker Compose: V1, V2 e V3 sul computer

Serve a verificare l'app durante la fase F2 (milestone M2). Il confronto tra le versioni si fa su Kubernetes (F3), non qui.

## Come si usa

Serve Docker Desktop. Da questa cartella:

```bash
make v1      # una copia dell'API sincrona                      → 201
make v2      # tre copie dell'API sincrona dietro un bilanciatore → 201
make v3      # API con la coda e tre worker                     → 202
make giu     # ferma tutto e cancella i dati (database e coda)
```

Ogni comando riparte da zero: prima cancella quello che c'era, poi costruisce l'immagine `kintsugi:dev` dal codice di `../../app` (una volta sola) e aspetta che tutti i container siano pronti. L'API risponde su `http://localhost:8000/ordini`. Per inviare ordini:

```bash
python3 ../../harness/client/cliente.py --url http://localhost:8000/ordini --richieste 100 --ritmo 20
```

Il tempo di servizio si imposta a parte (predefinito 0): `make v3 SERVICE_TIME_S=0.05`.

## Che cosa parte

| Versione | Container | Note |
|---|---|---|
| V1 | `api`, `db` | |
| V2 | `api` (3 copie), `bilanciatore`, `db` | il bilanciatore (nginx) distribuisce a turno; su Kubernetes ci sarà un Service |
| V3 | `api`, `coda`, `worker` (3 copie), `db` | l'API non si collega al database |

Nella rete Docker i container si trovano per nome: `db` (PostgreSQL 18.6) e `coda` (RabbitMQ 4.4.0). Verso il computer si apre solo la porta 8000.

## Cose da sapere

- **La deadline non si scrive qui.** `make` la legge da `config/parametri.yaml` (`tempi.deadline_api_s`) e la passa come `DEADLINE_S`. Se si lancia `docker compose` a mano senza, si ferma con un errore: è voluto.
- **Lo schema del database è `deploy/k8s/base/schema.sql`,** lo stesso che userà Kubernetes. Si carica una volta sola, quando il volume è vuoto.
- **I dati stanno in due volumi** (`db-dati`, `coda-dati`): `docker compose stop db` e `start db` li conservano, `make giu` li cancella. Serve per provare il database fermo.
- **Le password (`kintsugi`) sono valori di prova,** validi solo dentro questa rete. Non si riusano altrove.
- **Il controllo di RabbitMQ guarda la porta,** non esegue `rabbitmq-diagnostics`: un comando di RabbitMQ lanciato prima che il server sia partito crea `.erlang.cookie` come root e il server non parte più.
- **Ogni servizio ha `stop_grace_period: 10s`.** Senza, Docker Desktop concede meno dei 10 s documentati (circa 1,5 s su un Mac, 3,2 s su un altro) prima di uccidere il container, e PostgreSQL potrebbe essere ucciso a metà dell'arresto.
- **Le versioni delle immagini sono fissate** (`postgres:18.6-alpine`, `rabbitmq:4.4.0-alpine`, `nginx:1.29.8-alpine`) come quelle di Python e delle librerie.
