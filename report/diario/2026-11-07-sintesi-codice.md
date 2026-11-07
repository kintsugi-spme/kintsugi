# 2026-11-07 — Sintesi: sezione sul codice e sull'ambiente di prova

**Chi:** Francesco · **Fase:** F2 · **Durata:** 1 h · **Issue:** —

## Cosa abbiamo fatto

Nuova sezione 6 della relazione di sintesi, «Il codice e l'ambiente di prova» (`docs/sintesi/06-codice.tex`), tra le previsioni e i limiti:

- i tre lavori dello stesso programma (API sincrona, API asincrona, worker), scelti da `MODE` e `ROLE`, con le versioni che li usano;
- i moduli Python, con un diagramma di chi usa chi e una riga per modulo;
- l'immagine Docker e le tre scelte che servono all'esperimento (programma come primo processo, codice già compilato, due architetture di processore);
- i container durante lo sviluppo, sulla stessa rete Docker, e il passaggio a kind dalla fase F3.

## Perché

La relazione descriveva le architetture ma non come sono realizzate. Chi legge ora vede che le versioni sono configurazioni dello stesso codice e perché l'ambiente di sviluppo è Docker e quello delle misure è Kubernetes.

## Comandi e configurazione

```bash
cd docs && make sintesi
```

## Risultato

Relazione di sintesi di 21 pagine (erano 19), compilata senza errori; la sezione nuova occupa le pagine 16–17.

## Problemi e soluzioni

- **PyYAML mancante sul Mac:** `make sintesi` genera prima i parametri e si fermava. Generati con un ambiente Python temporaneo.
- **Compilazione fallita con caratteri nulli** (`Text line contains an invalid character`): una compilazione dell'editor sugli stessi file era in corso nello stesso momento. Rilanciata da sola, è riuscita.

## Limiti dello strumento emersi

Nessuno.
