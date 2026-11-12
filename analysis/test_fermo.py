"""Prove dello script del ripristino e del fermo (solo libreria standard, nessun servizio).

    pytest -q analysis
"""

import csv
import random
from datetime import datetime, timedelta, timezone

import pytest

import fermo
from categorie import ErroreDati

INIZIO = datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc).timestamp()


def richieste_a_ritmo(ritmo, durata, guasto_da=None, guasto_a=None, eccezioni=()):
    """Richieste inviate a `ritmo` al secondo per `durata` secondi (istanti relativi a INIZIO).

    Quelle inviate tra `guasto_da` e `guasto_a` falliscono; `eccezioni` sono altri istanti, fuori
    da quell'intervallo, che falliscono lo stesso. Restituisce [(istante assoluto, riuscita)].
    """
    risultato = []
    for k in range(int(durata * ritmo)):
        t = k / ritmo
        fallita = (guasto_da is not None and guasto_da <= t < guasto_a) or any(
            abs(t - e) < 0.5 / ritmo for e in eccezioni)
        risultato.append((INIZIO + t, not fallita))
    return risultato


def test_con_un_fermo_il_ripristino_e_la_prima_richiesta_dopo_la_fine_del_guasto():
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=14.3)
    t_r = fermo.ripristino(richieste, INIZIO + 10)
    assert t_r == pytest.approx(INIZIO + 14.3, abs=0.05)  # una richiesta ogni 50 ms


def test_il_fermo_ha_una_risoluzione_sotto_il_secondo():
    richieste = richieste_a_ritmo(50, 40, guasto_da=10, guasto_a=13.14)
    fermo_s = fermo.ripristino(richieste, INIZIO + 10) - (INIZIO + 10)
    assert fermo_s == pytest.approx(3.14, abs=0.02)
    assert fermo_s != round(fermo_s)


def test_senza_nessun_fermo_visibile_il_fermo_e_zero():
    richieste = richieste_a_ritmo(20, 30)
    assert fermo.ripristino(richieste, INIZIO + 10) == INIZIO + 10


def test_se_il_servizio_non_torna_non_c_e_ripristino():
    richieste = richieste_a_ritmo(20, 30, guasto_da=10, guasto_a=1000)
    assert fermo.ripristino(richieste, INIZIO + 10) is None


def test_se_il_log_finisce_prima_di_confermare_i_cinque_secondi_non_c_e_ripristino():
    richieste = richieste_a_ritmo(20, 30, guasto_da=10, guasto_a=27)  # torna a 27 s, il log finisce a 30
    assert fermo.ripristino(richieste, INIZIO + 10) is None


def test_un_singolo_errore_dopo_il_ritorno_sposta_il_ripristino():
    # A 20 richieste al secondo un errore su 20 è il 95%: quel secondo non è disponibile.
    richieste = richieste_a_ritmo(20, 60, guasto_da=10, guasto_a=12, eccezioni=(14.0,))
    t_r = fermo.ripristino(richieste, INIZIO + 10)
    assert t_r == pytest.approx(INIZIO + 14.05, abs=0.06)  # dopo l'errore isolato, non a 12 s


def test_la_soglia_del_99_per_cento_ammette_un_errore_su_cento():
    richieste = richieste_a_ritmo(100, 30, eccezioni=(12.0,))  # 1 su 100 in quel secondo: 99%
    assert fermo.ripristino(richieste, INIZIO + 10, soglia_percentuale=99) == INIZIO + 10
    # Con la soglia al 100% il secondo dell'errore non è disponibile: il ripristino è dopo di lui.
    assert fermo.ripristino(richieste, INIZIO + 10, soglia_percentuale=100) == pytest.approx(INIZIO + 12.01, abs=0.011)


def test_un_buco_di_secondi_senza_richieste_non_e_disponibile():
    richieste = [r for r in richieste_a_ritmo(20, 40) if not 12 <= r[0] - INIZIO < 15]
    t_r = fermo.ripristino(richieste, INIZIO + 10)
    assert t_r == pytest.approx(INIZIO + 15.0, abs=0.06)


def test_i_secondi_consecutivi_si_possono_cambiare():
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=12, eccezioni=(16.0,))
    con_tre = fermo.ripristino(richieste, INIZIO + 10, secondi=3)
    assert con_tre == pytest.approx(INIZIO + 12.0, abs=0.06)  # [12, 15) non tocca l'errore a 16 s
    con_cinque = fermo.ripristino(richieste, INIZIO + 10, secondi=5)
    assert con_cinque == pytest.approx(INIZIO + 16.05, abs=0.06)  # [12, 17) lo contiene


