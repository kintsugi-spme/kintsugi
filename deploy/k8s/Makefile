# Cluster kind e immagine dell'app (fase F3, issue #72). Da questa cartella:
#
#   make immagine   crea il cluster se manca, lo controlla, costruisce kintsugi:dev e la carica nei nodi
#   make cluster    solo il cluster: creazione (se manca) e controllo
#   make prova      un pod con kintsugi:dev su ognuno dei due worker, senza scaricare nulla
#   make v1         V1 da zero (cluster e immagine se mancano, database vuoto), aspetta che sia pronta
#   make v2         V2 da zero, come V1 ma con più copie dell'API (versioni.copie_api in config/parametri.yaml)
#   make v2-sonde-standard  V2 con le sonde standard dell'API, solo per il guasto F7 (sonde.sonda_standard_*)
#   make v3         V3 da zero: l'API mette gli ordini in coda (RabbitMQ) e i worker li salvano
#   make v4a        V4a da zero: come V2, con PostgreSQL primario e standby (CloudNativePG), replica asincrona
#   make v4s        V4s da zero: come V4a, con replica sincrona
#   make cnpg       solo l'operatore CloudNativePG (lo installano anche make v4a e make v4s)
#   make v5         V5 da zero: come V3, con i worker da 1 a 10 secondo la coda (KEDA)
#   make keda       solo KEDA (lo installa anche make v5)
#   make osservabilita  Prometheus e kube-state-metrics (D0019; lo installano anche make v1 … make v5)
#   make togli      toglie la versione accesa, dati compresi; il cluster, l'operatore, KEDA e l'osservabilità restano
#   make giu        cancella il cluster
#   make verifica   i criteri di F3 (issue #86): V1-V3 funzionano e un crash F1 dà fermo e ripristino con i millisecondi
#   make reset VERSIONE=v2   riporta la versione accesa allo stato iniziale e lo verifica (V1, V2, V3; issue #121)
#
# Tutti i comandi di kubectl usano il contesto `kind-kintsugi`: non toccano altri cluster
# che il computer conosca.
#
# `make v1` … `make v5` lanciano parametri.py, che richiede PyYAML:  pip install pyyaml

CLUSTER  := kintsugi
IMMAGINE := kintsugi:dev
KUBECTL  := kubectl --context kind-$(CLUSTER)
# Su Windows l'interprete si chiama di solito `python`:  make v1 PYTHON=python
PYTHON   ?= python3

# La versione di Kubernetes sta in kind-cluster.yaml (immagine dei nodi): non si riscrive qui.
VERSIONE_KUBERNETES := $(shell awk -F: '/image: kindest\/node/ {print $$NF; exit}' kind-cluster.yaml)

# I nodi di kind si chiamano come il cluster; D0006 li chiama worker1 e worker2.
CONTROL_PLANE := $(CLUSTER)-control-plane
WORKER_DATI   := $(CLUSTER)-worker
WORKER_CALCOLO := $(CLUSTER)-worker2

# L'immagine si costruisce con lo stesso nome che usa Compose (deploy/compose/Makefile).
# `kind load` la copia dentro i due worker: i manifest la usano con `imagePullPolicy: Never` e non la
# scaricano da nessun registro. Il control plane non ospita pod dell'app (D0006): niente copia.
# `--provenance=false`: senza, Docker Desktop aggiunge alla build un'attestazione con l'ora e l'ID
# dell'immagine cambia a ogni build anche a codice uguale; così resta lo stesso e si può confrontare.
immagine: cluster
	docker build --provenance=false -q -t $(IMMAGINE) ../../app
	kind load docker-image $(IMMAGINE) --name $(CLUSTER) --nodes $(WORKER_DATI),$(WORKER_CALCOLO)

cluster:
	@kind get clusters 2>/dev/null | grep -qx $(CLUSTER) \
		|| kind create cluster --name $(CLUSTER) --config kind-cluster.yaml
	@$(MAKE) --no-print-directory controlla

