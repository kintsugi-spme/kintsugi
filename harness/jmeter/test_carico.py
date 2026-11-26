"""Prove di carico.py senza JMeter: profili, programma degli arrivi, proprietà, esiti e conversione in client.csv."""

import csv
import io
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import carico

JTL = """timeStamp,elapsed,label,responseCode,responseMessage,threadName,dataType,success,failureMessage,bytes,sentBytes,grpThreads,allThreads,URL,Latency,IdleTime,Connect,"id"
1795684839535,60,POST /ordini,201,Created,Ordini 1-2,text,true,,212,217,1,1,http://localhost:8080/ordini,58,0,1,bbbb
1795684839485,1967,POST /ordini,503,Service Unavailable,Ordini 1-1,text,false,,212,217,1,1,http://localhost:8080/ordini,1940,0,31,aaaa
1795684839585,2001,POST /ordini,"Non HTTP response code: java.net.SocketTimeoutException","Non HTTP response message: Read timed out",Ordini 1-3,text,false,,0,0,1,1,http://localhost:8080/ordini,0,0,1,cccc
1795684839635,3,POST /ordini,Non HTTP response code: org.apache.http.conn.HttpHostConnectException,Non HTTP response message: Connect to localhost:8080 failed,Ordini 1-4,text,false,,0,0,1,1,http://localhost:8080/ordini,0,0,3,dddd
"""

CARICHI = {"w2_base_percentuale_mu1": 50, "w2_picco_percentuale_mu1": 500, "w2_durata_picco_s": 60,
           "w2_inizio_picco_minuto": 2, "w2_finestra_costo_min": 10}


def test_il_profilo_costante_e_un_tratto_solo():
    assert carico.profilo_costante(50, 180) == [carico.Tratto(0, 180, 50)]


@pytest.mark.parametrize("ritmo,durata", [(0, 10), (10, 0), (-1, 10)])
def test_il_profilo_costante_rifiuta_valori_non_positivi(ritmo, durata):
    with pytest.raises(ValueError):
        carico.profilo_costante(ritmo, durata)


def test_w2_e_base_picco_base_con_i_valori_di_parametri_yaml():
    tratti = carico.profilo_w2(20, CARICHI)
    assert tratti == [carico.Tratto(0, 120, 10), carico.Tratto(120, 180, 100), carico.Tratto(180, 720, 10)]


def test_w2_con_una_durata_scelta_e_che_non_taglia_il_picco():
    assert carico.profilo_w2(20, CARICHI, 300)[-1] == carico.Tratto(180, 300, 10)
    with pytest.raises(ValueError):
        carico.profilo_w2(20, CARICHI, 180)
    with pytest.raises(ValueError):
        carico.profilo_w2(0, CARICHI)


def test_il_programma_fa_gradini_e_finisce_con_una_pausa():
    p = carico.programma(carico.profilo_w2(20, CARICHI), 3)
    assert p == ("rate(10/sec) even_arrivals(120 sec) rate(10/sec) "
                 "rate(100/sec) even_arrivals(60 sec) rate(100/sec) "
                 "rate(10/sec) even_arrivals(540 sec) rate(10/sec) pause(3 sec)")


def test_le_proprieta_vengono_dall_indirizzo_e_dal_timeout():
    p = carico.proprieta("http://localhost:8080/ordini", carico.profilo_costante(50, 180), 2)
    assert (p["host"], p["porta"], p["percorso"]) == ("localhost", "8080", "/ordini")
    assert p["programma"] == "rate(50/sec) even_arrivals(180 sec) rate(50/sec) pause(3 sec)"
    assert p["timeout_ms"] == "2000"
    assert p["sample_variables"] == "id"
    assert p["sampleresult.timestamp.start"] == "true"
    assert p["jmeterengine.force.system.exit"] == "true"  # niente minuto di attesa a fine test


@pytest.mark.parametrize("url", ["https://localhost/ordini", "localhost:8080/ordini", "http:///ordini"])
def test_un_indirizzo_non_valido_si_rifiuta(url):
    with pytest.raises(ValueError):
        carico.proprieta(url, carico.profilo_costante(10, 10), 2)


def test_un_timeout_non_positivo_si_rifiuta():
    with pytest.raises(ValueError):
        carico.proprieta("http://localhost:8080/ordini", carico.profilo_costante(10, 10), 0)


@pytest.mark.parametrize("codice,atteso", [
    ("201", "201"), ("202", "202"), ("503", "503"),
    ("Non HTTP response code: java.net.SocketTimeoutException", "timeout"),
    ("Non HTTP response code: org.apache.http.conn.ConnectTimeoutException", "timeout"),
    ("Non HTTP response code: org.apache.http.conn.HttpHostConnectException", "errore"),
    ("Non HTTP response code: org.apache.http.NoHttpResponseException", "errore"),
])
def test_esito_come_cliente_py(codice, atteso):
    assert carico.esito(codice) == atteso


def test_la_conversione_ordina_per_invio_e_scrive_le_colonne_di_client_csv():
    righe = carico.converti(csv.DictReader(io.StringIO(JTL)))
    assert [r[1] for r in righe] == ["aaaa", "bbbb", "cccc", "dddd"]
    assert [r[2] for r in righe] == ["503", "201", "timeout", "errore"]
    assert righe[0][0] == "2026-11-26T09:20:39.485000+00:00"
    assert righe[1][3] == "0.060000"


def test_client_csv_scritto_ha_l_intestazione_di_data_readme(tmp_path):
    jtl = tmp_path / "jmeter.jtl"
    jtl.write_text(JTL, encoding="utf-8")
    esiti = carico.scrivi_client_csv(jtl, tmp_path / "client.csv")
    with open(tmp_path / "client.csv", newline="", encoding="utf-8") as f:
        letto = list(csv.reader(f))
    assert letto[0] == ["ts_invio", "id", "esito", "tempo_risposta_s"]
    assert esiti == {"201": 1, "503": 1, "timeout": 1, "errore": 1}


def test_carico_json_descrive_i_tratti():
    d = carico.descrizione("w2", carico.profilo_w2(20, CARICHI), 20)
    assert d["profilo"] == "w2" and d["mu1"] == 20
    assert d["tratti"][1] == {"inizio_s": 120, "fine_s": 180, "ritmo": 100}


def test_il_piano_usa_le_proprieta_e_non_riusa_le_connessioni():
    """Le proprietà che carico.py passa sono quelle che carico.jmx legge; keep-alive spento (D0020)."""
    testo = carico.PIANO.read_text(encoding="utf-8")
    p = carico.proprieta("http://localhost:8080/ordini", carico.profilo_costante(10, 10), 2)
    for nome in ("host", "porta", "percorso", "programma", "timeout_ms"):
        assert f"__P({nome})" in testo, nome
        assert nome in p
    radice = ET.fromstring(testo)
    keepalive = [e.text for e in radice.iter("boolProp") if e.get("name") == "HTTPSampler.use_keepalive"]
    assert keepalive == ["false"]
    # Niente script Groovy: compilato al primo ordine, farebbe partire JMeter in ritardo (limite del 26/11).
    assert not [e for e in radice.iter() if e.tag.startswith("JSR223")]


def test_il_comando_lancia_jmeter_senza_interfaccia(tmp_path: Path):
    c = carico.comando("jmeter", tmp_path, {"programma": "rate(10/sec)"})
    assert c[:2] == ["jmeter", "-n"]
    assert str(tmp_path / "jmeter.jtl") in c and "-Jprogramma=rate(10/sec)" in c
