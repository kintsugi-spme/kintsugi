#!/usr/bin/env python3
"""Porta nei manifest i numeri di config/parametri.yaml (issue #73).

Kustomize non legge quel file: questo script ne ricava `base/parametri.env`, che un ConfigMap
generato (configMapGenerator) distribuisce ai pod. Gli overlay leggono da quel ConfigMap anche i numeri
che non sono variabili d'ambiente, come le copie dell'API (overlays/v2). Nessun numero si riscrive a mano
nei manifest.

  python3 deploy/k8s/parametri.py             scrive deploy/k8s/base/parametri.env
  python3 deploy/k8s/parametri.py --controlla esce con codice 1 se il file non coincide con parametri.yaml

Il file generato non si versiona (.gitignore). Serve PyYAML:  pip install pyyaml
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

# variabile d'ambiente -> percorso in config/parametri.yaml
# DEADLINE_S la leggono i pod. Gli altri no: li leggono i manifest, che li copiano nei campi dove servono
# (Kustomize `replacements`): COPIE_API e WORKER_V3 nelle `replicas` dell'API (V2, V3) e dei worker (V3);
# le SONDA_* nelle sonde dell'API (base/kustomization.yaml). Le SONDA_STANDARD_* sono per il guasto F7.
VALORI = {
    "DEADLINE_S": ("tempi", "deadline_api_s"),
    "COPIE_API": ("versioni", "copie_api"),
    "WORKER_V3": ("versioni", "worker_v3"),
    "SONDA_TIMEOUT_S": ("sonde", "sonda_timeout_s"),
    "SONDA_FALLIMENTI": ("sonde", "sonda_fallimenti_di_fila"),
    "SONDA_VELOCE_PRONTA_S": ("sonde", "sonda_veloce_pronta_periodo_s"),
    "SONDA_VELOCE_VIVA_S": ("sonde", "sonda_veloce_viva_periodo_s"),
    "SONDA_STANDARD_PRONTA_S": ("sonde", "sonda_standard_pronta_periodo_s"),
    "SONDA_STANDARD_VIVA_S": ("sonde", "sonda_standard_viva_periodo_s"),
}


def contenuto() -> str:
    parametri = yaml.safe_load(FILE_YAML.read_text(encoding="utf-8"))
    righe = []
    for nome, percorso in VALORI.items():
        valore = parametri
        for chiave in percorso:
            valore = valore[chiave]
        righe.append(f"{nome}={valore}")
    return "\n".join(righe) + "\n"


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argomenti.add_argument("--controlla", action="store_true")
    controlla = argomenti.parse_args().controlla
    atteso = contenuto()
    if controlla:
        if not FILE_ENV.exists() or FILE_ENV.read_text(encoding="utf-8") != atteso:
            print(f"{FILE_ENV.relative_to(QUI.parent.parent)} non coincide con config/parametri.yaml: "
                  "rilancia python3 deploy/k8s/parametri.py")
            return 1
        print("parametri.env coincide con config/parametri.yaml")
        return 0
    FILE_ENV.write_text(atteso, encoding="utf-8")
    print(f"scritto {FILE_ENV.relative_to(QUI.parent.parent)}:\n{atteso}", end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
