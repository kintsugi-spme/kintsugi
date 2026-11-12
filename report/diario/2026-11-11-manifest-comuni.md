# 2026-11-11 — Manifest comuni per Kubernetes

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 1 h · **Issue:** #73

## Cosa abbiamo fatto

In `deploy/k8s/base/` (Kustomize): PostgreSQL 18.6 con lo schema (ConfigMap) e il volume, l'API sincrona (1 copia) e il Service NodePort 30080, raggiungibile da `http://localhost:8080`. `deploy/k8s/parametri.py` scrive `base/parametri.env` (non versionato) da `config/parametri.yaml`: un ConfigMap generato dà `DEADLINE_S` all'API.

## Perché

Kustomize non legge `parametri.yaml`: lo script evita di riscrivere i numeri nei manifest. `MODE=sync` sta nella base perché l'API lo richiede; gli overlay lo cambiano.

## Comandi e configurazione

```bash
python3 deploy/k8s/parametri.py
kubectl apply -k deploy/k8s/base
```

## Risultato

- `db` e `api` pronti, 0 riavvii; `localhost:8080/healthz` risponde 200.
- 100 ordini a 10/s: 100 × `201`, 100 righe in `ordini`.
- Cambiando `deadline_api_s`, `--controlla` segnala il file vecchio e, rigenerato, il ConfigMap cambia (poi rimesso a 1,5).

## Problemi e soluzioni

- **Il database è finito sul nodo sbagliato** (`kintsugi-worker2`, e il suo volume è nato lì): senza regole Kubernetes sceglie un nodo qualsiasi. Risolto con `nodeSelector: kintsugi/ruolo: dati` nella base: in tre prove di fila parte su `kintsugi-worker`. Le altre regole di D0006 sono della #77.
- **Toxiproxy non è nella base:** il documento lo vuole tra applicazione e database, ma lo pianifica in F4 (issue #93). Le misure di M3 sono preliminari e senza Toxiproxy.

## Limiti dello strumento emersi

- Il volume `local-path` di kind si lega al nodo dove il pod parte la prima volta e non si sposta (riga nella tabella).
