"""Punto di ingresso: un solo programma per tutte le versioni (D0012).

Si avvia con la fabbrica `crea_app`, così la configurazione si legge all'avvio e non quando
si importa il file:

    MODE=sync  uvicorn --factory main:crea_app
    MODE=async uvicorn --factory main:crea_app                 # API della versione con la coda
    MODE=async ROLE=worker uvicorn --factory main:crea_app     # worker della versione con la coda

Gli endpoint stanno in `api.py` (per ora solo le sonde): qui si crea l'app e si include il
router. Gli endpoint degli ordini e il consumo dalla coda arrivano con le issue #30-#32 (API)
e #33-#34 (worker).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import router
from config import Config, da_ambiente

log = logging.getLogger("kintsugi")


def crea_app(config: Config | None = None) -> FastAPI:
    config = config or da_ambiente()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    @asynccontextmanager
    async def ciclo_di_vita(_: FastAPI):
        log.info("avvio: %s", config.riassunto())
        yield
        log.info("arresto")

    app = FastAPI(title="Kintsugi", lifespan=ciclo_di_vita)
    app.state.config = config
    app.include_router(router)
    return app
