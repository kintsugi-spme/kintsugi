"""Reset prima di ogni run (issue #121): riporta V1, V2 o V3 allo stato iniziale e lo verifica.

    python harness/reset/reset.py --versione v2
    python harness/reset/reset.py --versione v3 --cartella data/locale/<run-id>

Dalla cartella deploy/k8s:  make reset VERSIONE=v2

Il capitolo «Protocollo di misura» chiede che ogni run parta dallo stesso stato e che, se una condizione non è
soddisfatta, il run non parta. Passi, in quest'ordine (ogni ordine ha un motivo, scritto accanto):

  1. spegne l'API e i worker: nessuno scrive più nel database né legge dalla coda mentre si pulisce, e i pod
     vecchi spariscono (un pod in chiusura riceve ancora richieste dal Service: limite del 22/11);
  2. ricrea il database e il broker e li aspetta pronti: un'API partita prima del database resta a 503 per
     circa 2 minuti (limite del 15/11);
  3. svuota le tabelle `ordini` e `duplicati` e le code `ordini` e `ordini.falliti`;
  4. ricrea Toxiproxy, dopo il database: toglie ogni ritardo (#93) e non resta appeso su un database
     cancellato (limite del 24/11);
  5. riaccende l'API e i worker, che partono con tutto il resto già pronto: pod nuovi, con 0 riavvii (il ritardo
     dei riavvii di Kubernetes cresce a ogni crash: limite del 12/11) e collocati come D0006 dice (la
     `nodeAffinity` preferita non rimette a posto un pod già ripartito altrove: limite del 15/11);
  6. controlla tutto e scrive il motivo di ogni controllo fallito.

Esce con codice 0 solo se tutti i controlli passano. La durata si stampa e, con --cartella, si scrive in
`reset.json` accanto agli altri file del run. Tutti i comandi usano il contesto `kind-kintsugi`: non toccano altri
cluster. Per ora vale per V1, V2 e V3; i controlli di V4 e V5 si aggiungono con le issue #129 e #130 in
`versione_attesa` e in `controlli_versione`.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PARAMETRI = Path(__file__).resolve().parents[2] / "config" / "parametri.yaml"
RUOLO = "kintsugi/ruolo"
SELETTORE_POD = "app in (api,worker,db,coda,toxiproxy)"
CODE = ("ordini", "ordini.falliti")
ATTESA_S = 180  # per ogni passo; il database e il broker, a freddo, possono scaricare un'immagine


class ErroreReset(RuntimeError):
    """Un passo del reset non si può fare, o non finisce in tempo."""


@dataclass(frozen=True)
class Versione:
    nome: str
    api: int  # copie dell'API
    worker: int  # worker (0: la versione non ha la coda)

    @property
    def dati(self) -> list[str]:
        """I Deployment che stanno sul nodo `dati`, nell'ordine in cui si ricreano."""
        return ["db", "coda"] if self.worker else ["db"]

    @property
    def calcolo(self) -> dict[str, int]:
        """I Deployment che stanno sul nodo `calcolo`, con il numero di copie."""
        return {"api": self.api, **({"worker": self.worker} if self.worker else {})}

    def attesi(self) -> dict[str, tuple[int, str]]:
        """Per ogni Deployment: quante copie e su quale ruolo di nodo (D0006)."""
        attesi = {d: (1, "dati") for d in [*self.dati, "toxiproxy"]}
        attesi.update({d: (n, "calcolo") for d, n in self.calcolo.items()})
        return attesi


def versione_attesa(nome: str, parametri: dict) -> Versione:
    """Come deve essere la versione dopo il reset, da config/parametri.yaml."""
    copie = parametri["versioni"]["copie_api"]
    if nome == "v1":
        return Versione("v1", 1, 0)
    if nome == "v2":
        return Versione("v2", copie, 0)
    if nome == "v3":
        return Versione("v3", copie, parametri["versioni"]["worker_v3"])
    raise ErroreReset(f"versione {nome}: il reset di V4 e V5 arriva con le issue #129 e #130")


def pronto(pod: dict) -> bool:
    return any(c["type"] == "Ready" and c["status"] == "True" for c in pod.get("status", {}).get("conditions", []))


def in_chiusura(pod: dict) -> bool:
    return bool(pod["metadata"].get("deletionTimestamp"))


