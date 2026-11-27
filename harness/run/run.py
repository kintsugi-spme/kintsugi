"""Un run completo con un solo comando (issue #122): la figura «Struttura di un run» del «Protocollo di misura».

    python harness/run/run.py --versione V2 --guasto F1 --carico W1 --ritmo 20 --ripetizione 1
    python harness/run/run.py --versione V2 --carico W1 --ritmo 20                   senza guasto
    python harness/run/run.py --versione V3 --carico W2 --mu1 20                     W2 (picco), senza guasto
    Da deploy/k8s:  make run VERSIONE=V2 GUASTO=F1 CARICO=W1 RITMO=20

Crea `data/locale/<run-id>/` e, nell'ordine:

  1. scrive `meta.json` (configurazione, hash del commit, nome e memoria del computer, memoria di Docker);
  2. lancia il reset (harness/reset): se fallisce il run non parte e `meta.json` dice perché (codice 2);
  3. avvia JMeter (harness/jmeter/carico.py): riscaldamento e riferimento sono i primi minuti del carico;
  4. inietta il guasto al minuto `run.guasto_al_minuto` del carico (harness/faults, con `--alle`: tutto si
     prepara prima e il segnale parte a quell'istante). Il minuto si conta dalla prima richiesta di JMeter;
  5. osserva fino al ripristino più `run.osservazione_dopo_ripristino_min`, con il tetto `run.tetto_min`
     (`run.tetto_min_f6_e_w2` per F6 e per W2). Il ripristino si riconosce *durante* il run: si legge
     `jmeter.jtl` mentre JMeter lo scrive e si applica la regola di analysis/fermo.py (5 secondi di fila
     disponibili, a partire da ogni richiesta). Senza questo ogni run durerebbe fino al tetto. È il ripristino
     dell'accettazione; quello del completamento (V3 e V5) serve db.csv e si calcola a fine run: se non c'è,
     fermo.txt lo dice e il run va esaminato. Senza guasto il run dura `run.senza_guasti_min`;
  6. ferma JMeter, poi esporta (harness/esporta: db.csv, falliti.csv, duplicati.csv, events.csv, prometheus.csv e
     categorie.py), poi lancia analysis/fermo.py e analysis/ritmo.py e ne salva l'uscita in `fermo.txt` e
     `ritmo.txt`. I criteri di validità (#125) si aggiungeranno qui.

Il Mac non deve andare in stop durante il run (limite del 10/11): lo script si fa tenere sveglio con `caffeinate -i`
se c'è. Vale per V1, V2 e V3 (il reset di V4 e V5 arriva con le #129 e #130). Il ritmo di W1 e W3 e la capacità μ1
per W2 non hanno un valore predefinito: vengono dalle misure delle #127 e #128.
"""

import argparse
import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
for sottocartella in ("analysis", "harness/reset", "harness/jmeter"):
    sys.path.insert(0, str(RADICE / sottocartella))

import carico as modulo_carico  # noqa: E402
import fermo  # noqa: E402
import reset as modulo_reset  # noqa: E402
from categorie import ErroreDati, esito_positivo  # noqa: E402

PARAMETRI = RADICE / "config" / "parametri.yaml"
ANTICIPO_GUASTO_S = 20  # lo script del guasto parte così presto prima del minuto: apre le shell e cerca i PID
ATTESA_PRIME_RICHIESTE_S = 90
PORTA_COMANDI_JMETER = 4445

# guasto -> (script in harness/faults, versioni in cui ha senso)
GUASTI = {
    "F1": ("arresto", {"V1", "V2", "V3"}), "F2": ("arresto", {"V3"}), "F3": ("arresto", {"V3"}),
    "F4": ("arresto", {"V1", "V2", "V3"}), "F5": ("latenza", {"V2", "V3"}), "F7": ("arresto", {"V2"}),
}
VERSIONI = ("V1", "V2", "V3")

Richiesta = tuple[float, bool, float]  # come in analysis/fermo.py


class ErroreRun(RuntimeError):
    """Il run non si può eseguire."""


