"""Prove contro un RabbitMQ vero. Si saltano se non c'è, quindi non girano nella CI.

    docker run -d --rm --name kintsugi-rabbit -p 5672:5672 \
        -e RABBITMQ_DEFAULT_USER=prova -e RABBITMQ_DEFAULT_PASS=prova rabbitmq:4-alpine
    TEST_BROKER_URL=amqp://prova:prova@127.0.0.1:5672/ pytest test_broker.py

L'utente `guest` di RabbitMQ può collegarsi solo da localhost: da fuori del container, con la
porta pubblicata, serve un utente creato apposta.
"""

import asyncio
import os
import uuid

import aio_pika
import pytest

from broker import Broker

URL = os.environ.get("TEST_BROKER_URL")
pytestmark = pytest.mark.skipif(not URL, reason="serve un RabbitMQ: imposta TEST_BROKER_URL")


def test_il_messaggio_arriva_in_una_coda_durevole_ed_e_persistente():
    nome = f"prova-{uuid.uuid4()}"

    async def prova():
        broker = Broker(URL, nome_coda=nome)
        connessione = await aio_pika.connect(URL)
        try:
            await broker.pubblica(b'{"id": "x"}')
            canale = await connessione.channel()
            coda = await canale.declare_queue(nome, durable=True)  # stessi argomenti: non rifiuta
            messaggio = await coda.get(timeout=2)
            assert messaggio.body == b'{"id": "x"}'
            assert messaggio.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
            await messaggio.ack()
        finally:
            canale = await connessione.channel()
            await canale.queue_delete(nome)
            await connessione.close()
            await broker.chiudi()

    asyncio.run(prova())


def test_con_il_broker_spento_la_pubblicazione_fallisce():
    async def prova():
        broker = Broker("amqp://prova:prova@127.0.0.1:1/")
        with pytest.raises(Exception):
            await asyncio.wait_for(broker.pubblica(b"{}"), timeout=3)

    asyncio.run(prova())
