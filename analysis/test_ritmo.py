"""Prove dello script del ritmo inviato (solo libreria standard, nessun servizio).

    pytest -q analysis
"""

import csv
import json
import random
from datetime import datetime, timezone

import pytest

import ritmo
from categorie import ErroreDati

INIZIO = datetime(2026, 11, 14, 10, 0, 0, tzinfo=timezone.utc).timestamp()
TOLLERANZA = 5  # il valore di config/parametri.yaml: le prove lo passano a mano


def invii_a_ritmo(ritmo_al_secondo, durata, buchi=()):
    """Istanti di invio (assoluti) di un client a ritmo fisso per `durata` secondi.

    Dai `buchi`, coppie (da, a) in secondi dall'inizio, non parte nessuna richiesta: è ciò che
    farebbe un generatore a modello chiuso mentre aspetta le risposte durante un guasto.
    """
    istanti = [k / ritmo_al_secondo for k in range(int(durata * ritmo_al_secondo))]
    return [INIZIO + t for t in istanti if not any(da <= t < a for da, a in buchi)]


def scrivi_client(cartella, invii, ordine=None):
    """Scrive client.csv. Il client scrive alla fine di ogni richiesta, quindi l'ordine è sparso."""
    righe = [[datetime.fromtimestamp(t, timezone.utc).isoformat(), f"id{k}", "201", "0.01"]
             for k, t in enumerate(invii)]
    if ordine == "sparso":
        random.Random(1).shuffle(righe)
    with open(cartella / "client.csv", "w", newline="", encoding="utf-8") as f:
        scrittore = csv.writer(f)
        scrittore.writerow(["ts_invio", "id", "esito", "tempo_risposta_s"])
        scrittore.writerows(righe)


def test_il_ritmo_medio_e_le_richieste_meno_una_diviso_la_durata():
    # 200 richieste a 20 al secondo: dalla prima all'ultima passano 9,95 s
    assert ritmo.ritmo_medio(invii_a_ritmo(20, 10)) == pytest.approx(20)


def test_un_client_a_ritmo_fisso_ha_tutte_le_finestre_al_ritmo_chiesto():
    invii = invii_a_ritmo(50, 60)
    trovate = ritmo.finestre(invii, 50, 10)

    assert len(trovate) == 5  # l'ultimo tratto, sotto i 10 s, non è una finestra
    assert all(richieste == 500 for _, richieste, _ in trovate)
    assert all(abs(scarto) < 0.5 for _, _, scarto in trovate)


def test_le_finestre_partono_dalla_prima_richiesta():
    invii = invii_a_ritmo(50, 30)
    assert ritmo.finestre(invii, 50, 10)[0][0] == invii[0]
    assert ritmo.finestre(invii, 50, 10)[1][0] == pytest.approx(invii[0] + 10)


def test_il_log_sotto_una_finestra_non_ha_finestre():
    assert ritmo.finestre(invii_a_ritmo(50, 8), 50, 10) == []


def test_un_buco_si_vede_nelle_finestre_anche_se_la_media_resta_nei_limiti():
    """5 s senza invii in 3 minuti: la media cala del 2,8%, ma la finestra dal 60° al 70° s dimezza."""
    invii = invii_a_ritmo(50, 180, buchi=[(60, 65)])

    assert abs(ritmo.scarto_percentuale(ritmo.ritmo_medio(invii), 50)) < TOLLERANZA
    peggiore = min(ritmo.finestre(invii, 50, 10), key=lambda f: f[2])
    assert peggiore[1] == 250
    assert peggiore[2] == pytest.approx(-50)


def test_lo_scarto_e_in_percentuale_del_ritmo_chiesto():
    assert ritmo.scarto_percentuale(45, 50) == pytest.approx(-10)
    assert ritmo.scarto_percentuale(52.5, 50) == pytest.approx(5)


def test_pochi_dati_sono_errori():
    with pytest.raises(ErroreDati, match="meno di due"):
        ritmo.ritmo_medio([INIZIO])
    with pytest.raises(ErroreDati, match="meno di due"):
        ritmo.ritmo_medio([])
    with pytest.raises(ErroreDati, match="stesso istante"):
        ritmo.ritmo_medio([INIZIO, INIZIO, INIZIO])


def test_il_file_del_client_si_legge_anche_con_le_righe_fuori_ordine(tmp_path):
    invii = invii_a_ritmo(20, 5)
    scrivi_client(tmp_path, invii, ordine="sparso")
    letti = ritmo.leggi_invii(tmp_path)

    assert letti == sorted(letti)
    assert letti == pytest.approx(invii, abs=1e-6)


def lancia(monkeypatch, capsys, cartella, *argomenti):
    monkeypatch.setattr("sys.argv", ["ritmo.py", str(cartella), "--tolleranza", str(TOLLERANZA), *argomenti])
    ritmo.main()
    return capsys.readouterr().out


