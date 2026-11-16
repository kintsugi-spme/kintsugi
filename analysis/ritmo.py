"""Controlla che il client abbia inviato le richieste al ritmo chiesto, dal suo log.

    python analysis/ritmo.py data/<ambiente>/<run-id> --ritmo 50

È un criterio di validità del run (capitolo «Protocollo di misura»): il ritmo effettivamente inviato
resta entro la tolleranza (±5%) da quello previsto, anche durante il guasto. Un generatore a modello
chiuso smetterebbe di inviare proprio durante il guasto, e questo controllo lo scopre.

Legge `client.csv` e confronta il ritmo chiesto con gli istanti di invio scritti nel log (`ts_invio`),
non con quelli pianificati dal client. Stampa due cose:

    ritmo medio   le richieste inviate diviso il tempo tra la prima e l'ultima: (N - 1) / durata
    finestre      il ritmo in ogni finestra di 10 s consecutive, dalla prima richiesta

Il ritmo medio da solo nasconde un'interruzione breve: 5 s senza invii in un run di 3 minuti spostano la
media di meno del 3%, ma nelle finestre che la contengono il ritmo scende di un quarto o più. Per questo
si guardano anche le finestre. L'ultimo tratto, più corto di una finestra, conta solo nel ritmo medio: poche richieste per
tratto darebbero scarti dovuti solo all'arrotondamento. Con meno di una finestra si controlla solo la media.

Esce con codice 1 se il ritmo medio o una finestra supera la tolleranza, o se i dati non tornano.

Vale per un carico a ritmo costante (W1, W3). W2 ha un profilo, base e picco, e un solo ritmo chiesto
non basta. La finestra di 10 s è una scelta di questa verifica, da riconfermare con il generatore di F4.
"""

import argparse
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

from categorie import ErroreDati
from fermo import leggi_richieste

PARAMETRI = Path(__file__).resolve().parents[1] / "config" / "parametri.yaml"
FINESTRA_S = 10.0
# Quante finestre fuori tolleranza si elencano: il resto si conta soltanto.
FINESTRE_ELENCATE = 5

Finestra = tuple[float, int, float]  # (istante di inizio, richieste inviate, scarto in %)


def scarto_percentuale(ritmo_inviato: float, ritmo_chiesto: float) -> float:
    return (ritmo_inviato / ritmo_chiesto - 1) * 100


def ritmo_medio(invii: list[float]) -> float:
    """Richieste al secondo tra il primo e l'ultimo invio. `invii` è ordinata e ha almeno due istanti."""
    if len(invii) < 2:
        raise ErroreDati("client.csv ha meno di due richieste: il ritmo non si può calcolare")
    if invii[-1] <= invii[0]:
        raise ErroreDati("client.csv: tutte le richieste hanno lo stesso istante di invio")
    return (len(invii) - 1) / (invii[-1] - invii[0])


def finestre(invii: list[float], ritmo_chiesto: float, durata_s: float) -> list[Finestra]:
    """Le finestre intere di `durata_s` secondi dalla prima richiesta, con richieste e scarto.

    `invii` è ordinata. Ogni finestra va dal suo inizio (incluso) a inizio + `durata_s` (escluso).
    """
    inizio = invii[0]
    intere = int((invii[-1] - inizio) // durata_s)
    risultato = []
    for i in range(intere):
        da = inizio + i * durata_s
        richieste = bisect_left(invii, da + durata_s) - bisect_left(invii, da)
        risultato.append((da, richieste, scarto_percentuale(richieste / durata_s, ritmo_chiesto)))
    return risultato


def leggi_invii(cartella: Path) -> list[float]:
    """Gli istanti di invio di `client.csv`, in ordine (il client scrive alla fine di ogni richiesta)."""
    return [t for t, _, _ in leggi_richieste(cartella)]


def tolleranza_predefinita() -> float:
    """La tolleranza sta in config/parametri.yaml, scritta una volta sola."""
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere la tolleranza da config/parametri.yaml: "
                 "pip install pyyaml, oppure passa --tolleranza")
    with open(PARAMETRI, encoding="utf-8") as f:
        return float(yaml.safe_load(f)["carichi"]["ritmo_tolleranza_percentuale"])


def con_segno(scarto: float) -> str:
    """Uno scarto in % con il segno e un decimale; uno scarto minuscolo e negativo non diventa «-0.0»."""
    return f"{round(scarto, 1) + 0.0:+.1f}"


def come_testo(secondi_epoca: float) -> str:
    return datetime.fromtimestamp(secondi_epoca, timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cartella", type=Path, help="cartella del run (data/<ambiente>/<run-id>)")
    parser.add_argument("--ritmo", type=float, required=True, help="richieste al secondo chieste al client")
    parser.add_argument("--tolleranza", type=float, default=None,
                        help="scarto ammesso in percentuale (predefinito: config/parametri.yaml)")
    parser.add_argument("--finestra", type=float, default=FINESTRA_S,
                        help=f"durata delle finestre in secondi (predefinito: {FINESTRA_S:g})")
    argomenti = parser.parse_args()
    if argomenti.ritmo <= 0 or argomenti.finestra <= 0:
        parser.error("--ritmo e --finestra devono essere maggiori di 0")
    tolleranza = argomenti.tolleranza if argomenti.tolleranza is not None else tolleranza_predefinita()
    ritmo, durata_finestra = argomenti.ritmo, argomenti.finestra

    try:
        invii = leggi_invii(argomenti.cartella)
        medio = ritmo_medio(invii)
    except ErroreDati as errore:
        sys.exit(f"errore: {errore}")
    per_finestra = finestre(invii, ritmo, durata_finestra)

    scarto_medio = scarto_percentuale(medio, ritmo)
    fuori = [f for f in per_finestra if abs(f[2]) > tolleranza]
    print(f"chiesto      {ritmo:g} richieste/s, tolleranza ±{tolleranza:g} %")
    print(f"inviate      {len(invii)} richieste in {invii[-1] - invii[0]:.1f} s")
    print(f"ritmo medio  {medio:.2f} richieste/s (scarto {con_segno(scarto_medio)} %)")
    if per_finestra:
        peggiore = max(per_finestra, key=lambda f: abs(f[2]))
        print(f"finestre     {len(per_finestra)} da {durata_finestra:g} s, scarto massimo "
              f"{con_segno(peggiore[2])} % (dalle {come_testo(peggiore[0])})")
    else:
        print(f"finestre     nessuna: il log dura meno di {durata_finestra:g} s, "
              "si controlla solo il ritmo medio")
    for da, richieste, scarto in fuori[:FINESTRE_ELENCATE]:
        print(f"  fuori      dalle {come_testo(da)}: {richieste / durata_finestra:.1f} richieste/s "
              f"({con_segno(scarto)} %)")
    if len(fuori) > FINESTRE_ELENCATE:
        print(f"  … e altre {len(fuori) - FINESTRE_ELENCATE} finestre fuori tolleranza")

    if abs(scarto_medio) > tolleranza or fuori:
        sys.exit("ritmo fuori tolleranza: il run non è valido")
    print("ritmo entro la tolleranza")


if __name__ == "__main__":
    main()
