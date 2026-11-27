"""Prove dello script del ripristino e del fermo (solo libreria standard, nessun servizio).

    pytest -q analysis
"""

import csv
import json
import random
from datetime import datetime, timedelta, timezone

import pytest

import fermo
from categorie import ErroreDati

INIZIO = datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc).timestamp()
SECONDI, SOGLIA = 5, 99  # i valori di config/parametri.yaml: ripristino() non li ha come predefiniti


def ripristino(richieste, t_guasto, secondi=SECONDI, soglia_percentuale=SOGLIA):
    return fermo.ripristino(richieste, t_guasto, secondi, soglia_percentuale)


def richieste_a_ritmo(ritmo, durata, guasto_da=None, guasto_a=None, eccezioni=()):
    """Richieste inviate a `ritmo` al secondo per `durata` secondi (istanti relativi a INIZIO).

    Quelle inviate tra `guasto_da` e `guasto_a` falliscono; `eccezioni` sono altri istanti, fuori
    da quell'intervallo, che falliscono lo stesso. Restituisce [(istante assoluto, riuscita, durata)].
    """
    risultato = []
    for k in range(int(durata * ritmo)):
        t = k / ritmo
        fallita = (guasto_da is not None and guasto_da <= t < guasto_a) or any(
            abs(t - e) < 0.5 / ritmo for e in eccezioni)
        risultato.append((INIZIO + t, not fallita, 0.0))
    return risultato


def test_con_un_fermo_il_ripristino_e_la_prima_richiesta_dopo_la_fine_del_guasto():
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=14.3)
    t_r = ripristino(richieste, INIZIO + 10)
    assert t_r == pytest.approx(INIZIO + 14.3, abs=0.05)  # una richiesta ogni 50 ms


def test_il_fermo_ha_una_risoluzione_sotto_il_secondo():
    richieste = richieste_a_ritmo(50, 40, guasto_da=10, guasto_a=13.14)
    fermo_s = ripristino(richieste, INIZIO + 10) - (INIZIO + 10)
    assert fermo_s == pytest.approx(3.14, abs=0.02)
    assert fermo_s != round(fermo_s)


def test_senza_nessun_fermo_visibile_il_fermo_e_zero():
    richieste = richieste_a_ritmo(20, 30)
    assert ripristino(richieste, INIZIO + 10) == INIZIO + 10


def test_se_il_servizio_non_torna_non_c_e_ripristino():
    richieste = richieste_a_ritmo(20, 30, guasto_da=10, guasto_a=1000)
    assert ripristino(richieste, INIZIO + 10) is None


def test_se_il_log_finisce_prima_di_confermare_i_cinque_secondi_non_c_e_ripristino():
    richieste = richieste_a_ritmo(20, 30, guasto_da=10, guasto_a=27)  # torna a 27 s, il log finisce a 30
    assert ripristino(richieste, INIZIO + 10) is None


def test_un_singolo_errore_dopo_il_ritorno_sposta_il_ripristino():
    # A 20 richieste al secondo un errore su 20 è il 95%: quel secondo non è disponibile.
    richieste = richieste_a_ritmo(20, 60, guasto_da=10, guasto_a=12, eccezioni=(14.0,))
    t_r = ripristino(richieste, INIZIO + 10)
    assert t_r == pytest.approx(INIZIO + 14.05, abs=0.06)  # dopo l'errore isolato, non a 12 s


def test_la_soglia_del_99_per_cento_ammette_un_errore_su_cento():
    richieste = richieste_a_ritmo(100, 30, eccezioni=(12.0,))  # 1 su 100 in quel secondo: 99%
    assert ripristino(richieste, INIZIO + 10, soglia_percentuale=99) == INIZIO + 10
    # Con la soglia al 100% il secondo dell'errore non è disponibile: il ripristino è dopo di lui.
    assert ripristino(richieste, INIZIO + 10, soglia_percentuale=100) == pytest.approx(INIZIO + 12.01, abs=0.011)


def test_un_buco_di_secondi_senza_richieste_non_e_disponibile():
    richieste = [r for r in richieste_a_ritmo(20, 40) if not 12 <= r[0] - INIZIO < 15]
    t_r = ripristino(richieste, INIZIO + 10)
    assert t_r == pytest.approx(INIZIO + 15.0, abs=0.06)


