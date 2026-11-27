"""Calcola quanto è durato il fermo dopo un guasto: dell'accettazione (client.csv) e del completamento (db.csv).

    python analysis/fermo.py data/<ambiente>/<run-id> --guasto 2026-11-12T10:02:00.123+00:00
    python analysis/fermo.py data/<ambiente>/<run-id>                 l'istante di `ts_guasto` in guasto.json
    python analysis/fermo.py data/<ambiente>/<run-id> --sensibilita   anche con gli altri limiti di parametri.yaml

**Accettazione.** L'istante del guasto è quello preso sul computer, con lo stesso orologio del client
(`ts_invio`): l'orologio del cluster differisce di qualche millisecondo e falserebbe la misura. Legge
`client.csv` (una riga per richiesta: istante di invio, esito, durata) e stampa:

    ripristino   il momento in cui il servizio è tornato a funzionare
    fermo        il tempo passato tra il guasto e il ripristino
    fallite      le richieste fallite per il guasto, comprese quelle già in corso quando è avvenuto

«Tornato a funzionare» (capitolo «Protocollo di misura»): da quel momento, per 5 secondi di fila, in
ogni secondo almeno il 99% delle richieste ha avuto esito 2xx. Per avere i millisecondi i secondi non
sono quelli del calendario: si prova a partire da ogni richiesta inviata dopo il guasto e si prende
la prima da cui i 5 secondi seguenti vanno bene.

**Completamento** (issue #124; è la misura decisiva in V3 e V5: con il database fermo l'API continua ad
accettare ma non si salva nulla). Se nella cartella c'è `db.csv`, stampa le stesse tre righe per il
completamento: un ordine è completato se `ts_scrittura - ts_ricezione` non supera il limite di
completamento (tempi.limite_completamento_s), e un secondo è disponibile se almeno il 99% degli ordini
*ricevuti* in quel secondo (`ts_ricezione`) è completato. Gli istanti di `db.csv` sono del cluster, quindi
l'istante del guasto è `ts_nodo` di `guasto.json`, non quello del computer (D0005).

Gli ordini ricevuti sono quelli di `db.csv` e quelli che il client ha visto accettare (2xx) ma che nel
database non ci sono mai arrivati: non hanno un `ts_ricezione`, e per loro si usa l'istante di invio più lo
sfasamento tra i due orologi (`ts_nodo - ts_guasto` di `guasto.json`, incerto al più di `incertezza_s`).
Un ordine mai salvato conta come non completato. Con `--limite S` (anche più volte) o `--sensibilita`
(i valori di tempi.limite_completamento_sensibilita_s) il calcolo si ripete con altri limiti.

Quando i due ripristini ci sono, il servizio è ripristinato quando lo sono entrambi: la riga `servizio`
prende il più tardivo. Se il log finisce prima di confermare i 5 secondi, lo script dice
«ripristino non avvenuto». Esce con codice 1 se i dati non tornano.
"""

import argparse
import json
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from itertools import accumulate
from pathlib import Path

from categorie import ErroreDati, esito_positivo, leggi_colonne, normalizza

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


Richiesta = tuple[float, bool, float]  # (istante di invio, esito positivo, secondi fino alla risposta)


def durata(testo: str) -> float:
    try:
        return float(testo)
    except ValueError:
        raise ErroreDati(f"client.csv, tempo_risposta_s: «{testo}» non è un numero") from None


def leggi_richieste(cartella: Path) -> list[Richiesta]:
    """Le richieste del client come (istante di invio, esito positivo, durata), in ordine di invio.

    Il client scrive una riga quando la richiesta finisce, non quando parte: l'ordine del file
    non è quello di invio, e va rimesso.
    """
    righe = leggi_colonne(cartella / "client.csv", ["ts_invio", "esito", "tempo_risposta_s"])
    richieste = [(istante(r["ts_invio"], "client.csv, ts_invio"), esito_positivo(r["esito"]),
                  durata(r["tempo_risposta_s"])) for r in righe]
    richieste.sort(key=lambda r: r[0])
    return richieste


def ripristino(richieste: list[Richiesta], t_guasto: float,
               secondi: int, soglia_percentuale: float) -> float | None:
    """Istante t_r del ripristino, o None se il log non basta a confermarlo.

    `richieste` è ordinata per istante di invio. Un secondo è disponibile se almeno
    `soglia_percentuale`% delle richieste inviate in quel secondo è riuscita. `secondi` e
    `soglia_percentuale` non hanno un predefinito: i valori stanno in config/parametri.yaml
    (vedi `parametri_predefiniti`) e riscriverli qui li farebbe restare indietro.
    """
    if not richieste:
        raise ErroreDati("client.csv non ha nessuna richiesta")
    istanti = [r[0] for r in richieste]
    if t_guasto < istanti[0]:
        raise ErroreDati("il guasto è prima della prima richiesta del client: istante sbagliato?")
    if t_guasto > istanti[-1]:
        raise ErroreDati("il guasto è dopo l'ultima richiesta del client: istante sbagliato?")
    riuscite = [0, *accumulate(1 if r[1] else 0 for r in richieste)]

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


