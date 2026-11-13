"""Guasto F1: arresto improvviso (SIGKILL) di una copia dell'API, mandato dal nodo che la ospita.

    python harness/faults/arresto.py --cartella data/locale/<run-id>
    python harness/faults/arresto.py --cartella data/locale/<run-id> --selettore app=api --pod api-7694fd4cc7-85655

Il segnale parte dal nodo di kind (`docker exec` nel suo container) e non con `kubectl delete pod`,
che è una terminazione ordinata e non un guasto (D0016). Dentro il container il processo ha PID 1 e
il kernel scarterebbe il SIGKILL; dal nodo il processo ha un altro PID e il segnale arriva.

L'istante del guasto si prende sull'orologio del computer, lo stesso di `client.csv`, così
`analysis/fermo.py` sottrae istanti dello stesso orologio. Un `docker exec` costa da 0,1 a 0,3 s:
per questo la shell nel nodo si apre e si scalda prima, e al momento del guasto riceve solo il
comando di kill. Si scrivono gli istanti subito prima e subito dopo quel comando (la loro
differenza è l'incertezza) e l'istante letto dall'orologio del nodo, che fa da controllo dello
sfasamento tra computer e macchina virtuale di Docker (D0005).

`ts_guasto` è l'istante prima del comando, quindi il limite inferiore: il kill avviene tra
`ts_guasto` e `ts_conferma`. Chi sottrae `ts_guasto` ottiene un fermo più lungo del vero di al
massimo `incertezza_s`, mai più corto. Si è scelto il limite e non il punto medio perché non si sa
quanta parte del ritardo di `docker exec` sta prima del kill e quanta dopo.

Dopo il kill lo script aspetta che il container riparta nello stesso pod (riavviato, non
ricreato) e scrive tutto in `guasto.json` nella cartella del run. Esce con codice 1 se qualcosa
non torna: nessun pod, pod ricreato invece che riavviato, nessun riavvio entro l'attesa.
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


class ErroreGuasto(RuntimeError):
    """Il guasto non si può provocare o non ha avuto l'effetto atteso."""


@dataclass(frozen=True)
class Bersaglio:
    pod: str
    pod_uid: str
    nodo: str
    container: str
    container_id: str
    riavvii: int


def scegli_bersaglio(pods: dict, nome: str | None = None) -> Bersaglio:
    """Il pod da colpire, dall'uscita di `kubectl get pods -o json`.

    Solo i pod con il container in esecuzione e non in chiusura: dopo un rollout il pod vecchio
    risulta ancora «running» per qualche secondo, ma sta già terminando. Con più copie e senza
    `nome` si prende la prima in ordine alfabetico, così la scelta non dipende dall'ordine in
    cui kubectl le elenca.
    """
    candidati = []
    for pod in pods.get("items", []):
        if pod["metadata"].get("deletionTimestamp"):
            continue
        stati = pod.get("status", {}).get("containerStatuses") or []
        if not stati or "running" not in stati[0].get("state", {}):
            continue
        candidati.append((pod, stati[0]))
    if nome is not None:
        candidati = [(p, s) for p, s in candidati if p["metadata"]["name"] == nome]
    if not candidati:
        cosa = f"il pod {nome}" if nome else "nessun pod"
        raise ErroreGuasto(f"{cosa} con il container in esecuzione: niente da colpire")
    pod, stato = min(candidati, key=lambda c: c[0]["metadata"]["name"])
    return Bersaglio(
        pod=pod["metadata"]["name"],
        pod_uid=pod["metadata"]["uid"],
        nodo=pod["spec"]["nodeName"],
        container=stato["name"],
        container_id=stato["containerID"].split("://", 1)[-1],
        riavvii=stato["restartCount"],
    )


