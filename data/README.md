# Dati dei run

I risultati dei run non sono versionati in git (vedi `.gitignore`): sono troppo grandi e si rigenerano.

Ogni run salva una cartella `data/<ambiente>/<run-id>/` con:

| File | Contenuto |
|---|---|
| `meta.json` | configurazione (versione, carico, guasto, ripetizione), **hash del commit**, **host** (nome, RAM, CPU, memoria di Docker), istante del guasto, esito dei criteri di validità |
| `client.csv` | log per richiesta di JMeter: istante di invio, ID ordine, esito, tempo di risposta (colonne `ts_invio`, `id`, `esito`, `tempo_risposta_s`; in F2 lo scrive `harness/client/cliente.py`) |
| `db.csv` | ordini salvati: ID, `ts_ricezione` (istante di ricezione da parte dell'API) e `ts_scrittura` (istante dell'inserimento nel database, non del commit; D0005) |
| `falliti.csv` | ordini nella coda dei falliti a fine run, prima della rielaborazione: colonna `id`. Il file c'è sempre; ha solo l'intestazione se non ci sono ordini o la versione non ha una coda (V1, V2) |
| `duplicati.csv` | un arrivo di un ID già presente per riga (tabella `duplicati`, D0004): colonna `id`. Il file c'è sempre, anche vuoto |
| `events.csv` | eventi Kubernetes: pod terminato, creato, pronto |
| `prometheus.csv` | lunghezza ed età della coda, riprove, dead-letter, CPU e memoria |
| `categorie.csv` | categoria assegnata a ogni ID ordine (documento di architettura, capitolo «Protocollo di misura», sezione «Categorie degli ordini»); colonne `id`, `categoria`, `duplicati`. Lo scrive `python analysis/categorie.py data/<ambiente>/<run-id>` a partire da `client.csv`, `db.csv`, `falliti.csv` e `duplicati.csv`; esce con codice 1 se i dati non tornano |

L'archivio della campagna si conserva fuori dal repository (es. allegato a una release GitHub o su un drive condiviso), indicando qui dove si trova.
