# Cluster kind e immagine dell'app (fase F3, issue #72). Da questa cartella:
#
#   make immagine   crea il cluster se manca, lo controlla, costruisce kintsugi:dev e la carica nei nodi
#   make cluster    solo il cluster: creazione (se manca) e controllo
#   make prova      un pod con kintsugi:dev su ognuno dei due worker, senza scaricare nulla
#   make v1         V1 da zero (cluster e immagine se mancano, database vuoto), aspetta che sia pronta
#   make togli      toglie la versione accesa, dati compresi; il cluster resta
#   make giu        cancella il cluster
#
# Tutti i comandi di kubectl usano il contesto `kind-kintsugi`: non toccano altri cluster
# che il computer conosca.
#
# `make v1` lancia parametri.py, che richiede PyYAML:  pip install pyyaml

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
v1: immagine
	$(PYTHON) parametri.py
	$(KUBECTL) kustomize overlays/$@ >/dev/null
	@$(MAKE) --no-print-directory togli
	$(KUBECTL) apply -k overlays/$@
	$(KUBECTL) wait --for=condition=Available deployment -l $(ETICHETTA) --timeout=$(ATTESA_VERSIONE) \
		|| { echo "errore: $@ non è pronta in $(ATTESA_VERSIONE)"; \
			$(KUBECTL) get pods -o wide; \
			$(KUBECTL) get events --field-selector type=Warning; exit 1; }
	$(KUBECTL) get pods -o wide -L kintsugi/versione
	@echo "$@ pronta: gli ordini vanno a http://localhost:8080/ordini"

# Tutto ciò che porta l'etichetta della base (base/kustomization.yaml), qualunque versione sia: `all`
# comprende Deployment, Service e pod. `--wait` aspetta che il volume del database sia cancellato.
togli:
	$(KUBECTL) delete all,pvc,configmap -l $(ETICHETTA) --ignore-not-found --wait

giu:
	kind delete cluster --name $(CLUSTER)

.PHONY: immagine cluster controlla prova v1 togli giu
