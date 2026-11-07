"""Punto di ingresso: un solo programma per tutte le versioni (D0012).

Si avvia con la fabbrica `crea_app`, così la configurazione si legge all'avvio e non quando
si importa il file:

    MODE=sync  uvicorn --factory main:crea_app
    MODE=async uvicorn --factory main:crea_app                 # API della versione con la coda
    MODE=async ROLE=worker uvicorn --factory main:crea_app     # worker della versione con la coda

Gli endpoint stanno in `api.py`: qui si crea l'app e si includono i router. Con ROLE=worker il
processo consuma la coda in sottofondo (`worker.py`). L'endpoint della versione sincrona arriva
con la issue #30.
"""

import asyncio
import contextlib
import logging
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import router, router_ordini
from broker import Broker
import servizio
import worker
from config import Config, da_ambiente
from db import crea_pool

log = logging.getLogger("kintsugi")


def crea_app(config: Config | None = None, broker: Broker | None = None) -> FastAPI:
    """`broker` serve ai test, per passare un broker finto; altrimenti lo crea la configurazione."""
    config = config or da_ambiente()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # L'endpoint degli ordini c'è per ora solo nell'API della versione con la coda.
    # La #30 lo aggiungerà anche per MODE=sync, togliendo la prima condizione.
    espone_ordini = config.mode == "async" and config.role == "api"

    @asynccontextmanager
    async def ciclo_di_vita(app: FastAPI):
        log.info("avvio: %s", config.riassunto())
        if config.role == "worker":
            async with _worker_in_sottofondo(config):
                yield
        else:
            yield
        if app.state.broker is not None:
            await app.state.broker.chiudi()
        log.info("arresto")

    app = FastAPI(title="Kintsugi", lifespan=ciclo_di_vita)
    app.state.config = config
    # Il broker non si collega all'avvio, ma alla prima pubblicazione (D0007).
    app.state.broker = broker or (Broker(config.broker_url) if espone_ordini else None)
    app.include_router(router)
    if espone_ordini:
        app.include_router(router_ordini)
    return app


@asynccontextmanager
async def _worker_in_sottofondo(config: Config):
    """Apre il pool e consuma la coda finché il processo è vivo (#33).

    Il pool si apre senza aspettare il database: con il database spento il processo parte lo
    stesso e le sonde rispondono (D0007). All'arresto il messaggio in lavorazione non è stato
    confermato, quindi RabbitMQ lo riconsegna a un altro worker (D0002).
    """
    pool = crea_pool(config.database_url)
    await pool.open(wait=False)
    # Nome del pod su Kubernetes: finisce in `duplicati.ricevuto_da` (D0004).
    ricevuto_da = socket.gethostname()

    async def salva(id_ordine, ts_ricezione):
        return await servizio.salva(pool, config, id_ordine, ts_ricezione, ricevuto_da)

    compito = asyncio.create_task(worker.esegui(config.broker_url, salva))
    try:
        yield
    finally:
        compito.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await compito
        await pool.close()
