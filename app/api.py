"""Endpoint HTTP dell'API, raccolti in router che `main.py` include.

`router` ha le sonde, presenti in ogni processo. `router_ordini` ha l'endpoint degli ordini, solo
nell'API. L'endpoint non contiene logica: chiama `servizio.accetta_ordine`, che sceglie cosa fare
in base a MODE. La versione sincrona (#30) si aggiunge in `servizio.py`.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from modelli import OrdineIn
from servizio import ServizioNonDisponibile, accetta_ordine

router = APIRouter()
router_ordini = APIRouter()


# Le sonde controllano solo che il processo risponda, mai database o broker (D0007):
# con il database fermo non devono far riavviare né escludere dal Service tutte le copie.
@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"stato": "vivo"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    return {"stato": "pronto"}


@router_ordini.post("/ordini", status_code=202)
async def crea_ordine(ordine: OrdineIn, richiesta: Request) -> dict[str, str]:
    # D0005: l'istante di ricezione si prende subito, all'arrivo della richiesta.
    ts_ricezione = datetime.now(timezone.utc)
    stato = richiesta.app.state
    try:
        await accetta_ordine(ordine, ts_ricezione, stato.config, stato.broker)
    except ServizioNonDisponibile as errore:
        raise HTTPException(status_code=503, detail=str(errore)) from errore
    return {"id": str(ordine.id), "stato": "ricevuto"}
