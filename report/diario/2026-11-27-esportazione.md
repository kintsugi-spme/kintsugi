# 2026-11-27 — Esportazione di fine run

**Chi:** Gianmarco · **Fase:** F4 · **Durata:** 1 h · **Issue:** #123 · **PR:** #147

## Cosa e perché

`harness/esporta/esporta.py` salva nella cartella del run i file che stanno dentro il cluster: `db.csv`, `falliti.csv`, `duplicati.csv`, `events.csv` e `prometheus.csv`, poi lancia `categorie.py`. Tre scelte non ovvie:

- **L'ordine dei passi è l'unico modo di non nascondere un run sbagliato.** `db.csv` e `falliti.csv` si esportano prima della rielaborazione dei falliti: se si esportano dopo, gli ordini in dead-letter sono già nel database e risultano «completato in tempo». Per questo la rielaborazione non parte se `db.csv` o `falliti.csv` non si sono potuti scrivere (c'è un test).
- **`falliti.csv` si legge senza consumare la coda.** Lo script prende i messaggi con `basic.get`, li legge e li rimette con `nack`: non c'è altro modo di guardare una coda senza il plugin di gestione di RabbitMQ. A fine lettura sono tutti ancora in coda.
- **Il database si legge direttamente e in UTC** (`PGTZ=UTC`, nel pod del database, non da Toxiproxy): con la latenza del guasto F5 l'esportazione non rallenta, e gli istanti sono sulla stessa scala di `client.csv` e di `ts_nodo`.

## Risultato

Sul Mac da 16 GB, kind v1.37.0, run a 20 ordini/s. Il tempo dell'esportazione entra nella durata di ogni run (lo scrive `esportazione.json`).

| Run | Ordini | Eventi | Righe di Prometheus | Durata | Passo più lungo |
|---|---|---|---|---|---|
| V2, guasto F1 | 4819 | 102 | 12437 | 1,1 s | `db` 0,43 s |
| V3, guasto F4 | 4806 | 162 | 15807 | 1,5 s | `falliti` 0,47 s |
| V3, con 3 ordini messi a mano nella coda dei falliti | 2000 | 246 | 11355 | 3,7 s | rielaborazione 2,5 s |

- Con i 3 ordini nella coda dei falliti: `falliti.csv` ne ha 3, `categorie.py` li dà «in dead-letter» (3) e «completato in tempo» (2000). La rielaborazione ne sposta 3, i worker ne salvano 3, 0 restano in coda.
- Per stimare le ore della campagna: circa 2 s per run senza falliti. La rielaborazione aspetta i worker (fino a 90 s) e dipende da quanti ordini sono nella coda.
- **Non provato su V4**: il codice legge dal primario (`cnpg.io/instanceRole=primary`), ma V4 non era acceso. Si prova a mano o nella #129.

## Problemi e limiti

- AMQP non ha un comando per leggere una coda senza prendere i messaggi (riga nella tabella dei limiti).
