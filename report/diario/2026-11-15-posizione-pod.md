# 2026-11-15 — Posizione dei pod sui nodi (D0006)

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 1 h · **Issue:** #77

## Cosa abbiamo fatto

- `deploy/k8s/base/api.yaml` e `deploy/k8s/overlays/v3/worker.yaml`: `nodeAffinity` *preferita* (peso 100) per i nodi con `kintsugi/ruolo: calcolo`. Le copie dell'API e i worker partono lì; se il nodo non c'è, possono partire su `dati`.
- Database e coda erano già fissati sul nodo `dati` con `nodeSelector` (regola rigida, #73 e #76): qui cambiano solo i commenti, che dicevano «le altre regole sono della #77».
- Intestazioni degli overlay V2 e V3: dicono dove stanno i pod invece di rimandare alla #77.
- Il control plane non ha bisogno di una regola: ha il taint `NoSchedule` di kind e nessun pod dell'app lo tollera. `make cluster` lo controlla già.

## Perché

D0006 vuole una topologia uguale in ogni run: database e coda sul nodo `dati`, API e worker sul nodo `calcolo` con il cluster integro. Senza regole, nella #75 due copie dell'API su tre erano finite sul nodo `dati`.

- **Preferita, non rigida, per API e worker:** D0006 lo chiede, perché nel guasto F6 (spento il nodo `calcolo`) Kubernetes deve poter ricreare i pod sull'altro nodo.
- **Rigida per database e coda:** il disco `local-path` è legato al nodo; se `dati` non c'è, i pod restano in attesa e non ripartono altrove.
- **Nessun valore nuovo in `parametri.yaml`:** sono regole di piazzamento, non numeri di misura. Il peso 100 è il massimo che Kubernetes accetta.

## Comandi e configurazione

```bash
cd deploy/k8s
make v3
kubectl --context kind-kintsugi get pods -o wide -L kintsugi/versione   # colonna NODE
kubectl --context kind-kintsugi delete pods --all                       # ricrea tutti i pod; ripetere 3 volte
kubectl --context kind-kintsugi cordon kintsugi-worker2                 # simula «calcolo non disponibile»
kubectl --context kind-kintsugi uncordon kintsugi-worker2
```

## Risultato

- **V1:** API su `kintsugi-worker2` (`calcolo`), database su `kintsugi-worker` (`dati`). Ricreati tutti i pod 3 volte: sempre allo stesso modo.
- **V2:** tre copie dell'API, sempre tutte e tre su `kintsugi-worker2`: partenza e 6 ricreazioni dell'API. Prima della regola erano due su `dati` e una su `calcolo`.
- **V3:** API ×3 e worker ×3 su `kintsugi-worker2`, coda e database su `kintsugi-worker`. Ricreati tutti i pod 3 volte: identico ogni volta.
- **Con 10 worker** (scalati a mano con `kubectl scale`, come in V3 con 10 worker della #79 e nella scalatura di V5): tutti e 10 su `kintsugi-worker2`. La preferenza regge anche quando i pod si accumulano su un nodo solo.
- **Nodo `calcolo` non disponibile** (`cordon`): API e worker ricreati ripartono tutti su `kintsugi-worker`. Quindi è davvero una preferenza.
- **Nodo `dati` non disponibile** (`cordon`): database e coda ricreati restano `Pending`, con l'avviso `FailedScheduling` («didn't match Pod's node affinity/selector»). Riaperto il nodo, ripartono. Quindi è davvero una regola rigida.
- Nessun pod dell'app è mai finito sul control plane, in nessuna prova.

## Problemi e soluzioni

- **Ricreando insieme API e database, l'API risponde 503 per circa 2 minuti dopo che il database è pronto.** Prova in V1: `kubectl delete pods --all` e subito 100 ordini: 100 × `503`; ancora 503 dopo 24 s; il primo `201` dopo circa 2 minuti dal riavvio dell'API. Il log dell'API ha solo `error connecting in 'pool-1': connection timeout expired`. Non dipende dalla posizione: l'API parte mentre il database non risponde e il pool di connessioni (`psycopg_pool`) aspetta sempre di più tra un tentativo e l'altro (stesso comportamento del 08/11, vedi `2026-11-08-worker-riprova.md`). Non è risolto qui.

## Limiti dello strumento emersi

- Kubernetes (`nodeAffinity` preferita, `IgnoredDuringExecution`): la regola vale quando si sceglie il nodo di un pod nuovo. Se `calcolo` si ferma e poi torna, i pod già ripartiti su `dati` restano lì: per tornare alla topologia di D0006 vanno ricreati. Il reset di F4 deve ricrearli e poi confrontare la collocazione con quella attesa.
- Ricreare insieme API e database lascia l'API senza ordini per circa 2 minuti: il reset di F4 deve ricreare prima il database e aspettarlo, oppure ricreare l'API dopo.