def controlla_pod(pods: dict, nodi: dict, versione: Versione, nomi_prima: set[str]) -> list[str]:
    """I controlli sui pod, dall'uscita di `kubectl get pods -o json` e `get nodes -o json`. Un problema per riga."""
    ruolo_del_nodo = {n["metadata"]["name"]: n["metadata"].get("labels", {}).get(RUOLO) for n in nodi["items"]}
    per_componente: dict[str, list[dict]] = {}
    problemi = []
    for pod in pods["items"]:
        nome = pod["metadata"]["name"]
        app = pod["metadata"].get("labels", {}).get("app", "?")
        per_componente.setdefault(app, []).append(pod)
        if in_chiusura(pod):
            problemi.append(f"{nome} è ancora in chiusura")
            continue
        if nome in nomi_prima:
            problemi.append(f"{nome} è un pod di prima del reset: non è stato ricreato")
        riavvii = sum(c["restartCount"] for c in pod.get("status", {}).get("containerStatuses", []))
        if riavvii:
            problemi.append(f"{nome} ha {riavvii} riavvii, ne servono 0")
        if not pronto(pod):
            problemi.append(f"{nome} non è pronto")
        atteso = versione.attesi().get(app)
        if atteso:
            nodo = pod["spec"].get("nodeName")
            if ruolo_del_nodo.get(nodo) != atteso[1]:
                problemi.append(f"{nome} sta sul nodo {nodo} (ruolo {ruolo_del_nodo.get(nodo)}), D0006 lo vuole su {atteso[1]}")
    for app, (copie, _) in versione.attesi().items():
        n = sum(1 for p in per_componente.get(app, []) if not in_chiusura(p))
        if n != copie:
            problemi.append(f"{app}: {n} copie, ne servono {copie}")
    for app in per_componente:
        if app not in versione.attesi():
            problemi.append(f"{app}: c'è un componente che questa versione non ha")
    return problemi


def messaggi_per_coda(uscita: str) -> dict[str, int]:
    """`rabbitmqctl list_queues name messages`: righe «nome numero», le altre (titoli, avvisi) si ignorano."""
    code = {}
    for riga in uscita.splitlines():
        campi = riga.split()
        if len(campi) == 2 and campi[1].isdigit():
            code[campi[0]] = int(campi[1])
    return code


def toxic_presenti(proxy: dict) -> list[str]:
    """I nomi dei «toxic» (ritardi e altri guasti) attivi, da `GET /proxies/postgres` di Toxiproxy."""
    return [t["name"] for t in proxy.get("toxics", [])]


def aspetta(condizione, cosa: str, attesa_s: float = ATTESA_S) -> None:
    scadenza = time.monotonic() + attesa_s
    while not condizione():
        if time.monotonic() > scadenza:
            raise ErroreReset(f"{cosa}: non è successo entro {attesa_s:g} s")
        time.sleep(1)