def test_i_secondi_consecutivi_si_possono_cambiare():
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=12, eccezioni=(16.0,))
    con_tre = ripristino(richieste, INIZIO + 10, secondi=3)
    assert con_tre == pytest.approx(INIZIO + 12.0, abs=0.06)  # [12, 15) non tocca l'errore a 16 s
    con_cinque = ripristino(richieste, INIZIO + 10, secondi=5)
    assert con_cinque == pytest.approx(INIZIO + 16.05, abs=0.06)  # [12, 17) lo contiene


def test_le_richieste_fallite_si_contano_tra_guasto_e_ripristino():
    richieste = richieste_a_ritmo(20, 40, guasto_da=10, guasto_a=12)
    t_r = ripristino(richieste, INIZIO + 10)
    assert fermo.richieste_fallite(richieste, INIZIO + 10, t_r) == 40


def test_il_guasto_fuori_dal_log_e_un_errore():
    richieste = richieste_a_ritmo(20, 30)
    with pytest.raises(ErroreDati, match="prima della prima"):
        ripristino(richieste, INIZIO - 5)
    with pytest.raises(ErroreDati, match="dopo l'ultima"):
        ripristino(richieste, INIZIO + 500)
    with pytest.raises(ErroreDati, match="nessuna richiesta"):
        ripristino([], INIZIO)


def scrivi_client(cartella, richieste, ordine=None):
    """Scrive client.csv. Il client scrive alla fine di ogni richiesta, quindi l'ordine è sparso."""
    righe = [[datetime.fromtimestamp(t, timezone.utc).isoformat(), f"id{k}",
              "201" if ok else "timeout", str(secondi)] for k, (t, ok, secondi) in enumerate(richieste)]
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
    assert [r[0] for r in lette] == sorted(r[0] for r in lette)
    assert ripristino(lette, INIZIO + 10) == pytest.approx(INIZIO + 14.3, abs=0.05)


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
    assert "richieste fallite per il guasto: 86" in uscita


def test_da_riga_di_comando_dice_quando_il_ripristino_non_e_avvenuto(tmp_path, monkeypatch, capsys):
    scrivi_client(tmp_path, richieste_a_ritmo(20, 30, guasto_da=10, guasto_a=1000))
    guasto = datetime.fromtimestamp(INIZIO + 10, timezone.utc).isoformat()
    uscita = lancia(monkeypatch, capsys, tmp_path, "--guasto", guasto)
    assert "ripristino non avvenuto" in uscita
    assert "fermo      t_r" not in uscita


def test_da_riga_di_comando_i_dati_sbagliati_escono_con_errore(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit, match="manca il file"):
        lancia(monkeypatch, capsys, tmp_path, "--guasto", "2026-11-12T10:00:10+00:00")


def test_le_richieste_in_corso_al_momento_del_guasto_si_contano_tra_le_fallite():
    t_g = INIZIO + 10
    richieste = [
        (t_g - 1.0, False, 0.2),   # partita prima e già finita: non è per il guasto
        (t_g - 0.1, False, 0.3),   # in corso al guasto, fallita: conta
        (t_g - 0.1, True, 0.3),    # in corso al guasto ma riuscita: non conta
        (t_g + 0.5, False, 0.0),   # inviata dopo il guasto, fallita: conta
        (t_g + 6.0, False, 0.0),   # dopo il ripristino: non conta
    ]
    assert fermo.richieste_fallite(richieste, t_g, t_g + 5) == 2


def test_il_tempo_di_risposta_che_non_e_un_numero_e_un_errore(tmp_path):
    (tmp_path / "client.csv").write_text(
        "ts_invio,id,esito,tempo_risposta_s\n2026-11-12T10:00:00+00:00,a,201,abc\n")
    with pytest.raises(ErroreDati, match="tempo_risposta_s"):
        fermo.leggi_richieste(tmp_path)


def test_i_secondi_e_la_soglia_non_hanno_un_predefinito():
    with pytest.raises(TypeError):
        fermo.ripristino(richieste_a_ritmo(20, 30), INIZIO + 10)


# --- Fermo del completamento (issue #124): db.csv, istanti del cluster, ts_nodo di guasto.json ---

def come_iso(secondi_epoca, stile="iso"):
    quando = datetime.fromtimestamp(secondi_epoca, timezone.utc)
    if stile == "postgres":  # come lo scrive psql: spazio al posto della T e «+00»
        return quando.strftime("%Y-%m-%d %H:%M:%S.%f") + "+00"
    return quando.isoformat(timespec="milliseconds")


