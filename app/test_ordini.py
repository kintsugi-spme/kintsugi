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


class SalvaFinto:
    """Al posto di PostgreSQL per l'API sincrona: annota gli ordini, oppure ritarda o fallisce.

    `pulizia_s` imita psycopg con il database congelato: annullato, impiega ancora del tempo a finire.
    """

    def __init__(self, ritardo_s=0.0, errore=None, pulizia_s=0.0):
        self.ordini = []
        self.ritardo_s = ritardo_s
        self.errore = errore
        self.pulizia_s = pulizia_s

    async def __call__(self, id_ordine, ts_ricezione):
        if self.ritardo_s:
            try:
                await asyncio.sleep(self.ritardo_s)
            except asyncio.CancelledError:
                await asyncio.sleep(self.pulizia_s)
                raise
        if self.errore:
            raise self.errore
        self.ordini.append((id_ordine, ts_ricezione))
        return True


def app_con(broker=None, **ambiente):
    env = {"MODE": "async", "DEADLINE_S": str(DEADLINE_S), **ambiente}
    return crea_app(da_ambiente(env), broker)


def app_sincrona(salva):
    env = {"MODE": "sync", "DEADLINE_S": str(DEADLINE_S), "DATABASE_URL": "postgresql://db/k"}
    return crea_app(da_ambiente(env), salva=salva)


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


def test_il_worker_non_ha_l_endpoint_degli_ordini():
    ordine = {"id": str(uuid.uuid4())}
    app = app_con(ROLE="worker", DATABASE_URL="postgresql://db/k", BROKER_URL="amqp://broker")
    assert TestClient(app).post("/ordini", json=ordine).status_code == 404


def test_ordine_sincrono_confermato_solo_dopo_il_salvataggio():
    salva = SalvaFinto()
    prima = datetime.now(timezone.utc)
    risposta = TestClient(app_sincrona(salva)).post("/ordini", json={"id": str(uuid.uuid4())})
    assert risposta.status_code == 201
    assert len(salva.ordini) == 1
    id_ordine, istante = salva.ordini[0]
    assert risposta.json() == {"id": str(id_ordine), "stato": "salvato"}
    assert prima <= istante <= datetime.now(timezone.utc)


def test_se_il_database_fallisce_l_ordine_sincrono_non_e_accettato():
    salva = SalvaFinto(errore=OSError("database spento"))
    risposta = TestClient(app_sincrona(salva)).post("/ordini", json={"id": str(uuid.uuid4())})
    assert risposta.status_code == 503
    assert "database" in risposta.text


def test_il_salvataggio_lento_viene_abbandonato_alla_deadline():
    """Criterio della #31, in scala: tempo di servizio oltre la deadline, 503 alla deadline."""
    salva = SalvaFinto(ritardo_s=5)
    inizio = time.perf_counter()
    risposta = TestClient(app_sincrona(salva)).post("/ordini", json={"id": str(uuid.uuid4())})
    durata = time.perf_counter() - inizio
    assert risposta.status_code == 503
    assert DEADLINE_S <= durata < DEADLINE_S + 0.5
    assert salva.ordini == []


def test_la_deadline_non_aspetta_la_pulizia_del_lavoro_annullato():
    """Con il database congelato psycopg impiega fino a 10 s ad arrendersi: il 503 arriva lo stesso alla deadline."""
    salva = SalvaFinto(ritardo_s=5, pulizia_s=2)
    inizio = time.perf_counter()
    risposta = TestClient(app_sincrona(salva)).post("/ordini", json={"id": str(uuid.uuid4())})
    durata = time.perf_counter() - inizio
    assert risposta.status_code == 503
    assert DEADLINE_S <= durata < DEADLINE_S + 0.5
