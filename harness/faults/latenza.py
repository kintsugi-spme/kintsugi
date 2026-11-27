"""Guasto F5: latenza tra l'applicazione e il database, con l'API di Toxiproxy (#93).

    python harness/faults/latenza.py --cartella data/locale/<run-id>
    python harness/faults/latenza.py --cartella data/locale/<run-id> --latenza-ms 200 --durata 60

All'istante del guasto aggiunge al proxy `postgres` un «toxic» di latenza: ogni risposta del database arriva
all'applicazione `--latenza-ms` millisecondi più tardi. Dopo `--durata` secondi lo toglie. I valori predefiniti
vengono da config/parametri.yaml (guasti.f5_latenza_ms, guasti.f5_durata_s; capitolo «Guasti»).

Come per `arresto.py` (D0016), la strada verso Toxiproxy si apre prima del guasto: una shell nel nodo del suo
pod, già scaldata, a cui al momento giusto si manda solo il comando `curl` verso la sua API (porta 8474).
Per l'inizio e per la fine si scrivono gli istanti subito prima e subito dopo il comando sull'orologio del
computer (la differenza è l'incertezza) e quello letto nel nodo, sull'orologio del cluster. `ts_guasto` è il
limite inferiore dell'inizio, `ts_fine` quello della fine.

La latenza si toglie comunque: se lo script si interrompe (Ctrl-C, SIGTERM) o qualcosa va storto a metà. La
shell nel nodo gira in una sessione sua, così il Ctrl-C del terminale non la chiude; se è morta lo stesso, la
latenza si toglie con un `docker exec` nuovo. Alla fine lo script rilegge i toxic del proxy e li scrive in
`guasto.json` (`toxic_dopo`, deve essere vuoto); se ne resta qualcuno esce con codice 1. Solo un SIGKILL dello
script lascerebbe la latenza: il reset (#121) lo controlla prima di ogni run.
"""

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import arresto
from arresto import ErroreGuasto, come_testo

PROXY = "postgres"
TOXIC = "latenza_f5"
PORTA_API = 8474


def toxic(latenza_ms: int) -> dict:
    """La latenza sulle risposte del database (`downstream`), uguale per tutte (niente variazione casuale)."""
    return {"name": TOXIC, "type": "latency", "stream": "downstream", "toxicity": 1.0,
            "attributes": {"latency": latenza_ms, "jitter": 0}}


def comando_aggiungi(indirizzo: str, latenza_ms: int) -> str:
    corpo = json.dumps(toxic(latenza_ms), separators=(",", ":"))
    return (f"t=$(date +%s.%N) && curl -sf -o /dev/null -X POST -H 'Content-Type: application/json'"
            f" -d '{corpo}' http://{indirizzo}:{PORTA_API}/proxies/{PROXY}/toxics && echo \"ok $t\" || echo fallito")


def comando_togli(indirizzo: str) -> str:
    return (f"t=$(date +%s.%N) && curl -sf -o /dev/null -X DELETE"
            f" http://{indirizzo}:{PORTA_API}/proxies/{PROXY}/toxics/{TOXIC} && echo \"ok $t\" || echo fallito")


def comando_elenco(indirizzo: str) -> str:
    """I toxic del proxy in una riga (JSON), oppure «errore»."""
    return f"echo \"$(curl -sf http://{indirizzo}:{PORTA_API}/proxies/{PROXY}/toxics | tr -d '\\n' || echo errore)\""


def esegui(shell, riga: str, orologio=time.time) -> dict:
    """Manda `riga`, che stampa «ok <istante del nodo>», e restituisce gli istanti prima, dopo e nel nodo."""
    prima = orologio()
    risposta = shell.comando(riga)
    dopo = orologio()
    parti = risposta.split()
    if len(parti) != 2 or parti[0] != "ok":
        raise ErroreGuasto(f"la chiamata a Toxiproxy non è riuscita ({risposta!r})")
    return {"prima": prima, "dopo": dopo, "nodo": float(parti[1])}


def elenco(esegui_riga, indirizzo: str) -> list[str]:
    risposta = esegui_riga(comando_elenco(indirizzo))
    try:
        return [t["name"] for t in json.loads(risposta)]
    except (json.JSONDecodeError, TypeError, KeyError):
        raise ErroreGuasto(f"l'elenco dei toxic di Toxiproxy non si legge ({risposta!r})") from None


# Le chiavi di guasto.json per gli istanti dell'inizio e della fine: prima, dopo, incertezza, nel nodo.
INIZIO = ("ts_guasto", "ts_conferma", "incertezza_s", "ts_nodo")
FINE = ("ts_fine", "ts_fine_conferma", "incertezza_fine_s", "ts_nodo_fine")


def istanti(i: dict, chiavi: tuple[str, str, str, str]) -> dict:
    prima, dopo, incertezza, nodo = chiavi
    return {prima: come_testo(i["prima"]), dopo: come_testo(i["dopo"]),
            incertezza: round(i["dopo"] - i["prima"], 4), nodo: come_testo(i["nodo"])}