def scenario(cartella, ritmo=20, durata=60, guasto=10.0, database_fermo=None, scritti_dopo=0.05,
             sfasamento=0.0, stile="iso", mai_salvati=()):
    """Un run di V3: il client invia a `ritmo` e riceve sempre 202; il database salva ogni ordine dopo
    `scritti_dopo` secondi, ma gli ordini ricevuti mentre è fermo (`database_fermo` = (da, a)) restano
    in coda e si salvano appena torna (a + scritti_dopo). `sfasamento`: di quanto l'orologio del cluster
    è avanti rispetto a quello del computer. `mai_salvati`: indici di ordini accettati e mai salvati."""
    richieste = [(INIZIO + k / ritmo, True, 0.01) for k in range(int(durata * ritmo))]
    scrivi_client(cartella, richieste)
    righe = ["id,ts_ricezione,ts_scrittura"]
    for k, (t, _, _) in enumerate(richieste):
        if k in mai_salvati:
            continue
        ricevuto = (t - INIZIO)
        if database_fermo and database_fermo[0] <= ricevuto < database_fermo[1]:
            scritto = database_fermo[1] + scritti_dopo + (ricevuto - database_fermo[0]) / 1000
        else:
            scritto = ricevuto + scritti_dopo
        righe.append(f"id{k},{come_iso(INIZIO + ricevuto + sfasamento, stile)},{come_iso(INIZIO + scritto + sfasamento, stile)}")
    (cartella / "db.csv").write_text("\n".join(righe) + "\n", encoding="utf-8")
    (cartella / "guasto.json").write_text(json.dumps({
        "ts_guasto": come_iso(INIZIO + guasto), "ts_nodo": come_iso(INIZIO + guasto + sfasamento)}), encoding="utf-8")
    return richieste


def ordini_del_run(cartella):
    guasto = fermo.leggi_guasto(cartella)
    return fermo.leggi_ordini(cartella, guasto["ts_nodo"] - guasto["ts_guasto"]), guasto


def fermo_completamento(cartella, limite=2.0):
    ordini, guasto = ordini_del_run(cartella)
    t_r = fermo.ripristino(fermo.completamento(ordini, limite), guasto["ts_nodo"], SECONDI, SOGLIA)
    return None if t_r is None else t_r - guasto["ts_nodo"]


def test_database_fermo_il_completamento_dura_piu_dell_accettazione(tmp_path):
    # Il database è fermo dal secondo 10 al 40: l'API accetta tutto (nessun fermo di accettazione), ma gli
    # ordini ricevuti in quei 30 s si salvano solo a 40 s. Il completamento riparte con gli ordini ricevuti
    # da 38,05 s in poi, che si salvano entro il limite di 2 s: fermo 28,1 s, non 30.
    richieste = scenario(tmp_path, database_fermo=(10, 40))
    accettazione = fermo.ripristino(richieste, INIZIO + 10, SECONDI, SOGLIA) - (INIZIO + 10)
    completamento = fermo_completamento(tmp_path)
    assert accettazione == pytest.approx(0, abs=0.05)
    assert completamento == pytest.approx(28.1, abs=0.1)
    assert completamento > accettazione


def test_senza_guasto_il_fermo_del_completamento_e_zero(tmp_path):
    scenario(tmp_path)
    assert fermo_completamento(tmp_path) == pytest.approx(0, abs=0.01)


def test_l_orologio_del_cluster_avanti_non_cambia_il_risultato(tmp_path):
    # D0005: gli istanti di db.csv e ts_nodo sono del cluster, 3 s avanti rispetto al computer.
    scenario(tmp_path, database_fermo=(10, 40), sfasamento=3.0)
    assert fermo_completamento(tmp_path) == pytest.approx(28.1, abs=0.1)


def test_gli_istanti_di_postgres_si_leggono(tmp_path):
    scenario(tmp_path, database_fermo=(10, 40), stile="postgres")
    assert fermo_completamento(tmp_path) == pytest.approx(28.1, abs=0.1)


def test_un_ordine_mai_salvato_conta_come_non_completato(tmp_path):
    # Dall'ordine 200 (secondo 10) al 259 (secondo 12,95) il database perde ogni ordine: il ripristino
    # del completamento arriva dopo, anche se l'API ha accettato tutto.
    scenario(tmp_path, mai_salvati=range(200, 260))
    assert fermo_completamento(tmp_path) == pytest.approx(3.0, abs=0.1)