def test_da_riga_di_comando_un_ritmo_giusto_e_entro_la_tolleranza(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, invii_a_ritmo(50, 60))
    uscita = lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")

    assert "chiesto      50 richieste/s, tolleranza ±5 %" in uscita
    assert "inviate      3000 richieste in 60.0 s" in uscita
    assert "ritmo medio  50.00 richieste/s" in uscita
    assert "finestre     5 da 10 s" in uscita
    assert "ritmo entro la tolleranza" in uscita


@pytest.mark.parametrize("inviato, dentro", [(48, True), (52, True), (47, False), (53, False)])
def test_il_confine_e_il_cinque_per_cento(tmp_path, monkeypatch, capsys, inviato, dentro):
    scrivi_client(tmp_path, invii_a_ritmo(inviato, 60))
    if dentro:
        assert "ritmo entro la tolleranza" in lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")
    else:
        with pytest.raises(SystemExit, match="fuori tolleranza"):
            lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")


def test_da_riga_di_comando_un_buco_rende_il_run_non_valido_e_dice_dove(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, invii_a_ritmo(50, 180, buchi=[(60, 65)]))
    with pytest.raises(SystemExit, match="fuori tolleranza"):
        lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")

    uscita = capsys.readouterr().out
    assert "scarto massimo -50.0 % (dalle 2026-11-14T10:01:00+00:00)" in uscita
    assert uscita.count("  fuori      dalle") == 1
    assert "  fuori      dalle 2026-11-14T10:01:00+00:00: 25.0 richieste/s (-50.0 %)" in uscita


def test_l_elenco_delle_finestre_fuori_tolleranza_si_ferma_a_cinque(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, invii_a_ritmo(25, 120))  # metà del ritmo chiesto: tutte le 11 finestre sono fuori
    with pytest.raises(SystemExit):
        lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")
    uscita = capsys.readouterr().out

    assert uscita.count("  fuori      dalle") == 5
    assert "e altre 6 finestre fuori tolleranza" in uscita


def test_con_un_log_sotto_una_finestra_si_controlla_solo_la_media(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, invii_a_ritmo(50, 8))
    uscita = lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")

    assert "nessuna: il log dura meno di 10 s, si controlla solo il ritmo medio" in uscita
    assert "ritmo entro la tolleranza" in uscita


def test_la_finestra_si_puo_cambiare(tmp_path, monkeypatch, capsys):
    # un buco di 2 s: dentro la tolleranza su una finestra da 60 s, fuori su una da 10 s
    scrivi_client(tmp_path, invii_a_ritmo(50, 180, buchi=[(60, 62)]))
    assert "finestre     2 da 60 s" in lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50", "--finestra", "60")
    with pytest.raises(SystemExit, match="fuori tolleranza"):
        lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50", "--finestra", "10")


def test_da_riga_di_comando_i_dati_sbagliati_escono_con_errore(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit, match="manca il file"):
        lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")
    scrivi_client(tmp_path, [INIZIO])
    with pytest.raises(SystemExit, match="errore: client.csv ha meno di due"):
        lancia(monkeypatch, capsys, tmp_path, "--ritmo", "50")


@pytest.mark.parametrize("opzione, valore", [("--ritmo", "0"), ("--ritmo", "-5"), ("--finestra", "0")])
def test_un_ritmo_o_una_finestra_non_positivi_sono_rifiutati(tmp_path, monkeypatch, capsys, opzione, valore):
    scrivi_client(tmp_path, invii_a_ritmo(50, 20))
    argomenti = ["--ritmo", "50"] if opzione != "--ritmo" else []
    with pytest.raises(SystemExit):
        lancia(monkeypatch, capsys, tmp_path, *argomenti, opzione, valore)


def test_la_tolleranza_predefinita_e_quella_di_parametri_yaml():
    yaml = pytest.importorskip("yaml")  # nella CI di questo job PyYAML non c'è: la prova gira dove c'è
    with open(ritmo.PARAMETRI, encoding="utf-8") as f:
        atteso = yaml.safe_load(f)["carichi"]["ritmo_tolleranza_percentuale"]
    assert ritmo.tolleranza_predefinita() == atteso


def test_uno_scarto_minuscolo_non_si_scrive_meno_zero():
    assert ritmo.con_segno(-0.0004) == "+0.0"
    assert ritmo.con_segno(-9.09) == "-9.1"
    assert ritmo.con_segno(3.04) == "+3.0"


# --- Profilo da carico.json (W2, #117) ----------------------------------------------------------------------------

W2 = [(0, 120, 10), (120, 180, 100), (180, 300, 10)]  # base, picco, base: come carico.py con mu1 = 20


