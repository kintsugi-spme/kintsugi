"""Prove del client contro un'API finta (solo libreria standard, nessun servizio da avviare).

    pytest -q harness/client
"""

import csv
import io
import json
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import cliente


class ApiFinta:
    """Un server HTTP locale: `risposta(n)` decide codice e attesa per l'n-esima richiesta."""

    def __init__(self, risposta):
        self.corpi: list[dict] = []
        self._blocco = threading.Lock()
        finta = self

        class Gestore(BaseHTTPRequestHandler):
            def do_POST(self):
                lunghezza = int(self.headers["Content-Length"])
                corpo = json.loads(self.rfile.read(lunghezza))
                with finta._blocco:
                    finta.corpi.append(corpo)
                    n = len(finta.corpi)
                codice, attesa_s = risposta(n)
                time.sleep(attesa_s)
                self.send_response(codice)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/ordini"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def chiudi(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def api_finta():
    create = []

    def crea(risposta):
        api = ApiFinta(risposta)
        create.append(api)
        return api

    yield crea
    for api in create:
        api.chiudi()


def lancia(url, richieste, ritmo, timeout_s=2.0):
    uscita = io.StringIO()
    esiti = cliente.esegui(url, richieste, ritmo, timeout_s, uscita)
    righe = list(csv.DictReader(io.StringIO(uscita.getvalue())))
    return esiti, righe


def test_cento_ordini_cento_righe(api_finta):
    """Criterio della #36: 100 ordini, una riga per richiesta."""
    api = api_finta(lambda n: (202, 0))
    esiti, righe = lancia(api.url, 100, ritmo=500)

    assert len(righe) == 100
    assert esiti == {"202": 100}
    assert all(r["esito"] == "202" for r in righe)
    assert len(api.corpi) == 100


def test_intestazione_e_colonne(api_finta):
    api = api_finta(lambda n: (201, 0))
    uscita = io.StringIO()
    cliente.esegui(api.url, 3, 100, 2.0, uscita)

    assert uscita.getvalue().splitlines()[0] == "ts_invio,id,esito,tempo_risposta_s"
    riga = uscita.getvalue().splitlines()[1].split(",")
    assert float(riga[3]) >= 0


def test_ogni_ordine_ha_un_uuid_diverso_e_lo_stesso_nel_log(api_finta):
    api = api_finta(lambda n: (202, 0))
    _, righe = lancia(api.url, 50, ritmo=500)

    inviati = {corpo["id"] for corpo in api.corpi}
    assert len(inviati) == 50
    for id_ordine in inviati:
        assert str(uuid.UUID(id_ordine)) == id_ordine  # UUID scritto in modo canonico
    assert {r["id"] for r in righe} == inviati


def test_esiti_503_e_timeout_si_distinguono(api_finta):
    # 1ª risposta 202; 2ª risposta 503; 3ª oltre il timeout
    piano = {1: (202, 0), 2: (503, 0), 3: (202, 1.0)}
    api = api_finta(lambda n: piano[n])
    # Un ordine alla volta (ritmo basso) perché l'ordine di arrivo sia quello del piano.
    esiti, righe = lancia(api.url, 3, ritmo=5, timeout_s=0.3)

    assert esiti == {"202": 1, "503": 1, "timeout": 1}
    assert len(righe) == 3
    lento = next(r for r in righe if r["esito"] == "timeout")
    assert 0.3 <= float(lento["tempo_risposta_s"]) < 0.9  # ha rinunciato al timeout, non dopo


def test_server_irraggiungibile_e_errore(api_finta):
    api = api_finta(lambda n: (202, 0))
    url = api.url
    api.chiudi()  # la porta non risponde più
    esiti, righe = lancia(url, 3, ritmo=100, timeout_s=0.5)

    assert esiti == {"errore": 3}
    assert [r["esito"] for r in righe] == ["errore"] * 3


def test_modello_aperto_non_aspetta_le_risposte(api_finta):
    """20 richieste a 20 al secondo con risposte da 0,5 s.

    Un client che aspetta ogni risposta impiegherebbe 20 x 0,5 = 10 s a inviarle; uno a modello
    aperto le invia in circa 1 s.
    """
    api = api_finta(lambda n: (202, 0.5))
    _, righe = lancia(api.url, 20, ritmo=20, timeout_s=2.0)

    invii = sorted(datetime.fromisoformat(r["ts_invio"]).timestamp() for r in righe)
    assert invii[-1] - invii[0] < 1.5


def test_ritmo_fisso(api_finta):
    """10 richieste a 20 al secondo: 9 intervalli da 50 ms, quindi circa 0,45 s da prima a ultima."""
    api = api_finta(lambda n: (202, 0))
    _, righe = lancia(api.url, 10, ritmo=20)

    invii = sorted(datetime.fromisoformat(r["ts_invio"]).timestamp() for r in righe)
    assert 0.40 <= invii[-1] - invii[0] <= 0.60
