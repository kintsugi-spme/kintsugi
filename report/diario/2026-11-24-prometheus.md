# 2026-11-24 — Prometheus leggero sul nodo dati

**Chi:** Francesco · **Fase:** F4 · **Durata:** 2,5 h · **Issue:** #114 · **PR:** #136

## Cosa e perché

`make osservabilita` installa Prometheus 3.16.0 e kube-state-metrics 2.20.0 nel namespace `osservabilita`, sul nodo `dati` (D0006); lo richiamano anche `make v1` … `make v5`, e `make togli` non lo toglie. Prometheus raccoglie ogni 5 s (D0019, `osservabilita.intervallo_raccolta_s`): ordini per coda da RabbitMQ (modulo già acceso nell'immagine 4.4.0), CPU e memoria dei container dal kubelet, copie pronte, riavvii e motivo dell'ultimo arresto da kube-state-metrics. Tiene solo le serie che servono. La sua configurazione la genera `deploy/k8s/parametri.py` da `prometheus.modello.yml`. L'app non espone metriche: riprove dal log dei worker, tempo in coda da `db.csv` (D0019).

## Risultato

Sul Mac da 8 GB, kind v1.37.0. Installazione in 29 s con le immagini da scaricare.

- **V3**, 100 ordini a 10/s, worker a 0,3 s per ordine: la coda `ordini` arriva a 10 messaggi; CPU di ogni copia dell'API 0,017-0,028 core (media su 30 s); copie pronte di tutti i Deployment, Toxiproxy compreso.
- **V5**, worker rallentati a 0,5 s per ordine, 400 ordini a 20/s: coda massima 295, worker pronti fino a **7 sia per Prometheus sia per `kubectl`** (letto ogni 2 s); 305 worker-secondi negli ultimi 3 minuti.
- **Consumo dell'osservabilità**, con V5 e con V4s accese: Prometheus 83-84 MiB e 0,016 core, kube-state-metrics 11-13 MiB e 0,008 core.
- `make togli` lascia accesi Prometheus e kube-state-metrics.

Query usate, da `http://localhost:9090` dopo `kubectl --context kind-kintsugi -n osservabilita port-forward svc/prometheus 9090:9090`:

```
max_over_time(rabbitmq_detailed_queue_messages{queue="ordini"}[5m])
sum by (pod) (rate(container_cpu_usage_seconds_total{container="api"}[30s]))
max_over_time(kube_deployment_status_replicas_ready{deployment="worker"}[5m])
sum_over_time(kube_deployment_status_replicas_ready{deployment="worker"}[3m]) * 5
```

## Problemi e limiti

- **kube-state-metrics riavviato 6 volte:** avevo messo la sonda «vivo?» su `/livez` della porta 8081, che risponde 404; quell'indirizzo sta sulla porta delle metriche, 8080. Corretto: 0 riavvii dopo la correzione.
- Subito dopo `make v3` il bersaglio di RabbitMQ risulta giù per qualche secondo, finché RabbitMQ non ha finito di partire: le prime raccolte dopo un cambio di versione possono mancare.