class Reset:
    """Un reset: tiene il `kubectl` (una funzione che prende la lista di argomenti e dà l'uscita)."""

    def __init__(self, kubectl, versione: Versione, ingresso: str | None = None, risponde=None):
        self.k = kubectl
        self.v = versione
        self.ingresso = ingresso
        self.risponde = risponde or risponde_http

    def pods(self) -> dict:
        return json.loads(self.k(["get", "pods", "-l", SELETTORE_POD, "-o", "json"]))

    def spenti(self, selettore: str) -> bool:
        return not json.loads(self.k(["get", "pods", "-l", selettore, "-o", "json"]))["items"]

    def senza_pod_in_chiusura(self) -> bool:
        return not any(in_chiusura(p) for p in self.pods()["items"])

    def spegni_calcolo(self) -> None:
        self.k(["scale", "--replicas=0", *[f"deployment/{d}" for d in self.v.calcolo]])
        aspetta(lambda: self.spenti("app in (api,worker)"), "i pod dell'API e dei worker non spariscono")

    def ricrea(self, deployment: list[str]) -> None:
        self.k(["rollout", "restart", *[f"deployment/{d}" for d in deployment]])
        for d in deployment:
            self.k(["rollout", "status", f"deployment/{d}", f"--timeout={ATTESA_S}s"])
        aspetta(self.senza_pod_in_chiusura, f"i pod vecchi di {', '.join(deployment)} non spariscono")

    def pulisci(self) -> None:
        self.k(["exec", "deploy/db", "--", "psql", "-U", "kintsugi", "-d", "kintsugi", "-v", "ON_ERROR_STOP=1",
                "-c", "TRUNCATE ordini, duplicati"])
        if self.v.worker:
            presenti = messaggi_per_coda(self.k(["exec", "deploy/coda", "--", "rabbitmqctl", "list_queues", "name", "messages"]))
            for coda in CODE:
                if coda in presenti:
                    self.k(["exec", "deploy/coda", "--", "rabbitmqctl", "purge_queue", coda])

    def accendi_calcolo(self) -> None:
        for d, copie in self.v.calcolo.items():
            self.k(["scale", f"--replicas={copie}", f"deployment/{d}"])
        for d in self.v.calcolo:
            self.k(["rollout", "status", f"deployment/{d}", f"--timeout={ATTESA_S}s"])
        if self.ingresso:
            # Il Service ci mette un attimo a conoscere i pod nuovi: con una sola copia (V1) i primi ordini si
            # perderebbero. Si aspetta che l'ingresso risponda tre volte di fila.
            consecutive = []

            def risponde_di_fila() -> bool:
                consecutive.append(self.risponde(self.ingresso))
                del consecutive[:-3]
                return len(consecutive) == 3 and all(consecutive)

            aspetta(risponde_di_fila, f"l'ingresso {self.ingresso} non risponde", 60)

    def controlli(self, nomi_prima: set[str]) -> list[str]:
        problemi = controlla_pod(self.pods(), json.loads(self.k(["get", "nodes", "-o", "json"])), self.v, nomi_prima)
        for tabella in ("ordini", "duplicati"):
            righe = self.k(["exec", "deploy/db", "--", "psql", "-U", "kintsugi", "-d", "kintsugi", "-tAc",
                            f"select count(*) from {tabella}"]).strip()
            if righe != "0":
                problemi.append(f"la tabella {tabella} ha {righe} righe, ne servono 0")
        if self.v.worker:
            presenti = messaggi_per_coda(self.k(["exec", "deploy/coda", "--", "rabbitmqctl", "list_queues", "name", "messages"]))
            for coda in CODE:
                if presenti.get(coda, 0) != 0:
                    problemi.append(f"la coda {coda} ha {presenti[coda]} messaggi, ne servono 0")
        proxy = json.loads(self.k(["get", "--raw", "/api/v1/namespaces/default/services/toxiproxy:api/proxy/proxies/postgres"]))
        if toxic_presenti(proxy):
            problemi.append(f"Toxiproxy ha ancora dei toxic: {', '.join(toxic_presenti(proxy))}")
        return problemi

    def esegui(self) -> dict:
        """Il reset intero. Alza ErroreReset se un passo non si può fare; altrimenti dà i controlli falliti."""
        inizio = time.time()
        nomi_prima = {p["metadata"]["name"] for p in self.pods()["items"]}
        self.spegni_calcolo()
        self.ricrea(self.v.dati)
        self.pulisci()
        self.ricrea(["toxiproxy"])
        self.accendi_calcolo()
        problemi = self.controlli(nomi_prima)
        fine = time.time()
        return {"versione": self.v.nome, "ts_inizio": inizio, "ts_fine": fine, "durata_s": round(fine - inizio, 1),
                "problemi": problemi}


def risponde_http(indirizzo: str) -> bool:
    try:
        with urllib.request.urlopen(indirizzo.rstrip("/") + "/readyz", timeout=2) as risposta:
            return risposta.status == 200
    except OSError:
        return False


def leggi_parametri() -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere le copie da config/parametri.yaml: pip install pyyaml")
    with open(PARAMETRI, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--versione", required=True, choices=["v1", "v2", "v3"])
    parser.add_argument("--cartella", default=None, help="cartella del run: ci si scrive reset.json")
    parser.add_argument("--ingresso", default="http://localhost:8080", help="indirizzo dell'API dal computer")
    parser.add_argument("--contesto", default="kind-kintsugi")
    argomenti = parser.parse_args()
    if not argomenti.contesto.startswith("kind-"):
        sys.exit(f"errore: il contesto {argomenti.contesto} non è un cluster kind: il reset cancella i dati")

    def kubectl(parametri: list[str]) -> str:
        return subprocess.run(["kubectl", "--context", argomenti.contesto, *parametri],
                              check=True, capture_output=True, text=True).stdout

    try:
        risultato = Reset(kubectl, versione_attesa(argomenti.versione, leggi_parametri()), argomenti.ingresso).esegui()
    except (ErroreReset, subprocess.CalledProcessError, FileNotFoundError) as errore:
        sys.exit(f"errore: {getattr(errore, 'stderr', None) or errore}")
    if argomenti.cartella:
        cartella = Path(argomenti.cartella)
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / "reset.json").write_text(json.dumps(risultato, indent=2) + "\n", encoding="utf-8")
    for problema in risultato["problemi"]:
        print(f"FALLITO  {problema}", file=sys.stderr)
    stato = "completato" if not risultato["problemi"] else "NON riuscito"
    print(f"reset {risultato['versione']} {stato} in {risultato['durata_s']:g} s")
    sys.exit(1 if risultato["problemi"] else 0)


if __name__ == "__main__":
    main()
