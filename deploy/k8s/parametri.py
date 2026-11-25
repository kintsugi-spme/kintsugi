#!/usr/bin/env python3
"""Porta nei manifest i numeri di config/parametri.yaml (issue #73).

Kustomize non legge quel file: questo script ne ricava `base/parametri.env`, che un ConfigMap
generato (configMapGenerator) distribuisce ai pod. Gli overlay leggono da quel ConfigMap anche i numeri
che non sono variabili d'ambiente, come le copie dell'API (overlays/v2). Nessun numero si riscrive a mano
nei manifest.

  python3 deploy/k8s/parametri.py             scrive deploy/k8s/base/parametri.env e osservabilita/prometheus.yml
  python3 deploy/k8s/parametri.py --controlla esce con codice 1 se un file non coincide con parametri.yaml

La configurazione di Prometheus è un testo unico, non un campo che Kustomize possa sostituire: si ricava da
osservabilita/prometheus.modello.yml mettendo al posto dei segnaposti @CHIAVE@ i valori di MODELLO.

I file generati non si versionano (.gitignore). Serve PyYAML:  pip install pyyaml
Per aggiungere un valore: una riga in VALORI, con il nome della variabile d'ambiente e il percorso in YAML.

Questo è uno dei tre lettori di config/parametri.yaml: gli altri sono docs/scripts/parametri.py (documenti,
ha `valori()`) e l'`awk` di deploy/compose/Makefile (deadline). Se la struttura del file cambia, vanno
corretti tutti e tre.
"""
import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Manca PyYAML: installalo con  pip install pyyaml")

QUI = Path(__file__).resolve().parent
FILE_YAML = QUI.parent.parent / "config" / "parametri.yaml"
FILE_ENV = QUI / "base" / "parametri.env"
FILE_MODELLO = QUI / "osservabilita" / "prometheus.modello.yml"
FILE_PROMETHEUS = QUI / "osservabilita" / "prometheus.yml"

# segnaposto in prometheus.modello.yml -> percorso in config/parametri.yaml (D0019)
MODELLO = {
    "INTERVALLO_RACCOLTA_S": ("osservabilita", "intervallo_raccolta_s"),
}

# variabile d'ambiente -> percorso in config/parametri.yaml
# DEADLINE_S e SERVICE_TIME_S (D0018) li leggono i pod, l'API e i worker. Gli altri no: li leggono i manifest, che li copiano nei campi dove servono
# (Kustomize `replacements`): COPIE_API e WORKER_V3 nelle `replicas` dell'API (V2, V3) e dei worker (V3);
# le SONDA_* nelle sonde dell'API (base/kustomization.yaml). Le SONDA_STANDARD_* sono per il guasto F7.
# WORKER_V5_* e KEDA_* vanno nello ScaledObject di V5 (overlays/v5/kustomization.yaml).
VALORI = {
    "DEADLINE_S": ("tempi", "deadline_api_s"),
    "SERVICE_TIME_S": ("tempi", "tempo_servizio_s"),
    "COPIE_API": ("versioni", "copie_api"),
    "WORKER_V3": ("versioni", "worker_v3"),
    "SONDA_TIMEOUT_S": ("sonde", "sonda_timeout_s"),
    "SONDA_FALLIMENTI": ("sonde", "sonda_fallimenti_di_fila"),
    "SONDA_VELOCE_PRONTA_S": ("sonde", "sonda_veloce_pronta_periodo_s"),
    "SONDA_VELOCE_VIVA_S": ("sonde", "sonda_veloce_viva_periodo_s"),
    "SONDA_STANDARD_PRONTA_S": ("sonde", "sonda_standard_pronta_periodo_s"),
    "SONDA_STANDARD_VIVA_S": ("sonde", "sonda_standard_viva_periodo_s"),
    "WORKER_V5_MIN": ("versioni", "worker_v5_min"),
    "WORKER_V5_MAX": ("versioni", "worker_v5_max"),
    "KEDA_CONTROLLO_0_1_S": ("keda", "controllo_keda_da_0_a_1_s"),
    "KEDA_SOGLIA": ("keda", "soglia_ordini_per_worker"),
    "KEDA_ATTESA_S": ("keda", "attesa_prima_di_togliere_s"),
}


def valore(parametri: dict, percorso: tuple[str, ...]):
    for chiave in percorso:
        parametri = parametri[chiave]
    return parametri


def contenuto() -> dict[Path, str]:
    """I file generati, ognuno con il testo che deve avere."""
    parametri = yaml.safe_load(FILE_YAML.read_text(encoding="utf-8"))
    env = "\n".join(f"{nome}={valore(parametri, percorso)}" for nome, percorso in VALORI.items()) + "\n"
    prometheus = FILE_MODELLO.read_text(encoding="utf-8")
    for nome, percorso in MODELLO.items():
        prometheus = prometheus.replace(f"@{nome}@", str(valore(parametri, percorso)))
    if "@" in "".join(r.split("#")[0] for r in prometheus.splitlines()):
        sys.exit(f"{FILE_MODELLO.name}: è rimasto un segnaposto senza valore in MODELLO")
    return {FILE_ENV: env, FILE_PROMETHEUS: prometheus}


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argomenti.add_argument("--controlla", action="store_true")
    controlla = argomenti.parse_args().controlla
    attesi = contenuto()
    if controlla:
        diversi = [f for f, testo in attesi.items() if not f.exists() or f.read_text(encoding="utf-8") != testo]
        for f in diversi:
            print(f"{f.relative_to(QUI.parent.parent)} non coincide con config/parametri.yaml: "
                  "rilancia python3 deploy/k8s/parametri.py")
        if not diversi:
            print("parametri.env e prometheus.yml coincidono con config/parametri.yaml")
        return 1 if diversi else 0
    for f, testo in attesi.items():
        f.write_text(testo, encoding="utf-8")
    print(f"scritto {FILE_ENV.relative_to(QUI.parent.parent)}:\n{attesi[FILE_ENV]}", end="")
    print(f"scritto {FILE_PROMETHEUS.relative_to(QUI.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