def test_un_ordine_rifiutato_e_mai_salvato_non_e_stato_ricevuto(tmp_path):
    # Ogni secondo degli ordini 200-259 ne perde uno: il client vede un 503 e nel database non arriva nulla.
    # Non è un ordine ricevuto, quindi non è un ordine non completato (lo dice l'accettazione): gli altri
    # sono tutti salvati subito e il completamento non ha fermo.
    rifiutati = range(200, 260, 2)
    richieste = scenario(tmp_path, mai_salvati=rifiutati)
    scrivi_client(tmp_path, [(t, k not in rifiutati, s) for k, (t, _, s) in enumerate(richieste)])
    assert fermo_completamento(tmp_path) == pytest.approx(0, abs=0.01)
    # lo stesso scenario, con quegli ordini accettati dal client: mai salvati, quindi non completati (1 su 2)
    scrivi_client(tmp_path, richieste)
    assert fermo_completamento(tmp_path) == pytest.approx(3.0, abs=0.1)


def test_un_ordine_salvato_dopo_un_timeout_e_ricevuto_e_conta(tmp_path):
    richieste = scenario(tmp_path, database_fermo=(10, 40))
    scrivi_client(tmp_path, [(t, k % 2 == 0, s) for k, (t, _, s) in enumerate(richieste)])  # metà con esito negativo
    assert fermo_completamento(tmp_path) == pytest.approx(28.1, abs=0.1)  # sono in db.csv: ricevuti lo stesso


def test_il_limite_di_completamento_cambia_il_fermo(tmp_path):
    # ogni ordine si salva 1,5 s dopo la ricezione: completato con il limite di 2 s, non con quello di 1 s
    scenario(tmp_path, scritti_dopo=1.5)
    assert fermo_completamento(tmp_path, limite=2) == pytest.approx(0, abs=0.01)
    ordini, guasto = ordini_del_run(tmp_path)
    assert fermo.ripristino(fermo.completamento(ordini, 1), guasto["ts_nodo"], SECONDI, SOGLIA) is None


def test_il_guasto_di_guasto_json_manca_o_e_sbagliato(tmp_path):
    scenario(tmp_path)
    (tmp_path / "guasto.json").unlink()
    with pytest.raises(ErroreDati, match="ts_nodo"):
        fermo.leggi_guasto(tmp_path)
    (tmp_path / "guasto.json").write_text('{"ts_guasto": "2026-11-12T10:00:10+00:00"}')
    with pytest.raises(ErroreDati, match="servono ts_guasto e ts_nodo"):
        fermo.leggi_guasto(tmp_path)


def test_da_riga_di_comando_stampa_anche_il_completamento(tmp_path, monkeypatch, capsys):
    scenario(tmp_path, database_fermo=(10, 40))
    uscita = lancia(monkeypatch, capsys, tmp_path, "--limite", "2")  # --guasto: ts_guasto di guasto.json
    assert "fermo      t_r - t_g = 0.000 s" in uscita  # accettazione
    assert "completamento, limite 2 s" in uscita
    assert "fermo      t_r - t_g = 28.1" in uscita
    assert "servizio   fermo = 28.1" in uscita
    assert "ordini non completati per il guasto: 562" in uscita


def test_sensibilita_ripete_il_calcolo_con_i_limiti_di_parametri_yaml(tmp_path, monkeypatch, capsys):
    # i valori di parametri.yaml li controlla `make -C docs controlla`; qui basta che si usino (e la CI non ha PyYAML)
    monkeypatch.setattr(fermo, "leggi_parametri", lambda: {"tempi": {
        "limite_completamento_s": 2, "limite_completamento_sensibilita_s": [1, 5]}})
    scenario(tmp_path, scritti_dopo=1.5)
    uscita = lancia(monkeypatch, capsys, tmp_path, "--sensibilita")
    assert "completamento, limite 2 s" in uscita
    assert "completamento, limite 1 s" in uscita
    assert "completamento, limite 5 s" in uscita
    assert "ripristino non avvenuto: gli ordini finiscono" in uscita  # con 1 s non c'è ripristino


def test_senza_db_csv_resta_solo_l_accettazione(tmp_path, monkeypatch, capsys):
    scenario(tmp_path)
    (tmp_path / "db.csv").unlink()
    assert "completamento" not in lancia(monkeypatch, capsys, tmp_path)


def test_con_db_csv_ma_senza_guasto_json_e_un_errore(tmp_path, monkeypatch, capsys):
    scenario(tmp_path)
    (tmp_path / "guasto.json").unlink()
    with pytest.raises(SystemExit, match="guasto.json"):
        lancia(monkeypatch, capsys, tmp_path, "--guasto", come_iso(INIZIO + 10))
