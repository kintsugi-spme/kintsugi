# 2026-11-06 — API asincrona: pubblicazione su RabbitMQ

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 2 h · **Issue:** #32

## Cosa abbiamo fatto

L'API con `MODE=async` ora ha `POST /ordini`: pubblica l'ordine su RabbitMQ e risponde **202 solo dopo la conferma del broker** (*publisher confirm*, D0001, D0002). Se la conferma non arriva, risponde 503.

| File | Cosa fa | Strato |
|---|---|---|
| `app/modelli.py` | `OrdineIn`: l'ordine ricevuto, con il solo identificativo UUID, validato da FastAPI | modello |
| `app/api.py` | `POST /ordini`: prende `ts_ricezione`, chiama il servizio, traduce l'errore in 503. Nessuna logica | API |
| `app/servizio.py` | `accetta_ordine`: sceglie in base a `MODE`; con la coda pubblica entro `DEADLINE_S` | servizio |
| `app/broker.py` | `Broker`: connessione a RabbitMQ, coda durevole, messaggi persistenti, attesa della conferma | accesso ai dati |
| `app/main.py` | crea il `Broker` e include il router degli ordini, solo per `MODE=async` e `ROLE=api` | |
| `app/test_ordini.py` | 7 test con un broker finto | |
| `app/test_broker.py` | 2 prove contro un RabbitMQ vero; si saltano se non c'è | |
| `app/requirements.txt` | aggiunti `aio-pika` e le sue 5 dipendenze, tutte con versione esatta | |

Il messaggio in coda è un JSON: `{"id": "<uuid>", "ts_ricezione": "<istante UTC>"}`. L'istante lo prende l'API appena arriva la richiesta e lo scriverà il worker nella tabella (D0005).

## Perché

- **`aio-pika` 10.1.1.** FastAPI è asincrono e `aio-pika` lo è: l'endpoint `async def` aspetta la conferma senza bloccare gli altri. `pika` è sincrono e andrebbe messo in un thread a parte. Ho preso la 10.1.1 (del 10/10) e non la 10.2.2, uscita quattro giorni fa: la libreria cambia ogni pochi giorni e preferisco una versione già in giro da qualche settimana. D0011 vuole le librerie fisse.
- **Connessione alla prima pubblicazione, non all'avvio.** Con il broker spento l'API deve partire e le sonde rispondere (D0007). Dopo la prima connessione, `aio-pika` la ripristina da solo.
- **503 per qualunque motivo per cui la conferma manca:** broker spento, non configurato, lento oltre `DEADLINE_S`. La deadline (D0008) copre anche la connessione, perché è tutta dentro `asyncio.wait_for`. Per l'API sincrona la deadline la aggiunge la #31.
- **Coda dichiarata senza argomenti aggiuntivi.** RabbitMQ rifiuta di dichiarare una coda già esistente con argomenti diversi. Il worker (#33) deve quindi dichiararla uguale. La coda dei falliti (D0002) sarà una coda separata dove il worker pubblica (#34), non un argomento di questa coda.
- **Endpoint solo per `async` e `api`.** Il worker non espone `/ordini`, e `MODE=sync` non lo avrà finché non arriva la #30: lei toglie la prima condizione da `main.py` e riempie il ramo `else` di `accetta_ordine`.
- **Configurazione invariata.** `BROKER_URL` e `DEADLINE_S` restano facoltativi all'avvio, altrimenti il job «Immagine» della CI, che avvia il container con il solo `MODE`, andrebbe in errore. Senza `BROKER_URL` l'ordine non è accettato (503).

## Comandi e configurazione

```bash
docker run -d --rm --name kintsugi-rabbit -p 5672:5672 -e RABBITMQ_DEFAULT_USER=prova -e RABBITMQ_DEFAULT_PASS=prova rabbitmq:4-alpine
cd app
TEST_BROKER_URL=amqp://prova:prova@127.0.0.1:5672/ pytest -q
MODE=async DEADLINE_S=1.5 BROKER_URL=amqp://prova:prova@127.0.0.1:5672/ uvicorn --factory main:crea_app
curl -i -X POST localhost:8000/ordini -H 'content-type: application/json' -d '{"id": "3f2b8c1e-5d4a-4e7b-9a10-1c2d3e4f5a6b"}'
docker exec kintsugi-rabbit rabbitmqctl list_queues name messages durable
```

## Risultato

Provato con RabbitMQ 4.4.0 (`rabbitmq:4-alpine`):

| Prova | Risultato |
|---|---|
| Broker attivo, `POST /ordini` | **202** in 12 ms; in coda 1 messaggio, `ordini` è durevole |
| Messaggio letto dalla coda | corpo `{"id": …, "ts_ricezione": …}`, `delivery_mode` **PERSISTENT** |
| Broker fermato | **503** in 2 ms, `il broker non ha confermato (AMQPConnectionError)`; **nessun 202** |
| Sonde con il broker fermo | `/healthz` e `/readyz` → 200 |
| Broker riavviato | l'API torna a rispondere 202 da sola dopo circa 3,5 s, il tempo che RabbitMQ impiega ad avviarsi |
| Immagine Docker con le nuove librerie | parte nei tre modi, processo 1 `uvicorn`; con broker irraggiungibile `POST /ordini` dà 503 |
| `pytest` | 26 superati, 2 saltati (quelli contro RabbitMQ, che si eseguono con `TEST_BROKER_URL`) |

Il criterio della #32 è soddisfatto: con il broker attivo risponde 202 e il messaggio è in coda; con il broker spento risponde un errore e non 202.

## Problemi e soluzioni

- **L'utente `guest` di RabbitMQ non funziona da fuori del container.** Si può collegare solo da localhost, quindi con la porta pubblicata serve un utente creato con `RABBITMQ_DEFAULT_USER` e `RABBITMQ_DEFAULT_PASS`. Vale anche per `docker-compose` (#35) e per i manifest (F3).
- **Primo `POST` dopo l'avvio del broker: 503.** Il broker risponde al `ping` prima di ascoltare sulla porta AMQP. Il tentativo successivo riesce. Nei test conviene aspettare che la porta risponda.
- **Versione di RabbitMQ non fissata nei documenti.** Provato con la 4.4.0; va scelta nella #35, come per PostgreSQL.
- **Un'altra libreria pesa sulla riproducibilità:** `requirements.txt` è passato da 14 a 20 pacchetti, rigenerati dentro la base del Dockerfile (Python 3.12).

## Limiti dello strumento emersi

- **Le prove contro RabbitMQ non girano nella CI:** non c'è un broker nel flusso di GitHub. Si possono eseguire in locale con `TEST_BROKER_URL`. Un container di servizio nella CI si valuta con la parte codice della #41.
- **Il test con il broker fermo misura una connessione già aperta:** il caso del broker che non risponde affatto (indirizzo irraggiungibile, senza rifiuto) è coperto dalla deadline, ma l'ho provato solo con un broker finto lento.
