"""Carico a ritmo costante con JMeter (issue #116): lancia costante.jmx e scrive client.csv.

    python harness/jmeter/carico.py --ritmo 50 --durata 180 --uscita data/locale/<run-id>/client.csv

Il generatore della campagna è JMeter con l'Open Model Thread Group (modello aperto, da riga di comando). Questo
script gli passa ritmo, durata, indirizzo e timeout come proprietà, lo lancia senza interfaccia e converte i
suoi risultati (`jmeter.jtl`) in `client.csv` con le colonne di `data/README.md`: le stesse di
harness/client/cliente.py, così `analysis/ritmo.py`, `fermo.py` e `categorie.py` restano uguali.

Accanto a client.csv restano `jmeter.jtl` (i risultati grezzi) e `jmeter.log`. Serve JMeter 5.5 o più
(l'Open Model Thread Group); quello usato è scritto nel diario. Il timeout predefinito è quello di
config/parametri.yaml (tempi.timeout_client_s, D0008), letto con PyYAML.
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

QUI = Path(__file__).resolve().parent
PIANO = QUI / "costante.jmx"
PARAMETRI = QUI.parents[1] / "config" / "parametri.yaml"
COLONNE = ["ts_invio", "id", "esito", "tempo_risposta_s"]
HEAP_PREDEFINITO = "512m"


def proprieta(url: str, ritmo: float, durata_s: float, timeout_s: float) -> dict[str, str]:
    """Le proprietà che costante.jmx legge (-Jnome=valore) e quelle che dicono a JMeter come salvare i risultati.

    `coda_s` è una pausa dopo l'ultimo invio, lunga quanto il timeout: senza, JMeter interromperebbe alla fine
    della durata le richieste ancora in volo, e le ultime non avrebbero un esito.
    """
    if ritmo <= 0 or durata_s <= 0 or timeout_s <= 0:
        raise ValueError("ritmo, durata e timeout devono essere positivi")
    parti = urlsplit(url)
    if parti.scheme != "http" or not parti.hostname:
        raise ValueError(f"indirizzo non valido: {url} (serve http://host:porta/percorso)")
    return {
        "host": parti.hostname,
        "porta": str(parti.port or 80),
        "percorso": parti.path or "/",
        "ritmo": f"{ritmo:g}",
        "durata": f"{durata_s:g}",
        "coda_s": f"{timeout_s + 1:g}",
        "timeout_ms": str(round(timeout_s * 1000)),
        # Il codice dell'ordine (variabile `id`) finisce in una colonna dei risultati.
        "sample_variables": "id",
        "jmeter.save.saveservice.output_format": "csv",
        "jmeter.save.saveservice.print_field_names": "true",
        # L'istante salvato è quello di invio, non quello della risposta.
        "sampleresult.timestamp.start": "true",
        # A fine test JMeter resterebbe acceso circa 60 s, finché un gruppo di thread interno non si spegne da solo:
        # un minuto perso a ogni run (circa 3,5 ore sulla campagna). Così esce appena il test è finito.
        "jmeterengine.force.system.exit": "true",
    }


def esito(codice: str) -> str:
    """Il codice HTTP, oppure «timeout» o «errore», come in cliente.py.

    Quando la risposta non arriva, JMeter scrive al posto del codice il nome dell'eccezione Java, per esempio
    «Non HTTP response code: java.net.SocketTimeoutException».
    """
    codice = codice.strip()
    if codice.isdigit():
        return codice
    return "timeout" if "Timeout" in codice else "errore"


def converti(righe_jtl) -> list[list[str]]:
    """Dalle righe di jmeter.jtl (dizionari) alle righe di client.csv, in ordine di invio."""
    righe = []
    for r in righe_jtl:
        istante = datetime.fromtimestamp(int(r["timeStamp"]) / 1000, tz=timezone.utc)
        righe.append((istante, [istante.isoformat(), r["id"], esito(r["responseCode"]),
                                f"{int(r['elapsed']) / 1000:.6f}"]))
    righe.sort(key=lambda x: x[0])
    return [riga for _, riga in righe]


def scrivi_client_csv(percorso_jtl: Path, percorso_csv: Path) -> Counter:
    with open(percorso_jtl, newline="", encoding="utf-8") as f:
        righe = converti(csv.DictReader(f))
    with open(percorso_csv, "w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(COLONNE)
        scrittore.writerows(righe)
    return Counter(r[2] for r in righe)


def comando(jmeter: str, cartella: Path, props: dict[str, str]) -> list[str]:
    return [jmeter, "-n", "-t", str(PIANO), "-l", str(cartella / "jmeter.jtl"), "-j", str(cartella / "jmeter.log"),
            *[f"-J{k}={v}" for k, v in props.items()]]


def timeout_predefinito() -> float:
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere il timeout da config/parametri.yaml: pip install pyyaml, oppure passa --timeout")
    with open(PARAMETRI, encoding="utf-8") as f:
        return float(yaml.safe_load(f)["tempi"]["timeout_client_s"])


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--url", default="http://localhost:8080/ordini")
    parser.add_argument("--ritmo", type=float, required=True, help="ordini al secondo")
    parser.add_argument("--durata", type=float, required=True, help="secondi di invio")
    parser.add_argument("--uscita", required=True, help="client.csv; jmeter.jtl e jmeter.log vanno nella stessa cartella")
    parser.add_argument("--timeout", type=float, default=None, help="secondi (predefinito: tempi.timeout_client_s)")
    parser.add_argument("--heap", default=HEAP_PREDEFINITO, help="memoria di JMeter, per esempio 512m")
    parser.add_argument("--jmeter", default="jmeter", help="il comando di JMeter")
    a = parser.parse_args()
    timeout_s = a.timeout if a.timeout is not None else timeout_predefinito()
    uscita = Path(a.uscita)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    try:
        props = proprieta(a.url, a.ritmo, a.durata, timeout_s)
    except ValueError as errore:
        sys.exit(f"errore: {errore}")
    # Memoria fissa e uguale in ogni run: JMeter gira sul computer insieme al cluster.
    ambiente = {**os.environ, "HEAP": f"-Xms{a.heap} -Xmx{a.heap}"}
    inizio = time.monotonic()
    try:
        subprocess.run(comando(a.jmeter, uscita.parent, props), check=True, env=ambiente,
                       stdout=subprocess.DEVNULL)
    except FileNotFoundError:
        sys.exit(f"errore: programma non trovato: {a.jmeter} (serve JMeter 5.5 o più)")
    except subprocess.CalledProcessError as errore:
        sys.exit(f"errore: JMeter è uscito con codice {errore.returncode} (vedi {uscita.parent / 'jmeter.log'})")
    esiti = scrivi_client_csv(uscita.parent / "jmeter.jtl", uscita)
    dettaglio = ", ".join(f"{k}: {v}" for k, v in sorted(esiti.items()))
    print(f"inviate {sum(esiti.values())} richieste in {time.monotonic() - inizio:.1f} s ({dettaglio}); log in {uscita}")


if __name__ == "__main__":
    main()
