"""Prove del worker. Le prime usano un messaggio finto; le ultime un RabbitMQ e un PostgreSQL veri,
che nella CI ci sono (job «Test dell'app»); in locale si saltano se non ci sono:

    docker run -d --rm --name kintsugi-rabbit -p 5672:5672 \
        -e RABBITMQ_DEFAULT_USER=prova -e RABBITMQ_DEFAULT_PASS=prova rabbitmq:4-alpine
    docker run -d --rm --name kintsugi-pg -p 5433:5432 -e POSTGRES_HOST_AUTH_METHOD=trust \
        -e POSTGRES_DB=kintsugi -v "$PWD/deploy/k8s/base/schema.sql:/docker-entrypoint-initdb.d/01.sql:ro" \
        postgres:18-alpine
    TEST_BROKER_URL=amqp://prova:prova@127.0.0.1:5672/ \
        TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/kintsugi pytest test_worker.py

Le prove con il database svuotano le tabelle: usare solo un database di prova.
"""

import asyncio
import contextlib
import json
import os
import uuid
from datetime import datetime, timezone

import aio_pika
import psycopg
import pytest

import worker
from broker import dichiara_code
from config import da_ambiente
from db import crea_pool
from servizio import salva
from worker import MessaggioIlleggibile, gestisci, leggi_ordine

ADESSO = datetime.now(timezone.utc)


def corpo(id_ordine=None, ts=ADESSO):
    """Il messaggio come lo scrive l'API (servizio.py)."""
    return json.dumps({"id": str(id_ordine or uuid.uuid4()), "ts_ricezione": ts.isoformat()}).encode()


class MessaggioFinto:
    """Al posto di un messaggio di RabbitMQ: annota come è stato chiuso."""

    def __init__(self, body):
        self.body = body
        self.esito = None

    async def ack(self):
        self.esito = "ack"

    async def reject(self, requeue):
        self.esito = f"reject(requeue={requeue})"

    async def nack(self, requeue):
        self.esito = f"nack(requeue={requeue})"


def test_legge_identificativo_e_istante_scritti_dall_api():
    id_ordine = uuid.uuid4()
    assert leggi_ordine(corpo(id_ordine)) == (id_ordine, ADESSO)


@pytest.mark.parametrize("body", [
    b"non json",
    b'{"ts_ricezione": "2026-11-07T10:00:00+00:00"}',
    b'{"id": "non-un-uuid", "ts_ricezione": "2026-11-07T10:00:00+00:00"}',
    b'{"id": "6f1c0e2a-0000-4000-8000-000000000000", "ts_ricezione": "ieri"}',
    # Senza fuso orario PostgreSQL userebbe quello della sessione (D0005).
    b'{"id": "6f1c0e2a-0000-4000-8000-000000000000", "ts_ricezione": "2026-11-07T10:00:00"}',
    b'{"id": 5, "ts_ricezione": "2026-11-07T10:00:00+00:00"}',
    b'{"id": ["x"], "ts_ricezione": "2026-11-07T10:00:00+00:00"}',
])
def test_messaggio_illeggibile(body):
    with pytest.raises(MessaggioIlleggibile):
        leggi_ordine(body)


def test_conferma_solo_dopo_il_salvataggio():
    messaggio = MessaggioFinto(corpo())
    salvati = []

    async def salva_finto(id_ordine, ts_ricezione):
        # Al momento del salvataggio il messaggio non è ancora confermato (D0002).
        salvati.append(messaggio.esito)
        return True

    asyncio.run(gestisci(messaggio, salva_finto))
    assert salvati == [None]
    assert messaggio.esito == "ack"


def test_anche_il_doppio_si_conferma():
    messaggio = MessaggioFinto(corpo())

    async def doppio(id_ordine, ts_ricezione):
        return False

    asyncio.run(gestisci(messaggio, doppio))
    assert messaggio.esito == "ack"


def test_il_messaggio_illeggibile_va_tra_i_falliti_senza_salvare():
    messaggio = MessaggioFinto(b"non json")

    async def non_chiamare(id_ordine, ts_ricezione):
        raise AssertionError("non doveva salvare")

    asyncio.run(gestisci(messaggio, non_chiamare))
    assert messaggio.esito == "reject(requeue=False)"


@pytest.fixture
def riprova_veloce(monkeypatch):
    """Le attese e i limiti di D0003 ridotti a millisecondi, per non aspettare secondi veri."""
    monkeypatch.setattr(worker, "ATTESE_RIPROVA_S", (0.001, 0.002))
    monkeypatch.setattr(worker, "TEMPO_MASSIMO_RIPROVE_S", 0.1)
    monkeypatch.setattr(worker, "LIMITE_SCRITTURA_S", 0.05)


def test_le_attese_crescono_e_poi_restano_a_10_secondi():
    """D0003: 0,5 s, poi 1, 2, 4, 8 s, poi ogni 10 s."""
    assert [worker.attesa_riprova(n) for n in range(8)] == [0.5, 1, 2, 4, 8, 10, 10, 10]


