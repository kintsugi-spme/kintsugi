"""La logica per accettare un ordine, scelta in base a MODE (D0001).

L'API (`api.py`) chiama solo `accetta_ordine`; cosa succede dietro dipende dalla configurazione.
"""

import asyncio
import json
from datetime import datetime

from broker import Broker
from config import Config
from modelli import OrdineIn


class ServizioNonDisponibile(Exception):
    """L'ordine non è stato accettato: l'API risponde 503 (D0008)."""


async def accetta_ordine(ordine: OrdineIn, ts_ricezione: datetime, config: Config, broker: Broker) -> None:
    if config.mode == "async":
        await _accetta_con_coda(ordine, ts_ricezione, config, broker)
    else:
        raise NotImplementedError("MODE=sync: arriva con la issue #30")


async def _accetta_con_coda(ordine: OrdineIn, ts_ricezione: datetime, config: Config, broker: Broker) -> None:
    """Versione con coda: accettato solo quando il broker conferma (D0001, D0002).

    Se la conferma non arriva entro DEADLINE_S (D0008), o il broker è spento o non configurato,
    l'ordine non è accettato. `ts_ricezione` viaggia nel messaggio: lo scriverà il worker (D0005).
    """
    corpo = json.dumps({"id": str(ordine.id), "ts_ricezione": ts_ricezione.isoformat()}).encode()
    try:
        await asyncio.wait_for(broker.pubblica(corpo), timeout=config.deadline_s)
    except TimeoutError:
        raise ServizioNonDisponibile(f"il broker non ha confermato entro {config.deadline_s} s") from None
    except Exception as errore:
        raise ServizioNonDisponibile(f"il broker non ha confermato ({type(errore).__name__})") from errore
