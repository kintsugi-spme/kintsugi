# 2026-11-27 — Esportazione di fine run

**Chi:** Gianmarco · **Fase:** F4 · **Durata:** 1 h · **Issue:** #123 · **PR:** #147

## Cosa e perché

`harness/esporta/esporta.py` salva nella cartella del run i file che stanno dentro il cluster: `db.csv`, `falliti.csv`, `duplicati.csv`, `events.csv` e `prometheus.csv`, poi lancia `categorie.py`. Quattro scelte non ovvie:

- **In V3 e V5 prima si aspetta che la coda `ordini` sia vuota** (revisione di Francesco). Un ordine accettato e ancora in coda non è né in `db.csv` né in `falliti.csv`: `categorie.py` lo direbbe «perso», che per il protocollo vuol dire «mai salvato, nemmeno dopo la rielaborazione», mentre è solo in attesa. Succede con W3 su V3, che accumula coda per costruzione (RQ2). L'attesa ha un tempo massimo (`run.attesa_coda_vuota_s`, 300 s: abbastanza per smaltire l'arretrato e per i 120 s dopo cui un ordine non riuscito va nei falliti, D0003); se non basta, `esportazione.json` dice quanti ordini restavano (`coda_ordini`) e l'esportazione esce con codice 1. Se `rabbitmqctl` non elenca la coda `ordini` è un errore, non una coda vuota.
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
- **Attesa della coda, prova vera su V3**: worker spenti (`kubectl scale --replicas=0`), 200 ordini accettati e rimasti in coda; l'esportazione parte, i worker si riaccendono 12 s dopo, e `esportazione.json` dà `coda_ordini` 200 all'inizio e 0 alla fine dopo 18,2 s di attesa; `db.csv` 200 righe e `categorie.py` 0. Senza l'attesa `db.csv` sarebbe stato vuoto e i 200 ordini «persi».
- Per stimare le ore della campagna: circa 2 s per run senza falliti. La rielaborazione aspetta i worker (fino a 90 s) e dipende da quanti ordini sono nella coda.

**V4: letto dal primario di quel momento, anche dopo un failover.** Provato su V4a e V4s a 20 ordini/s (criterio 3 della #123), con il primario `db-1` cancellato a mano (`kubectl delete pod db-1 --force`) 15 s dopo l'inizio di 60 s di carico:

| Prova | Esito del client | Esportazione |
|---|---|---|
| V4a, 30 s di carico senza guasto (primario `db-1`) | 600 × `201` | `db.csv` 600, `categorie.py` 0, 1,02 s |
| V4a, 60 s con il primario cancellato (failover a `db-2` dopo circa 22 s) | 877 × `201`, 323 × `503` | dal nuovo primario in 0,93 s: tutti gli 877 accettati sono in `db.csv`. Le 600 righe della prova precedente erano ancora nella tabella (V4 non ha il reset, #129): `categorie.py` le segnala come «in `db.csv` ma mai inviate», cioè si accorge che il run è sporco |
| V4a, tabelle svuotate sul nuovo primario, 20 s | 400 × `201` | `db.csv` 400, `categorie.py` 0, 1,0 s |
| V4s, 60 s con il primario cancellato (poi primario `db-2`) | 838 × `201`, 362 × `503` | 856 righe: i 838 accettati e 18 ordini salvati dopo il `503` (limite del 17/11); `categorie.py` 0, nessun ordine perso, 0,96 s |

Il tempo dell'esportazione su V4 è lo stesso di V2 e V3 (circa 1 s).

## Problemi e limiti

- AMQP non ha un comando per leggere una coda senza prendere i messaggi (riga nella tabella dei limiti).