def test_se_il_database_torna_l_ordine_si_salva_senza_lasciare_il_worker(riprova_veloce):
    messaggio = MessaggioFinto(corpo())
    chiamate = []

    async def database_che_torna(id_ordine, ts_ricezione):
        # Tra un tentativo e l'altro il messaggio resta con il worker: non è né confermato né rimesso in coda.
        chiamate.append(messaggio.esito)
        if len(chiamate) <= 2:
            raise psycopg.OperationalError("database spento")
        return True

    asyncio.run(gestisci(messaggio, database_che_torna))
    assert chiamate == [None, None, None]
    assert messaggio.esito == "ack"


def test_una_scrittura_troppo_lenta_si_ritenta(riprova_veloce):
    messaggio = MessaggioFinto(corpo())
    chiamate = []

    async def database_lento_la_prima_volta(id_ordine, ts_ricezione):
        chiamate.append(1)
        if len(chiamate) == 1:
            await asyncio.sleep(5)  # più del limite di scrittura: viene interrotta
        return True

    asyncio.run(gestisci(messaggio, database_lento_la_prima_volta))
    assert len(chiamate) == 2
    assert messaggio.esito == "ack"


def test_se_il_database_non_torna_in_tempo_l_ordine_va_tra_i_falliti(riprova_veloce):
    messaggio = MessaggioFinto(corpo())
    chiamate = []

    async def database_spento(id_ordine, ts_ricezione):
        chiamate.append(1)
        raise ConnectionError("database spento")

    asyncio.run(gestisci(messaggio, database_spento))
    assert len(chiamate) > 2  # ha riprovato, non si è arreso al primo errore
    assert messaggio.esito == "reject(requeue=False)"


def test_un_errore_che_non_passa_con_il_tempo_va_subito_tra_i_falliti(riprova_veloce):
    messaggio = MessaggioFinto(corpo())
    chiamate = []

    async def errore_di_programma(id_ordine, ts_ricezione):
        chiamate.append(1)
        raise ValueError("non dipende dal database")

    asyncio.run(gestisci(messaggio, errore_di_programma))
    assert len(chiamate) == 1
    assert messaggio.esito == "reject(requeue=False)"


def test_se_il_processo_si_ferma_durante_la_riprova_il_messaggio_resta_aperto(monkeypatch):
    """All'arresto RabbitMQ lo riconsegna a un altro worker (D0002): il messaggio non va né confermato né rifiutato."""
    monkeypatch.setattr(worker, "ATTESE_RIPROVA_S", (10,))
    messaggio = MessaggioFinto(corpo())

    async def database_spento(id_ordine, ts_ricezione):
        raise psycopg.OperationalError("database spento")

    async def prova():
        compito = asyncio.create_task(gestisci(messaggio, database_spento))
        await asyncio.sleep(0.05)
        compito.cancel()
        with pytest.raises(asyncio.CancelledError):
            await compito

    asyncio.run(prova())
    assert messaggio.esito is None


# --- Con RabbitMQ e PostgreSQL veri ------------------------------------------------------------

URL_BROKER = os.environ.get("TEST_BROKER_URL")
URL_DATABASE = os.environ.get("TEST_DATABASE_URL")
con_broker_e_database = pytest.mark.skipif(
    not (URL_BROKER and URL_DATABASE), reason="servono RabbitMQ e PostgreSQL: TEST_BROKER_URL e TEST_DATABASE_URL"
)


async def svuota_database():
    async with await psycopg.AsyncConnection.connect(URL_DATABASE) as c:
        nome = (await (await c.execute("SELECT current_database()")).fetchone())[0]
        # Difesa: le prove svuotano le tabelle, quindi solo su un database di prova.
        assert nome.startswith("kintsugi"), f"database {nome!r}: usa un database di prova"
        await c.execute("TRUNCATE ordini, duplicati")


async def conta_righe():
    async with await psycopg.AsyncConnection.connect(URL_DATABASE) as c:
        ordini = (await (await c.execute("SELECT count(*) FROM ordini")).fetchone())[0]
        doppi = (await (await c.execute("SELECT count(*) FROM duplicati")).fetchone())[0]
        return ordini, doppi


async def con_worker(nome_coda, prova, url_database=None, database_acceso=None):
    """Avvia il worker su una coda di prova, esegue `prova(canale)` e poi ferma tutto.

    `url_database` sostituisce il database di prova (per provare un indirizzo su cui non risponde
    nessuno). `database_acceso`, un `asyncio.Event`, simula un database spento finché non è impostato.
    """
    url = url_database or URL_DATABASE
    config = da_ambiente({"MODE": "async", "ROLE": "worker", "DATABASE_URL": url, "BROKER_URL": URL_BROKER})
    pool = crea_pool(url)
    await pool.open(wait=url_database is None)

    async def salva_vero(id_ordine, ts_ricezione):
        if database_acceso is not None and not database_acceso.is_set():
            raise psycopg.OperationalError("database spento (simulato dalla prova)")
        return await salva(pool, config, id_ordine, ts_ricezione, "worker-di-prova")

    compito = asyncio.create_task(worker.esegui(URL_BROKER, salva_vero, nome_coda))
    connessione = await aio_pika.connect(URL_BROKER)
    try:
        canale = await connessione.channel()
        await dichiara_code(canale, nome_coda)
        await prova(canale)
    finally:
        compito.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await compito
        canale = await connessione.channel()
        await canale.queue_delete(nome_coda)
        await canale.queue_delete(f"{nome_coda}.falliti")
        await connessione.close()
        await pool.close()


