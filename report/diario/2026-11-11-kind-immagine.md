# 2026-11-11 — Cluster kind e immagine dell'app nei nodi

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 1 h · **Issue:** #72

## Cosa abbiamo fatto

`make immagine` in `deploy/k8s/` crea il cluster kind (se manca), controlla che sia come vuole D0006 (3 nodi pronti con la versione di `kind-cluster.yaml`, etichette `dati` e `calcolo`, control plane con `NoSchedule`), costruisce `kintsugi:dev` e la copia nei due worker con `kind load`. `make prova` fa partire un pod di prova su ogni worker (`prova-immagine.yaml`); se non partono, stampa lo stato e gli avvisi di Kubernetes e toglie i pod.

## Perché

I nodi di kind sono container con un deposito di immagini proprio: quella del Mac non c'è finché non si carica. I pod di prova hanno `imagePullPolicy: Never`, quindi se partono l'immagine era già nel nodo. Il control plane non ospita pod dell'app (D0006): niente copia. Un cluster già acceso non viene ricreato, per questo si controlla anche la versione di Kubernetes.

## Comandi e configurazione

```bash
cd deploy/k8s
make immagine   # cluster, controllo, build e caricamento nei due worker
make prova      # un pod per ruolo
make giu        # cancella il cluster
```

## Risultato

- Cluster ricreato da zero e immagine caricata in circa 39 s; con il cluster già acceso, circa 4 s.
- `make prova`: `prova-dati` su `kintsugi-worker` e `prova-calcolo` su `kintsugi-worker2`, entrambi `Completed`, immagine «already present on machine».
- Con l'etichetta `dati`, il taint o la versione sbagliati di proposito, `make controlla` si ferma con un messaggio chiaro; con un'immagine tolta da un nodo, `make prova` mostra `ErrImageNeverPull` e non lascia pod.
- Due `make immagine` di fila stampano lo stesso ID (`--provenance=false`).

## Problemi e soluzioni

Nessuno.

## Limiti dello strumento emersi

- Docker Desktop (archivio containerd) e kind: ogni build aggiunge un'attestazione con l'ora e l'ID cambia anche a codice uguale (`--provenance=false` lo rende stabile); inoltre `kind load` confronta ID diversi (indice contro contenuto) e ricopia l'immagine a ogni lancio. Pochi secondi, nessun effetto sulle misure.
