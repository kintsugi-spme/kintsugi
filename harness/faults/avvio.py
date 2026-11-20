"""Misura a vuoto dei tempi di avvio: quanto ci mette un componente a tornare pronto dopo un SIGKILL.

    python harness/faults/avvio.py --selettore app=api --ripetizioni 5 --evento "Application startup complete"
    python harness/faults/avvio.py --selettore app=db --evento "ready to accept connections"

Senza carico. A ogni ripetizione il pod si ricrea (un secondo kill sullo stesso pod fa scattare il
back-off di Kubernetes: 10, 20, 40 s di attesa prima del riavvio) e si lascia assestare; poi il
SIGKILL parte dal nodo, come in `arresto.py` (D0016), e si legge lo stato del pod ogni 0,1 s:

    riavvio   dal kill al container di nuovo in esecuzione
    pronto    dal kill al pod `Ready` (con la sonda del componente: periodo compreso)
    evento    dal kill alla riga di log scelta con --evento. Il timestamp è quello del log del
              container, sull'orologio del nodo, lo stesso del `date` del kill: non dipende dal
              ritmo del controllo.

Il kill si conta dall'istante `prima` di `arresto.manda_sigkill`: i tempi sono più lunghi del vero
di al massimo l'incertezza di quel comando (0,1-0,3 s) più il periodo del controllo (0,1 s);
`riavvio` e `pronto` hanno in più il tempo di una chiamata a kubectl.
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

import arresto

ATTESA_EVENTO_S = 30  # quanto aspettare la riga di log dopo il «pronto»

RIGA_CON_ORA = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z (.*)$")


def istante_del_log(testo: str, evento: str) -> float | None:
    """Istante (secondi dall'epoca) della prima riga di `kubectl logs --timestamps` che contiene `evento`."""
    for riga in testo.splitlines():
        trovata = RIGA_CON_ORA.match(riga)
        if trovata and evento in trovata.group(3):
            frazione = (trovata.group(2) or "0").ljust(6, "0")[:6]
            ora = datetime.fromisoformat(f"{trovata.group(1)}.{frazione}+00:00")
            return ora.astimezone(timezone.utc).timestamp()
    return None


def stato_del_container(pod: dict, riavvii_prima: int) -> tuple[bool, bool]:
    """(in esecuzione, pronto) dopo un nuovo riavvio: contano solo i riavvii oltre `riavvii_prima`."""
    stato = pod["status"]["containerStatuses"][0]
    ripartito = stato["restartCount"] > riavvii_prima and "running" in stato.get("state", {})
    pronto = any(c["type"] == "Ready" and c["status"] == "True" for c in pod["status"].get("conditions", []))
    return ripartito, ripartito and pronto


def riassunto(valori: list[float]) -> tuple[float, float, float]:
    """Mediana, minimo e massimo."""
    return statistics.median(valori), min(valori), max(valori)


def tabella(nome: str, misure: dict[str, list[float]]) -> str:
    """Righe Markdown, con la virgola decimale come nel diario."""
    def n(x):
        return f"{x:.1f}".replace(".", ",")
    righe = []
    for chiave, valori in misure.items():
        if valori:
            mediana, minimo, massimo = riassunto(valori)
            righe.append(f"| {nome} | {chiave} | {len(valori)} | {n(mediana)} | {n(minimo)} | {n(massimo)} |")
    return "\n".join(righe)


def una_ripetizione(kubectl, selettore: str, evento: str | None, assestamento_s: float, attesa_s: float) -> dict:
    """Ricrea il pod, lo lascia assestare, manda il SIGKILL e misura i tempi."""
    pods = json.loads(kubectl(["get", "pods", "-l", selettore, "-o", "json"]))
    kubectl(["delete", "pod", arresto.scegli_bersaglio(pods).pod, "--wait=true"])
    scadenza = time.monotonic() + attesa_s
    while True:  # aspetta un pod `Ready`, mai riavviato
        pods = json.loads(kubectl(["get", "pods", "-l", selettore, "-o", "json"]))
        pronti = [p for p in pods["items"] if not p["metadata"].get("deletionTimestamp")
                  and stato_del_container(p, -1)[1] and p["status"]["containerStatuses"][0]["restartCount"] == 0]
        if pronti:
            break
        if time.monotonic() > scadenza:
            raise arresto.ErroreGuasto(f"nessun pod {selettore} pronto entro {attesa_s:g} s")
        time.sleep(1)
    time.sleep(assestamento_s)
    pods = json.loads(kubectl(["get", "pods", "-l", selettore, "-o", "json"]))
    bersaglio = arresto.scegli_bersaglio(pods, pronti[0]["metadata"]["name"])
    shell = arresto.ShellNelNodo(bersaglio.nodo)
    try:
        shell.comando("echo pronto")
        pid = arresto.pid_nel_nodo(shell, bersaglio.container_id)
        istanti = arresto.manda_sigkill(shell, pid, bersaglio.container_id)
    finally:
        shell.chiudi()
    t_riavvio = t_pronto = None
    scadenza = time.monotonic() + attesa_s
    while t_pronto is None:
        pod = arresto.stato_del_pod(kubectl, bersaglio.pod)
        ora = time.time()
        in_esecuzione, pronto = stato_del_container(pod, bersaglio.riavvii)
        if in_esecuzione and t_riavvio is None:
            t_riavvio = ora
        if pronto:
            t_pronto = ora
        elif time.monotonic() > scadenza:
            raise arresto.ErroreGuasto(f"il pod {bersaglio.pod} non è tornato pronto entro {attesa_s:g} s")
        time.sleep(0.1)
    risultato = {"pod": bersaglio.pod, "riavvio": t_riavvio - istanti["prima"], "pronto": t_pronto - istanti["prima"]}
    if evento:
        # Il log del container riavviato; l'istante del kill sull'orologio del nodo. La riga può arrivare dopo
        # il «pronto» di Kubernetes (il worker non ha sonde e si collega al broker dopo l'avvio): si aspetta.
        scadenza = time.monotonic() + ATTESA_EVENTO_S
        while True:
            quando = istante_del_log(kubectl(["logs", bersaglio.pod, "--timestamps"]), evento)
            if quando is not None:
                risultato["evento"] = quando - istanti["nodo"]
                break
            if time.monotonic() > scadenza:
                break
            time.sleep(0.5)
    return risultato


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selettore", required=True, help="etichette dei pod, per esempio app=db")
    parser.add_argument("--nome", default=None, help="nome del componente nella tabella (predefinito: il selettore)")
    parser.add_argument("--ripetizioni", type=int, default=5)
    parser.add_argument("--evento", default=None, help="testo della riga di log che dice «pronto» per l'applicazione")
    parser.add_argument("--assestamento", type=float, default=10, help="secondi tra «pronto» e il kill")
    parser.add_argument("--attesa", type=float, default=120, help="secondi prima di dare errore")
    parser.add_argument("--contesto", default="kind-kintsugi")
    argomenti = parser.parse_args()

    def kubectl(parametri: list[str]) -> str:
        return subprocess.run(["kubectl", "--context", argomenti.contesto, *parametri],
                              check=True, capture_output=True, text=True).stdout

    misure: dict[str, list[float]] = {"riavvio": [], "pronto": [], "evento": []}
    try:
        for k in range(1, argomenti.ripetizioni + 1):
            r = una_ripetizione(kubectl, argomenti.selettore, argomenti.evento, argomenti.assestamento, argomenti.attesa)
            for chiave in misure:
                if chiave in r:
                    misure[chiave].append(r[chiave])
            print(f"{k}: " + ", ".join(f"{c} {v:.2f} s" for c, v in r.items() if c != "pod"), file=sys.stderr)
    except (arresto.ErroreGuasto, subprocess.CalledProcessError, FileNotFoundError) as errore:
        sys.exit(f"errore: {getattr(errore, 'stderr', None) or errore}")
    print("| Componente | Misura (s) | Prove | Mediana | Minimo | Massimo |\n|---|---|---|---|---|---|")
    print(tabella(argomenti.nome or argomenti.selettore, misure))


if __name__ == "__main__":
    main()
