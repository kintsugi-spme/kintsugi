"""Client minimo: invia ordini a ritmo fisso e scrive il log in client.csv.

È provvisorio: serve a provare l'app in fase F2. Il generatore di carico vero (JMeter a modello
aperto) arriva in F4 e scriverà un client.csv con le stesse colonne (data/README.md).

    python harness/client/cliente.py --url http://localhost:8000/ordini --richieste 100 --ritmo 10

Modello aperto (documento di architettura, capitolo «Protocollo di misura»): la richiesta k parte
all'istante k / ritmo dall'avvio, anche se le risposte precedenti non sono ancora arrivate. Se il
client aspettasse ogni risposta prima di inviare la successiva, durante un guasto smetterebbe di
inviare proprio quando serve (coordinated omission). Per questo ogni richiesta ha un suo thread.

Ogni ordine ha un identificativo UUID scelto dal client (D0004). Il client non riprova: una riga
per richiesta, con l'esito che ha visto.

Colonne di client.csv:
    ts_invio          istante di invio (UTC, ISO 8601, microsecondi)
    id                identificativo dell'ordine
    esito             codice HTTP (201, 202, 503…), «timeout» se non risponde entro il timeout,
                      «errore» se non riesce a collegarsi
    tempo_risposta_s  secondi tra invio e risposta (o tra invio e rinuncia)
"""

import argparse
import csv
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

COLONNE = ["ts_invio", "id", "esito", "tempo_risposta_s"]
PARAMETRI = Path(__file__).resolve().parents[2] / "config" / "parametri.yaml"


def timeout_predefinito() -> float:
    """Il timeout del client sta in config/parametri.yaml (D0008), scritto una volta sola."""
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere il timeout da config/parametri.yaml: "
                 "pip install pyyaml, oppure passa --timeout")
    with open(PARAMETRI, encoding="utf-8") as f:
        return float(yaml.safe_load(f)["tempi"]["timeout_client_s"])


def invia(url: str, id_ordine: str, timeout_s: float) -> str:
    """Invia un ordine e restituisce l'esito: codice HTTP, «timeout» o «errore»."""
    richiesta = urllib.request.Request(
        url,
        data=json.dumps({"id": id_ordine}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout_s) as risposta:
            risposta.read()
            return str(risposta.status)
    except urllib.error.HTTPError as errore:  # il server ha risposto con 4xx o 5xx
        return str(errore.code)
    except TimeoutError:
        return "timeout"
    except urllib.error.URLError as errore:
        return "timeout" if isinstance(errore.reason, TimeoutError) else "errore"
    except OSError:  # collegamento caduto a metà risposta
        return "errore"


def esegui(url: str, richieste: int, ritmo: float, timeout_s: float, uscita) -> dict[str, int]:
    """Invia `richieste` ordini a `ritmo` al secondo e scrive una riga per richiesta su `uscita`.

    Restituisce il numero di richieste per esito.
    """
    scrittore = csv.writer(uscita)
    scrittore.writerow(COLONNE)
    blocco = threading.Lock()
    esiti: dict[str, int] = {}

    def una_richiesta(id_ordine: str) -> None:
        ts_invio = datetime.now(timezone.utc)
        inizio = time.perf_counter()
        esito = invia(url, id_ordine, timeout_s)
        durata = time.perf_counter() - inizio
        with blocco:
            scrittore.writerow([ts_invio.isoformat(), id_ordine, esito, f"{durata:.6f}"])
            uscita.flush()
            esiti[esito] = esiti.get(esito, 0) + 1

    fili = []
    partenza = time.monotonic()
    for k in range(richieste):
        # Aspetta l'istante previsto per la richiesta k, senza dipendere dalle risposte.
        attesa = partenza + k / ritmo - time.monotonic()
        if attesa > 0:
            time.sleep(attesa)
        filo = threading.Thread(target=una_richiesta, args=(str(uuid.uuid4()),))
        filo.start()
        fili.append(filo)
    for filo in fili:
        filo.join()
    return esiti


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", required=True, help="indirizzo di POST /ordini")
    parser.add_argument("--richieste", type=int, default=100, help="quanti ordini inviare")
    parser.add_argument("--ritmo", type=float, default=10, help="ordini al secondo")
    parser.add_argument("--timeout", type=float, default=None,
                        help="secondi prima di rinunciare (predefinito: config/parametri.yaml)")
    parser.add_argument("--uscita", default="client.csv", help="file del log")
    argomenti = parser.parse_args()
    if argomenti.richieste < 1 or argomenti.ritmo <= 0:
        parser.error("--richieste deve essere almeno 1 e --ritmo maggiore di 0")
    timeout_s = argomenti.timeout if argomenti.timeout is not None else timeout_predefinito()

    inizio = time.monotonic()
    with open(argomenti.uscita, "w", newline="", encoding="utf-8") as uscita:
        esiti = esegui(argomenti.url, argomenti.richieste, argomenti.ritmo, timeout_s, uscita)
    durata = time.monotonic() - inizio

    riassunto = ", ".join(f"{esito}: {n}" for esito, n in sorted(esiti.items()))
    print(f"inviate {argomenti.richieste} richieste in {durata:.1f} s ({riassunto}); "
          f"log in {argomenti.uscita}")


if __name__ == "__main__":
    main()
