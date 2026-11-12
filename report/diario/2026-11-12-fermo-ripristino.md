# 2026-11-12 — Calcolo di fermo e ripristino

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 0,5 h · **Issue:** #85

## Cosa abbiamo fatto

`analysis/fermo.py` calcola il ripristino e il fermo (t_r − t_g) da `client.csv` e dall'istante del guasto, con le definizioni del capitolo «Protocollo di misura». 22 prove in `analysis/test_fermo.py`. I 5 secondi e il 99% si leggono da `config/parametri.yaml` e non hanno un predefinito nel codice. Le richieste fallite per il guasto comprendono anche quelle già in corso al momento del guasto.

## Perché

Il documento chiede millisecondi ma definisce la disponibilità per secondi interi: qui i secondi partono da ogni richiesta dopo il guasto, e t_r è la prima da cui i 5 secondi seguenti sono tutti disponibili. La definizione è scritta anche nel capitolo «Protocollo di misura» (riga «Ripristinato»). `client.csv` si rimette in ordine di invio: il client scrive quando la richiesta finisce.

## Comandi e configurazione

```bash
python analysis/fermo.py data/<ambiente>/<run-id> --guasto 2026-11-12T10:02:00.123+00:00
```

L'istante del guasto è quello preso sul computer, con lo stesso orologio del client.

## Risultato

Su dati costruiti a mano il risultato è quello atteso. Run vero (client a 50/s contro un server finto fermato con `kill -9` e riavviato dopo 4 s): **fermo 4,093 s**, 204 richieste fallite (4,08 s × 50/s).

## Problemi e soluzioni

Non ancora fatto: il ripristino del completamento (V3, V5), che richiede `db.csv`, e il formato del file con l'istante del guasto (#84).

## Limiti dello strumento emersi

Nessuno.