@dataclass(frozen=True)
class Piano:
    versione: str
    carico: str  # W1, W3 o W2
    guasto: str | None
    ripetizione: int
    ritmo: float | None
    mu1: float | None
    run: dict  # la sezione `run` di config/parametri.yaml
    soglia_percentuale: float

    @property
    def id(self) -> str:
        return "-".join([self.versione, self.guasto or "nessuno", self.carico, f"r{self.ripetizione}"])

    @property
    def tetto_s(self) -> float:
        lungo = self.carico == "W2" or self.guasto == "F6"
        return 60 * (self.run["tetto_min_f6_e_w2"] if lungo else self.run["tetto_min"])


def controlla_piano(piano: Piano) -> None:
    if piano.versione not in VERSIONI:
        raise ErroreRun(f"versione {piano.versione}: per ora V1, V2 e V3 (il reset di V4 e V5 arriva con le #129 e #130)")
    if piano.guasto is not None:
        if piano.guasto not in GUASTI:
            raise ErroreRun(f"guasto {piano.guasto}: scegli tra {', '.join(sorted(GUASTI))}")
        if piano.versione not in GUASTI[piano.guasto][1]:
            raise ErroreRun(f"il guasto {piano.guasto} non si fa su {piano.versione}: solo su {', '.join(sorted(GUASTI[piano.guasto][1]))}")
    if piano.carico in ("W1", "W3") and not piano.ritmo:
        raise ErroreRun(f"il carico {piano.carico} vuole --ritmo (ordini al secondo): il valore viene dalla misura della capacità (#127)")
    if piano.carico == "W2" and not piano.mu1:
        raise ErroreRun("il carico W2 vuole --mu1, la capacità di un worker (#128)")
    if piano.carico not in ("W1", "W3", "W2"):
        raise ErroreRun(f"carico {piano.carico}: W1, W3 o W2")


def quando_fermarsi(piano: Piano, ora: float, t0: float, t_ripristino: float | None) -> str | None:
    """Il motivo per cui il run finisce adesso, o None se continua.

    `t0` è la prima richiesta del carico, `t_ripristino` l'istante di ripristino dell'accettazione (None se non
    c'è ancora, o senza guasto). Senza guasto il run dura `senza_guasti_min` (con W2, quanto dura il suo profilo);
    con il guasto, fino al ripristino più `osservazione_dopo_ripristino_min`, ma mai oltre il tetto.
    """
    if piano.guasto is None:
        if piano.carico == "W2":  # il profilo W2 ha la sua durata: il carico finisce da solo, o si arriva al tetto
            return "tetto raggiunto" if ora >= t0 + piano.tetto_s else None
        if ora >= t0 + 60 * piano.run["senza_guasti_min"]:
            return "durata senza guasti"
        return None
    if t_ripristino is not None and ora >= t_ripristino + 60 * piano.run["osservazione_dopo_ripristino_min"]:
        return "ripristino più osservazione"
    if ora >= t0 + piano.tetto_s:
        return "tetto raggiunto: ripristino non avvenuto" if t_ripristino is None else "tetto raggiunto"
    return None


class LettoreJtl:
    """Legge jmeter.jtl mentre JMeter lo scrive: ogni chiamata dà le righe complete arrivate dall'ultima volta."""

    def __init__(self, percorso: Path):
        self.percorso = percorso
        self.posizione = 0
        self.intestazione: list[str] | None = None
        self.resto = ""

    def nuove(self) -> list[Richiesta]:
        if not self.percorso.is_file():
            return []
        with open(self.percorso, encoding="utf-8", newline="") as f:
            f.seek(self.posizione)
            testo = self.resto + f.read()
            self.posizione = f.tell()
        completo, _, self.resto = testo.rpartition("\n")
        if not completo and not testo.endswith("\n"):
            return []
        richieste = []
        for campi in csv.reader(completo.splitlines()):
            if not campi:
                continue
            if self.intestazione is None:
                self.intestazione = campi
                continue
            riga = dict(zip(self.intestazione, campi))
            try:
                richieste.append((int(riga["timeStamp"]) / 1000, esito_positivo(modulo_carico.esito(riga["responseCode"])),
                                  int(riga["elapsed"]) / 1000))
            except (KeyError, ValueError):
                continue  # una riga che non si legge non ferma il run: a fine run la conversione la ricontrolla
        return richieste


