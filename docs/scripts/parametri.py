#!/usr/bin/env python3
"""Valori numerici di Kintsugi: legge config/parametri.yaml (alla radice) e li porta nei documenti.

  python3 scripts/parametri.py genera
      scrive docs/config/parametri.tex, con la macro \\parametro{chiave} per i file LaTeX
  python3 scripts/parametri.py controlla [--fix] [file.md ...]
      confronta con il file dei valori i numeri marcati nei file Markdown:
      <!-- num:run_totali -->220<!-- /num -->
      Senza file controlla tutti i .md del repository tranne il diario (report/diario).
      Con --fix riscrive i numeri sbagliati invece di segnalarli.
  python3 scripts/parametri.py elenca
      stampa chiavi e valori

Serve PyYAML:  pip install pyyaml
"""
import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Manca PyYAML: installalo con  pip install pyyaml")

DOCS = Path(__file__).resolve().parent.parent
RADICE = DOCS.parent
FILE_YAML = RADICE / "config" / "parametri.yaml"
FILE_TEX = DOCS / "config" / "parametri.tex"
CARTELLE_SALTATE = {".git", ".venv", "venv", "node_modules"}

MARCATORE = re.compile(r"<!-- num:(\w+) -->(.*?)<!-- /num -->")

INTESTAZIONE_TEX = r"""% File generato da scripts/parametri.py a partire da config/parametri.yaml.
% Non modificarlo a mano: make lo rigenera. Nel testo si scrive \parametro{run_totali}.
\newcommand{\parametro}[1]{%
  \ifcsname parametro:#1\endcsname
    \csname parametro:#1\endcsname
  \else
    \PackageError{parametri}{Parametro sconosciuto: #1}{Controlla config/parametri.yaml.}%
  \fi}
"""


def raccogli_numeri(nodo, trovati):
    """Raccoglie i numeri dei dizionari annidati, con il nome dell'ultima chiave. Salta le liste."""
    for chiave, valore in nodo.items():
        if isinstance(valore, dict):
            raccogli_numeri(valore, trovati)
        elif isinstance(valore, (int, float)) and not isinstance(valore, bool):
            if not re.fullmatch(r"[a-z0-9_]+", chiave):
                sys.exit(f"Chiave non valida in parametri.yaml: {chiave} (solo minuscole, cifre e _)")
            if chiave in trovati:
                sys.exit(f"Chiave ripetuta in parametri.yaml: {chiave}")
            trovati[chiave] = valore


def valori():
    dati = yaml.safe_load(FILE_YAML.read_text(encoding="utf-8"))
    trovati = {}
    raccogli_numeri(dati, trovati)
    calcolati = {
        "run_totali": sum(g["ripetizioni"] * len(g["configurazioni"]) for g in dati["matrice"]),
        "budget_errore_minuti": round(
            trovati["finestra_giorni"] * 24 * 60 * (100 - trovati["obiettivo_percentuale"]) / 100, 1
        ),
    }
    for chiave in calcolati:
        if chiave in trovati:
            sys.exit(f"{chiave} non va scritto in parametri.yaml: lo calcola lo script")
    trovati.update(calcolati)
    return trovati


def formato(numero):
    """Il numero come si scrive in italiano: 1,5 e non 1.5."""
    if isinstance(numero, float) and numero.is_integer():
        numero = int(numero)
    return str(numero).replace(".", ",")


def genera():
    v = valori()
    righe = [INTESTAZIONE_TEX]
    for chiave, numero in sorted(v.items()):
        righe.append(rf"\expandafter\def\csname parametro:{chiave}\endcsname{{{formato(numero)}}}")
    FILE_TEX.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"Scritto {FILE_TEX.relative_to(RADICE)} ({len(v)} valori)")


def elenca():
    for chiave, numero in sorted(valori().items()):
        print(f"{chiave:45} {formato(numero)}")


def nome(percorso):
    try:
        return percorso.resolve().relative_to(RADICE).as_posix()
    except ValueError:
        return str(percorso)


def file_markdown():
    for cartella, sotto, file in os.walk(RADICE):
        sotto[:] = sorted(d for d in sotto if d not in CARTELLE_SALTATE)
        relativa = Path(cartella).relative_to(RADICE).as_posix()
        if relativa == "report/diario" or relativa.startswith("report/diario/"):
            continue
        for f in sorted(file):
            if f.endswith(".md"):
                yield Path(cartella) / f


def controlla(file, correggi):
    v = valori()
    controllati = sbagliati = 0
    for percorso in file or file_markdown():
        testo = percorso.read_text(encoding="utf-8")

        def verifica(m):
            nonlocal controllati, sbagliati
            controllati += 1
            chiave, trovato = m.groups()
            riga = testo.count("\n", 0, m.start()) + 1
            if chiave not in v:
                print(f"{nome(percorso)}:{riga}: chiave sconosciuta «{chiave}»")
                sbagliati += 1
                return m.group(0)
            atteso = formato(v[chiave])
            if trovato == atteso:
                return m.group(0)
            if correggi:
                print(f"{nome(percorso)}:{riga}: corretto {trovato} -> {atteso} ({chiave})")
                return f"<!-- num:{chiave} -->{atteso}<!-- /num -->"
            print(f"{nome(percorso)}:{riga}: trovato {trovato}, atteso {atteso} ({chiave})")
            sbagliati += 1
            return m.group(0)

        nuovo = MARCATORE.sub(verifica, testo)
        if correggi and nuovo != testo:
            percorso.write_text(nuovo, encoding="utf-8")

    if controllati == 0:
        print("Nessun numero marcato trovato.")
    elif sbagliati == 0:
        print(f"{controllati} numeri controllati: tutti corretti.")
    else:
        print(f"{sbagliati} numeri da correggere su {controllati} controllati (usa --fix).")
    return 1 if sbagliati else 0


def main():
    parser = argparse.ArgumentParser(description="Valori numerici di Kintsugi")
    comandi = parser.add_subparsers(dest="comando", required=True)
    comandi.add_parser("genera", help="scrive config/parametri.tex")
    comandi.add_parser("elenca", help="stampa chiavi e valori")
    c = comandi.add_parser("controlla", help="confronta i numeri marcati nei file Markdown")
    c.add_argument("--fix", action="store_true", help="riscrive i numeri sbagliati")
    c.add_argument("file", nargs="*", type=Path)
    args = parser.parse_args()
    if args.comando == "genera":
        genera()
    elif args.comando == "elenca":
        elenca()
    else:
        sys.exit(controlla(args.file, args.fix))


if __name__ == "__main__":
    main()
