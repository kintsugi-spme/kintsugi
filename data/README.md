# Dati dei run

I risultati dei run non sono versionati in git (vedi `.gitignore`): sono troppo grandi e si rigenerano.

Ogni run salva una cartella `data/<ambiente>/<run-id>/` con:

| File | Contenuto |
|---|---|
| `meta.json` | configurazione (versione, carico, guasto, ripetizione), **hash del commit**, **host** (nome, RAM, CPU, memoria di Docker), istante del guasto, esito dei criteri di validità |
| `client.csv` | log per richiesta di JMeter: istante di invio, ID ordine, esito, tempo di risposta |
| `db.csv` | ordini salvati: ID, `ts_ricezione` (istante di ricezione da parte dell'API) e `ts_scrittura` (istante dell'inserimento nel database, non del commit; D0005) |
| `events.csv` | eventi Kubernetes: pod terminato, creato, pronto |
| `prometheus.csv` | lunghezza ed età della coda, riprove, dead-letter, CPU e memoria |
| `categorie.csv` | categoria assegnata a ogni ID ordine (documento di architettura, capitolo «Protocollo di misura», sezione «Categorie degli ordini») |

L'archivio della campagna si conserva fuori dal repository (es. allegato a una release GitHub o su un drive condiviso), indicando qui dove si trova.
