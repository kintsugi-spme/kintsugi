"""Guasti F1-F4 e F7: arresto improvviso (SIGKILL) o blocco (SIGSTOP) di un componente, mandato dal suo nodo.

    python harness/faults/arresto.py --cartella data/locale/<run-id>                 # F1, una copia dell'API
    python harness/faults/arresto.py --cartella data/locale/<run-id> --guasto F2     # tutti i worker (V3)
    python harness/faults/arresto.py --cartella data/locale/<run-id> --guasto F3     # il broker (V3)
    python harness/faults/arresto.py --cartella data/locale/<run-id> --guasto F4     # il database (V1-V3)
    python harness/faults/arresto.py --cartella data/locale/<run-id> --guasto F7     # blocca una copia dell'API (V2)
    python harness/faults/arresto.py --cartella data/locale/<run-id> --pod api-7694fd4cc7-85655

Ogni guasto (tabella GUASTI) dice quali pod colpire e quale container deve trovarci: il kill va al processo
principale di quel container (PostgreSQL, RabbitMQ, l'API o un worker). Toxiproxy non è mai un bersaglio:
ha un altro selettore e un altro container (#93). V4 (database replicato) è nella #129.

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

Con più bersagli (F2: tutti i worker) i PID si cercano tutti prima e ogni nodo riceve un solo comando, che
li uccide insieme. `ts_guasto` è prima del primo comando, `ts_conferma` dopo l'ultimo: l'incertezza comprende
la distanza tra il primo e l'ultimo kill. Sull'orologio del nodo, `ts_nodo` è prima del primo kill e
`ts_nodo_ultimo` dopo l'ultimo.

Dopo il kill lo script aspetta che ogni container riparta nello stesso pod (riavviato, non
ricreato) e scrive tutto in `guasto.json` nella cartella del run. Esce con codice 1 se qualcosa
non torna: nessun pod, pod ricreato invece che riavviato, nessun riavvio entro l'attesa.

Il guasto F7 manda SIGSTOP: il processo resta in vita ma non risponde, e Kubernetes se ne accorge solo dalle
sonde (D0007). Lo script registra quando la copia esce dagli endpoint del Service (`ts_fuori_dal_service`, la
readiness l'ha esclusa: lì finisce il fermo di V2) e quando la liveness l'ha fatta ripartire. Il riavvio
arriva tardi: Kubernetes manda prima SIGTERM, che un processo fermo non riceve, e il SIGKILL solo dopo il
tempo di chiusura del pod (30 s). Gli istanti dopo il guasto si leggono con kubectl ogni 0,2 s: sono in
ritardo sul vero di al massimo una lettura (circa 0,3 s).
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
class Guasto:
    """Un guasto del capitolo «Guasti»: quali pod colpire, quale container deve esserci, con quale segnale."""
    nome: str
    selettore: str
    container: str
    tutti: bool  # tutti i pod del selettore (F2) o uno solo
    descrizione: str
    segnale: str = "KILL"
    service: str | None = None  # con un blocco: il Service da cui la copia deve uscire


GUASTI = {g.nome: g for g in [
    Guasto("F1", "app=api", "api", False, "una copia dell'API"),
    Guasto("F2", "app=worker", "worker", True, "tutti i worker"),
    Guasto("F3", "app=coda", "rabbitmq", False, "il broker"),
    Guasto("F4", "app=db", "postgres", False, "il database"),
    Guasto("F7", "app=api", "api", False, "blocca una copia dell'API", segnale="STOP", service="api"),
]}


@dataclass(frozen=True)
class Bersaglio:
    pod: str
    pod_uid: str
    nodo: str
    container: str
    container_id: str
    riavvii: int


def _stato(pod: dict, container: str | None) -> dict | None:
    stati = pod.get("status", {}).get("containerStatuses") or []
    if container is None:
        return stati[0] if stati else None
    return next((s for s in stati if s["name"] == container), None)


def _bersaglio(pod: dict, stato: dict) -> Bersaglio:
    return Bersaglio(
        pod=pod["metadata"]["name"],
        pod_uid=pod["metadata"]["uid"],
        nodo=pod["spec"]["nodeName"],
        container=stato["name"],
        container_id=stato["containerID"].split("://", 1)[-1],
        riavvii=stato["restartCount"],
    )


def scegli_bersagli(pods: dict, container: str | None = None, nome: str | None = None,
                    tutti: bool = False) -> list[Bersaglio]:
    """I pod da colpire, dall'uscita di `kubectl get pods -o json`, in ordine alfabetico.

    Contano solo i pod non in chiusura: dopo un rollout il pod vecchio risulta ancora «running» per qualche
    secondo, ma sta già terminando. Ogni pod deve avere il container `container` (se dato) in esecuzione.
    Con `tutti` si colpiscono tutti, e un pod con il container fermo è un errore: non sarebbero più tutti.
    Altrimenti si prende il pod `nome` o il primo in ordine alfabetico, così la scelta non dipende
    dall'ordine in cui kubectl li elenca.
    """
    vivi = sorted((p for p in pods.get("items", []) if not p["metadata"].get("deletionTimestamp")),
                  key=lambda p: p["metadata"]["name"])
    if nome is not None:
        vivi = [p for p in vivi if p["metadata"]["name"] == nome]
    candidati, fermi = [], []
    for pod in vivi:
        stato = _stato(pod, container)
        if stato is not None and "running" in stato.get("state", {}):
            candidati.append(_bersaglio(pod, stato))
        else:
            fermi.append(pod["metadata"]["name"])
    if tutti and fermi:
        raise ErroreGuasto(f"non tutti i pod sono in esecuzione ({', '.join(fermi)}): non si colpirebbero tutti")
    if not candidati:
        cosa = f"il pod {nome}" if nome else "nessun pod"
        dove = f" con il container {container}" if container else " con il container"
        raise ErroreGuasto(f"{cosa}{dove} in esecuzione: niente da colpire")
    return candidati if tutti else candidati[:1]


def scegli_bersaglio(pods: dict, nome: str | None = None) -> Bersaglio:
    """Un pod solo, il primo o quello di nome `nome`, con il suo primo container (per avvio.py)."""
    return scegli_bersagli(pods, nome=nome)[0]


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


def nome_del_processo(shell, pid: int) -> str:
    """Il nome del programma con quel PID (per esempio `postgres`, `beam.smp`): finisce in guasto.json."""
    return shell.comando(f"echo \"$(cat /proc/{pid}/comm 2>/dev/null)\"")


def manda_segnale(shell, colpi: list[tuple[int, str]], segnale: str = "KILL", orologio=time.time) -> dict:
    """Manda `segnale` a tutti i PID di `colpi` (coppie PID, container) con un solo comando nel nodo.

    Restituisce gli istanti (secondi dall'epoca): `prima` e `dopo` il comando sul computer, `nodo` prima
    del primo kill e `nodo_fine` dopo l'ultimo, sull'orologio del nodo. Il comando ricontrolla che ogni PID
    sia ancora del suo container (dal cgroup): tra la ricerca del PID e il kill il container potrebbe essere
    ripartito, e il PID dato a un altro processo. Se un controllo fallisce, non parte nessun kill.
    """
    controlli = " && ".join(f"grep -q {cid} /proc/{pid}/cgroup 2>/dev/null" for pid, cid in colpi)
    pids = " ".join(str(pid) for pid, _ in colpi)
    riga = (f"{controlli} && t=$(date +%s.%N) && kill -{segnale} {pids}"
            f" && echo \"ok $t $(date +%s.%N)\" || echo fallito")
    prima = orologio()
    risposta = shell.comando(riga)
    dopo = orologio()
    parti = risposta.split()
    if len(parti) != 3 or parti[0] != "ok":
        raise ErroreGuasto(f"il segnale {segnale} ai PID {pids} non è riuscito ({risposta!r})")
    return {"prima": prima, "dopo": dopo, "nodo": float(parti[1]), "nodo_fine": float(parti[2])}


def stato_del_pod(kubectl, pod: str) -> dict:
    return json.loads(kubectl(["get", "pod", pod, "-o", "json"]))


def fuori_dal_service(slices: dict, pod: str) -> bool:
    """Vero se nessun endpoint pronto del Service è `pod`, da `kubectl get endpointslices -o json`."""
    return not any(e.get("targetRef", {}).get("name") == pod and e.get("conditions", {}).get("ready")
                   for s in slices.get("items", []) for e in s.get("endpoints") or [])


def aspetta_fuori_dal_service(kubectl, service: str, pod: str, attesa_s: float, pausa_s: float = 0.2,
                              orologio=time.monotonic, ora=time.time, dormi=time.sleep) -> float:
    """Aspetta che la readiness escluda `pod` dal Service; restituisce l'istante (orologio del computer)."""
    scadenza = orologio() + attesa_s
    while True:
        slices = json.loads(kubectl(["get", "endpointslices", "-l", f"kubernetes.io/service-name={service}",
                                     "-o", "json"]))
        if fuori_dal_service(slices, pod):
            return ora()
        if orologio() >= scadenza:
            raise ErroreGuasto(f"{pod} è ancora tra gli endpoint pronti del Service {service} dopo {attesa_s:g} s")
        dormi(pausa_s)


def aspetta_riavvio(kubectl, bersaglio: Bersaglio, attesa_s: float, pausa_s: float = 0.5,
                    orologio=time.monotonic, dormi=time.sleep) -> dict:
    """Aspetta che il container riparta nello stesso pod; restituisce il suo nuovo stato."""
    scadenza = orologio() + attesa_s
    while True:
        pod = stato_del_pod(kubectl, bersaglio.pod)
        if pod["metadata"]["uid"] != bersaglio.pod_uid:
            raise ErroreGuasto(f"il pod {bersaglio.pod} è stato ricreato, non riavviato")
        stato = _stato(pod, bersaglio.container)
        if stato["restartCount"] > bersaglio.riavvii and "running" in stato.get("state", {}):
            return stato
        if orologio() >= scadenza:
            # Il caso tipico è il back-off di Kubernetes: dopo crash ravvicinati l'attesa prima
            # del riavvio raddoppia (10, 20, 40, 80 s… fino a 5 minuti).
            raise ErroreGuasto(f"il container di {bersaglio.pod} non è ripartito entro {attesa_s:g} s (riavvii "
                               f"già avuti: {bersaglio.riavvii}; se sono più di zero è probabilmente il "
                               "back-off di Kubernetes: ricreare il pod prima del run)")
        dormi(pausa_s)


def come_testo(secondi_epoca: float) -> str:
    return datetime.fromtimestamp(secondi_epoca, timezone.utc).isoformat(timespec="milliseconds")


def resoconto_del_kill(guasto: Guasto, bersagli: list[dict], istanti: list[dict]) -> dict:
    """La prima parte di guasto.json, scritta subito dopo il kill. `istanti`: uno per comando, in ordine."""
    prima, dopo = istanti[0]["prima"], istanti[-1]["dopo"]
    return {
        "guasto": guasto.nome,
        "segnale": f"SIG{guasto.segnale}",
        "ts_guasto": come_testo(prima),
        "ts_conferma": come_testo(dopo),
        "incertezza_s": round(dopo - prima, 4),
        "ts_nodo": come_testo(min(i["nodo"] for i in istanti)),
        "ts_nodo_ultimo": come_testo(max(i["nodo_fine"] for i in istanti)),
        "bersagli": bersagli,
    }


def provoca(kubectl, apri_shell, guasto: Guasto, nome: str | None, attesa_s: float, scrivi,
            orologio=time.time, ora=time.time, aspetta_servizio=aspetta_fuori_dal_service) -> dict:
    """Sceglie i pod, manda il segnale dai loro nodi e aspetta i riavvii.

    Prima del primo kill si apre e si scalda una shell per nodo e si cercano tutti i PID: al momento del
    guasto parte solo un comando per nodo. `scrivi` riceve guasto.json due volte: subito dopo il kill,
    perché il run ha bisogno dell'istante del guasto anche se il riavvio non arriva, e poi con l'esito.
    `orologio` dà gli istanti del kill, `ora` quelli osservati dopo (uscita dal Service, riavvio).
    """
    pods = json.loads(kubectl(["get", "pods", "-l", guasto.selettore, "-o", "json"]))
    bersagli = scegli_bersagli(pods, guasto.container, nome, guasto.tutti)
    nodi = sorted({b.nodo for b in bersagli})
    shell = {}
    try:
        for n in nodi:
            shell[n] = apri_shell(n)
            shell[n].comando("echo pronto")  # il primo comando di una shell nuova è lento: non va misurato
        righe = []
        for b in bersagli:
            pid = pid_nel_nodo(shell[b.nodo], b.container_id)
            righe.append({**asdict(b), "pid_nel_nodo": pid, "processo": nome_del_processo(shell[b.nodo], pid)})
        istanti = [manda_segnale(shell[n], [(r["pid_nel_nodo"], r["container_id"]) for r in righe if r["nodo"] == n],
                                 guasto.segnale, orologio) for n in nodi]
    finally:
        for s in shell.values():
            s.chiudi()
    dati = resoconto_del_kill(guasto, righe, istanti)
    scrivi(dati)
    try:
        if guasto.service:
            fuori = aspetta_servizio(kubectl, guasto.service, bersagli[0].pod, attesa_s)
            dati |= {"ts_fuori_dal_service": come_testo(fuori),
                     "fuori_dal_service_dopo_s": round(fuori - istanti[0]["prima"], 3)}
            scrivi(dati)
        for b, riga in zip(bersagli, righe):
            stato_dopo = aspetta_riavvio(kubectl, b, attesa_s)
            riga |= {"container_id_dopo": stato_dopo["containerID"].split("://", 1)[-1],
                     "riavvii_dopo": stato_dopo["restartCount"],
                     "riavvio_visto_dopo_s": round(ora() - istanti[0]["prima"], 3)}
    except ErroreGuasto as errore:
        scrivi({**dati, "riavviati_nello_stesso_pod": False, "errore": str(errore)})
        raise
    dati["riavviati_nello_stesso_pod"] = True
    scrivi(dati)
    return dati


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cartella", type=Path, required=True,
                        help="cartella del run (data/<ambiente>/<run-id>): vi si scrive guasto.json")
    parser.add_argument("--guasto", choices=sorted(GUASTI), default="F1",
                        help="; ".join(f"{g.nome}: {g.descrizione}" for g in GUASTI.values()))
    parser.add_argument("--pod", default=None, help="nome del pod da colpire (predefinito: il primo; non con F2)")
    parser.add_argument("--contesto", default="kind-kintsugi", help="contesto di kubectl")
    parser.add_argument("--attesa", type=float, default=120,
                        help="secondi di attesa del riavvio di ogni container prima di dare errore")
    argomenti = parser.parse_args()
    guasto = GUASTI[argomenti.guasto]
    if guasto.tutti and argomenti.pod:
        parser.error(f"il guasto {guasto.nome} colpisce {guasto.descrizione}: --pod non si usa")

    def kubectl(parametri: list[str]) -> str:
        return subprocess.run(["kubectl", "--context", argomenti.contesto, *parametri],
                              check=True, capture_output=True, text=True).stdout

    file = argomenti.cartella / "guasto.json"

    def scrivi(dati: dict) -> None:
        argomenti.cartella.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        risultato = provoca(kubectl, ShellNelNodo, guasto, argomenti.pod, argomenti.attesa, scrivi)
    except FileNotFoundError as errore:
        sys.exit(f"errore: programma non trovato: {errore.filename} (servono docker e kubectl)")
    except (ErroreGuasto, subprocess.CalledProcessError, subprocess.TimeoutExpired) as errore:
        nota = f" (istante del guasto in {file})" if file.exists() else ""
        sys.exit(f"errore: {getattr(errore, 'stderr', None) or errore}{nota}")

    colpiti = ", ".join(f"{b['pod']} ({b['processo']}, PID {b['pid_nel_nodo']} su {b['nodo']}, "
                        f"riavvii {b['riavvii']} → {b['riavvii_dopo']})" for b in risultato["bersagli"])
    fuori = (f"fuori dal Service dopo {risultato['fuori_dal_service_dopo_s']:.1f} s; "
             if "fuori_dal_service_dopo_s" in risultato else "")
    print(f"{risultato['guasto']}, {risultato['segnale']} a {colpiti} alle {risultato['ts_guasto']}, incertezza "
          f"{risultato['incertezza_s'] * 1000:.1f} ms; {fuori}riavviati nello stesso pod; scritto {file}")


if __name__ == "__main__":
    main()