def info_host() -> dict:
    def comando(*argomenti) -> str:
        try:
            return subprocess.run(argomenti, capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    memoria = comando("sysctl", "-n", "hw.memsize")
    docker = comando("docker", "info", "--format", "{{.MemTotal}}")
    return {"nome": socket.gethostname(), "sistema": comando("uname", "-sr"), "cpu": comando("sysctl", "-n", "machdep.cpu.brand_string"),
            "core": os.cpu_count(), "memoria_gib": round(int(memoria) / 2**30, 1) if memoria.isdigit() else None,
            "docker_memoria_gib": round(int(docker) / 2**30, 1) if docker.isdigit() else None}


def info_commit() -> dict:
    def git(*argomenti) -> str:
        return subprocess.run(["git", "-C", str(RADICE), *argomenti], capture_output=True, text=True).stdout.strip()
    return {"hash": git("rev-parse", "HEAD"), "modificato": bool(git("status", "--porcelain"))}


def come_testo(secondi: float | None) -> str | None:
    return None if secondi is None else datetime.fromtimestamp(secondi, timezone.utc).isoformat(timespec="milliseconds")


class Ambiente:
    """Tutto quello che tocca il mondo: orologio, processi, cluster. In produzione `AmbienteReale`; nelle prove un finto."""

    def orologio(self) -> float: ...
    def dormi(self, secondi: float) -> None: ...
    def reset(self, piano: Piano) -> dict: ...
    def avvia_carico(self, piano: Piano, cartella: Path): ...  # .nuove() .vivo() .ferma() .attendi()
    def avvia_guasto(self, piano: Piano, cartella: Path, alle: float): ...  # .vivo() .attendi()
    def ts_guasto(self, cartella: Path) -> float | None: ...
    def dopo_il_run(self, piano: Piano, cartella: Path) -> dict: ...


class Run:
    def __init__(self, piano: Piano, ambiente: Ambiente, cartella: Path, host: dict | None = None, commit: dict | None = None):
        self.p, self.a, self.cartella = piano, ambiente, cartella
        self.meta: dict = {}
        self.host, self.commit = host or {}, commit or {}

    def scrivi_meta(self, **campi) -> None:
        self.meta.update(campi)
        (self.cartella / "meta.json").write_text(json.dumps(self.meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def esegui(self) -> int:
        p, a = self.p, self.a
        self.cartella.mkdir(parents=True, exist_ok=True)
        inizio = a.orologio()
        self.scrivi_meta(run_id=self.cartella.name, ambiente=self.cartella.parent.name, versione=p.versione,
                         carico={"nome": p.carico, "ritmo": p.ritmo, "mu1": p.mu1}, guasto=p.guasto,
                         ripetizione=p.ripetizione, commit=self.commit, host=self.host, parametri_run=p.run,
                         ts_inizio=come_testo(inizio), stato="avviato")
        # 2. il reset: se non riesce, il run non parte
        try:
            esito_reset = a.reset(p)
        except (modulo_reset.ErroreReset, subprocess.SubprocessError, OSError) as errore:
            esito_reset = {"durata_s": None, "problemi": [str(getattr(errore, "stderr", None) or errore)]}
        self.scrivi_meta(reset=esito_reset)
        if esito_reset["problemi"]:
            self.scrivi_meta(stato="reset fallito", motivo="; ".join(esito_reset["problemi"]), ts_fine=come_testo(a.orologio()))
            return 2
        # 3. il carico; qualunque cosa succeda da qui in poi, JMeter non deve restare acceso
        carico = a.avvia_carico(p, self.cartella)
        try:
            return self.dal_carico_in_poi(carico, inizio)
        except BaseException as errore:
            carico.ferma()
            self.scrivi_meta(stato="errore", motivo=f"{type(errore).__name__}: {errore}", ts_fine=come_testo(a.orologio()))
            raise

    def dal_carico_in_poi(self, carico, inizio: float) -> int:
        p, a = self.p, self.a
        richieste: list[Richiesta] = []
        t0 = None
        scadenza = a.orologio() + ATTESA_PRIME_RICHIESTE_S
        while t0 is None:
            richieste += carico.nuove()
            if richieste:
                t0 = min(r[0] for r in richieste)
            elif not carico.vivo() or a.orologio() > scadenza:
                carico.ferma()
                self.scrivi_meta(stato="errore", motivo="JMeter non ha inviato nessuna richiesta", ts_fine=come_testo(a.orologio()))
                return 1
            else:
                a.dormi(0.5)
        self.scrivi_meta(carico_t0=come_testo(t0))
        # 4. e 5. il guasto e l'osservazione
        t_guasto_previsto = t0 + 60 * p.run["guasto_al_minuto"] if p.guasto else None
        guasto = None
        t_guasto = t_ripristino = None
        motivo = None
        while motivo is None:
            a.dormi(1.0)
            richieste += carico.nuove()
            ora = a.orologio()
            if t_guasto_previsto is not None and guasto is None and ora >= t_guasto_previsto - ANTICIPO_GUASTO_S:
                guasto = a.avvia_guasto(p, self.cartella, t_guasto_previsto)
            if guasto is not None and t_guasto is None:
                t_guasto = a.ts_guasto(self.cartella)
                if t_guasto is not None:
                    self.scrivi_meta(guasto_ts=come_testo(t_guasto))
            if t_guasto is not None and t_ripristino is None:
                try:
                    t_ripristino = fermo.ripristino(sorted(richieste), t_guasto, p.run["ripristino_secondi_consecutivi"],
                                                    p.soglia_percentuale)
                except ErroreDati:
                    t_ripristino = None
                if t_ripristino is not None:
                    self.scrivi_meta(ripristino_accettazione=come_testo(t_ripristino))
            motivo = quando_fermarsi(p, ora, t0, t_ripristino)
            if motivo is None and not carico.vivo():
                motivo = "il carico è finito da solo"
        # 6. si ferma il carico, si esporta e si analizza
        carico.ferma()
        carico.attendi()
        if guasto is not None:
            guasto.attendi()
        fine_carico = a.orologio()
        self.scrivi_meta(fine_osservazione={"motivo": motivo, "ts": come_testo(fine_carico)})
        analisi = a.dopo_il_run(p, self.cartella)
        self.scrivi_meta(analisi=analisi, stato="completato", ts_fine=come_testo(a.orologio()),
                         durata_s=round(a.orologio() - inizio, 1), criteri_di_validita=None)
        return 0 if analisi.get("esportazione") == 0 else 1


class AmbienteReale(Ambiente):
    def __init__(self, contesto: str = "kind-kintsugi", ingresso: str = "http://localhost:8080"):
        self.contesto, self.ingresso = contesto, ingresso

    def orologio(self) -> float:
        return time.time()

    def dormi(self, secondi: float) -> None:
        time.sleep(secondi)

    def kubectl(self, parametri: list[str]) -> str:
        return subprocess.run(["kubectl", "--context", self.contesto, *parametri], check=True, capture_output=True, text=True).stdout

    def reset(self, piano: Piano) -> dict:
        parametri = leggi_parametri()
        r = modulo_reset.Reset(self.kubectl, modulo_reset.versione_attesa(piano.versione.lower(), parametri), self.ingresso)
        return r.esegui()

    def avvia_carico(self, piano: Piano, cartella: Path):
        argomenti = [sys.executable, str(RADICE / "harness/jmeter/carico.py"), "--uscita", str(cartella / "client.csv")]
        if piano.carico == "W2":
            argomenti += ["--profilo", "w2", "--mu1", f"{piano.mu1:g}"]
        else:
            argomenti += ["--profilo", "costante", "--ritmo", f"{piano.ritmo:g}", "--durata",
                          f"{piano.tetto_s if piano.guasto else 60 * piano.run['senza_guasti_min']:g}"]
        return CaricoReale(argomenti, cartella)

    def avvia_guasto(self, piano: Piano, cartella: Path, alle: float):
        script = GUASTI[piano.guasto][0]
        argomenti = [sys.executable, str(RADICE / f"harness/faults/{script}.py"), "--cartella", str(cartella),
                     "--contesto", self.contesto, "--alle", come_testo(alle)]
        if script == "arresto":
            argomenti += ["--guasto", piano.guasto]
        return ProcessoReale(argomenti, cartella / "guasto.txt")

    def ts_guasto(self, cartella: Path) -> float | None:
        try:
            return fermo.istante(json.loads((cartella / "guasto.json").read_text(encoding="utf-8"))["ts_guasto"], "guasto.json")
        except (OSError, ValueError, KeyError, ErroreDati):
            return None

    def dopo_il_run(self, piano: Piano, cartella: Path) -> dict:
        def lancia(nome: str, *argomenti: str) -> int:
            r = subprocess.run([sys.executable, *argomenti], capture_output=True, text=True)
            (cartella / f"{nome}.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
            return r.returncode
        esito = {"esportazione": lancia("esportazione", str(RADICE / "harness/esporta/esporta.py"), str(cartella),
                                        "--contesto", self.contesto)}
        if piano.guasto and (cartella / "guasto.json").is_file():
            esito["fermo"] = lancia("fermo", str(RADICE / "analysis/fermo.py"), str(cartella))
        esito["ritmo"] = lancia("ritmo", str(RADICE / "analysis/ritmo.py"), str(cartella))
        return esito


class ProcessoReale:
    def __init__(self, argomenti: list[str], uscita: Path):
        self.f = open(uscita, "w", encoding="utf-8")
        self.p = subprocess.Popen(argomenti, stdout=self.f, stderr=subprocess.STDOUT)

    def vivo(self) -> bool:
        return self.p.poll() is None

    def attendi(self, secondi: float = 180) -> int | None:
        try:
            codice = self.p.wait(timeout=secondi)
        except subprocess.TimeoutExpired:
            self.p.terminate()
            codice = None
        self.f.close()
        return codice


class CaricoReale(ProcessoReale):
    def __init__(self, argomenti: list[str], cartella: Path):
        super().__init__(argomenti, cartella / "carico.txt")
        self.lettore = LettoreJtl(cartella / "jmeter.jtl")

    def nuove(self) -> list[Richiesta]:
        return self.lettore.nuove()

    def ferma(self) -> None:
        """Niente nuovi arrivi (`Shutdown`), si lasciano finire le richieste in volo; poi `StopTestNow`.

        Dopo `Shutdown` il processo di JMeter resta acceso a lungo (provato: oltre 2 minuti): `StopTestNow` lo
        chiude in un secondo e i risultati restano scritti.
        """
        if not self.vivo():
            return
        for comando, attesa_s in ((b"Shutdown", 4.0), (b"StopTestNow", 10.0)):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(comando, ("127.0.0.1", PORTA_COMANDI_JMETER))
            scadenza = time.monotonic() + attesa_s
            while self.vivo() and time.monotonic() < scadenza:
                time.sleep(0.2)
            if not self.vivo():
                return
        self.p.terminate()


def leggi_parametri() -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere config/parametri.yaml: pip install pyyaml")
    with open(PARAMETRI, encoding="utf-8") as f:
        return yaml.safe_load(f)


def id_del_run(piano: Piano, ora: datetime) -> str:
    return f"{ora.strftime('%Y%m%d-%H%M%S')}-{piano.id}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--versione", required=True, type=str.upper, choices=VERSIONI)
    parser.add_argument("--carico", required=True, type=str.upper, choices=["W1", "W3", "W2"])
    parser.add_argument("--guasto", default=None, type=str.upper, help="F1, F2, F3, F4, F5 o F7; senza: nessun guasto")
    parser.add_argument("--ritmo", type=float, default=None, help="ordini al secondo (W1 e W3)")
    parser.add_argument("--mu1", type=float, default=None, help="capacità di un worker in ordini/s (W2)")
    parser.add_argument("--ripetizione", type=int, default=1)
    parser.add_argument("--ambiente", default="locale", help="cartella di data/ (predefinita: locale)")
    parser.add_argument("--contesto", default="kind-kintsugi")
    a = parser.parse_args()
    parametri = leggi_parametri()
    piano = Piano(a.versione, a.carico, a.guasto, a.ripetizione, a.ritmo, a.mu1, parametri["run"],
                  float(parametri["tempi"]["soglia_secondo_disponibile_percentuale"]))
    try:
        controlla_piano(piano)
    except ErroreRun as errore:
        sys.exit(f"errore: {errore}")
    cartella = RADICE / "data" / a.ambiente / id_del_run(piano, datetime.now(timezone.utc))
    if shutil.which("caffeinate"):  # il Mac non va in stop finché questo processo è vivo (limite del 10/11)
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    run = Run(piano, AmbienteReale(a.contesto), cartella, info_host(), info_commit())
    codice = run.esegui()
    stato = run.meta.get("stato")
    print(f"run {cartella.name}: {stato}" + (f" ({run.meta.get('motivo')})" if run.meta.get("motivo") else "")
          + f"; file in {cartella}")
    sys.exit(codice)


if __name__ == "__main__":
    main()
