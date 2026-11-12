"""Calcola quanto è durato il fermo dopo un guasto, dal log del client.

    python analysis/fermo.py data/<ambiente>/<run-id> --guasto 2026-11-12T10:02:00.123+00:00

Legge `client.csv` (una riga per richiesta: istante di invio ed esito) e l'istante del guasto, e stampa:

    ripristino   il momento in cui il servizio è tornato a funzionare
    fermo        il tempo passato tra il guasto e il ripristino

«Tornato a funzionare» (capitolo «Protocollo di misura»): da quel momento, per 5 secondi di fila, in
ogni secondo almeno il 99% delle richieste ha avuto esito 2xx. Per avere i millisecondi i secondi non
sono quelli del calendario: si prova a partire da ogni richiesta inviata dopo il guasto e si prende
la prima da cui i 5 secondi seguenti vanno bene.

È il ripristino dell'accettazione, visto dal client. Quello del completamento (richiesto in V3 e V5)
serve anche db.csv e non c'è. Se il log finisce prima di confermare i 5 secondi, lo script dice
«ripristino non avvenuto». Esce con codice 1 se i dati non tornano.
"""

import argparse
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from itertools import accumulate
from pathlib import Path

from categorie import ErroreDati, esito_positivo, leggi_colonne

PARAMETRI = Path(__file__).resolve().parents[1] / "config" / "parametri.yaml"


def istante(testo: str, cosa: str) -> float:
    """Secondi dall'epoca di un istante ISO 8601 con fuso orario (quello del client è UTC)."""
    try:
        quando = datetime.fromisoformat(testo.strip())
    except ValueError:
        raise ErroreDati(f"{cosa}: «{testo}» non è un istante ISO 8601") from None
    if quando.tzinfo is None:
        raise ErroreDati(f"{cosa}: «{testo}» non ha il fuso orario (per esempio +00:00 o Z)")
    return quando.timestamp()


def leggi_richieste(cartella: Path) -> list[tuple[float, bool]]:
    """Le richieste del client come (istante di invio, esito positivo), in ordine di invio.

    Il client scrive una riga quando la richiesta finisce, non quando parte: l'ordine del file
    non è quello di invio, e va rimesso.
    """
    righe = leggi_colonne(cartella / "client.csv", ["ts_invio", "esito"])
    richieste = [(istante(r["ts_invio"], "client.csv, ts_invio"), esito_positivo(r["esito"]))
                 for r in righe]
    richieste.sort(key=lambda r: r[0])
    return richieste


def ripristino(richieste: list[tuple[float, bool]], t_guasto: float,
               secondi: int = 5, soglia_percentuale: float = 99) -> float | None:
    """Istante t_r del ripristino, o None se il log non basta a confermarlo.

    `richieste` è ordinata per istante di invio. Un secondo è disponibile se almeno
    `soglia_percentuale`% delle richieste inviate in quel secondo è riuscita.
    """
    if not richieste:
        raise ErroreDati("client.csv non ha nessuna richiesta")
    istanti = [t for t, _ in richieste]
    if t_guasto < istanti[0]:
        raise ErroreDati("il guasto è prima della prima richiesta del client: istante sbagliato?")
    if t_guasto > istanti[-1]:
        raise ErroreDati("il guasto è dopo l'ultima richiesta del client: istante sbagliato?")
    riuscite = [0, *accumulate(1 if ok else 0 for _, ok in richieste)]

    def disponibile(inizio: float) -> bool:
        a, b = bisect_left(istanti, inizio), bisect_left(istanti, inizio + 1)
        inviate = b - a
        # In interi: il confronto con 0,99 in virgola mobile sbaglierebbe sul 99% esatto.
        return inviate > 0 and (riuscite[b] - riuscite[a]) * 100 >= soglia_percentuale * inviate

    fine_log = istanti[-1]
    for candidato in [t_guasto, *istanti[bisect_left(istanti, t_guasto):]]:
        if candidato + secondi > fine_log:
            return None  # l'ultima finestra uscirebbe dal log: non si può confermare
        if all(disponibile(candidato + i) for i in range(secondi)):
            return candidato
    return None


def richieste_fallite(richieste: list[tuple[float, bool]], da: float, fino_a: float) -> int:
    return sum(1 for t, ok in richieste if da <= t < fino_a and not ok)


def parametri_predefiniti() -> tuple[int, float]:
    """I secondi consecutivi e la soglia stanno in config/parametri.yaml, scritti una volta sola."""
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere i valori da config/parametri.yaml: "
                 "pip install pyyaml, oppure passa --secondi e --soglia")
    with open(PARAMETRI, encoding="utf-8") as f:
        valori = yaml.safe_load(f)
    return (int(valori["run"]["ripristino_secondi_consecutivi"]),
            float(valori["tempi"]["soglia_secondo_disponibile_percentuale"]))


def come_testo(secondi_epoca: float) -> str:
    return datetime.fromtimestamp(secondi_epoca, timezone.utc).isoformat(timespec="milliseconds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cartella", type=Path, help="cartella del run (data/<ambiente>/<run-id>)")
    parser.add_argument("--guasto", required=True,
                        help="istante del guasto, ISO 8601 con fuso orario (es. 2026-11-12T10:02:00.123+00:00)")
    parser.add_argument("--secondi", type=int, default=None,
                        help="secondi consecutivi disponibili (predefinito: config/parametri.yaml)")
    parser.add_argument("--soglia", type=float, default=None,
                        help="percentuale di richieste riuscite di un secondo disponibile (predefinito: config/parametri.yaml)")
    argomenti = parser.parse_args()
    secondi, soglia = argomenti.secondi, argomenti.soglia
    if secondi is None or soglia is None:
        predefinito = parametri_predefiniti()
        secondi = predefinito[0] if secondi is None else secondi
        soglia = predefinito[1] if soglia is None else soglia

    try:
        t_guasto = istante(argomenti.guasto, "--guasto")
        richieste = leggi_richieste(argomenti.cartella)
        t_ripristino = ripristino(richieste, t_guasto, secondi, soglia)
    except ErroreDati as errore:
        sys.exit(f"errore: {errore}")

    print(f"guasto     t_g = {come_testo(t_guasto)}")
    if t_ripristino is None:
        print(f"ripristino non avvenuto: il log finisce prima di {secondi} secondi consecutivi disponibili")
        print(f"richieste fallite dal guasto alla fine del log: "
              f"{richieste_fallite(richieste, t_guasto, float('inf'))}")
        return
    print(f"ripristino t_r = {come_testo(t_ripristino)}")
    print(f"fermo      t_r - t_g = {t_ripristino - t_guasto:.3f} s")
    print(f"richieste fallite tra guasto e ripristino: {richieste_fallite(richieste, t_guasto, t_ripristino)}")


if __name__ == "__main__":
    main()
