# 2026-11-24 — Toxiproxy tra l'applicazione e il database

**Chi:** Francesco · **Fase:** F4 · **Durata:** 3 h · **Issue:** #93 · **PR:** #135

## Cosa e perché

Toxiproxy 2.13.0 sta tra l'applicazione e il database in tutte le versioni, come chiedono il capitolo «Architettura» e il guasto F5. Una sola copia, sul nodo `dati` con regola rigida (D0006). API e worker si collegano a `toxiproxy:5432`; il proxy `postgres` inoltra a `db:5432`, in V4 a `db-rw:5432`. La sonda di readiness chiede il proxy `postgres` (`GET /proxies/postgres`): se il file di configurazione non si legge, Toxiproxy parte lo stesso ma senza proxy, e così non entra nel Service.

## Risultato

Sul Mac da 8 GB, kind v1.37.0, tempo di servizio 0,05 s (D0018). Prova di funzionamento, non misura ufficiale (D0013).

| | Ordini (100 a 10/s) | Ricezione → salvataggio, mediana | Connessioni dell'app al database |
|---|---|---|---|
| V1 | 100 × `201` | 0,052 s | 5, tutte da Toxiproxy |
| V2 | 100 × `201` | 0,053 s | 15, tutte da Toxiproxy |
| V3 | 100 × `202` | 0,054 s | 15, tutte da Toxiproxy |
| V4a | 100 × `201` | 0,053 s | 15, tutte da Toxiproxy (verso `db-rw`) |
| V4s | 100 × `201` | 0,053 s | 15, tutte da Toxiproxy (verso `db-rw`) |
| V5 | 100 × `202` | 0,055 s | 5, tutte da Toxiproxy |

Le connessioni si contano in `pg_stat_activity`: l'indirizzo di provenienza è sempre quello del pod di Toxiproxy. Memoria di Toxiproxy: da 7 a 13 MiB.

- **Latenza a mano (V2):** con un ritardo di 200 ms (`toxiproxy-cli toxic add -t latency -a latency=200 postgres`) la mediana passa a 0,456 s (massimo 0,662), 30 ordini su 30 salvati. Tolto il ritardo torna a 0,055 s.
- **Verifica di M3 con Toxiproxy (`make verifica`):** «Criteri soddisfatti». Fermo dopo il crash di una copia dell'API: V1 0,352 s, V2 0,472 s, V3 0,323 s. Un run per versione: non è un confronto con i valori senza Toxiproxy del 22/11.
- **Guasto F4 vero su V2** (`SIGKILL` a PostgreSQL dal nodo, `arresto.py --selettore app=db`), due volte di fila, ordini a 5/s:

| | Senza Toxiproxy | Con Toxiproxy |
|---|---|---|
| 1° guasto | fermo 1,02 s | fermo 1,26 s |
| 2° guasto, stesso container | 12,6 s | 14,8 s |

Il secondo guasto è più lungo in tutti e due i casi per l'attesa di Kubernetes prima di riavviare di nuovo lo stesso container (limite del 12/11).

## Problemi e limiti

- **Database cancellato invece che ucciso: 114 s senza ordini.** Spegnendo il database con `kubectl scale --replicas=0` per 20 s, senza Toxiproxy il primo `201` è tornato 3,2 s dopo il database; con Toxiproxy dopo 114 s. Anche una connessione nuova aperta a mano da un pod dell'API restava appesa per tutto quel tempo. Causa, nel codice di Toxiproxy 2.13.0 (`proxy.go`, righe 183-215): per ogni cliente nuovo apre la connessione verso il database dentro il ciclo che accetta i clienti, con `net.Dial` senza tempo massimo. Quando il pod del database viene cancellato il suo indirizzo sparisce: un tentativo verso il vecchio indirizzo resta appeso finché Linux non rinuncia (circa 127 s) e tutti i clienti successivi aspettano dietro di lui. Con il guasto F4 vero il pod e il suo indirizzo restano, la connessione viene rifiutata subito, e il fermo è uguale con e senza Toxiproxy (tabella sopra).
- Impatto da tenere presente: il reset tra un run e l'altro (#121) ricrea i pod, e l'eccezione di D0016 per V4 (#129) cancella con la forza il pod del primario. In tutti e due i casi va controllato che Toxiproxy non resti bloccato (per esempio ricreandolo dopo il database, o aspettando che risponda prima di avviare il carico).