async def pubblica(canale, nome_coda, body):
    messaggio = aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
    await canale.default_exchange.publish(messaggio, routing_key=nome_coda)


async def aspetta(condizione, secondi=10):
    for _ in range(int(secondi / 0.1)):
        if await condizione():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condizione non raggiunta in tempo")


async def messaggi_in(canale, nome_coda):
    coda = await canale.declare_queue(nome_coda, passive=True)
    return coda.declaration_result.message_count


@con_broker_e_database
def test_lo_stesso_messaggio_due_volte_e_salvato_una_volta_e_contato():
    """Criterio 3 di M2."""
    nome = f"prova-{uuid.uuid4()}"
    body = corpo()

    async def prova(canale):
        await pubblica(canale, nome, body)
        await pubblica(canale, nome, body)
        await aspetta(lambda: _uguale(conta_righe(), (1, 1)))
        # Entrambi confermati: la coda è vuota e non c'è nulla tra i falliti.
        assert await messaggi_in(canale, nome) == 0
        assert await messaggi_in(canale, f"{nome}.falliti") == 0

    async def tutto():
        await svuota_database()
        await con_worker(nome, prova)

    asyncio.run(tutto())


@con_broker_e_database
def test_cento_ordini_diversi_sono_tutti_salvati():
    nome = f"prova-{uuid.uuid4()}"

    async def prova(canale):
        for _ in range(100):
            await pubblica(canale, nome, corpo())
        await aspetta(lambda: _uguale(conta_righe(), (100, 0)), secondi=30)

    async def tutto():
        await svuota_database()
        await con_worker(nome, prova)

    asyncio.run(tutto())


@con_broker_e_database
def test_il_messaggio_illeggibile_finisce_nella_coda_dei_falliti():
    nome = f"prova-{uuid.uuid4()}"

    async def prova(canale):
        await pubblica(canale, nome, b"non json")
        await aspetta(lambda: _uguale(messaggi_in(canale, f"{nome}.falliti"), 1))
        assert await conta_righe() == (0, 0)

    async def tutto():
        await svuota_database()
        await con_worker(nome, prova)

    asyncio.run(tutto())


@con_broker_e_database
def test_con_il_database_spento_gli_ordini_aspettano_e_si_salvano_al_ritorno(monkeypatch):
    """D0003: mentre il worker ritenta, l'ordine non torna in coda e gli altri restano in coda."""
    monkeypatch.setattr(worker, "ATTESE_RIPROVA_S", (0.05,))
    nome = f"prova-{uuid.uuid4()}"
    database_acceso = asyncio.Event()

    async def prova(canale):
        for _ in range(3):
            await pubblica(canale, nome, corpo())
        await asyncio.sleep(1)
        # Il worker ne tiene uno solo (prefetch = 1), gli altri due aspettano in coda.
        assert await messaggi_in(canale, nome) == 2
        assert await conta_righe() == (0, 0)
        database_acceso.set()
        await aspetta(lambda: _uguale(conta_righe(), (3, 0)))
        assert await messaggi_in(canale, nome) == 0
        assert await messaggi_in(canale, f"{nome}.falliti") == 0

    async def tutto():
        await svuota_database()
        await con_worker(nome, prova, database_acceso=database_acceso)

    asyncio.run(tutto())


@con_broker_e_database
def test_se_il_database_non_risponde_oltre_il_tempo_massimo_l_ordine_va_tra_i_falliti(monkeypatch):
    """Un indirizzo su cui non risponde nessuno: errori veri del pool, non simulati."""
    monkeypatch.setattr(worker, "ATTESE_RIPROVA_S", (0.1,))
    monkeypatch.setattr(worker, "TEMPO_MASSIMO_RIPROVE_S", 1)
    monkeypatch.setattr(worker, "LIMITE_SCRITTURA_S", 0.3)
    nome = f"prova-{uuid.uuid4()}"

    async def prova(canale):
        await pubblica(canale, nome, corpo())
        await aspetta(lambda: _uguale(messaggi_in(canale, f"{nome}.falliti"), 1), secondi=15)
        assert await messaggi_in(canale, nome) == 0
        assert await conta_righe() == (0, 0)

    async def tutto():
        await svuota_database()
        await con_worker(nome, prova, url_database="postgresql://postgres@127.0.0.1:1/kintsugi")

    asyncio.run(tutto())


async def _uguale(valore, atteso):
    return await valore == atteso
