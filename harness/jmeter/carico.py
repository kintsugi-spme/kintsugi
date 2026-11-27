"""Il carico della campagna con JMeter (issue #116, #117): lancia carico.jmx e scrive client.csv.

    python harness/jmeter/carico.py --ritmo 50 --durata 180 --uscita data/locale/<run-id>/client.csv
    python harness/jmeter/carico.py --profilo w2 --mu1 20 --uscita data/locale/<run-id>/client.csv

Due profili:

    costante   W1 e W3: `--ritmo` ordini al secondo per `--durata` secondi
    w2         base, picco e di nuovo base, rispetto alla capacità di un worker `--mu1` (capitolo «Protocollo di
               misura»): base al carichi.w2_base_percentuale_mu1 % di mu1, picco al carichi.w2_picco_percentuale_mu1 %
               per carichi.w2_durata_picco_s secondi dal minuto carichi.w2_inizio_picco_minuto. Durata predefinita: fino
               alla fine della finestra del costo (carichi.w2_finestra_costo_min dopo l'inizio del picco)

Il profilo diventa il programma degli arrivi dell'Open Model Thread Group (modello aperto, arrivi regolari) e si
scrive anche in `carico.json`, nella cartella del run: `analysis/ritmo.py` lo legge da lì per sapere quale ritmo
aspettarsi in ogni finestra. Così il profilo è scritto una volta sola, da chi lo genera.

I risultati di JMeter (`jmeter.jtl`) diventano `client.csv` con le colonne di `data/README.md`: le stesse di
harness/client/cliente.py, così `analysis/ritmo.py`, `fermo.py` e `categorie.py` restano uguali. Accanto restano
`jmeter.jtl` e `jmeter.log`. Serve JMeter 5.5 o più (l'Open Model Thread Group). Timeout e percentuali vengono
da config/parametri.yaml (tempi.timeout_client_s, D0008; carichi.w2_*), letto con PyYAML.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

QUI = Path(__file__).resolve().parent
PIANO = QUI / "carico.jmx"
PARAMETRI = QUI.parents[1] / "config" / "parametri.yaml"
COLONNE = ["ts_invio", "id", "esito", "tempo_risposta_s"]
HEAP_PREDEFINITO = "512m"


@dataclass(frozen=True)
class Tratto:
    """Un tratto del profilo: da `inizio_s` a `fine_s` (secondi dall'inizio del carico) a `ritmo` ordini/s."""
    inizio_s: float
    fine_s: float
    ritmo: float


def profilo_costante(ritmo: float, durata_s: float) -> list[Tratto]:
    if ritmo <= 0 or durata_s <= 0:
        raise ValueError("ritmo e durata devono essere positivi")
    return [Tratto(0, durata_s, ritmo)]


def profilo_w2(mu1: float, carichi: dict, durata_s: float | None = None) -> list[Tratto]:
    """Base, picco, base (W2), con le percentuali e i tempi di `carichi` (la sezione di parametri.yaml)."""
    if mu1 <= 0:
        raise ValueError("mu1 deve essere positiva")
    base = mu1 * carichi["w2_base_percentuale_mu1"] / 100
    picco = mu1 * carichi["w2_picco_percentuale_mu1"] / 100
    inizio_picco = carichi["w2_inizio_picco_minuto"] * 60
    fine_picco = inizio_picco + carichi["w2_durata_picco_s"]
    if durata_s is None:
        durata_s = inizio_picco + carichi["w2_finestra_costo_min"] * 60
    if durata_s <= fine_picco:
        raise ValueError(f"con W2 la durata deve superare la fine del picco ({fine_picco:g} s)")
    return [Tratto(0, inizio_picco, base), Tratto(inizio_picco, fine_picco, picco), Tratto(fine_picco, durata_s, base)]


def programma(tratti: list[Tratto], coda_s: float) -> str:
    """Il programma degli arrivi per l'Open Model Thread Group.

    Ogni tratto si apre e si chiude con lo stesso `rate(...)`: due `rate` di fila fanno un gradino. Con un `rate`
    solo tra due tratti JMeter passerebbe da un ritmo all'altro in modo graduale lungo tutto il tratto (provato:
    da 10 a 100 ordini/s salirebbe di circa 9 al secondo invece di saltare). Alla fine, una pausa senza arrivi
    lascia finire le richieste in volo: senza, JMeter le interromperebbe e le ultime non avrebbero un esito.
    """
    parti = []
    for t in tratti:
        r = f"rate({t.ritmo:g}/sec)"
        parti += [r, f"even_arrivals({t.fine_s - t.inizio_s:g} sec)", r]
    return " ".join(parti + [f"pause({coda_s:g} sec)"])


def proprieta(url: str, tratti: list[Tratto], timeout_s: float) -> dict[str, str]:
    """Le proprietà che carico.jmx legge (-Jnome=valore) e quelle che dicono a JMeter come salvare i risultati."""
    if timeout_s <= 0:
        raise ValueError("il timeout deve essere positivo")
    parti = urlsplit(url)
    if parti.scheme != "http" or not parti.hostname:
        raise ValueError(f"indirizzo non valido: {url} (serve http://host:porta/percorso)")
    return {
        "host": parti.hostname,
        "porta": str(parti.port or 80),
        "percorso": parti.path or "/",
        "programma": programma(tratti, timeout_s + 1),
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


def descrizione(nome: str, tratti: list[Tratto], mu1: float | None) -> dict:
    """Il contenuto di carico.json: il profilo chiesto, che analysis/ritmo.py confronta con gli invii."""
    return {"profilo": nome, "mu1": mu1, "tratti": [asdict(t) for t in tratti]}


def comando(jmeter: str, cartella: Path, props: dict[str, str]) -> list[str]:
    return [jmeter, "-n", "-t", str(PIANO), "-l", str(cartella / "jmeter.jtl"), "-j", str(cartella / "jmeter.log"),
            *[f"-J{k}={v}" for k, v in props.items()]]


def leggi_parametri() -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere config/parametri.yaml: pip install pyyaml")
    with open(PARAMETRI, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--profilo", choices=["costante", "w2"], default="costante")
    parser.add_argument("--ritmo", type=float, help="ordini al secondo (profilo costante)")
    parser.add_argument("--durata", type=float, help="secondi di carico (obbligatoria per il profilo costante)")
    parser.add_argument("--mu1", type=float, help="capacità di un worker in ordini/s (profilo w2)")
    parser.add_argument("--uscita", required=True, help="client.csv; carico.json, jmeter.jtl e jmeter.log vanno accanto")
    parser.add_argument("--url", default="http://localhost:8080/ordini")
    parser.add_argument("--timeout", type=float, default=None, help="secondi (predefinito: tempi.timeout_client_s)")
    parser.add_argument("--heap", default=HEAP_PREDEFINITO, help="memoria di JMeter, per esempio 512m")
    parser.add_argument("--jmeter", default="jmeter", help="il comando di JMeter")
    a = parser.parse_args()
    parametri = leggi_parametri()
    timeout_s = a.timeout if a.timeout is not None else float(parametri["tempi"]["timeout_client_s"])
    try:
        if a.profilo == "costante":
            if a.ritmo is None or a.durata is None:
                parser.error("il profilo costante vuole --ritmo e --durata")
            tratti = profilo_costante(a.ritmo, a.durata)
        else:
            if a.mu1 is None:
                parser.error("il profilo w2 vuole --mu1, la capacità di un worker")
            tratti = profilo_w2(a.mu1, parametri["carichi"], a.durata)
        props = proprieta(a.url, tratti, timeout_s)
    except ValueError as errore:
        sys.exit(f"errore: {errore}")
    uscita = Path(a.uscita)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    (uscita.parent / "carico.json").write_text(
        json.dumps(descrizione(a.profilo, tratti, a.mu1), indent=2) + "\n", encoding="utf-8")
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
