"""Endpoint HTTP dell'API, raccolti in un router che `main.py` include.

Per ora ci sono solo le sonde. Gli endpoint degli ordini arrivano con le issue #30 (versione
sincrona) e #32 (versione con la coda): si aggiungono qui, senza toccare `main.py`.
"""

from fastapi import APIRouter

router = APIRouter()


# Le sonde controllano solo che il processo risponda, mai database o broker (D0007):
# con il database fermo non devono far riavviare né escludere dal Service tutte le copie.
@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"stato": "vivo"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    return {"stato": "pronto"}