def richieste_fallite(richieste: list[Richiesta], t_guasto: float, fino_a: float) -> int:
    """Richieste fallite per il guasto: quelle inviate dal guasto al ripristino e quelle che al
    momento del guasto erano già in corso (inviate prima, finite dopo): con un SIGKILL falliscono
    anche loro. Non dipende dalla soglia del 99%.
    """
    return sum(1 for t, ok, secondi in richieste
               if not ok and (t_guasto <= t < fino_a or t < t_guasto <= t + secondi))


def leggi_guasto(cartella: Path) -> dict:
    """guasto.json: serve `ts_nodo` (orologio del cluster) e `ts_guasto` (orologio del computer)."""
    percorso = cartella / "guasto.json"
    if not percorso.is_file():
        raise ErroreDati(f"manca il file {percorso}: l'istante del guasto sull'orologio del cluster è `ts_nodo` lì dentro")
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        return {"ts_guasto": istante(dati["ts_guasto"], "guasto.json, ts_guasto"),
                "ts_nodo": istante(dati["ts_nodo"], "guasto.json, ts_nodo")}
    except (json.JSONDecodeError, KeyError, TypeError) as errore:
        raise ErroreDati(f"{percorso}: servono ts_guasto e ts_nodo ({errore})") from None


Ordine = tuple[float, float | None]  # (istante di ricezione, istante di scrittura o None se mai salvato)


def leggi_ordini(cartella: Path, sfasamento_s: float) -> list[Ordine]:
    """Gli ordini ricevuti, sull'orologio del cluster, in ordine di ricezione.

    Quelli di `db.csv` hanno `ts_ricezione` e `ts_scrittura`. Quelli che il client ha visto accettare ma che
    nel database non ci sono hanno solo l'istante di invio: si porta sull'orologio del cluster con lo
    sfasamento. Gli ordini rifiutati (503, timeout) e mai salvati non sono stati ricevuti: non contano.
    """
    righe = leggi_colonne(cartella / "db.csv", ["id", "ts_ricezione", "ts_scrittura"])
    salvati = {normalizza(r["id"]): (istante(r["ts_ricezione"], "db.csv, ts_ricezione"),
                                     istante(r["ts_scrittura"], "db.csv, ts_scrittura")) for r in righe}
    ordini: list[Ordine] = list(salvati.values())
    for r in leggi_colonne(cartella / "client.csv", ["ts_invio", "id", "esito"]):
        if esito_positivo(r["esito"]) and normalizza(r["id"]) not in salvati:
            ordini.append((istante(r["ts_invio"], "client.csv, ts_invio") + sfasamento_s, None))
    ordini.sort(key=lambda o: o[0])
    return ordini


def completamento(ordini: list[Ordine], limite_s: float) -> list[Richiesta]:
    """Gli ordini come richieste per `ripristino`: riuscita = completato entro il limite (mai salvato: no)."""
    return [(ricevuto, scritto is not None and scritto - ricevuto <= limite_s, 0.0) for ricevuto, scritto in ordini]


def parametri_completamento() -> tuple[float, list[float]]:
    """Il limite di completamento e quelli della sensibilità, da config/parametri.yaml."""
    valori = leggi_parametri()
    return (float(valori["tempi"]["limite_completamento_s"]),
            [float(x) for x in valori["tempi"]["limite_completamento_sensibilita_s"]])


