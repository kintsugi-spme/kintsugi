"""Controlla che il client abbia inviato le richieste al ritmo chiesto, dal suo log.

    python analysis/ritmo.py data/<ambiente>/<run-id> --ritmo 50     ritmo costante (W1, W3)
    python analysis/ritmo.py data/<ambiente>/<run-id>                 il profilo di carico.json (W2, #117)

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

Senza `--ritmo` il ritmo chiesto viene da `carico.json`, che harness/jmeter/carico.py scrive nella cartella del
run: un elenco di tratti, ognuno con inizio e fine (secondi dalla prima richiesta) e ritmo. Per ogni finestra si
aspettano le richieste che i tratti prevedono in quei secondi: una finestra a cavallo di un cambio di ritmo (il
picco di W2) conta la media pesata dei due tratti. Il ritmo costante è il caso di un tratto solo. La finestra di
10 s è una scelta di questa verifica, riconfermata con JMeter (diario del 26/11).

Lo zero del profilo non è il primo invio: JMeter parte con qualche decimo di secondo di ritardo e recupera
mandando insieme le prime richieste, quindi il primo invio cade dopo lo zero del suo programma. Con un profilo
che cambia, mezzo secondo di sfasamento sposta 45 richieste da una finestra all'altra al confine del picco (run
del 26/11: +51 % e -5 %). Lo zero si ricava dagli invii del primo tratto: a ritmo regolare la richiesta i parte
a zero + i / ritmo, e la mediana di (istante - i / ritmo) è lo zero, senza che la raffica iniziale la sposti.
Si guardano solo i primi 10 s, così un ritmo sbagliato non sposta lo zero fino a nasconderlo. Con un ritmo
costante lo zero resta il primo invio: senza cambi di ritmo uno sfasamento non conta.
"""

import argparse
import json
import math
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
Tratto = tuple[float, float, float]  # (inizio, fine, ritmo): secondi dalla prima richiesta e richieste al secondo


def tratti_di(ritmo_chiesto: float | list[Tratto]) -> list[Tratto]:
    """Un ritmo costante è un tratto solo, senza fine."""
    if isinstance(ritmo_chiesto, (int, float)):
        return [(0.0, math.inf, float(ritmo_chiesto))]
    return ritmo_chiesto


def attese(tratti: list[Tratto], da_s: float, a_s: float) -> float:
    """Le richieste che il profilo prevede tra `da_s` e `a_s` secondi dalla prima: ritmo per tempo, tratto per tratto."""
    return sum(max(0.0, min(a_s, fine) - max(da_s, inizio)) * ritmo for inizio, fine, ritmo in tratti)


def leggi_profilo(cartella: Path) -> tuple[str, list[Tratto]]:
    """Il profilo che carico.py ha scritto in carico.json: nome e tratti."""
    percorso = cartella / "carico.json"
    if not percorso.exists():
        raise ErroreDati(f"{percorso} non c'è: passa --ritmo, o lancia il carico con harness/jmeter/carico.py")
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    try:
        tratti = [(float(t["inizio_s"]), float(t["fine_s"]), float(t["ritmo"])) for t in dati["tratti"]]
    except (KeyError, TypeError, ValueError) as errore:
        raise ErroreDati(f"{percorso}: tratti non leggibili ({errore})") from errore
    if not tratti or any(r <= 0 or f <= i for i, f, r in tratti):
        raise ErroreDati(f"{percorso}: servono tratti con ritmo positivo e fine dopo l'inizio")
    return dati.get("profilo", "?"), tratti


def scarto_percentuale(ritmo_inviato: float, ritmo_chiesto: float) -> float:
    return (ritmo_inviato / ritmo_chiesto - 1) * 100


def ritmo_medio(invii: list[float]) -> float:
    """Richieste al secondo tra il primo e l'ultimo invio. `invii` è ordinata e ha almeno due istanti."""
    if len(invii) < 2:
        raise ErroreDati("client.csv ha meno di due richieste: il ritmo non si può calcolare")
    if invii[-1] <= invii[0]:
        raise ErroreDati("client.csv: tutte le richieste hanno lo stesso istante di invio")
    return (len(invii) - 1) / (invii[-1] - invii[0])


