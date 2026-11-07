import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from config import da_ambiente
from main import crea_app

DEADLINE_S = 0.3


class BrokerFinto:
    """Al posto di RabbitMQ: tiene i messaggi in una lista, oppure ritarda o fallisce."""

    def __init__(self, ritardo_s=0.0, errore=None):
        self.messaggi = []
        self.ritardo_s = ritardo_s
        self.errore = errore
        self.chiuso = False

    async def pubblica(self, corpo):
        if self.ritardo_s:
            await asyncio.sleep(self.ritardo_s)
        if self.errore:
            raise self.errore
        self.messaggi.append(json.loads(corpo))

    async def chiudi(self):
        self.chiuso = True


def app_con(broker=None, **ambiente):
    env = {"MODE": "async", "DEADLINE_S": str(DEADLINE_S), **ambiente}
    return crea_app(da_ambiente(env), broker)


def test_ordine_accettato_solo_dopo_la_conferma_del_broker():
    broker = BrokerFinto()
    prima = datetime.now(timezone.utc)
    risposta = TestClient(app_con(broker)).post("/ordini", json={"id": str(uuid.uuid4())})
    assert risposta.status_code == 202
    assert len(broker.messaggi) == 1
    messaggio = broker.messaggi[0]
    assert risposta.json() == {"id": messaggio["id"], "stato": "ricevuto"}
    # ts_ricezione viaggia nel messaggio ed è un istante preso dall'API, in UTC (D0005).
    istante = datetime.fromisoformat(messaggio["ts_ricezione"])
    assert prima <= istante <= datetime.now(timezone.utc)


def test_identificativo_non_valido_e_rifiutato_senza_toccare_il_broker():
    broker = BrokerFinto()
    risposta = TestClient(app_con(broker)).post("/ordini", json={"id": "non-un-uuid"})
    assert risposta.status_code == 422
    assert broker.messaggi == []


def test_se_il_broker_non_conferma_l_ordine_non_e_accettato():
    broker = BrokerFinto(errore=ConnectionError("broker spento"))
    risposta = TestClient(app_con(broker)).post("/ordini", json={"id": str(uuid.uuid4())})
    assert risposta.status_code == 503


def test_il_broker_lento_viene_abbandonato_alla_deadline():
    broker = BrokerFinto(ritardo_s=5)
    inizio = time.perf_counter()
    risposta = TestClient(app_con(broker)).post("/ordini", json={"id": str(uuid.uuid4())})
    durata = time.perf_counter() - inizio
    assert risposta.status_code == 503
    assert DEADLINE_S <= durata < DEADLINE_S + 0.5


def test_senza_indirizzo_del_broker_l_ordine_non_e_accettato():
    risposta = TestClient(app_con()).post("/ordini", json={"id": str(uuid.uuid4())})
    assert risposta.status_code == 503
    assert "BROKER_URL" in risposta.text or "broker" in risposta.text


def test_il_broker_si_chiude_all_arresto():
    broker = BrokerFinto()
    with TestClient(app_con(broker)):
        pass
    assert broker.chiuso


def test_l_endpoint_degli_ordini_c_e_solo_nell_api_con_la_coda():
    ordine = {"id": str(uuid.uuid4())}
    assert TestClient(app_con(ROLE="worker")).post("/ordini", json=ordine).status_code == 404
    assert TestClient(crea_app(da_ambiente({"MODE": "sync"}))).post("/ordini", json=ordine).status_code == 404
