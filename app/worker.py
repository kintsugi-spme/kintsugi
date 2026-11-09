"""Il worker della versione con la coda (V3, V5): legge gli ordini da RabbitMQ e li salva (D0002).

Un ordine alla volta (prefetch = 1) e conferma al broker (ack) solo dopo il salvataggio: se il
worker si spegne prima, RabbitMQ consegna l'ordine a un altro worker. Il doppio che può nascere
così si conta in `duplicati` (D0004).

Gira nello stesso processo uvicorn dell'API (D0012): `main.py` lo avvia in sottofondo quando
ROLE=worker, e le sonde restano attive.

Se il database non risponde, il worker ritenta lo stesso ordine tenendolo con sé, senza confermarlo
né rimetterlo in coda, con attese crescenti (D0003). Dopo TEMPO_MASSIMO_RIPROVE_S l'ordine va nella
coda dei falliti. Gli altri ordini aspettano in coda: ogni worker ne tiene uno solo (prefetch = 1).

Se il broker cade, il worker si ricollega da solo riprovando ogni ATTESA_RICONNESSIONE_S. È l'unico
meccanismo di riconnessione, così il tempo di ripresa dopo F3 si spiega con questo ciclo.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

import aio_pika
import psycopg

from broker import NOME_CODA, dichiara_code

log = logging.getLogger("kintsugi")

ATTESA_RICONNESSIONE_S = 1.0

# D0003: la riprova quando il database non risponde.
# Una scrittura più lenta di così è un errore temporaneo, come un database irraggiungibile.
LIMITE_SCRITTURA_S = 1.5
# Attese tra un tentativo e il successivo: 0,5 s, poi 1, 2, 4, 8 s, poi ogni 10 s.
ATTESE_RIPROVA_S = (0.5, 1, 2, 4, 8, 10)
# Dopo almeno questo tempo di tentativi falliti l'ordine va nella coda dei falliti. È un valore
# indicativo: la soglia si verifica sul campo (F4) e si cambia qui, senza toccare il meccanismo.
TEMPO_MASSIMO_RIPROVE_S = 120
# Gli unici errori che si ritentano: database irraggiungibile (OSError e OperationalError, che
# comprende anche l'attesa scaduta del pool), connessione caduta (InterfaceError) o troppo lento
# (TimeoutError, che è un OSError, da LIMITE_SCRITTURA_S). Ogni altro errore non passa con il tempo:
# l'ordine va tra i falliti.
ERRORI_TEMPORANEI = (OSError, psycopg.OperationalError, psycopg.InterfaceError)

Salva = Callable[[UUID, datetime], Awaitable[bool]]


class MessaggioIlleggibile(ValueError):
    """Il messaggio non contiene un ordine valido: riprovarlo non serve."""


class OrdineNonSalvato(Exception):
    """Il salvataggio non è riuscito e riprovare non serve più: l'ordine va nella coda dei falliti."""


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


def attesa_riprova(tentativo: int) -> float:
    """Secondi da aspettare dopo il tentativo fallito numero `tentativo` (0 è il primo): l'ultima attesa si ripete."""
    return ATTESE_RIPROVA_S[min(tentativo, len(ATTESE_RIPROVA_S) - 1)]


def _descrivi(errore: Exception) -> str:
    if isinstance(errore, TimeoutError) and not str(errore):
        return f"il database non ha risposto entro {LIMITE_SCRITTURA_S} s"
    return f"{type(errore).__name__}: {errore}"


async def salva_con_riprova(salva: Salva, id_ordine: UUID, ts_ricezione: datetime) -> None:
    """Salva l'ordine, ritentando gli errori temporanei con attese crescenti (D0003).

    Il tempo si conta dal primo tentativo. Se il database non torna entro TEMPO_MASSIMO_RIPROVE_S,
    o se l'errore non è temporaneo, solleva OrdineNonSalvato.
    """
    inizio = time.monotonic()
    tentativo = 0
    while True:
        try:
            await asyncio.wait_for(salva(id_ordine, ts_ricezione), LIMITE_SCRITTURA_S)
            return
        except ERRORI_TEMPORANEI as errore:
            trascorso = time.monotonic() - inizio
            if trascorso >= TEMPO_MASSIMO_RIPROVE_S:
                raise OrdineNonSalvato(
                    f"database non tornato dopo {tentativo + 1} tentativi in {trascorso:.0f} s (ultimo errore: {_descrivi(errore)})"
                ) from errore
            attesa = attesa_riprova(tentativo)
            log.warning(
                "worker: salvataggio di %s non riuscito (%s), tentativo %d dopo %.1f s: riprovo tra %s s",
                id_ordine, _descrivi(errore), tentativo + 1, trascorso, attesa,
            )
            await asyncio.sleep(attesa)
            tentativo += 1
        except Exception as errore:
            raise OrdineNonSalvato(f"errore che non passa con il tempo ({_descrivi(errore)})") from errore


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
        await salva_con_riprova(salva, id_ordine, ts_ricezione)
    except OrdineNonSalvato as errore:
        # Senza `requeue` RabbitMQ lo inoltra da solo alla coda dei falliti (D0002).
        log.error("worker: ordine %s nella coda dei falliti: %s", id_ordine, errore)
        await messaggio.reject(requeue=False)
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