# Il cluster è come lo vuole D0006: tre nodi pronti, la versione di Kubernetes di kind-cluster.yaml, le
# etichette `dati` e `calcolo` sui due worker, e il control plane che rifiuta i pod dell'app (kind gli
# mette di suo il taint NoSchedule). Un cluster già acceso non viene ricreato: per questo si controlla
# la versione, che potrebbe essere quella di prima che kind-cluster.yaml la fissasse.
controlla:
	@$(KUBECTL) wait --for=condition=Ready node --all --timeout=120s >/dev/null
	@versioni=$$($(KUBECTL) get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}' | tr ' ' '\n' | sort -u | paste -sd ' ' -); \
		[ "$$versioni" = "$(VERSIONE_KUBERNETES)" ] \
		|| { echo "errore: i nodi hanno Kubernetes $$versioni, kind-cluster.yaml vuole $(VERSIONE_KUBERNETES): cancella il cluster (make giu) e rifai make cluster"; exit 1; }
	@n=$$($(KUBECTL) get nodes --no-headers | wc -l | tr -d ' '); \
		[ "$$n" = 3 ] || { echo "errore: il cluster ha $$n nodi, ne servono 3"; exit 1; }
	@[ "$$($(KUBECTL) get node $(WORKER_DATI) -o jsonpath='{.metadata.labels.kintsugi/ruolo}')" = dati ] \
		|| { echo "errore: $(WORKER_DATI) non ha l'etichetta kintsugi/ruolo=dati"; exit 1; }
	@[ "$$($(KUBECTL) get node $(WORKER_CALCOLO) -o jsonpath='{.metadata.labels.kintsugi/ruolo}')" = calcolo ] \
		|| { echo "errore: $(WORKER_CALCOLO) non ha l'etichetta kintsugi/ruolo=calcolo"; exit 1; }
	@$(KUBECTL) get node $(CONTROL_PLANE) -o jsonpath='{.spec.taints[*].effect}' | tr ' ' '\n' | grep -qx NoSchedule \
		|| { echo "errore: $(CONTROL_PLANE) accetta pod dell'app (manca il taint NoSchedule)"; exit 1; }
	@echo "cluster $(CLUSTER) ok: 3 nodi pronti con Kubernetes $(VERSIONE_KUBERNETES), $(WORKER_DATI)=dati, $(WORKER_CALCOLO)=calcolo, control plane senza pod dell'app"

# Un pod per ruolo, con `imagePullPolicy: Never`: se l'immagine non è già nel nodo il pod non parte
# (ErrImageNeverPull), quindi un pod riuscito prova che non è stato scaricato nulla.
# Se un pod non finisce in tempo, si stampano lo stato e gli avvisi di Kubernetes (il motivo) e si
# tolgono i pod di prova, che altrimenti resterebbero nel cluster.
ATTESA_PROVA := 90s
prova:
	$(KUBECTL) delete -f prova-immagine.yaml --ignore-not-found >/dev/null
	$(KUBECTL) apply -f prova-immagine.yaml
	$(KUBECTL) wait --for=jsonpath='{.status.phase}'=Succeeded pod/prova-dati pod/prova-calcolo --timeout=$(ATTESA_PROVA) \
		|| { echo "errore: i pod di prova non sono finiti in $(ATTESA_PROVA)"; \
			$(KUBECTL) get pod prova-dati prova-calcolo -o wide; \
			$(KUBECTL) get events --field-selector type=Warning,involvedObject.kind=Pod; \
			$(KUBECTL) delete -f prova-immagine.yaml >/dev/null; exit 1; }
	$(KUBECTL) get pod prova-dati prova-calcolo -o wide
	$(KUBECTL) delete -f prova-immagine.yaml >/dev/null

# Una versione dell'app da zero. Prima di toccare il cluster si rigenera parametri.env da
# config/parametri.yaml e si compone l'overlay: se uno dei due fallisce (per esempio manca PyYAML),
# la versione accesa resta com'è. Poi si toglie quella accesa (anche il volume del database, quindi si
# riparte senza ordini) e si aspetta che tutti i Deployment siano pronti. Se non lo sono in tempo, si
# stampano i pod e gli avvisi di Kubernetes.
ATTESA_VERSIONE := 180s
ETICHETTA := app.kubernetes.io/part-of=kintsugi
VERSIONI := v1 v2 v2-sonde-standard v3 v4a v4s v5
# In V4 il database è un cluster di CloudNativePG e non un Deployment: si aspetta anche lui, più a lungo,
# perché la prima volta i nodi scaricano l'immagine di PostgreSQL. Poi si riavvia l'API: partita prima del
# database, ritenterebbe la connessione a intervalli sempre più lunghi e resterebbe senza ordini fino a circa
# 2 minuti (limite del 15/11 in report/diario/README.md). Le altre versioni non hanno niente in più.
ATTESA_DATABASE := 600s
v4a v4s: cnpg
v4a v4s: ASPETTA_DATABASE = $(KUBECTL) wait --for=condition=Ready cluster/db --timeout=$(ATTESA_DATABASE) \
	&& $(KUBECTL) rollout restart deployment/api && $(KUBECTL) rollout status deployment/api --timeout=$(ATTESA_VERSIONE)
v5: keda
$(VERSIONI): immagine osservabilita
	$(PYTHON) parametri.py
	$(KUBECTL) kustomize overlays/$@ >/dev/null
	@$(MAKE) --no-print-directory togli
	$(KUBECTL) apply -k overlays/$@
	$(ASPETTA_DATABASE)
	$(KUBECTL) wait --for=condition=Available deployment -l $(ETICHETTA) --timeout=$(ATTESA_VERSIONE) \
		|| { echo "errore: $@ non è pronta in $(ATTESA_VERSIONE)"; \
			$(KUBECTL) get pods -o wide; \
			$(KUBECTL) get events --field-selector type=Warning; exit 1; }
	$(KUBECTL) get pods -o wide -L kintsugi/versione
	@echo "$@ pronta: gli ordini vanno a http://localhost:8080/ordini"

