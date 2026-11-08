"""Endpoint HTTP dell'API, raccolti in router che `main.py` include.

`router` ha le sonde, presenti in ogni processo. `router_ordini` ha l'endpoint degli ordini, solo
nell'API. L'endpoint non contiene logica: chiama `servizio.accetta_ordine`, che sceglie cosa fare
in base a MODE.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

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


# Il codice di risposta dice al cliente che cosa è successo all'ordine (D0001):
# 201 se è già nel database (MODE=sync), 202 se è in coda e lo salverà un worker (MODE=async).
RISPOSTE = {"sync": (201, "salvato"), "async": (202, "ricevuto")}


@router_ordini.post("/ordini", responses={201: {}, 202: {}, 503: {}})
async def crea_ordine(ordine: OrdineIn, richiesta: Request, risposta: Response) -> dict[str, str]:
    # D0005: l'istante di ricezione si prende subito, all'arrivo della richiesta.
    ts_ricezione = datetime.now(timezone.utc)
    stato = richiesta.app.state
    try:
        await accetta_ordine(ordine, ts_ricezione, stato.config, stato.broker, stato.salva)
    except ServizioNonDisponibile as errore:
        raise HTTPException(status_code=503, detail=str(errore)) from errore
    risposta.status_code, esito = RISPOSTE[stato.config.mode]
    return {"id": str(ordine.id), "stato": esito}