def zero(invii: list[float], ritmo_chiesto: float | list[Tratto], primi_s: float = FINESTRA_S) -> float:
    """Lo zero del profilo: il primo invio con un tratto solo; altrimenti la mediana di (istante - i / ritmo)
    sulle richieste dei primi `primi_s` secondi del primo tratto."""
    tratti = tratti_di(ritmo_chiesto)
    if len(tratti) == 1:
        return invii[0]
    inizio, fine, r = tratti[0]
    quante = max(1, min(len(invii), int(min(fine - inizio, primi_s) * r)))
    scarti = sorted(invii[i] - i / r for i in range(quante))
    return scarti[len(scarti) // 2] - inizio


def finestre(invii: list[float], ritmo_chiesto: float | list[Tratto], durata_s: float) -> list[Finestra]:
    """Le finestre intere di `durata_s` secondi dallo zero del profilo, con richieste e scarto.

    `invii` è ordinata. Ogni finestra va dal suo inizio (incluso) a inizio + `durata_s` (escluso). Lo scarto è
    tra le richieste inviate e quelle attese dal profilo in quella finestra.
    """
    tratti = tratti_di(ritmo_chiesto)
    inizio = min(zero(invii, tratti), invii[0])
    intere = int((invii[-1] - inizio) // durata_s)
    risultato = []
    for i in range(intere):
        da = inizio + i * durata_s
        richieste = bisect_left(invii, da + durata_s) - bisect_left(invii, da)
        attese_qui = attese(tratti, i * durata_s, (i + 1) * durata_s)
        risultato.append((da, richieste, scarto_percentuale(richieste, attese_qui)))
    return risultato


def scarto_medio(invii: list[float], ritmo_chiesto: float | list[Tratto]) -> float:
    """Lo scarto del ritmo medio: richieste inviate meno una, contro quelle attese dallo zero all'ultima."""
    tratti = tratti_di(ritmo_chiesto)
    inizio = min(zero(invii, tratti), invii[0])
    return scarto_percentuale(len(invii) - 1, attese(tratti, 0, invii[-1] - inizio))


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
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("cartella", type=Path, help="cartella del run (data/<ambiente>/<run-id>)")
    parser.add_argument("--ritmo", type=float, default=None,
                        help="richieste al secondo chieste al client (senza: il profilo di carico.json)")
    parser.add_argument("--tolleranza", type=float, default=None,
                        help="scarto ammesso in percentuale (predefinito: config/parametri.yaml)")
    parser.add_argument("--finestra", type=float, default=FINESTRA_S,
                        help=f"durata delle finestre in secondi (predefinito: {FINESTRA_S:g})")
    argomenti = parser.parse_args()
    if (argomenti.ritmo is not None and argomenti.ritmo <= 0) or argomenti.finestra <= 0:
        parser.error("--ritmo e --finestra devono essere maggiori di 0")
    tolleranza = argomenti.tolleranza if argomenti.tolleranza is not None else tolleranza_predefinita()
    durata_finestra = argomenti.finestra

    try:
        if argomenti.ritmo is not None:
            chiesto, descritto = argomenti.ritmo, f"{argomenti.ritmo:g} richieste/s"
        else:
            nome, chiesto = leggi_profilo(argomenti.cartella)
            descritto = f"profilo {nome} di carico.json: " + ", ".join(
                f"{r:g}/s da {i:g} a {f:g} s" for i, f, r in chiesto)
        invii = leggi_invii(argomenti.cartella)
        medio = ritmo_medio(invii)
    except ErroreDati as errore:
        sys.exit(f"errore: {errore}")
    per_finestra = finestre(invii, chiesto, durata_finestra)

    scarto_del_medio = scarto_medio(invii, chiesto)
    fuori = [f for f in per_finestra if abs(f[2]) > tolleranza]
    print(f"chiesto      {descritto}, tolleranza ±{tolleranza:g} %")
    print(f"inviate      {len(invii)} richieste in {invii[-1] - invii[0]:.1f} s")
    print(f"ritmo medio  {medio:.2f} richieste/s (scarto {con_segno(scarto_del_medio)} %)")
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

    if abs(scarto_del_medio) > tolleranza or fuori:
        sys.exit("ritmo fuori tolleranza: il run non è valido")
    print("ritmo entro la tolleranza")


if __name__ == "__main__":
    main()