# L'operatore CloudNativePG alla versione fissata (D0014), dal file della release ufficiale. `apply` non
# cambia nulla se è già installato; la seconda riga aspetta che risponda, perché crea e controlla i cluster
# di PostgreSQL e prima non li accetta. Resta nel cluster anche dopo `make togli`.
# La prima volta il nodo scarica l'immagine dell'operatore: l'attesa è quella del database, non i 180 s
# delle versioni.
VERSIONE_CNPG := 1.30.2
ATTESA_OPERATORE := $(ATTESA_DATABASE)
cnpg:
	$(KUBECTL) apply --server-side -f https://github.com/cloudnative-pg/cloudnative-pg/releases/download/v$(VERSIONE_CNPG)/cnpg-$(VERSIONE_CNPG).yaml >/dev/null
	$(KUBECTL) -n cnpg-system rollout status deployment cnpg-controller-manager --timeout=$(ATTESA_OPERATORE)

# KEDA alla versione fissata (D0015), dal file della release ufficiale. `apply` non cambia nulla se è già
# installato; poi si aspettano i suoi tre componenti, perché prima non accettano uno ScaledObject. Resta nel
# cluster anche dopo `make togli`. Con Kubernetes 1.37 (kind-cluster.yaml) KEDA 2.21 è fuori dalla finestra
# provata dai suoi autori (1.34-1.36): D0015 chiede di verificarlo all'installazione, vedi report/diario/2026-11-19-keda-v5.md.
VERSIONE_KEDA := 2.21.1
# La prima volta i nodi scaricano le immagini di KEDA (tre) e il cluster può metterci più dei 180 s delle versioni.
ATTESA_KEDA := 600s
# Prometheus e kube-state-metrics (D0019), nel namespace `osservabilita` sul nodo `dati`. Restano accesi tra un
# cambio di versione e l'altro, così ogni versione si misura nelle stesse condizioni. La configurazione di
# Prometheus la genera parametri.py (intervallo di raccolta da config/parametri.yaml).
osservabilita: cluster
	$(PYTHON) parametri.py >/dev/null
	$(KUBECTL) apply -k osservabilita >/dev/null
	$(KUBECTL) -n osservabilita wait --for=condition=Available deployment --all --timeout=$(ATTESA_KEDA)

keda:
	$(KUBECTL) apply --server-side -f https://github.com/kedacore/keda/releases/download/v$(VERSIONE_KEDA)/keda-$(VERSIONE_KEDA).yaml >/dev/null
	$(KUBECTL) -n keda wait --for=condition=Available deployment --all --timeout=$(ATTESA_KEDA)

# Tutto ciò che porta l'etichetta della base (base/kustomization.yaml), qualunque versione sia: `all`
# comprende Deployment, Service e pod. `--wait` aspetta che i volumi (database, coda) siano cancellati.
# Lo ScaledObject di V5 non è in `all` e il suo tipo esiste solo con KEDA installato: si toglie per primo, perché
# KEDA riporti i worker al Deployment e cancelli da solo l'autoscaler che ha creato.
# Il cluster di PostgreSQL di V4 non è in `all`, e il suo tipo esiste solo con l'operatore installato: si
# toglie dopo l'API, aspettando che spariscano anche i suoi pod e volumi (`--cascade=foreground`), così una
# versione nuova non ritrova i dischi di quella vecchia.
togli:
	@if $(KUBECTL) get crd scaledobjects.keda.sh >/dev/null 2>&1; then \
		$(KUBECTL) delete scaledobjects.keda.sh -l $(ETICHETTA) --ignore-not-found --wait; \
	fi
	$(KUBECTL) delete all,pvc,configmap,secret -l $(ETICHETTA) --ignore-not-found --wait
	@if $(KUBECTL) get crd clusters.postgresql.cnpg.io >/dev/null 2>&1; then \
		$(KUBECTL) delete clusters.postgresql.cnpg.io -l $(ETICHETTA) --ignore-not-found --cascade=foreground --wait; \
	fi

giu:
	kind delete cluster --name $(CLUSTER)

# Verifica dei criteri di F3 (deploy/k8s/verifica-m3.sh): ogni versione riparte da zero, circa 10 minuti. I file dei
# run vanno in data/locale/verifica-m3-<ora>/. Serve Python 3.10 o più:  make verifica PYTHON=python3.14
verifica:
	PYTHON=$(PYTHON) ./verifica-m3.sh

# Reset prima di un run (harness/reset/reset.py, issue #121): la versione resta accesa, ma torna allo stato iniziale
# (tabelle e code vuote, pod ricreati, nessun ritardo di Toxiproxy) e lo verifica. Per ora V1, V2 e V3. Serve PyYAML.
#   make reset VERSIONE=v2
reset:
	@test -n "$(VERSIONE)" || { echo "errore: dì quale versione è accesa, per esempio  make reset VERSIONE=v2  (v1, v2 o v3)"; exit 1; }
	$(PYTHON) ../../harness/reset/reset.py --versione $(VERSIONE)

.PHONY: immagine cluster controlla prova $(VERSIONI) cnpg keda osservabilita togli giu verifica reset
