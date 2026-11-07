"""Prove del worker. Le prime usano un messaggio finto; le ultime un RabbitMQ e un PostgreSQL veri,
e si saltano se non ci sono (quindi non girano nella CI):

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


def test_se_il_salvataggio_fallisce_il_messaggio_torna_in_coda(monkeypatch):
    monkeypatch.setattr(worker, "ATTESA_DOPO_ERRORE_S", 0)
    messaggio = MessaggioFinto(corpo())

    async def database_spento(id_ordine, ts_ricezione):
        raise ConnectionError("database spento")

    asyncio.run(gestisci(messaggio, database_spento))
    assert messaggio.esito == "nack(requeue=True)"


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


async def con_worker(nome_coda, prova):
    """Avvia il worker su una coda di prova, esegue `prova(canale)` e poi ferma tutto."""
    config = da_ambiente({"MODE": "async", "ROLE": "worker", "DATABASE_URL": URL_DATABASE, "BROKER_URL": URL_BROKER})
    pool = crea_pool(URL_DATABASE)
    await pool.open(wait=True)

    async def salva_vero(id_ordine, ts_ricezione):
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


async def _uguale(valore, atteso):
    return await valore == atteso
