# Dati dei run

I risultati dei run non sono versionati in git (vedi `.gitignore`): sono troppo grandi e si rigenerano.

Ogni run salva una cartella `data/<ambiente>/<run-id>/` con:

| File | Contenuto |
|---|---|
| `meta.json` | configurazione (versione, carico, guasto, ripetizione), **hash del commit**, **host** (nome, RAM, CPU, memoria di Docker), guasto (solo il tipo: gli istanti sono in `guasto.json`), esito dei criteri di validità |
| `client.csv` | log per richiesta di JMeter: istante di invio, ID ordine, esito, tempo di risposta (colonne `ts_invio`, `id`, `esito`, `tempo_risposta_s`; in F2 lo scrive `harness/client/cliente.py`) |
| `db.csv` | ordini salvati: ID, `ts_ricezione` (istante di ricezione da parte dell'API) e `ts_scrittura` (istante dell'inserimento nel database, non del commit; D0005). **Si esporta prima della rielaborazione dei falliti, insieme a `falliti.csv`:** se si esporta dopo, gli ordini in dead-letter sono già nel database e risultano «completato in tempo», senza anomalie e con un run che sembra buono |
| `falliti.csv` | ordini nella coda dei falliti a fine run, prima della rielaborazione: colonna `id`. Il file c'è sempre; ha solo l'intestazione se non ci sono ordini o la versione non ha una coda (V1, V2) |
| `duplicati.csv` | un arrivo di un ID già presente per riga (tabella `duplicati`, D0004): colonna `id`. Il file c'è sempre, anche vuoto |
| `guasto.json` | il guasto provocato: due istanti del guasto, incertezza, pod, nodo, PID ed esito del riavvio. Lo scrive `python harness/faults/arresto.py --cartella data/<ambiente>/<run-id>` (F1); c'è anche se il container non riparte. **Ogni misura sottrae istanti dello stesso orologio:** `ts_guasto` è sull'orologio del computer, come `client.csv`, e serve al fermo dell'accettazione; `ts_nodo` è sull'orologio del cluster, come `ts_ricezione` e `ts_scrittura` di `db.csv`, e serve al fermo del completamento (D0005). `ts_guasto` è l'istante prima del comando di kill, quindi il limite inferiore: il kill avviene tra `ts_guasto` e `ts_conferma`, e il fermo calcolato da `ts_guasto` è più lungo del vero di al massimo `incertezza_s` |
| `events.csv` | eventi Kubernetes: pod terminato, creato, pronto |
| `prometheus.csv` | lunghezza ed età della coda, riprove, dead-letter, CPU e memoria |
| `categorie.csv` | categoria assegnata a ogni ID ordine (documento di architettura, capitolo «Protocollo di misura», sezione «Categorie degli ordini»); colonne `id`, `categoria`, `duplicati`. Lo scrive `python analysis/categorie.py data/<ambiente>/<run-id>` a partire da `client.csv`, `db.csv`, `falliti.csv` e `duplicati.csv`; esce con codice 1 se i dati non tornano |

L'archivio della campagna si conserva fuori dal repository (es. allegato a una release GitHub o su un drive condiviso), indicando qui dove si trova.
