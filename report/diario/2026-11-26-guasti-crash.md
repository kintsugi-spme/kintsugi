# 2026-11-26 — Guasti F2, F3 e F4 dal nodo

**Chi:** Francesco · **Fase:** F4 · **Durata:** 2 h · **Issue:** #118 · **PR:** #NNN

## Cosa e perché

`harness/faults/arresto.py` faceva solo il guasto F1. Ora `--guasto F1|F2|F3|F4` sceglie una riga di una tabella: selettore dei pod, container che deve esserci, uno o tutti i pod. Il kill va sempre al processo principale del container, dal nodo (D0016): per F3 è `beam.smp` (RabbitMQ), per F4 `postgres`. Il nome del processo finisce in `guasto.json`, insieme agli altri dati di ogni pod colpito (`bersagli`). Toxiproxy non può essere colpito: ha un altro selettore e un altro container, e un test lo controlla.

Per F2 (tutti i worker) si aprono prima le shell nei nodi e si cercano tutti i PID; al momento del guasto ogni nodo riceve un solo comando, che li uccide insieme. `ts_guasto` è prima del primo comando, `ts_conferma` dopo l'ultimo: l'incertezza comprende la distanza tra il primo e l'ultimo kill.

## Risultato

Sul Mac da 8 GB, kind v1.37.0, S = 0,05 s, dopo `make reset`:

| Guasto | Versione | Processo | Incertezza | Esito |
|---|---|---|---|---|
| F2 | V3 | 3 × `uvicorn`, stesso nodo | 17,1 ms (primo e ultimo kill a 1 ms sull'orologio del nodo) | 3 container riavviati nello stesso pod |
| F3 | V3 | `beam.smp` | 3,5 ms | riavviato nello stesso pod |
| F4 | V3 | `postgres` | 6,4 ms | riavviato nello stesso pod |
| F4 | V2 | `postgres` | 2,6 ms | riavviato nello stesso pod |
| F4 | V1 | `postgres` | 3,7 ms | riavviato nello stesso pod |

**Criterio 2 della fase F4.** V1 sotto JMeter a 30 ordini/s per 300 s, guasto F4 a 120 s. Il ritmo di W1 non è ancora fissato (#127): 30/s è provvisorio, cioè metà di 60/s, la capacità di V3 con 3 worker e μ1 provvisoria di 20 ordini/s. La prova si ripete nella verifica di M4 (#133).

| | |
|---|---|
| Ordini | 9000: 8956 × `201`, 44 × `503`, nessun timeout |
| Ritmo (`analysis/ritmo.py --ritmo 30`) | medio +0,1 %; 29 finestre, scarto massimo +4,0 % nella prima (avvio di JMeter, limite del 26/11); codice 0 |
| Fermo (`analysis/fermo.py`) | 1,437 s |
| Riavvii dell'API durante il guasto | nessuno (il limite del 17/11 non si è ripresentato) |

Con il database fermo l'API risponde `503` alla deadline o prima (D0008) e il generatore non rallenta: il ritmo resta quello chiesto anche nelle finestre del guasto.

## Problemi e limiti

- **La prima finestra resta vicina alla tolleranza.** A 30/s la raffica di avvio di JMeter porta la prima finestra a +4,0 % (a 50/s era +1,6 %): a ritmi bassi le stesse richieste in più pesano di più. Nei run della campagna la prima finestra cade nel minuto di riscaldamento, ma `ritmo.py` controlla tutto il run. Se un ritmo di W1 più basso la portasse oltre il 5 %, si potrà escludere il riscaldamento dal controllo; per ora non serve.