def invii_a_profilo(tratti):
    """Istanti di invio (assoluti) di un generatore che segue i tratti, ognuno a ritmo regolare."""
    istanti = []
    for inizio, fine, r in tratti:
        istanti += [inizio + k / r for k in range(round((fine - inizio) * r))]
    return [INIZIO + t for t in istanti]


def scrivi_carico(cartella, tratti, profilo="w2"):
    (cartella / "carico.json").write_text(json.dumps(
        {"profilo": profilo, "mu1": 20, "tratti": [{"inizio_s": i, "fine_s": f, "ritmo": r} for i, f, r in tratti]}))


def test_le_attese_di_una_finestra_a_cavallo_del_picco_sono_la_media_pesata():
    assert ritmo.attese(W2, 115, 125) == 5 * 10 + 5 * 100
    assert ritmo.attese(W2, 0, 300) == 120 * 10 + 60 * 100 + 120 * 10
    assert ritmo.attese([(0.0, float("inf"), 50.0)], 0, 10) == 500


def test_un_profilo_rispettato_ha_tutte_le_finestre_nella_tolleranza():
    per_finestra = ritmo.finestre(invii_a_profilo(W2), W2, 10)
    assert per_finestra and all(abs(scarto) < 1 for _, _, scarto in per_finestra)


def test_un_profilo_rispettato_anche_con_il_cambio_a_meta_finestra():
    tratti = [(0, 125, 10), (125, 185, 100), (185, 300, 10)]
    per_finestra = ritmo.finestre(invii_a_profilo(tratti), tratti, 10)
    assert all(abs(scarto) < 1 for _, _, scarto in per_finestra)


def test_da_riga_di_comando_senza_ritmo_si_usa_carico_json(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, invii_a_profilo(W2))
    scrivi_carico(tmp_path, W2)
    uscita = lancia(monkeypatch, capsys, tmp_path)
    assert "profilo w2 di carico.json" in uscita and "100/s da 120 a 180 s" in uscita
    assert "ritmo entro la tolleranza" in uscita


@pytest.mark.parametrize("inviato", [
    [(0, 300, 10)],                                    # il picco non c'è: il generatore resta alla base
    [(0, 120, 10), (120, 150, 100), (150, 300, 10)],   # il picco dura metà
])
def test_un_picco_mancato_o_troncato_rende_il_run_non_valido(tmp_path, monkeypatch, capsys, inviato):
    scrivi_client(tmp_path, invii_a_profilo(inviato))
    scrivi_carico(tmp_path, W2)
    with pytest.raises(SystemExit, match="fuori tolleranza"):
        lancia(monkeypatch, capsys, tmp_path)


def test_senza_ritmo_e_senza_carico_json_e_un_errore(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, invii_a_ritmo(50, 30))
    with pytest.raises(SystemExit, match="carico.json"):
        lancia(monkeypatch, capsys, tmp_path)


@pytest.mark.parametrize("contenuto", [
    {"profilo": "w2"},
    {"tratti": [{"inizio_s": 0, "fine_s": 10, "ritmo": 0}]},
    {"tratti": [{"inizio_s": 10, "fine_s": 5, "ritmo": 10}]},
    {"tratti": []},
])
def test_un_carico_json_rotto_e_un_errore(tmp_path, monkeypatch, capsys, contenuto):
    scrivi_client(tmp_path, invii_a_ritmo(50, 30))
    (tmp_path / "carico.json").write_text(json.dumps(contenuto))
    with pytest.raises(SystemExit, match="errore"):
        lancia(monkeypatch, capsys, tmp_path)


def test_lo_zero_si_ricava_anche_con_il_ritardo_e_la_raffica_di_jmeter():
    """Come nel run W2 del 26/11: lo zero del programma è 0,6 s prima del primo invio, e le prime 6 richieste
    (quelle dei primi 0,6 s) partono insieme quando JMeter recupera il ritardo."""
    istanti = [t - INIZIO for t in invii_a_profilo(W2)]
    con_ritardo = [INIZIO + max(t, 0.6) for t in istanti]
    assert abs(ritmo.zero(con_ritardo, W2) - INIZIO) < 0.01
    per_finestra = ritmo.finestre(con_ritardo, W2, 10)
    assert all(abs(scarto) < 1 for _, _, scarto in per_finestra)
    assert abs(ritmo.scarto_medio(con_ritardo, W2)) < 1


def test_con_il_primo_invio_come_zero_il_picco_sarebbe_fuori_tolleranza():
    """Il motivo di zero(): contando dal primo invio, mezzo secondo di sfasamento basta a uscire dal 5 %."""
    spostati = [t + 0.6 for t in invii_a_profilo(W2)]
    assert abs(ritmo.zero(spostati, W2) - (INIZIO + 0.6)) < 0.01
    assert all(abs(scarto) < 1 for _, _, scarto in ritmo.finestre(spostati, W2, 10))
