"""Assegna ogni ordine inviato dal client a una categoria e scrive categorie.csv.

Documento di architettura, capitolo «Protocollo di misura», sezione «Categorie degli ordini».
Si lancia a fine run, sulla cartella del run (data/README.md):

    python analysis/categorie.py data/<ambiente>/<run-id>

Legge quattro file della cartella, che devono esserci tutti (vuoti, con la sola intestazione, se
non c'è nulla da dire: per esempio in V1 e V2 non c'è la coda dei falliti):

    client.csv     ordini inviati e esito visto dal client (colonne id, esito)
    db.csv         ordini salvati nel database (colonna id)
    falliti.csv    ordini nella coda dei falliti (colonna id)
    duplicati.csv  arrivi di un id già presente, uno per riga (colonna id)

Per ogni id inviato il percorso è quello della figura del documento:

    esito positivo (2xx)?  sì → nel database?  sì → completato in tempo
                                               no → nei falliti? sì → in dead-letter
                                                                 no → perso
                           no → nel database?  sì → completato dopo il timeout
                                               no → fallito

I duplicati non sono una categoria: si contano a parte, nella colonna `duplicati`.

Esce con codice 1 se i dati non tornano (id nel database ma mai inviato, id inviato due volte…):
il documento chiede di esaminare il run prima di proseguire la campagna.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

COMPLETATO_IN_TEMPO = "completato in tempo"
COMPLETATO_DOPO_TIMEOUT = "completato dopo il timeout"
FALLITO = "fallito"
IN_DEAD_LETTER = "in dead-letter"
PERSO = "perso"
CATEGORIE = [COMPLETATO_IN_TEMPO, COMPLETATO_DOPO_TIMEOUT, FALLITO, IN_DEAD_LETTER, PERSO]

COLONNE = ["id", "categoria", "duplicati"]


class ErroreDati(Exception):
    """File mancante o senza la colonna attesa: l'esportazione del run è sbagliata."""


def normalizza(id_ordine: str) -> str:
    return id_ordine.strip().lower()


def leggi_colonne(percorso: Path, colonne: list[str]) -> list[dict[str, str]]:
    if not percorso.is_file():
        raise ErroreDati(f"manca il file {percorso}")
    with open(percorso, newline="", encoding="utf-8") as f:
        lettore = csv.DictReader(f)
        mancanti = [c for c in colonne if c not in (lettore.fieldnames or [])]
        if mancanti:
            raise ErroreDati(f"{percorso.name}: manca la colonna {', '.join(mancanti)}")
        return [{c: riga[c] for c in colonne} for riga in lettore]


def esito_positivo(esito: str) -> bool:
    """Codici 2xx (201 in V1 e V2, 202 in V3). «timeout», «errore» e 4xx/5xx non lo sono."""
    return esito.strip().isdigit() and 200 <= int(esito) < 300


def categoria(positivo: bool, nel_database: bool, nei_falliti: bool) -> str:
    if positivo:
        if nel_database:
            return COMPLETATO_IN_TEMPO
        return IN_DEAD_LETTER if nei_falliti else PERSO
    return COMPLETATO_DOPO_TIMEOUT if nel_database else FALLITO


def classifica(cartella: Path) -> tuple[list[dict], list[str]]:
    """Restituisce le righe di categorie.csv (nell'ordine del log del client) e le anomalie."""
    client = leggi_colonne(cartella / "client.csv", ["id", "esito"])
    database = [normalizza(r["id"]) for r in leggi_colonne(cartella / "db.csv", ["id"])]
    falliti = [normalizza(r["id"]) for r in leggi_colonne(cartella / "falliti.csv", ["id"])]
    duplicati = Counter(normalizza(r["id"]) for r in leggi_colonne(cartella / "duplicati.csv", ["id"]))

    anomalie: list[str] = []
    inviati: dict[str, str] = {}
    for riga in client:
        id_ordine = normalizza(riga["id"])
        if id_ordine in inviati:
            anomalie.append(f"{id_ordine}: compare più volte in client.csv")
        else:
            inviati[id_ordine] = riga["esito"]

    for nome, ids in (("db.csv", database), ("falliti.csv", falliti)):
        for id_ordine, volte in Counter(ids).items():
            if id_ordine not in inviati:
                anomalie.append(f"{id_ordine}: è in {nome} ma il client non l'ha inviato")
            elif nome == "db.csv" and volte > 1:
                anomalie.append(f"{id_ordine}: compare {volte} volte in db.csv")
    for id_ordine in duplicati:
        if id_ordine not in inviati:
            anomalie.append(f"{id_ordine}: è in duplicati.csv ma il client non l'ha inviato")

    nel_database, nei_falliti = set(database), set(falliti)
    righe = [
        {
            "id": id_ordine,
            "categoria": categoria(esito_positivo(esito), id_ordine in nel_database,
                                   id_ordine in nei_falliti),
            "duplicati": duplicati.get(id_ordine, 0),
        }
        for id_ordine, esito in inviati.items()
    ]
    return righe, anomalie


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("cartella", type=Path, help="cartella del run (data/<ambiente>/<run-id>)")
    parser.add_argument("--uscita", type=Path, default=None,
                        help="file da scrivere (predefinito: categorie.csv nella cartella)")
    argomenti = parser.parse_args()
    uscita = argomenti.uscita or argomenti.cartella / "categorie.csv"

    try:
        righe, anomalie = classifica(argomenti.cartella)
    except ErroreDati as errore:
        sys.exit(f"errore: {errore}")

    with open(uscita, "w", newline="", encoding="utf-8") as f:
        scrittore = csv.DictWriter(f, fieldnames=COLONNE)
        scrittore.writeheader()
        scrittore.writerows(righe)

    conteggi = Counter(r["categoria"] for r in righe)
    print(f"{len(righe)} ordini inviati; categorie in {uscita}")
    for nome in CATEGORIE:
        print(f"  {nome}: {conteggi[nome]}")
    print(f"  duplicati (a parte): {sum(r['duplicati'] for r in righe)}")
    if anomalie:
        print(f"\nATTENZIONE: {len(anomalie)} anomalie, il run va esaminato prima di proseguire:",
              file=sys.stderr)
        for anomalia in anomalie:
            print(f"  - {anomalia}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
