"""Il worker della versione con la coda (V3, V5): legge gli ordini da RabbitMQ e li salva (D0002).

Un ordine alla volta (prefetch = 1) e conferma al broker (ack) solo dopo il salvataggio: se il
worker si spegne prima, RabbitMQ consegna l'ordine a un altro worker. Il doppio che può nascere
così si conta in `duplicati` (D0004).

Gira nello stesso processo uvicorn dell'API (D0012): `main.py` lo avvia in sottofondo quando
ROLE=worker, e le sonde restano attive.

Se il broker cade, il worker si ricollega da solo riprovando ogni ATTESA_RICONNESSIONE_S. È l'unico
meccanismo di riconnessione, così il tempo di ripresa dopo F3 si spiega con questo ciclo.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

import aio_pika

from broker import NOME_CODA, dichiara_code

log = logging.getLogger("kintsugi")

ATTESA_RICONNESSIONE_S = 1.0
# Provvisoria: con la #34 l'errore del database si gestisce con la riprova di D0003.
ATTESA_DOPO_ERRORE_S = 1.0

Salva = Callable[[UUID, datetime], Awaitable[bool]]


class MessaggioIlleggibile(ValueError):
    """Il messaggio non contiene un ordine valido: riprovarlo non serve."""


def leggi_ordine(corpo: bytes) -> tuple[UUID, datetime]:
    """Estrae identificativo e istante di ricezione dal messaggio scritto dall'API (servizio.py)."""
    try:
        dati = json.loads(corpo)
        id_ordine = UUID(dati["id"])
        ts_ricezione = datetime.fromisoformat(dati["ts_ricezione"])
    except (ValueError, KeyError, TypeError, AttributeError) as errore:
        raise MessaggioIlleggibile(f"{type(errore).__name__}: {errore}") from errore
    # Senza fuso orario PostgreSQL lo interpreterebbe nel fuso della sessione (D0005).
    if ts_ricezione.tzinfo is None:
        raise MessaggioIlleggibile("ts_ricezione senza fuso orario")
    return id_ordine, ts_ricezione


async def gestisci(messaggio: aio_pika.abc.AbstractIncomingMessage, salva: Salva) -> None:
    """Salva un ordine e lo conferma al broker solo dopo il salvataggio (D0002)."""
    try:
        id_ordine, ts_ricezione = leggi_ordine(messaggio.body)
    except MessaggioIlleggibile as errore:
        # D0003: un messaggio illeggibile va subito tra i falliti, senza riprove.
        log.warning("worker: messaggio illeggibile, va nella coda dei falliti (%s)", errore)
        await messaggio.reject(requeue=False)
        return
    try:
        await salva(id_ordine, ts_ricezione)
    except Exception as errore:
        log.warning("worker: salvataggio di %s non riuscito (%s), torna in coda", id_ordine, errore)
        await asyncio.sleep(ATTESA_DOPO_ERRORE_S)
        await messaggio.nack(requeue=True)
        return
    # Anche un doppio si conferma: è già salvato e contato in `duplicati` (D0004).
    await messaggio.ack()


async def esegui(url: str, salva: Salva, nome_coda: str = NOME_CODA) -> None:
    """Consuma la coda finché il processo non si ferma, ricollegandosi se il broker cade."""
    while True:
        try:
            connessione = await aio_pika.connect(url)
            async with connessione:
                canale = await connessione.channel()
                await canale.set_qos(prefetch_count=1)
                coda = await dichiara_code(canale, nome_coda)
                log.info("worker: collegato al broker, in ascolto sulla coda %s", nome_coda)
                async with coda.iterator() as messaggi:
                    async for messaggio in messaggi:
                        await gestisci(messaggio, salva)
        except asyncio.CancelledError:
            raise
        except aio_pika.exceptions.ChannelPreconditionFailed as errore:
            log.error("worker: la coda %s esiste già con impostazioni diverse: va cancellata e ricreata (%s)", nome_coda, errore)
        except (OSError, aio_pika.exceptions.AMQPException) as errore:
            log.warning("worker: problema con il broker (%s: %s)", type(errore).__name__, errore)
        except Exception:
            log.exception("worker: errore imprevisto, mi ricollego")
        await asyncio.sleep(ATTESA_RICONNESSIONE_S)
