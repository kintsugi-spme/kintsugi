# 2026-11-18 — Misura a vuoto dei tempi di avvio

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 1,5 h · **Issue:** #82

## Cosa abbiamo fatto

- `harness/faults/avvio.py` e `test_avvio.py`: a ogni ripetizione ricrea il pod, lo lascia assestare 10 s e manda il SIGKILL dal nodo (le funzioni di `arresto.py`, D0016). Legge lo stato del pod ogni 0,1 s: **riavvio** (container di nuovo in esecuzione), **pronto** (pod `Ready`) ed **evento** (riga di log «pronto» dell'applicazione), tutti dal kill. Stampa mediana, minimo e massimo.
- README: lo script nell'albero delle cartelle.

## Perché

Il pod si ricrea a ogni ripetizione perché un secondo kill sullo stesso pod fa scattare il back-off di Kubernetes (10, 20, 40 s). «Pronto» è quello di Kubernetes, con le sonde di V3 (D0007): API ogni 1 s, PostgreSQL e RabbitMQ ogni 2 s, nessuna per il worker. Arriva fino a un periodo di sonda dopo che l'applicazione è davvero pronta, quindi è per eccesso. I tempi partono dal kill, quindi comprendono il rilevamento ($T_{ril}$, circa 1 s): le ipotesi sotto sono sommate con $T_{ril}$.

## Comandi e configurazione

```bash
cd deploy/k8s && make v3
python3 harness/faults/avvio.py --selettore app=api --nome API --evento "Application startup complete"
python3 harness/faults/avvio.py --selettore app=worker --nome Worker --evento "collegato al broker"
python3 harness/faults/avvio.py --selettore app=db --nome PostgreSQL --evento "ready to accept connections"
python3 harness/faults/avvio.py --selettore app=coda --nome RabbitMQ --evento "Server startup complete"
```

## Risultato

V3 a vuoto (3 API, 3 worker, coda, database), 5 prove per componente, secondi. Le previsioni (`tab:ipotesi`) non si toccano.

| Componente | Misura | Mediana | Minimo | Massimo | Ipotizzato |
|---|---|---|---|---|---|
| API | dal kill al container riavviato | 0,9 | 0,8 | 1,4 | 2-4 ($T_{ril}+T_{riavvio}$) |
| API | dal container al pod pronto | 1,8 | 0,8 | 2,6 | ≤ 1 ($T_{pronto}$) |
| API | dal kill al pod pronto | 2,7 | 1,7 | 4,0 | 3-5 (somma, guasto F1 su V1) |
| Worker | dal kill al container riavviato (senza sonde: pronto) | 2,7 | 0,7 | 4,4 | 2-4 ($T_{ril}+T_{riavvio}$) |
| Worker | dal container a «collegato al broker» | 5,4 | 2,7 | 6,3 | 1-5 ($T_{riconn}$) |
| PostgreSQL | dal kill al pod pronto | 12,2 | 6,0 | 16,2 | 4-9 ($T_{ril}+T_{DB}$) |
| RabbitMQ | dal kill al pod pronto | 14,1 | 12,0 | 38,8 | 6-16 ($T_{ril}+T_{MQ}$) |

Scarti:
- **API:** dal kill al pronto sotto l'ipotesi in 4 prove su 5 (1,7-2,7 s). Dal container al pronto servono più di 1 s in 3 prove su 5 (avvio dell'applicazione e periodo della sonda, 1 s).
- **Worker:** riavvio nell'ipotesi in 3 prove su 5. La riconnessione supera 5 s in 3 prove su 5.
- **PostgreSQL:** sopra 9 s in 3 prove su 5; il container a volte impiega fino a 14 s a ripartire.
- **RabbitMQ:** mediana nell'ipotesi, ma 2 prove su 5 sopra 16 s (19,8 e 38,8).

## Problemi e limiti

- Nella prima passata il worker non aveva il tempo di riconnessione: la riga «collegato al broker» arriva dopo il «pronto» di Kubernetes. Lo script ora la aspetta fino a 30 s.
- **Due copie dell'API sono state riavviate dalla liveness** durante la misura, con `context deadline exceeded` su più pod nello stesso momento, anche con richieste e limiti (#79): la macchina virtuale di Docker a volte è occupata per più di 1 s. Non risolto.
- kind sul Mac: il riavvio di un container varia da 0,7 a 14 s a parità di condizioni (tra «creato» e «avviato» fino a 4 s). Le ipotesi vanno lette come intervalli larghi; in F4 si riporta la dispersione. I tempi del kill e del pronto sono per eccesso di circa 0,3 s.
