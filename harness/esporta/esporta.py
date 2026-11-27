"""Esportazione di fine run (issue #123): salva nella cartella del run i file di data/README.md che stanno nel cluster.

    python harness/esporta/esporta.py data/locale/<run-id>
    python harness/esporta/esporta.py data/locale/<run-id> --da 2026-11-27T09:00:00+00:00 --a 2026-11-27T09:12:00+00:00

Nell'ordine, che conta:

  1. `db.csv`, `falliti.csv` e `duplicati.csv`, **prima della rielaborazione dei falliti**: se si esporta dopo,
     gli ordini della coda dei falliti sono già nel database e risultano «completato in tempo», senza anomalie
     e con un run che sembra buono (avvertenza di data/README.md). `falliti.csv` si legge senza consumare la
     coda; vale per V3 (e V5), in V1 e V2 ha solo l'intestazione.
  2. La rielaborazione degli ordini nella coda dei falliti (D0002: «a fine esperimento vengono rielaborati e
     contati a parte»): tornano nella coda `ordini`, i worker li riprovano, e quanti ne sono stati salvati si
     scrive in `esportazione.json`. Si salta con --senza-rielaborazione.
  3. `events.csv`: gli eventi di Kubernetes del run. Kubernetes li tiene per poco tempo, quindi si salvano
     subito, non a fine campagna.
  4. `prometheus.csv`: le serie del run lette dall'API di Prometheus (#114, D0019), una riga per misura.
  5. `analysis/categorie.py` e il suo controllo di coerenza: se esce con codice 1 il run va esaminato.

L'intervallo del run (per eventi e serie) è quello di `client.csv`, con 5 minuti prima (il reset e i pod
ricreati) e 1 minuto dopo; si cambia con --da e --a. Si scrive anche `esportazione.json`, con i secondi di ogni
passo: il tempo dell'esportazione entra nella durata di ogni run.

Il database si legge direttamente, non da Toxiproxy: il guasto F5 non rallenta l'esportazione. In V4 (database
replicato) si legge dal primario di CloudNativePG di quel momento, anche dopo un failover: scritto, ma non
ancora provato su V4 (si prova a mano o nella #129). Tutti i comandi usano il contesto `kind-kintsugi`.
Esce con codice 1 se un passo non riesce o categorie.py trova un'anomalia.
"""

import argparse
import csv
import io
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
CATEGORIE = RADICE / "analysis" / "categorie.py"
PARAMETRI = RADICE / "config" / "parametri.yaml"

COLONNE_DB = ["id", "ts_ricezione", "ts_scrittura"]
COLONNE_FALLITI = ["id", "ts_ricezione"]
COLONNE_DUPLICATI = ["id"]
COLONNE_EVENTI = ["ts", "tipo", "motivo", "oggetto", "messaggio", "volte"]
COLONNE_PROMETHEUS = ["ts", "metrica", "etichette", "valore"]
JOB_PROMETHEUS = ("rabbitmq", "cadvisor", "kube-state-metrics")
PROXY_PROMETHEUS = "/api/v1/namespaces/osservabilita/services/prometheus:web/proxy"
MARGINE_PRIMA_S, MARGINE_DOPO_S = 300, 60
ATTESA_RIELABORAZIONE_S = 90


class ErroreEsportazione(RuntimeError):
    """Un passo dell'esportazione non è riuscito."""


# Gira dentro un pod con l'immagine dell'app (che ha aio_pika e BROKER_URL), passato da standard input.
# «leggi»: legge tutti i messaggi della coda dei falliti senza consumarli (a fine script tornano in coda);
# «sposta»: li rimette nella coda `ordini`. Stampa i corpi dei messaggi in una riga JSON.
SCRIPT_CODA = '''
import asyncio, json, os, sys
import aio_pika

async def main(modo):
    connessione = await aio_pika.connect_robust(os.environ["BROKER_URL"])
    async with connessione:
        canale = await connessione.channel()
        falliti = await canale.declare_queue("ordini.falliti", durable=True, passive=True)
        letti = []
        while True:
            messaggio = await falliti.get(fail=False, no_ack=False)
            if messaggio is None:
                break
            letti.append(messaggio)
        for messaggio in letti:
            if modo == "sposta":
                await canale.default_exchange.publish(
                    aio_pika.Message(body=messaggio.body, content_type="application/json",
                                     delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key="ordini")
                await messaggio.ack()
            else:
                await messaggio.nack(requeue=True)
        print(json.dumps([m.body.decode("utf-8", "replace") for m in letti]))

asyncio.run(main(sys.argv[1]))
'''