class ShellNelNodo:
    """Una shell aperta in anticipo nel container di un nodo di kind, a cui si mandano comandi."""

    def __init__(self, nodo: str):
        self._processo = subprocess.Popen(
            ["docker", "exec", "-i", nodo, "sh"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def comando(self, riga: str) -> str:
        """Esegue `riga` e restituisce la prima riga che stampa (ogni comando ne stampa una)."""
        self._processo.stdin.write(riga + "\n")
        self._processo.stdin.flush()
        risposta = self._processo.stdout.readline()
        if not risposta:
            raise ErroreGuasto(f"la shell nel nodo si è chiusa durante: {riga}")
        return risposta.strip()

    def chiudi(self) -> None:
        """Chiude la shell. Se non esce entro 10 s la si uccide: il kill è già stato mandato
        e un errore qui farebbe perdere gli istanti del guasto, che si scrivono dopo."""
        self._processo.stdin.close()
        try:
            self._processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._processo.kill()
            self._processo.wait()


def pid_nel_nodo(shell, container_id: str) -> int:
    """Il PID del processo principale del container, visto dal nodo (non 1 come dentro il container)."""
    # `echo "$(…)"` stampa sempre una riga, anche se crictl non stampa nulla: la shell non resta in attesa.
    risposta = shell.comando(
        f"echo \"$(crictl inspect --output go-template --template '{{{{.info.pid}}}}' {container_id}"
        " 2>/dev/null)\"")
    pid = int(risposta) if risposta.isdigit() else 0
    if pid <= 1:
        raise ErroreGuasto(f"PID del container {container_id[:12]} non trovato nel nodo ({risposta!r})")
    return pid


def manda_sigkill(shell, pid: int, container_id: str, orologio=time.time) -> dict:
    """Manda SIGKILL a `pid` e restituisce gli istanti del guasto (secondi dall'epoca).

    Il comando ricontrolla che il PID sia ancora del container (dal suo cgroup): tra la ricerca
    del PID e il kill il container potrebbe essere ripartito, e il PID dato a un altro processo.
    """
    riga = (f"grep -q {container_id} /proc/{pid}/cgroup 2>/dev/null"
            f" && t=$(date +%s.%N) && kill -KILL {pid} && echo \"ok $t\" || echo fallito")
    prima = orologio()
    risposta = shell.comando(riga)
    dopo = orologio()
    parti = risposta.split()
    if len(parti) != 2 or parti[0] != "ok":
        raise ErroreGuasto(f"il kill del PID {pid} non è riuscito ({risposta!r})")
    return {"prima": prima, "dopo": dopo, "nodo": float(parti[1])}


def stato_del_pod(kubectl, pod: str) -> dict:
    return json.loads(kubectl(["get", "pod", pod, "-o", "json"]))


def aspetta_riavvio(kubectl, bersaglio: Bersaglio, attesa_s: float, pausa_s: float = 0.5,
                    orologio=time.monotonic, dormi=time.sleep) -> dict:
    """Aspetta che il container riparta nello stesso pod; restituisce il suo nuovo stato."""
    scadenza = orologio() + attesa_s
    while True:
        pod = stato_del_pod(kubectl, bersaglio.pod)
        if pod["metadata"]["uid"] != bersaglio.pod_uid:
            raise ErroreGuasto(f"il pod {bersaglio.pod} è stato ricreato, non riavviato")
        stato = next(s for s in pod["status"]["containerStatuses"] if s["name"] == bersaglio.container)
        if stato["restartCount"] > bersaglio.riavvii and "running" in stato.get("state", {}):
            return stato
        if orologio() >= scadenza:
            # Il caso tipico è il back-off di Kubernetes: dopo crash ravvicinati l'attesa prima
            # del riavvio raddoppia (10, 20, 40, 80 s… fino a 5 minuti).
            raise ErroreGuasto(f"il container non è ripartito entro {attesa_s:g} s (riavvii già "
                               f"avuti: {bersaglio.riavvii}; se sono più di zero è probabilmente il "
                               "back-off di Kubernetes: ricreare il pod prima del run)")
        dormi(pausa_s)


def come_testo(secondi_epoca: float) -> str:
    return datetime.fromtimestamp(secondi_epoca, timezone.utc).isoformat(timespec="milliseconds")


def resoconto_del_kill(bersaglio: Bersaglio, pid: int, istanti: dict) -> dict:
    """La prima parte di guasto.json, scritta subito dopo il kill."""
    return {
        "guasto": "F1",
        "segnale": "SIGKILL",
        "ts_guasto": come_testo(istanti["prima"]),
        "ts_conferma": come_testo(istanti["dopo"]),
        "incertezza_s": round(istanti["dopo"] - istanti["prima"], 4),
        "ts_nodo": come_testo(istanti["nodo"]),
        "pid_nel_nodo": pid,
        **asdict(bersaglio),
    }


def provoca(kubectl, apri_shell, selettore: str, nome: str | None, attesa_s: float, scrivi,
            orologio=time.time) -> dict:
    """Sceglie il pod, manda il SIGKILL dal suo nodo e aspetta il riavvio.

    `scrivi` riceve guasto.json due volte: subito dopo il kill, perché il run ha bisogno
    dell'istante del guasto anche se il riavvio non arriva, e poi con l'esito del riavvio.
    """
    pods = json.loads(kubectl(["get", "pods", "-l", selettore, "-o", "json"]))
    bersaglio = scegli_bersaglio(pods, nome)
    shell = apri_shell(bersaglio.nodo)
    try:
        shell.comando("echo pronto")  # il primo comando di una shell nuova è lento: non va misurato
        pid = pid_nel_nodo(shell, bersaglio.container_id)
        istanti = manda_sigkill(shell, pid, bersaglio.container_id, orologio)
    finally:
        shell.chiudi()
    dati = resoconto_del_kill(bersaglio, pid, istanti)
    scrivi(dati)
    try:
        stato_dopo = aspetta_riavvio(kubectl, bersaglio, attesa_s)
    except ErroreGuasto as errore:
        scrivi({**dati, "riavviato_nello_stesso_pod": False, "errore": str(errore)})
        raise
    dati |= {
        "riavviato_nello_stesso_pod": True,
        "container_id_dopo": stato_dopo["containerID"].split("://", 1)[-1],
        "riavvii_dopo": stato_dopo["restartCount"],
    }
    scrivi(dati)
    return dati


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cartella", type=Path, required=True,
                        help="cartella del run (data/<ambiente>/<run-id>): vi si scrive guasto.json")
    parser.add_argument("--selettore", default="app=api", help="etichette dei pod candidati")
    parser.add_argument("--pod", default=None, help="nome del pod da colpire (predefinito: il primo)")
    parser.add_argument("--contesto", default="kind-kintsugi", help="contesto di kubectl")
    parser.add_argument("--attesa", type=float, default=60,
                        help="secondi di attesa del riavvio prima di dare errore")
    argomenti = parser.parse_args()

    def kubectl(parametri: list[str]) -> str:
        return subprocess.run(["kubectl", "--context", argomenti.contesto, *parametri],
                              check=True, capture_output=True, text=True).stdout

    file = argomenti.cartella / "guasto.json"

    def scrivi(dati: dict) -> None:
        argomenti.cartella.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        risultato = provoca(kubectl, ShellNelNodo, argomenti.selettore, argomenti.pod,
                            argomenti.attesa, scrivi)
    except FileNotFoundError as errore:
        sys.exit(f"errore: programma non trovato: {errore.filename} (servono docker e kubectl)")
    except (ErroreGuasto, subprocess.CalledProcessError, subprocess.TimeoutExpired) as errore:
        nota = f" (istante del guasto in {file})" if file.exists() else ""
        sys.exit(f"errore: {getattr(errore, 'stderr', None) or errore}{nota}")

    print(f"SIGKILL a {risultato['pod']} (nodo {risultato['nodo']}, PID {risultato['pid_nel_nodo']}) "
          f"alle {risultato['ts_guasto']}, incertezza {risultato['incertezza_s'] * 1000:.1f} ms; "
          f"riavviato nello stesso pod (riavvii {risultato['riavvii']} → {risultato['riavvii_dopo']}); "
          f"scritto {file}")


if __name__ == "__main__":
    main()
