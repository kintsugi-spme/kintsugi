# 2026-11-27 — Un run completo con un solo comando

**Chi:** Gianmarco · **Fase:** F4 · **Durata:** 3 h · **Issue:** #122 · **PR:** #148

## Cosa e perché

`harness/run/run.py` (`make run VERSIONE=V2 GUASTO=F1 CARICO=W1 RITMO=20`) esegue un run come la figura «Struttura di un run»: cartella e `meta.json`, reset, JMeter, guasto al minuto 2, osservazione fino al ripristino più 2 minuti, esportazione (#123) e analisi. Quattro scelte non ovvie:

- **Il guasto parte in anticipo e aspetta.** Lo script del guasto apre le shell nei nodi e cerca i PID, e ci mette qualche secondo: lanciato al minuto 2 il guasto cadrebbe a un istante imprevedibile. `run.py` lo lancia 20 s prima con `--alle <istante>` (nuovo in `arresto.py` e `latenza.py`) e il segnale parte a quell'istante. Il minuto si conta dalla prima richiesta di JMeter (`carico_t0` in `meta.json`), non dal lancio.
- **Il ripristino si riconosce durante il run con la funzione di `fermo.py`**, non con una regola copiata: `run.py` legge `jmeter.jtl` ogni secondo e chiama `fermo.ripristino`. Così il run e l'analisi di fine run dicono la stessa cosa. Quello dell'accettazione: il completamento (V3, V5) serve `db.csv` e si calcola solo a fine run.
- **`fine_osservazione.ts` in `meta.json` è presa dopo lo stop di JMeter**, quindi è di circa 5 s dopo l'istante in cui il carico si ferma (120 s dopo il ripristino): 124,8 s e 125,0 s nei due run veri.
- **JMeter si ferma con `Shutdown` e poi `StopTestNow`** (vedi i limiti sotto).

## Risultato

Sul Mac da 16 GB, kind v1.37.0, 20 ordini/s. Prove di funzionamento, non misure ufficiali (D0013).

**Criterio 3 della fase F4: F1 su V2 (W1).** Un solo run (`20261127-090449-V2-F1-W1-r1`):

| | Previsione («Previsioni», F1 su V2, con 100 ordini/s) | Run vero (20 ordini/s) |
|---|---|---|
| Fermo | 1-2 s | **0,518 s** |
| Richieste fallite | circa 30-70 (a 20/s, un terzo del traffico per 1,5 s: circa 10) | **1**, a 0,47 s dal guasto, rifiutata in 3 ms |
| Ritmo inviato | | 20,01/s (+0,1 %), scarto massimo +2,0 % in 10 s |

Il guasto è a 120,01 s dalla prima richiesta; il run è durato 257,6 s (tetto: 10 minuti); il carico si è fermato 120 s dopo il ripristino.

**Lo scarto non è spiegato del tutto, ed è una sola prova.** Dopo l'unica richiesta fallita le successive vanno tutte a buon fine, comprese quelle a 0,5-1,5 s dal guasto: la copia uccisa è uscita dal Service in meno di 0,5 s, non in 1,5 s. L'ipotesi più semplice, coerente con `events.csv` (il container riparte alle 09:07:01, `Ready` alle 09:07:02, istanti al secondo): con il container morto Kubernetes toglie la copia dal Service subito, senza aspettare che la sonda di prontezza fallisca. Per vederlo bisogna campionare gli endpoint del Service come fa F7 (`ts_fuori_dal_service`): non è in questa PR e la previsione non si cambia. Con 10 ripetizioni (campagna) si vedrà se 1 richiesta fallita è la regola.

**Run senza guasto (W1 su V2):** `20261127-135224-V2-nessuno-W1-r1`: 6000 richieste, tutte `201`, a 20,01/s; l'ultima è partita 299,8 s dopo la prima, cioè dopo `run.senza_guasti_min` (5 minuti). Il run intero è durato 322,6 s: reset 15,1 s, carico 300 s, esportazione 1,05 s (per stimare le ore della campagna: circa 20 s in più del carico, a ogni run).

**Altri run di prova:** V3 con F4 (`20261127-091003-V3-F4-W1-r1`): guasto a 120,01 s, ripristino dell'accettazione a 0 s, 4806 ordini, `categorie.py` 0, fermo del completamento 1,715 s (vedi la voce del 27/11 sul fermo del completamento).

## Problemi e limiti

- **`Shutdown` non basta a fermare JMeter 5.6.3.** Il comando sulla porta UDP 4445 chiude il carico ma la JVM resta accesa per più di 2 minuti. `StopTestNow` la chiude in circa 1 s, con codice di uscita 1. `run.py` manda `Shutdown`, aspetta 4 s e poi `StopTestNow`; `carico.py` ora accetta il codice 1 se i risultati sono utilizzabili. Con `StopTestNow` il primo run completo non ha prodotto `client.csv`, perché `carico.py` convertiva solo con codice 0.
- **Il `.jtl` di JMeter si scrive a blocchi**: senza `jmeter.save.saveservice.autoflush=true` il ripristino si riconoscerebbe in ritardo e il run durerebbe fino al tetto.
- `analysis/ritmo.py` va in `ZeroDivisionError` se `client.csv` ha richieste dopo la fine del profilo. Non succede con JMeter (si ferma al profilo), l'ho visto solo con righe aggiunte a mano. Non toccato.
