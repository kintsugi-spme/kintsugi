# 2026-11-09 — Script delle categorie degli ordini

**Chi:** Francesco · **Fase:** F2 · **Durata:** 2 h · **Issue:** #37

## Cosa abbiamo fatto

- Nuovo `analysis/categorie.py`: a fine run assegna ogni ID inviato dal client a una delle cinque categorie del documento (completato in tempo, completato dopo il timeout, fallito, in dead-letter, perso) e scrive `categorie.csv` con le colonne `id`, `categoria`, `duplicati`. Segue la figura del documento: esito positivo (2xx) → nel database? → nei falliti?
- I duplicati non sono una categoria: si contano a parte nella colonna `duplicati`, senza cambiare la categoria dell'ordine.
- Lo script legge quattro file della cartella del run. Due erano già definiti (`client.csv`, `db.csv`); ne servivano altri due, ora descritti in `data/README.md`: `falliti.csv` e `duplicati.csv`, con la colonna `id`. I file ci sono sempre, vuoti (solo intestazione) quando non c'è nulla, per esempio in V1 e V2, che non hanno una coda. Se un file manca, lo script si ferma con un errore: un'esportazione sbagliata non deve passare per «nessun ordine fallito».
- Se i dati non tornano (ID nel database, tra i falliti o tra i duplicati ma mai inviato; ID inviato due volte; ID due volte nel database) lo script scrive comunque `categorie.csv`, elenca le anomalie ed esce con codice 1. Il documento chiede di esaminare un run incoerente prima di proseguire la campagna.
- `analysis/test_categorie.py`: 41 prove (le categorie una per una e nei casi limite, il controllo «una categoria per ogni ID», i duplicati, le anomalie, i file e le colonne mancanti, l'uscita del programma). Nuovo passo in «Test dell'app» nella CI.

## Perché

Il confronto fra le architetture si basa su quanti ordini finiscono in ogni categoria dopo un guasto, soprattutto «perso» (il client crede che l'ordine sia andato a buon fine, ma non è salvato) contro «fallito» (errore dichiarato). A mano non si può contare. Lo script usa solo la libreria standard: nessuna dipendenza in più.

Scelte dove il documento non decideva:
- **Esito positivo = codice 2xx.** Gli errori 4xx e 5xx, «timeout» ed «errore» sono negativi, come dice il documento («errore o timeout»).
- **Il database prevale sulla coda dei falliti,** come nello schema del documento: un ordine presente nel database e anche tra i falliti resta «completato in tempo». Perciò `db.csv` e `falliti.csv` vanno esportati prima della rielaborazione dei falliti.
- **Per chi ha visto un errore la coda dei falliti non cambia nulla:** un ordine con esito negativo che non è nel database è «fallito», anche se è nella coda.
- **Maiuscole e spazi negli ID non contano.**

## Comandi e configurazione

```bash
python analysis/categorie.py data/<ambiente>/<run-id>
pytest -q analysis
```

## Risultato

- 41 prove superate.
- Prova su dati veri: V3 con docker-compose (API, RabbitMQ, 3 worker, database), `cliente.py` con 100 ordini a 20 al secondo e il database fermato per 6 secondi durante l'invio. `db.csv` e `duplicati.csv` esportati con `psql`, la coda dei falliti era vuota (`rabbitmqctl`: 0 messaggi). Risultato: 100 ordini inviati, 100 «completato in tempo», nessuna anomalia, ogni ID con esattamente una categoria.
- Controprova sugli stessi dati: tolti due ordini da `db.csv`, lo script li assegna a «perso» (98 + 2).
- Il formato di `psql` (`\copy … with csv header`) è letto senza modifiche. Il formato degli istanti non serve allo script.

## Problemi e soluzioni

- **`make` non c'è su questo PC:** per la prova ho lanciato a mano gli stessi comandi del `Makefile` (`docker build`, `docker compose … up -d --wait`).
- **Il test sull'uscita del programma:** `main()` esce con `sys.exit` solo in caso di errore; le prove lo controllano in entrambi i casi.

## Limiti dello strumento emersi

- **Con il database fermo solo per pochi secondi non nasce nessun caso difficile:** i worker ritentano e salvano tutto. Le categorie «in dead-letter» e «perso» si vedono con guasti più lunghi (oltre i 120 s di riprove) e con V4 e V5: qui sono verificate dalle prove sui dati costruiti a mano.
- **Chi esporta la coda dei falliti (fase F4) deve scrivere `falliti.csv` prima della rielaborazione.** L'esportatore non esiste ancora: la richiesta è scritta in `data/README.md`.