def test_le_richieste_fallite_si_contano_tra_guasto_e_ripristino():
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=12)
    t_r = fermo.ripristino(richieste, INIZIO + 10)
    assert fermo.richieste_fallite(richieste, INIZIO + 10, t_r) == 40


def test_il_guasto_fuori_dal_log_e_un_errore():
    richieste = richieste_a_ritmo(20, 30)
    with pytest.raises(ErroreDati, match="prima della prima"):
        fermo.ripristino(richieste, INIZIO - 5)
    with pytest.raises(ErroreDati, match="dopo l'ultima"):
        fermo.ripristino(richieste, INIZIO + 500)
    with pytest.raises(ErroreDati, match="nessuna richiesta"):
        fermo.ripristino([], INIZIO)


def scrivi_client(cartella, richieste, ordine=None):
    """Scrive client.csv. Il client scrive alla fine di ogni richiesta, quindi l'ordine è sparso."""
    righe = [[datetime.fromtimestamp(t, timezone.utc).isoformat(), f"id{k}",
              "201" if ok else "timeout", "0.01"] for k, (t, ok) in enumerate(richieste)]
    if ordine == "sparso":
        random.Random(1).shuffle(righe)
    with open(cartella / "client.csv", "w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(["ts_invio", "id", "esito", "tempo_risposta_s"])
        scrittore.writerows(righe)


def test_il_file_del_client_si_legge_anche_con_le_righe_fuori_ordine(tmp_path):
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=14.3)
    scrivi_client(tmp_path, richieste, ordine="sparso")
    lette = fermo.leggi_richieste(tmp_path)
    assert [t for t, _ in lette] == sorted(t for t, _ in lette)
    assert fermo.ripristino(lette, INIZIO + 10) == pytest.approx(INIZIO + 14.3, abs=0.05)


@pytest.mark.parametrize("esito, riuscita", [("201", True), ("202", True), ("503", False),
                                              ("timeout", False), ("errore", False)])
def test_solo_i_codici_2xx_sono_riusciti(tmp_path, esito, riuscita):
    with open(tmp_path / "client.csv", "w", newline="", encoding="utf-8") as f:
        f.write("ts_invio,id,esito,tempo_risposta_s\n2026-11-12T10:00:00+00:00,a,%s,0.1\n" % esito)
    assert fermo.leggi_richieste(tmp_path)[0][1] is riuscita


def test_un_file_mancante_o_una_riga_incompleta_sono_errori(tmp_path):
    with pytest.raises(ErroreDati, match="manca il file"):
        fermo.leggi_richieste(tmp_path)
    (tmp_path / "client.csv").write_text("ts_invio,id,esito,tempo_risposta_s\n2026-11-12T10:00:00+00:00,a\n")
    with pytest.raises(ErroreDati, match="incompleta"):
        fermo.leggi_richieste(tmp_path)


def test_un_istante_senza_fuso_orario_o_non_valido_e_un_errore():
    with pytest.raises(ErroreDati, match="fuso orario"):
        fermo.istante("2026-11-12T10:00:00", "--guasto")
    with pytest.raises(ErroreDati, match="ISO 8601"):
        fermo.istante("ieri", "--guasto")
    assert fermo.istante("2026-11-12T10:00:00.250Z", "--guasto") == INIZIO + 0.25
    assert fermo.istante("2026-11-12T12:00:00+02:00", "--guasto") == INIZIO


def lancia(monkeypatch, capsys, cartella, *argomenti):
    monkeypatch.setattr("sys.argv", ["fermo.py", str(cartella), "--secondi", "5", "--soglia", "99", *argomenti])
    fermo.main()
    return capsys.readouterr().out


def test_da_riga_di_comando_stampa_ripristino_fermo_e_richieste_fallite(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=14.3))
    guasto = datetime.fromtimestamp(INIZIO + 10, timezone.utc).isoformat()
    uscita = lancia(monkeypatch, capsys, tmp_path, "--guasto", guasto)
    assert "t_r = 2026-11-12T10:00:14.30" in uscita
    assert "fermo      t_r - t_g = 4.300 s" in uscita
    assert "richieste fallite tra guasto e ripristino: 86" in uscita


def test_da_riga_di_comando_dice_quando_il_ripristino_non_e_avvenuto(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, richieste_a_ritmo(20, 30, guasto_da=10, guasto_a=1000))
    guasto = datetime.fromtimestamp(INIZIO + 10, timezone.utc).isoformat()
    uscita = lancia(monkeypatch, capsys, tmp_path, "--guasto", guasto)
    assert "ripristino non avvenuto" in uscita
    assert "fermo      t_r" not in uscita


def test_da_riga_di_comando_i_dati_sbagliati_escono_con_errore(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit, match="manca il file"):
        lancia(monkeypatch, capsys, tmp_path, "--guasto", "2026-11-12T10:00:10+00:00")
