# Avvio di V1, V2 e V3 sul computer con Docker Compose (fase F2). Vedi README.md.
#
#   make v1       una copia dell'API sincrona
#   make v2       tre copie dell'API sincrona dietro un bilanciatore
#   make v3       API con la coda e tre worker
#   make giu      ferma tutto e cancella i dati (database e coda)
#
# Il tempo di servizio si imposta a parte:  make v3 SERVICE_TIME_S=0.05

# La deadline dell'API sta in config/parametri.yaml (tempi.deadline_api_s) e non si riscrive qui.
DEADLINE_S := $(shell awk '/^ *deadline_api_s:/ {print $$2}' ../../config/parametri.yaml)
export DEADLINE_S

COMPOSE = docker compose -f base.yaml

# L'immagine si costruisce qui, una volta sola: se la costruissero insieme `api` e `worker`, Docker
# si fermerebbe con «image already exists».
v1 v2 v3: giu
	docker build -q -t kintsugi:dev ../../app
	$(COMPOSE) -f $@.yaml up -d --wait

# Include v3.yaml perché `down -v` cancella solo i volumi usati dai servizi che conosce, e quello
# della coda lo usa solo V3. I container delle altre versioni sono «orfani» e si cancellano lo stesso.
giu:
	$(COMPOSE) -f v3.yaml down -v --remove-orphans

.PHONY: v1 v2 v3 giu