def provoca(kubectl, apri_shell, ripiego, latenza_ms: int, durata_s: float, scrivi,
            orologio=time.time, dormi=time.sleep) -> dict:
    """Aggiunge la latenza, aspetta `durata_s` secondi e la toglie, anche se nel mezzo qualcosa si interrompe.

    `ripiego(nodo, riga)` esegue `riga` nel nodo con un `docker exec` nuovo: serve se la shell aperta prima
    è morta e la latenza va tolta lo stesso. `scrivi` riceve guasto.json all'inizio e alla fine.
    """
    pods = json.loads(kubectl(["get", "pods", "-l", "app=toxiproxy", "-o", "json"]))
    bersaglio = arresto.scegli_bersagli(pods, "toxiproxy")[0]
    indirizzo = next(p["status"]["podIP"] for p in pods["items"] if p["metadata"]["name"] == bersaglio.pod)
    dati = {"guasto": "F5", "latenza_ms": latenza_ms, "durata_s": durata_s, "toxic": toxic(latenza_ms),
            "pod": bersaglio.pod, "nodo": bersaglio.nodo}
    shell = apri_shell(bersaglio.nodo)
    try:
        shell.comando("echo pronto")  # il primo comando di una shell nuova è lento: non va misurato
        gia = elenco(shell.comando, indirizzo)
        if gia:
            raise ErroreGuasto(f"Toxiproxy ha già dei toxic ({', '.join(gia)}): rifare il reset prima del run")
        aggiunta, dati["interrotto"] = None, False
        try:
            aggiunta = esegui(shell, comando_aggiungi(indirizzo, latenza_ms), orologio)
            dati |= istanti(aggiunta, INIZIO)
            scrivi(dati)
            dormi(max(0.0, aggiunta["prima"] + durata_s - orologio()))
        except KeyboardInterrupt:
            dati["interrotto"] = True
            raise
        finally:
            dati |= togli(shell, ripiego, bersaglio.nodo, indirizzo, orologio)
            if aggiunta is not None:
                scrivi(dati)
    finally:
        shell.chiudi()
    if dati["toxic_dopo"]:
        raise ErroreGuasto(f"dopo il guasto Toxiproxy ha ancora dei toxic: {', '.join(dati['toxic_dopo'])}")
    return dati


def togli(shell, ripiego, nodo: str, indirizzo: str, orologio=time.time) -> dict:
    """Toglie la latenza e rilegge i toxic (`toxic_dopo`). Non solleva errori: è chiamata mentre se ne gestisce uno.

    Se la shell non risponde, o il DELETE fallisce (per esempio perché la latenza non era stata aggiunta), si
    riprova con `ripiego`, un `docker exec` nuovo, e si rilegge da lì.
    """
    try:
        esito = istanti(esegui(shell, comando_togli(indirizzo), orologio), FINE)
        return esito | {"toxic_dopo": elenco(shell.comando, indirizzo)}
    except (ErroreGuasto, OSError, ValueError):
        pass
    try:
        ripiego(nodo, comando_togli(indirizzo))
        return {"toxic_dopo": elenco(lambda riga: ripiego(nodo, riga), indirizzo)}
    except (ErroreGuasto, OSError, subprocess.SubprocessError) as errore:
        return {"toxic_dopo": ["non letto"], "errore_fine": str(errore)}


def ripiego_docker(nodo: str, riga: str) -> str:
    risultato = subprocess.run(["docker", "exec", nodo, "sh", "-c", riga], capture_output=True, text=True,
                               timeout=30)
    return (risultato.stdout.strip().splitlines() or [""])[0]


def leggi_guasti() -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere config/parametri.yaml: pip install pyyaml (oppure --latenza-ms e --durata)")
    with open(Path(__file__).resolve().parents[2] / "config" / "parametri.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["guasti"]


def interrompi(_segnale, _quadro):
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--cartella", type=Path, required=True,
                        help="cartella del run (data/<ambiente>/<run-id>): vi si scrive guasto.json")
    parser.add_argument("--latenza-ms", type=int, default=None, help="predefinito: guasti.f5_latenza_ms")
    parser.add_argument("--durata", type=float, default=None, help="secondi (predefinito: guasti.f5_durata_s)")
    parser.add_argument("--contesto", default="kind-kintsugi", help="contesto di kubectl")
    a = parser.parse_args()
    if a.latenza_ms is None or a.durata is None:
        guasti = leggi_guasti()
        a.latenza_ms = guasti["f5_latenza_ms"] if a.latenza_ms is None else a.latenza_ms
        a.durata = float(guasti["f5_durata_s"]) if a.durata is None else a.durata
    if a.latenza_ms <= 0 or a.durata <= 0:
        parser.error("latenza e durata devono essere positive")
    signal.signal(signal.SIGTERM, interrompi)

    def kubectl(parametri: list[str]) -> str:
        return subprocess.run(["kubectl", "--context", a.contesto, *parametri],
                              check=True, capture_output=True, text=True).stdout

    file = a.cartella / "guasto.json"

    def scrivi(dati: dict) -> None:
        a.cartella.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(dati, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        r = provoca(kubectl, arresto.ShellNelNodo, ripiego_docker, a.latenza_ms, a.durata, scrivi)
    except KeyboardInterrupt:
        sys.exit(f"interrotto: latenza tolta, toxic rimasti: {json.loads(file.read_text())['toxic_dopo'] if file.exists() else '?'}")
    except FileNotFoundError as errore:
        sys.exit(f"errore: programma non trovato: {errore.filename} (servono docker e kubectl)")
    except (ErroreGuasto, subprocess.CalledProcessError, subprocess.TimeoutExpired) as errore:
        sys.exit(f"errore: {getattr(errore, 'stderr', None) or errore}")
    print(f"F5, latenza di {r['latenza_ms']} ms verso il database dalle {r['ts_guasto']} (incertezza "
          f"{r['incertezza_s'] * 1000:.1f} ms) alle {r['ts_fine']} (incertezza {r['incertezza_fine_s'] * 1000:.1f} ms); "
          f"toxic rimasti: {len(r['toxic_dopo'])}; scritto {file}")


if __name__ == "__main__":
    main()
