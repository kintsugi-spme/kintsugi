# Cluster kind e immagine dell'app (fase F3, issue #72). Da questa cartella:
#
#   make immagine   crea il cluster se manca, lo controlla, costruisce kintsugi:dev e la carica nei nodi
#   make cluster    solo il cluster: creazione (se manca) e controllo
#   make prova      un pod con kintsugi:dev su ognuno dei due worker, senza scaricare nulla
#   make giu        cancella il cluster
#
# Tutti i comandi di kubectl usano il contesto `kind-kintsugi`: non toccano altri cluster
# che il computer conosca.

CLUSTER  := kintsugi
IMMAGINE := kintsugi:dev
KUBECTL  := kubectl --context kind-$(CLUSTER)

# I nodi di kind si chiamano come il cluster; D0006 li chiama worker1 e worker2.
CONTROL_PLANE := $(CLUSTER)-control-plane
WORKER_DATI   := $(CLUSTER)-worker
WORKER_CALCOLO := $(CLUSTER)-worker2

# L'immagine si costruisce con lo stesso nome che usa Compose (deploy/compose/Makefile).
# `kind load` la copia dentro ognuno dei tre nodi: i manifest la usano con
# `imagePullPolicy: Never` e non la scaricano da nessun registro.
immagine: cluster
	docker build -q -t $(IMMAGINE) ../../app
	kind load docker-image $(IMMAGINE) --name $(CLUSTER)

cluster:
	@kind get clusters 2>/dev/null | grep -qx $(CLUSTER) \
		|| kind create cluster --name $(CLUSTER) --config kind-cluster.yaml
	@$(MAKE) --no-print-directory controlla

# Il cluster è come lo vuole D0006: tre nodi pronti, le etichette `dati` e `calcolo` sui due worker,
# e il control plane che rifiuta i pod dell'app (kind gli mette di suo il taint NoSchedule).
controlla:
	@$(KUBECTL) wait --for=condition=Ready node --all --timeout=120s >/dev/null
	@n=$$($(KUBECTL) get nodes --no-headers | wc -l | tr -d ' '); \
		[ "$$n" = 3 ] || { echo "errore: il cluster ha $$n nodi, ne servono 3"; exit 1; }
	@[ "$$($(KUBECTL) get node $(WORKER_DATI) -o jsonpath='{.metadata.labels.kintsugi/ruolo}')" = dati ] \
		|| { echo "errore: $(WORKER_DATI) non ha l'etichetta kintsugi/ruolo=dati"; exit 1; }
	@[ "$$($(KUBECTL) get node $(WORKER_CALCOLO) -o jsonpath='{.metadata.labels.kintsugi/ruolo}')" = calcolo ] \
		|| { echo "errore: $(WORKER_CALCOLO) non ha l'etichetta kintsugi/ruolo=calcolo"; exit 1; }
	@$(KUBECTL) get node $(CONTROL_PLANE) -o jsonpath='{.spec.taints[*].effect}' | grep -q NoSchedule \
		|| { echo "errore: $(CONTROL_PLANE) accetta pod dell'app (manca il taint NoSchedule)"; exit 1; }
	@echo "cluster $(CLUSTER) ok: 3 nodi pronti, $(WORKER_DATI)=dati, $(WORKER_CALCOLO)=calcolo, control plane senza pod dell'app"

# Un pod per ruolo, con `imagePullPolicy: Never`: se l'immagine non è già nel nodo il pod non parte
# (ErrImageNeverPull), quindi un pod riuscito prova che non è stato scaricato nulla.
prova:
	$(KUBECTL) delete -f prova-immagine.yaml --ignore-not-found >/dev/null
	$(KUBECTL) apply -f prova-immagine.yaml
	$(KUBECTL) wait --for=jsonpath='{.status.phase}'=Succeeded pod/prova-dati pod/prova-calcolo --timeout=90s
	$(KUBECTL) get pod prova-dati prova-calcolo -o wide
	$(KUBECTL) delete -f prova-immagine.yaml >/dev/null

giu:
	kind delete cluster --name $(CLUSTER)

.PHONY: immagine cluster controlla prova giu