def leggi_parametri() -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit("serve PyYAML per leggere i valori da config/parametri.yaml: "
                 "pip install pyyaml, oppure passa --secondi, --soglia e --limite")
    with open(PARAMETRI, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parametri_predefiniti() -> tuple[int, float]:
    """I secondi consecutivi e la soglia stanno in config/parametri.yaml, scritti una volta sola."""
    valori = leggi_parametri()
    return (int(valori["run"]["ripristino_secondi_consecutivi"]),
            float(valori["tempi"]["soglia_secondo_disponibile_percentuale"]))


def come_testo(secondi_epoca: float) -> str:
    return datetime.fromtimestamp(secondi_epoca, timezone.utc).isoformat(timespec="milliseconds")


def numero(x: float) -> str:
    return f"{x:g}"


def stampa_accettazione(richieste: list[Richiesta], t_guasto: float, secondi: int, soglia: float) -> float | None:
    t_ripristino = ripristino(richieste, t_guasto, secondi, soglia)
    print(f"guasto     t_g = {come_testo(t_guasto)}")
    if t_ripristino is None:
        print(f"ripristino non avvenuto: il log finisce prima di {secondi} secondi consecutivi disponibili")
        print(f"richieste fallite per il guasto: {richieste_fallite(richieste, t_guasto, float('inf'))}")
        return None
    print(f"ripristino t_r = {come_testo(t_ripristino)}")
    print(f"fermo      t_r - t_g = {t_ripristino - t_guasto:.3f} s")
    print(f"richieste fallite per il guasto: {richieste_fallite(richieste, t_guasto, t_ripristino)}")
    return t_ripristino


def stampa_completamento(ordini: list[Ordine], t_guasto_nodo: float, limite_s: float, secondi: int,
                         soglia: float) -> float | None:
    """Le righe del completamento con un limite; restituisce il fermo (secondi) o None se non c'è ripristino."""
    richieste = completamento(ordini, limite_s)
    t_ripristino = ripristino(richieste, t_guasto_nodo, secondi, soglia)
    print(f"completamento, limite {numero(limite_s)} s (guasto sull'orologio del cluster, ts_nodo)")
    print(f"guasto     t_g = {come_testo(t_guasto_nodo)}")
    if t_ripristino is None:
        print(f"ripristino non avvenuto: gli ordini finiscono prima di {secondi} secondi consecutivi completati")
        print(f"ordini non completati per il guasto: {richieste_fallite(richieste, t_guasto_nodo, float('inf'))}")
        return None
    print(f"ripristino t_r = {come_testo(t_ripristino)}")
    print(f"fermo      t_r - t_g = {t_ripristino - t_guasto_nodo:.3f} s")
    print(f"ordini non completati per il guasto: {richieste_fallite(richieste, t_guasto_nodo, t_ripristino)}")
    return t_ripristino - t_guasto_nodo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cartella", type=Path, help="cartella del run (data/<ambiente>/<run-id>)")
    parser.add_argument("--guasto", default=None,
                        help="istante del guasto preso sul computer, con lo stesso orologio del client "
                             "(non quello del cluster), ISO 8601 con fuso orario "
                             "(es. 2026-11-12T10:02:00.123+00:00); predefinito: `ts_guasto` di guasto.json")
    parser.add_argument("--secondi", type=int, default=None,
                        help="secondi consecutivi disponibili (predefinito: config/parametri.yaml)")
    parser.add_argument("--soglia", type=float, default=None,
                        help="percentuale di richieste riuscite di un secondo disponibile (predefinito: config/parametri.yaml)")
    parser.add_argument("--limite", type=float, action="append", default=None, metavar="S",
                        help="limite di completamento in secondi, anche più volte (predefinito: tempi.limite_completamento_s)")
    parser.add_argument("--sensibilita", action="store_true",
                        help="il completamento anche con i valori di tempi.limite_completamento_sensibilita_s")
    argomenti = parser.parse_args()
    secondi, soglia = argomenti.secondi, argomenti.soglia
    if secondi is None or soglia is None:
        predefinito = parametri_predefiniti()
        secondi = predefinito[0] if secondi is None else secondi
        soglia = predefinito[1] if soglia is None else soglia

    try:
        guasto = leggi_guasto(argomenti.cartella) if (argomenti.cartella / "guasto.json").is_file() else None
        if argomenti.guasto is not None:
            t_guasto = istante(argomenti.guasto, "--guasto")
        elif guasto is not None:
            t_guasto = guasto["ts_guasto"]
        else:
            raise ErroreDati("serve --guasto, oppure guasto.json nella cartella")
        richieste = leggi_richieste(argomenti.cartella)
        t_accettazione = stampa_accettazione(richieste, t_guasto, secondi, soglia)

        if (argomenti.cartella / "db.csv").is_file():
            if guasto is None:
                leggi_guasto(argomenti.cartella)  # solleva l'errore: manca guasto.json
            limite, sensibilita = parametri_completamento()
            limiti = argomenti.limite or [limite]
            if argomenti.sensibilita:
                limiti += [x for x in sensibilita if x not in limiti]
            ordini = leggi_ordini(argomenti.cartella, guasto["ts_nodo"] - guasto["ts_guasto"])
            fermi = {}
            for x in limiti:
                print()
                fermi[x] = stampa_completamento(ordini, guasto["ts_nodo"], x, secondi, soglia)
            principale = limiti[0]
            if t_accettazione is not None and fermi[principale] is not None:
                fermo_servizio = max(t_accettazione - t_guasto, fermi[principale])
                print(f"\nservizio   fermo = {fermo_servizio:.3f} s (ripristinato quando lo sono "
                      f"accettazione e completamento, limite {numero(principale)} s)")
    except ErroreDati as errore:
        sys.exit(f"errore: {errore}")


if __name__ == "__main__":
    main()
