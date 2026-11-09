"""Prove dello script delle categorie (solo libreria standard, nessun servizio da avviare).

    pytest -q analysis
"""

import csv
import sys
import uuid

import pytest

import categorie


def nuovo_id() -> str:
    return str(uuid.uuid4())


def scrivi(cartella, nome, intestazione, righe):
    with open(cartella / nome, "w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(intestazione)
        scrittore.writerows(righe)


def prepara_run(cartella, inviati, database=(), falliti=(), duplicati=()):
    """Scrive i quattro file di un run. `inviati` è una lista di (id, esito)."""
    scrivi(cartella, "client.csv", ["ts_invio", "id", "esito", "tempo_risposta_s"],
           [["2026-11-09T10:00:00+00:00", i, esito, "0.01"] for i, esito in inviati])
    scrivi(cartella, "db.csv", ["id", "ts_ricezione", "ts_scrittura"],
           [[i, "2026-11-09T10:00:00+00:00", "2026-11-09T10:00:01+00:00"] for i in database])
    scrivi(cartella, "falliti.csv", ["id"], [[i] for i in falliti])
    scrivi(cartella, "duplicati.csv", ["id"], [[i] for i in duplicati])


def categorie_di(cartella):
    righe, anomalie = categorie.classifica(cartella)
    return {r["id"]: r["categoria"] for r in righe}, anomalie


@pytest.mark.parametrize("esito, nel_database, nei_falliti, atteso", [
    ("201", True, False, categorie.COMPLETATO_IN_TEMPO),
    ("202", True, False, categorie.COMPLETATO_IN_TEMPO),
    ("202", False, True, categorie.IN_DEAD_LETTER),
    ("202", False, False, categorie.PERSO),
    ("201", False, False, categorie.PERSO),
    ("timeout", True, False, categorie.COMPLETATO_DOPO_TIMEOUT),
    ("503", True, False, categorie.COMPLETATO_DOPO_TIMEOUT),
    ("errore", False, False, categorie.FALLITO),
    ("503", False, False, categorie.FALLITO),
    # Il database prevale sulla coda dei falliti, come nella figura del documento.
    ("202", True, True, categorie.COMPLETATO_IN_TEMPO),
    ("timeout", True, True, categorie.COMPLETATO_DOPO_TIMEOUT),
    # Per chi ha visto un errore, la coda dei falliti non cambia la categoria.
    ("timeout", False, True, categorie.FALLITO),
])
def test_le_cinque_categorie(tmp_path, esito, nel_database, nei_falliti, atteso):
    i = nuovo_id()
    prepara_run(tmp_path, [(i, esito)], database=[i] if nel_database else [],
                falliti=[i] if nei_falliti else [])
    assegnate, anomalie = categorie_di(tmp_path)
    assert assegnate == {i: atteso}
    assert anomalie == []


@pytest.mark.parametrize("esito, atteso", [
    ("200", True), ("201", True), ("202", True), ("299", True),
    ("199", False), ("300", False), ("400", False), ("422", False), ("503", False),
    ("timeout", False), ("errore", False), ("", False),
])
def test_esito_positivo_sono_i_codici_2xx(esito, atteso):
    assert categorie.esito_positivo(esito) is atteso


def test_ogni_id_inviato_ha_esattamente_una_categoria(tmp_path):
    inviati = [(nuovo_id(), esito) for esito in
               ["201", "202", "202", "202", "timeout", "errore", "503", "202", "201", "timeout"]]
    ids = [i for i, _ in inviati]
    prepara_run(tmp_path, inviati, database=[ids[0], ids[1], ids[4], ids[8]], falliti=[ids[2]])
    righe, anomalie = categorie.classifica(tmp_path)
    assert anomalie == []
    assert [r["id"] for r in righe] == ids  # nell'ordine del log, nessuno manca o è doppio
    assert all(r["categoria"] in categorie.CATEGORIE for r in righe)


def test_i_duplicati_si_contano_a_parte_senza_cambiare_la_categoria(tmp_path):
    a, b = nuovo_id(), nuovo_id()
    prepara_run(tmp_path, [(a, "201"), (b, "201")], database=[a, b], duplicati=[a, a, a])
    righe, anomalie = categorie.classifica(tmp_path)
    assert anomalie == []
    assert {r["id"]: (r["categoria"], r["duplicati"]) for r in righe} == {
        a: (categorie.COMPLETATO_IN_TEMPO, 3),
        b: (categorie.COMPLETATO_IN_TEMPO, 0),
    }


def test_maiuscole_e_spazi_negli_id_non_contano(tmp_path):
    i = nuovo_id()
    prepara_run(tmp_path, [(i, "201")], database=[f" {i.upper()} "])
    assegnate, anomalie = categorie_di(tmp_path)
    assert assegnate == {i: categorie.COMPLETATO_IN_TEMPO}
    assert anomalie == []


def test_un_id_nel_database_mai_inviato_e_un_anomalia(tmp_path):
    inviato, estraneo = nuovo_id(), nuovo_id()
    prepara_run(tmp_path, [(inviato, "201")], database=[inviato, estraneo])
    righe, anomalie = categorie.classifica(tmp_path)
    assert [r["id"] for r in righe] == [inviato]
    assert len(anomalie) == 1 and estraneo in anomalie[0] and "db.csv" in anomalie[0]


def test_un_id_nei_falliti_o_nei_duplicati_mai_inviato_e_un_anomalia(tmp_path):
    inviato, a, b = nuovo_id(), nuovo_id(), nuovo_id()
    prepara_run(tmp_path, [(inviato, "201")], database=[inviato], falliti=[a], duplicati=[b])
    _, anomalie = categorie.classifica(tmp_path)
    assert len(anomalie) == 2
    assert any(a in x and "falliti.csv" in x for x in anomalie)
    assert any(b in x and "duplicati.csv" in x for x in anomalie)


def test_un_id_inviato_due_volte_e_un_anomalia_e_conta_una_volta(tmp_path):
    i = nuovo_id()
    prepara_run(tmp_path, [(i, "201"), (i, "201")], database=[i])
    righe, anomalie = categorie.classifica(tmp_path)
    assert len(righe) == 1
    assert len(anomalie) == 1 and "più volte" in anomalie[0]


def test_un_id_due_volte_nel_database_e_un_anomalia(tmp_path):
    i = nuovo_id()
    prepara_run(tmp_path, [(i, "201")], database=[i, i])
    _, anomalie = categorie.classifica(tmp_path)
    assert len(anomalie) == 1 and "2 volte in db.csv" in anomalie[0]


@pytest.mark.parametrize("mancante", ["client.csv", "db.csv", "falliti.csv", "duplicati.csv"])
def test_un_file_mancante_e_un_errore(tmp_path, mancante):
    prepara_run(tmp_path, [(nuovo_id(), "201")])
    (tmp_path / mancante).unlink()
    with pytest.raises(categorie.ErroreDati, match=mancante):
        categorie.classifica(tmp_path)


def test_una_colonna_mancante_e_un_errore(tmp_path):
    prepara_run(tmp_path, [(nuovo_id(), "201")])
    scrivi(tmp_path, "db.csv", ["ordine"], [])
    with pytest.raises(categorie.ErroreDati, match="manca la colonna id"):
        categorie.classifica(tmp_path)


def test_run_senza_coda_con_file_vuoti(tmp_path):
    """V1 e V2: nessuna coda dei falliti, il file c'è ma ha solo l'intestazione."""
    ok, ko = nuovo_id(), nuovo_id()
    prepara_run(tmp_path, [(ok, "201"), (ko, "503")], database=[ok])
    assegnate, anomalie = categorie_di(tmp_path)
    assert assegnate == {ok: categorie.COMPLETATO_IN_TEMPO, ko: categorie.FALLITO}
    assert anomalie == []


def lancia(monkeypatch, *argomenti):
    monkeypatch.setattr(sys, "argv", ["categorie.py", *argomenti])
    with pytest.raises(SystemExit) as uscita:
        categorie.main()
    return uscita.value.code


def test_main_scrive_categorie_csv_e_il_riepilogo(tmp_path, monkeypatch, capsys):
    a, b = nuovo_id(), nuovo_id()
    prepara_run(tmp_path, [(a, "201"), (b, "202")], database=[a], falliti=[b], duplicati=[a])
    monkeypatch.setattr(sys, "argv", ["categorie.py", str(tmp_path)])
    categorie.main()
    with open(tmp_path / "categorie.csv", newline="", encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    assert righe == [
        {"id": a, "categoria": categorie.COMPLETATO_IN_TEMPO, "duplicati": "1"},
        {"id": b, "categoria": categorie.IN_DEAD_LETTER, "duplicati": "0"},
    ]
    uscita = capsys.readouterr().out
    assert "2 ordini inviati" in uscita and "in dead-letter: 1" in uscita
    assert "duplicati (a parte): 1" in uscita


def test_main_con_anomalie_scrive_il_file_ma_esce_con_codice_1(tmp_path, monkeypatch, capsys):
    inviato, estraneo = nuovo_id(), nuovo_id()
    prepara_run(tmp_path, [(inviato, "201")], database=[inviato, estraneo])
    assert lancia(monkeypatch, str(tmp_path)) == 1
    assert (tmp_path / "categorie.csv").is_file()
    assert estraneo in capsys.readouterr().err


def test_main_con_file_mancante_non_scrive_nulla(tmp_path, monkeypatch):
    prepara_run(tmp_path, [(nuovo_id(), "201")])
    (tmp_path / "falliti.csv").unlink()
    codice = lancia(monkeypatch, str(tmp_path))
    assert "falliti.csv" in str(codice)
    assert not (tmp_path / "categorie.csv").exists()


def test_main_accetta_un_file_di_uscita_diverso(tmp_path, monkeypatch):
    i = nuovo_id()
    prepara_run(tmp_path, [(i, "201")], database=[i])
    altro = tmp_path / "altro.csv"
    monkeypatch.setattr(sys, "argv", ["categorie.py", str(tmp_path), "--uscita", str(altro)])
    categorie.main()
    assert altro.is_file() and not (tmp_path / "categorie.csv").exists()
