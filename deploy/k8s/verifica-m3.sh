#!/bin/bash
# Verifica dei criteri di F3 (issue #86). Da deploy/k8s:  make verifica
#
#   Criterio 1  V1, V2 e V3 funzionano su Kubernetes: 100 ordini a 10/s, tutti accettati (201 in V1 e V2, 202 in
#               V3), 100 righe nel database e, in V3, le code `ordini` e `ordini.falliti` vuote.
#   Criterio 2  con un crash F1 l'harness minimo dà fermo e istante di ripristino con risoluzione sotto il
#               secondo: carico a 20/s per 60 s, SIGKILL a una copia dell'API al secondo 20
#               (harness/faults/arresto.py), poi analysis/fermo.py sul log del client.
#
# Ogni versione riparte da zero (`make vN`). I file di ogni prova vanno in data/locale/verifica-m3-<ora>/, che git
# non versiona. Esce con codice 0 solo se tutto è soddisfatto. Serve Python 3.10 o più e PyYAML:
#   PYTHON=python3.14 make verifica
set -u

PYTHON=${PYTHON:-python3}
QUI=$(cd "$(dirname "$0")" && pwd)
RADICE=$(cd "$QUI/../.." && pwd)
K="kubectl --context kind-kintsugi"
CARTELLA=${CARTELLA:-$RADICE/data/locale/verifica-m3-$(date +%Y%m%d-%H%M%S)}
RISULTATO=0

# esito NOME CODICE DETTAGLIO: CODICE 0 = soddisfatto
esito() {
  if [ "$2" -eq 0 ]; then echo "  ok       $1: $3"; else echo "  FALLITO  $1: $3"; RISULTATO=1; fi
}

righe_ordini() { $K exec deploy/db -- psql -U kintsugi -d kintsugi -tAc "select count(*) from ordini" | tr -d '[:space:]'; }
messaggi_in_coda() {
  $K exec deploy/coda -- rabbitmqctl list_queues name messages 2>/dev/null \
    | awk '$1 == "ordini" || $1 == "ordini.falliti" {s += $2} END {print s + 0}'
}

# Accende una versione da zero e la porta in uno stato in cui risponde subito. `make vN` torna quando i Deployment
# sono pronti, ma la sonda `/readyz` non guarda il database (D0007): un'API partita prima di lui ritenta la
# connessione a intervalli sempre più lunghi e per circa 2 minuti risponde 503 (limite del 15/11 in
# report/diario/README.md). A `make vN` finito il database è pronto, quindi si riavviano le copie dell'API (e, in V3,
# i worker, che hanno lo stesso pool): ripartono con il database già acceso.
accendi() {  # accendi VERSIONE CARTELLA
  local v=$1 d=$2 deploy
  make -C "$QUI" "$v" PYTHON="$PYTHON" >"$d/make.txt" 2>&1 || { esito "$v parte" 1 "make $v non è riuscito ($d/make.txt)"; return 1; }
  deploy="deployment/api"; [ "$v" = v3 ] && deploy="deployment/api deployment/worker"
  # shellcheck disable=SC2086
  { $K rollout restart $deploy && for x in $deploy; do $K rollout status "$x" --timeout=120s; done; } >>"$d/make.txt" 2>&1 \
    || { esito "$v parte" 1 "il riavvio dopo il database non è finito ($d/make.txt)"; return 1; }
}

criterio1() {  # criterio1 VERSIONE CODICE_ATTESO
  local v=$1 atteso=$2 d=$CARTELLA/criterio1-$1
  mkdir -p "$d"
  accendi "$v" "$d" || return
  $PYTHON "$RADICE/harness/client/cliente.py" --url http://localhost:8080/ordini --richieste 100 --ritmo 10 \
    --timeout 2 --uscita "$d/client.csv" >"$d/cliente.txt" 2>&1
  local buoni righe m
  buoni=$(awk -F, -v e="$atteso" 'NR > 1 && $3 == e {n++} END {print n + 0}' "$d/client.csv")
  esito "$v: ordini accettati con $atteso" "$([ "$buoni" = 100 ]; echo $?)" "$buoni su 100"
  if [ "$v" = v3 ]; then
    for _ in $(seq 1 30); do [ "$(messaggi_in_coda)" = 0 ] && break; sleep 1; done
  fi
  righe=$(righe_ordini)
  esito "$v: righe nel database" "$([ "$righe" = 100 ]; echo $?)" "$righe su 100"
  if [ "$v" = v3 ]; then
    m=$(messaggi_in_coda)
    esito "$v: code ordini e ordini.falliti vuote" "$([ "$m" = 0 ]; echo $?)" "$m messaggi"
  fi
}

criterio2() {  # criterio2 VERSIONE
  local v=$1 d=$CARTELLA/criterio2-$1 arresto fermo cliente guasto
  mkdir -p "$d"
  accendi "$v" "$d" || return
  sleep 10
  $PYTHON "$RADICE/harness/client/cliente.py" --url http://localhost:8080/ordini --durata 60 --ritmo 20 \
    --timeout 2 --uscita "$d/client.csv" >"$d/cliente.txt" 2>&1 &
  cliente=$!
  sleep 20
  $PYTHON "$RADICE/harness/faults/arresto.py" --cartella "$d" --selettore app=api >"$d/arresto.txt" 2>&1
  arresto=$?
  wait "$cliente"
  esito "$v: SIGKILL a una copia dell'API, riavviata nello stesso pod" "$arresto" "$(tail -1 "$d/arresto.txt" | cut -c1-140)"
  [ "$arresto" -eq 0 ] || return
  guasto=$($PYTHON -c "import json, sys; print(json.load(open(sys.argv[1]))['ts_guasto'])" "$d/guasto.json")
  $PYTHON "$RADICE/analysis/fermo.py" "$d" --guasto "$guasto" >"$d/fermo.txt" 2>&1
  fermo=$?
  sed 's/^/             /' "$d/fermo.txt"
  local con_fermo con_ripristino
  con_fermo=$(grep -c -E '^fermo +t_r - t_g = [0-9]+\.[0-9]{3} s' "$d/fermo.txt")
  con_ripristino=$(grep -c -E '^ripristino +t_r = .*:[0-9]{2}\.[0-9]{3}' "$d/fermo.txt")
  esito "$v: fermo e ripristino con i millisecondi" \
    "$([ "$fermo" -eq 0 ] && [ "$con_fermo" -eq 1 ] && [ "$con_ripristino" -eq 1 ]; echo $?)" "analysis/fermo.py, codice $fermo"
}

echo "Verifica dei criteri di F3. File dei run: $CARTELLA"
echo "Criterio 1: V1, V2 e V3 funzionano su Kubernetes"
criterio1 v1 201
criterio1 v2 201
criterio1 v3 202
echo "Criterio 2: con un crash F1, fermo e ripristino con risoluzione sotto il secondo"
criterio2 v1
criterio2 v2
criterio2 v3
make -C "$QUI" togli >/dev/null 2>&1
if [ "$RISULTATO" -eq 0 ]; then echo "Criteri soddisfatti."; else echo "Criteri NON soddisfatti: vedi i FALLITO qui sopra."; fi
exit "$RISULTATO"
