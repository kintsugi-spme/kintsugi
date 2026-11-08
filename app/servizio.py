"""La logica per accettare e salvare un ordine, scelta in base a MODE (D0001).

L'API (`api.py`) chiama solo `accetta_ordine`; cosa succede dietro dipende dalla configurazione.
`salva` è il lavoro su un ordine, uguale per l'API sincrona e per il worker (D0012).
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from broker import Broker
from config import Config
from db import salva_ordine
from modelli import OrdineIn


# Il salvataggio già legato a un pool e a un processo: riceve id e ts_ricezione, True se è nuovo.
Salva = Callable[[UUID, datetime], Awaitable[bool]]


class ServizioNonDisponibile(Exception):
    """L'ordine non è stato accettato: l'API risponde 503 (D0008)."""


async def accetta_ordine(
    ordine: OrdineIn, ts_ricezione: datetime, config: Config, broker: Broker | None, salva: Salva | None
) -> None:
    """Accetta l'ordine entro DEADLINE_S (D0008), altrimenti solleva ServizioNonDisponibile.

    Con MODE=sync l'ordine è accettato quando è nel database (V1, V2); con MODE=async quando il
    broker conferma di averlo conservato (V3, V5; D0002). In entrambi i casi un errore o la
    deadline scaduta danno 503. Alla deadline il lavoro si interrompe, ma un ordine sincrono può
    essere già stato scritto: il cliente riceve 503 per un ordine salvato, e le misure lo contano.
    """
    if config.mode == "async":
        # `ts_ricezione` viaggia nel messaggio: lo scriverà il worker (D0005).
        corpo = json.dumps({"id": str(ordine.id), "ts_ricezione": ts_ricezione.isoformat()}).encode()
        await _entro_la_deadline(broker.pubblica(corpo), config, "il broker non ha confermato")
    else:
        await _entro_la_deadline(salva(ordine.id, ts_ricezione), config, "il database non ha salvato")


# Lavori annullati alla deadline che non hanno ancora finito: senza un riferimento, il garbage
# collector potrebbe eliminarli a metà.
_abbandonati: set[asyncio.Task] = set()


async def _entro_la_deadline(lavoro: Awaitable, config: Config, problema: str) -> None:
    """Il 503 parte alla deadline senza aspettare che il lavoro annullato finisca.

    `asyncio.wait_for` aspetterebbe: con il database congelato (SIGSTOP) psycopg prova per 10 s
    ad annullare la query prima di arrendersi, e l'API risponderebbe dopo 11,5 s invece di 1,5 s.
    """
    compito = asyncio.ensure_future(lavoro)
    try:
        await asyncio.wait([compito], timeout=config.deadline_s)
    except asyncio.CancelledError:
        compito.cancel()
        raise
    if not compito.done():
        compito.cancel()
        _abbandonati.add(compito)
        compito.add_done_callback(_dimentica)
        raise ServizioNonDisponibile(f"{problema} entro {config.deadline_s} s")
    try:
        compito.result()
    except Exception as errore:
        raise ServizioNonDisponibile(f"{problema} ({type(errore).__name__})") from errore


def _dimentica(compito: asyncio.Task) -> None:
    _abbandonati.discard(compito)
    if not compito.cancelled():
        compito.exception()  # al cliente è già arrivato il 503: l'esito non serve più


async def salva(
    pool: AsyncConnectionPool, config: Config, id_ordine: UUID, ts_ricezione: datetime, ricevuto_da: str
) -> bool:
    """Il lavoro su un ordine: il tempo di servizio, poi il salvataggio. True se l'ordine è nuovo.

    Il tempo di servizio (SERVICE_TIME_S) è il tempo dell'ordine al database, quindi passa con la
    connessione in mano. Così in ogni versione la capacità dipende da S: 5 / S ordini al secondo
    per una copia dell'API sincrona (5 connessioni, D0010), 1 / S per un worker (un ordine alla
    volta), e sotto sovraccarico V1, V2 e V3 si saturano per la stessa causa.
    Senza carico, ts_scrittura - ts_ricezione vale il tempo di servizio più qualche millisecondo
    (criterio 2 di M2).
    """
    async with pool.connection() as connessione:
        if config.service_time_s:
            await asyncio.sleep(config.service_time_s)
        return await salva_ordine(connessione, id_ordine, ts_ricezione, ricevuto_da)
