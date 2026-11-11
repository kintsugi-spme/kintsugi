# 2026-11-11 — Cluster kind e immagine dell'app nei nodi

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 1 h · **Issue:** #72

## Cosa abbiamo fatto

`make immagine` in `deploy/k8s/` crea il cluster kind (se manca), controlla che sia come vuole D0006 (3 nodi pronti, etichette `dati` e `calcolo`, control plane con `NoSchedule`), costruisce `kintsugi:dev` e la copia nei tre nodi con `kind load`. `make prova` fa partire un pod di prova su ogni worker (`prova-immagine.yaml`).

## Perché

I nodi di kind sono container con un deposito di immagini proprio: quella del Mac non c'è finché non si carica. I pod di prova hanno `imagePullPolicy: Never`, quindi se partono l'immagine era già nel nodo.

## Comandi e configurazione

```bash
cd deploy/k8s
make immagine   # cluster, controllo, build e caricamento
make prova      # un pod per ruolo
make giu        # cancella il cluster
```

## Risultato

- Cluster ricreato da zero e immagine caricata in circa 42 s; con il cluster già acceso, 5-7 s.
- `make prova`: `prova-dati` su `kintsugi-worker` e `prova-calcolo` su `kintsugi-worker2`, entrambi `Completed`, immagine «already present on machine».
- Con l'etichetta `dati` o il taint tolti di proposito, `make controlla` si ferma con un messaggio chiaro.

## Problemi e soluzioni

Nessuno.

## Limiti dello strumento emersi

- `make immagine` ricarica l'immagine a ogni lancio: `compileall` nel `Dockerfile` cambia l'ID anche a codice uguale. Pochi secondi, nessun effetto sulle misure.
- `make` non c'è su tutti i computer (non sul PC di Francesco): i comandi si lanciano a mano nello stesso ordine.