def istante(testo: str) -> datetime:
    quando = datetime.fromisoformat(testo.strip().replace("Z", "+00:00"))
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def come_testo(quando: datetime) -> str:
    return quando.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def scrivi_csv(percorso: Path, colonne: list[str], righe) -> int:
    """Scrive intestazione e righe; restituisce quante righe."""
    righe = list(righe)
    with open(percorso, "w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(colonne)
        scrittore.writerows(righe)
    return len(righe)


def csv_di_psql(uscita: str, colonne: list[str]) -> list[list[str]]:
    """Le righe dell'uscita di `psql --csv` (la prima è l'intestazione, che deve essere quella attesa)."""
    righe = list(csv.reader(io.StringIO(uscita)))
    if not righe or righe[0] != colonne:
        raise ErroreEsportazione(f"psql ha dato un'intestazione inattesa: {righe[:1]} invece di {colonne}")
    return righe[1:]


def messaggi_falliti(corpi: list[str]) -> tuple[list[list[str]], int]:
    """Da corpi dei messaggi della coda dei falliti a righe (id, ts_ricezione); gli illeggibili si contano a parte."""
    righe, illeggibili = [], 0
    for corpo in corpi:
        try:
            dati = json.loads(corpo)
            righe.append([str(dati["id"]).strip().lower(), str(dati["ts_ricezione"])])
        except (ValueError, KeyError, TypeError):
            illeggibili += 1
    return righe, illeggibili


def righe_eventi(eventi: dict, pods: dict, da: datetime, a: datetime) -> list[list[str]]:
    """Gli eventi di Kubernetes e i passaggi a «pronto» dei pod nell'intervallo, in ordine di tempo.

    Gli eventi dicono creato, avviato e terminato (`Created`, `Started`, `Killing`…); «pronto» non è un evento ma
    una condizione del pod, e si aggiunge da lì per i pod che esistono ancora.
    """
    righe = []
    for e in eventi.get("items", []):
        quando = e.get("lastTimestamp") or e.get("eventTime") or e["metadata"]["creationTimestamp"]
        oggetto = e.get("involvedObject", {})
        righe.append((istante(quando), [e.get("type", ""), e.get("reason", ""),
                                        f"{oggetto.get('kind', '')}/{oggetto.get('name', '')}",
                                        " ".join(str(e.get("message", "")).split()), str(e.get("count", 1))]))
    for pod in pods.get("items", []):
        for condizione in pod.get("status", {}).get("conditions", []):
            if condizione["type"] == "Ready" and condizione.get("lastTransitionTime"):
                pronto = condizione["status"] == "True"
                righe.append((istante(condizione["lastTransitionTime"]),
                              ["Normal", "Ready" if pronto else "NotReady", f"Pod/{pod['metadata']['name']}", "", "1"]))
    return [[come_testo(quando), *resto] for quando, resto in sorted(righe, key=lambda r: r[0]) if da <= quando <= a]


def righe_prometheus(risposta: dict) -> list[list[str]]:
    """Da una risposta di `query_range` a righe (ts, metrica, etichette, valore), una per misura."""
    if risposta.get("status") != "success":
        raise ErroreEsportazione(f"Prometheus ha risposto: {risposta.get('error', risposta.get('status'))}")
    righe = []
    for serie in risposta["data"]["result"]:
        etichette = dict(serie["metric"])
        nome = etichette.pop("__name__", "")
        testo = ";".join(f"{k}={v}" for k, v in sorted(etichette.items()))
        for quando, valore in serie["values"]:
            righe.append([come_testo(datetime.fromtimestamp(float(quando), timezone.utc)), nome, testo, valore])
    return righe


def indirizzo_query(job: str, da: datetime, a: datetime, passo_s: float) -> str:
    parametri = urllib.parse.urlencode({"query": f'{{job="{job}"}}', "start": f"{da.timestamp():.3f}",
                                        "end": f"{a.timestamp():.3f}", "step": f"{passo_s:g}"})
    return f"{PROXY_PROMETHEUS}/api/v1/query_range?{parametri}"


def intervallo_del_run(cartella: Path) -> tuple[datetime, datetime]:
    """Dal primo all'ultimo `ts_invio` di client.csv, con i margini."""
    percorso = cartella / "client.csv"
    if not percorso.is_file():
        raise ErroreEsportazione(f"manca {percorso}: l'intervallo del run si ricava da lì (oppure --da e --a)")
    with open(percorso, newline="", encoding="utf-8") as f:
        istanti = [istante(r["ts_invio"]) for r in csv.DictReader(f)]
    if not istanti:
        raise ErroreEsportazione(f"{percorso} non ha nessuna richiesta")
    return min(istanti) - timedelta(seconds=MARGINE_PRIMA_S), max(istanti) + timedelta(seconds=MARGINE_DOPO_S)


class Esporta:
    """Un'esportazione. `kubectl(argomenti, input=None)` dà l'uscita del comando; `categorie(cartella)` dà (codice, testo)."""

    def __init__(self, kubectl, cartella: Path, da: datetime, a: datetime, passo_s: float = 5.0,
                 rielabora: bool = True, categorie=None):
        self.k = kubectl
        self.cartella = cartella
        self.da, self.a, self.passo_s = da, a, passo_s
        self.rielabora = rielabora
        self.categorie = categorie or esegui_categorie
        self.tempi: dict[str, float] = {}
        self.esito: dict = {}

    # --- il cluster ---

    def ha(self, risorsa: str) -> bool:
        return bool(self.k(["get", risorsa, "-o", "name", "--ignore-not-found"]).strip())

    def comando_psql(self) -> list[str]:
        """Dove e come leggere il database: il primario di CloudNativePG (V4) o il Deployment `db` (V1-V3)."""
        primario = self.k(["get", "pods", "-l", "cnpg.io/instanceRole=primary", "-o", "name"]).split()
        if primario:
            return ["exec", primario[0], "-c", "postgres", "--", "env", "PGTZ=UTC", "psql", "-d", "kintsugi"]
        return ["exec", "deploy/db", "--", "env", "PGTZ=UTC", "psql", "-U", "kintsugi", "-d", "kintsugi"]

    def query(self, sql: str, colonne: list[str]) -> list[list[str]]:
        return csv_di_psql(self.k([*self.comando_psql(), "--csv", "-c", sql]), colonne)

    def coda(self, modo: str) -> list[str]:
        uscita = self.k(["exec", "-i", "deploy/worker", "--", "python", "-", modo], input=SCRIPT_CODA)
        try:
            return json.loads(uscita.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise ErroreEsportazione(f"la coda dei falliti non si legge: {uscita[-200:]!r}") from None

    def messaggi_in_coda(self) -> dict[str, int]:
        uscita = self.k(["exec", "deploy/coda", "--", "rabbitmqctl", "list_queues", "name", "messages"])
        code = {}
        for riga in uscita.splitlines():
            campi = riga.split()
            if len(campi) == 2 and campi[1].isdigit():
                code[campi[0]] = int(campi[1])
        return code

    # --- i passi ---

    def passo(self, nome: str, funzione) -> None:
        inizio = time.monotonic()
        try:
            funzione()
        finally:
            self.tempi[nome] = round(time.monotonic() - inizio, 2)

    def database(self) -> None:
        sql = "select id, ts_ricezione, ts_scrittura from ordini order by ts_ricezione, id"
        self.esito["db"] = scrivi_csv(self.cartella / "db.csv", COLONNE_DB, self.query(sql, COLONNE_DB))
        self.esito["duplicati"] = scrivi_csv(self.cartella / "duplicati.csv", COLONNE_DUPLICATI,
                                             self.query("select id from duplicati order by n", COLONNE_DUPLICATI))

    def falliti(self) -> None:
        if self.ha("deployment/coda"):
            righe, illeggibili = messaggi_falliti(self.coda("leggi"))
            self.esito["falliti_illeggibili"] = illeggibili
        else:  # V1, V2, V4: nessuna coda
            righe = []
        self.esito["falliti"] = scrivi_csv(self.cartella / "falliti.csv", COLONNE_FALLITI, righe)

    def rielaborazione(self) -> None:
        """I falliti tornano in `ordini`; si aspetta che i worker li riprovino e si conta quanti si sono salvati."""
        if not self.ha("deployment/coda") or self.esito["falliti"] + self.esito.get("falliti_illeggibili", 0) == 0:
            self.esito["rielaborati"] = {"spostati": 0, "salvati": 0, "ancora_in_coda": 0}
            return
        prima = int(self.query("select count(*) as n from ordini", ["n"])[0][0])
        spostati = len(self.coda("sposta"))
        scadenza = time.monotonic() + ATTESA_RIELABORAZIONE_S
        while time.monotonic() < scadenza:
            code = self.messaggi_in_coda()
            if code.get("ordini", 0) == 0:
                break
            time.sleep(1)
        dopo = int(self.query("select count(*) as n from ordini", ["n"])[0][0])
        self.esito["rielaborati"] = {"spostati": spostati, "salvati": dopo - prima,
                                     "ancora_in_coda": self.messaggi_in_coda().get("ordini", 0)}

    def eventi(self) -> None:
        eventi = json.loads(self.k(["get", "events", "-o", "json"]))
        pods = json.loads(self.k(["get", "pods", "-o", "json"]))
        self.esito["eventi"] = scrivi_csv(self.cartella / "events.csv", COLONNE_EVENTI,
                                          righe_eventi(eventi, pods, self.da, self.a))

    def prometheus(self) -> None:
        righe = []
        for job in JOB_PROMETHEUS:
            risposta = json.loads(self.k(["get", "--raw", indirizzo_query(job, self.da, self.a, self.passo_s)]))
            righe += righe_prometheus(risposta)
        righe.sort(key=lambda r: (r[0], r[1], r[2]))
        self.esito["prometheus"] = scrivi_csv(self.cartella / "prometheus.csv", COLONNE_PROMETHEUS, righe)

    def coerenza(self) -> None:
        codice, testo = self.categorie(self.cartella)
        self.esito["categorie"] = {"codice": codice}
        print(testo.rstrip())
        if codice != 0:
            raise ErroreEsportazione("categorie.py ha trovato delle anomalie: il run va esaminato")

    def esegui(self) -> dict:
        """Tutti i passi nell'ordine. Un passo che fallisce non ferma gli altri, ma l'esito dice quali non sono riusciti."""
        inizio = time.monotonic()
        problemi = []
        passi = [("db", self.database), ("falliti", self.falliti)]
        if self.rielabora:
            passi.append(("rielaborazione", self.rielaborazione))
        passi += [("eventi", self.eventi), ("prometheus", self.prometheus), ("categorie", self.coerenza)]
        falliti_i_primi_due = False
        for nome, funzione in passi:
            if nome == "rielaborazione" and falliti_i_primi_due:
                continue  # senza db.csv e falliti.csv la rielaborazione sporcherebbe il run
            try:
                self.passo(nome, funzione)
            except (ErroreEsportazione, subprocess.CalledProcessError, OSError, ValueError, KeyError) as errore:
                problemi.append(f"{nome}: {getattr(errore, 'stderr', None) or errore}")
                falliti_i_primi_due = falliti_i_primi_due or nome in ("db", "falliti")
        self.esito.update({"durata_s": round(time.monotonic() - inizio, 2), "secondi_per_passo": self.tempi,
                           "da": come_testo(self.da), "a": come_testo(self.a), "problemi": problemi})
        (self.cartella / "esportazione.json").write_text(json.dumps(self.esito, indent=2, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
        return self.esito


def esegui_categorie(cartella: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(CATEGORIE), str(cartella)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def passo_di_raccolta() -> float:
    try:
        import yaml
        with open(PARAMETRI, encoding="utf-8") as f:
            return float(yaml.safe_load(f)["osservabilita"]["intervallo_raccolta_s"])
    except (ImportError, OSError, KeyError):
        return 5.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cartella", type=Path, help="cartella del run (data/<ambiente>/<run-id>)")
    parser.add_argument("--da", default=None, help="inizio dell'intervallo (ISO 8601): predefinito, 5 minuti prima del primo invio")
    parser.add_argument("--a", default=None, help="fine dell'intervallo: predefinito, 1 minuto dopo l'ultimo invio")
    parser.add_argument("--senza-rielaborazione", action="store_true", help="non rimette i falliti nella coda")
    parser.add_argument("--contesto", default="kind-kintsugi")
    argomenti = parser.parse_args()

    def kubectl(parametri: list[str], input: str | None = None) -> str:
        return subprocess.run(["kubectl", "--context", argomenti.contesto, *parametri],
                              check=True, capture_output=True, text=True, input=input).stdout

    try:
        da = istante(argomenti.da) if argomenti.da else None
        a = istante(argomenti.a) if argomenti.a else None
        if da is None or a is None:
            predefinito = intervallo_del_run(argomenti.cartella)
            da, a = da or predefinito[0], a or predefinito[1]
    except (ErroreEsportazione, ValueError) as errore:
        sys.exit(f"errore: {errore}")
    esito = Esporta(kubectl, argomenti.cartella, da, a, passo_di_raccolta(), not argomenti.senza_rielaborazione).esegui()
    righe = ", ".join(f"{k} {esito[k]}" for k in ("db", "falliti", "duplicati", "eventi", "prometheus") if k in esito)
    print(f"esportato in {esito['durata_s']:g} s: {righe}")
    if esito["problemi"]:
        for problema in esito["problemi"]:
            print(f"FALLITO  {problema}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
