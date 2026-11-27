# 2026-11-27 — Un run completo con un solo comando

**Chi:** Gianmarco · **Fase:** F4 · **Durata:** 3 h · **Issue:** #122 · **PR:** #148

## Cosa e perché

`harness/run/run.py` (`make run VERSIONE=V2 GUASTO=F1 CARICO=W1 RITMO=20`) esegue un run come la figura «Struttura di un run»: cartella e `meta.json`, reset, JMeter, guasto al minuto 2, osservazione fino al ripristino più 2 minuti, esportazione (#123) e analisi. Sei scelte non ovvie:

- **Il guasto parte in anticipo e aspetta.** Lo script del guasto apre le shell nei nodi e cerca i PID, e ci mette qualche secondo: lanciato al minuto 2 il guasto cadrebbe a un istante imprevedibile. `run.py` lo lancia 20 s prima con `--alle <istante>` (nuovo in `arresto.py` e `latenza.py`) e il segnale parte a quell'istante. Il minuto si conta dalla prima richiesta di JMeter (`carico_t0` in `meta.json`), non dal lancio.
- **Il ripristino si riconosce durante il run con la funzione di `fermo.py`**, non con una regola copiata: `run.py` legge `jmeter.jtl` ogni secondo e chiama `fermo.ripristino`. Così il run e l'analisi di fine run dicono la stessa cosa. Quello dell'accettazione: il completamento (V3, V5) serve `db.csv` e si calcola solo a fine run.
- **`fine_osservazione.ts` in `meta.json` è presa dopo lo stop di JMeter**, quindi è di circa 5 s dopo l'istante in cui il carico si ferma (120 s dopo il ripristino): 124,8 s e 125,0 s nei due run veri.
- **JMeter si ferma con `Shutdown` e poi `StopTestNow`** (vedi i limiti sotto).
- **In V3 e V5 il run non finisce con l'arretrato ancora in coda** (revisione di Francesco). Con il database, i worker o la latenza di F5 fermi l'accettazione non si ferma: il ripristino dell'accettazione è subito e il run finirebbe a t_g + 2 minuti anche con ordini ancora in coda. Se il carico si ferma con l'arretrato non smaltito, gli ultimi ordini ricevuti sono tutti in ritardo e il completamento risulta «non ripristinato» solo perché non arrivano altri ordini a provarlo. Un esempio, calcolato da Francesco con i numeri della D0021: F5 su V3 a 30 ordini/s, i worker salvano circa 6,7 ordini/s durante i 60 s del guasto, restano circa 1400 ordini in coda e si smaltiscono a 60 − 30 = 30/s in 47 s: la coda è smaltita a t_g + 107 s, ma con W1 un po' più alto no. Ora, passati i 2 minuti, il run continua finché nessun ordine aspetta in `ordini`, sempre entro il tetto.
  - **Si contano gli ordini in attesa, non la coda «vuota».** La proposta era aspettare la coda a 0, ma con il carico ancora acceso `rabbitmqctl list_queues name messages` non dà mai 0: ci sono sempre 1-3 ordini presi da un worker e non ancora confermati. Primo run vero (V3, F4, 20 ordini/s): la coda non è mai arrivata a 0 e il run è finito al tetto di 10 minuti (605 s) invece che a 2 minuti. Ora si guarda `messages_ready` (gli ordini che nessun worker ha ancora preso) e non quelli in lavorazione. L'esportazione invece, a carico fermo, aspetta il totale a 0 (#123).
  - **Secondo run vero** (`20261127-150724-V3-F4-W1-r1`, stesso comando): ripristino dell'accettazione a +0 s dal guasto, `ordini_in_attesa` 0 al primo controllo, carico fermato 120 s dopo e fine registrata a 126,7 s dal ripristino (120 s più gli ultimi controlli e i 4 s di `Shutdown`); `guasto_codice_uscita` 0, esportazione e analisi con codice 0.
  - **La coda si guarda solo da quando i 2 minuti sono passati**, ogni 5 s: `rabbitmqctl` avvia una macchina virtuale Erlang dentro il pod del broker e farlo di continuo lo disturberebbe. Un broker che non risponde non vale come «nessun ordine in attesa».
  - **Scelta da riconsiderare:** così i 2 minuti si contano dall'accettazione, non dal ripristino del completamento: il protocollo dice che il servizio è ripristinato quando lo sono entrambi, quindi si potrebbe contarli da quando l'arretrato è smaltito. Qui si è seguita la proposta di Francesco, più corta; la differenza è di una riga in `quando_fermarsi`.
- **Se lo script del guasto fallisce, il run non è «completato».** `run.py` guarda il codice di uscita dello script e `guasto.json`: se il codice non è 0 o il file manca, il run si ferma subito con `stato: guasto fallito` e codice di uscita 3 (l'esportazione si fa lo stesso, per capire cosa è successo). Prima andava al tetto di 10 minuti, non lanciava `fermo.py` e finiva con `stato: completato` e codice 0: in campagna non ce ne saremmo accorti. `arresto.py` esce con 0 anche quando il container non riparte (quel dato è valido, sta in `guasto.json`), quindi il codice diverso da 0 è davvero un errore.

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
- `analysis/ritmo.py` va in `ZeroDivisionError` se `client.csv` ha richieste dopo la fine del profilo (`scarto_percentuale` divide per un ritmo chiesto che là è 0). Non succede con JMeter (si ferma al profilo), l'ho visto solo con righe aggiunte a mano. Non toccato: issue #149, in M4.
