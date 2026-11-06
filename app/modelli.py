"""Dati che entrano nell'API.

Dell'ordine i documenti definiscono soltanto l'identificativo, scelto dal client (D0004):
gli istanti `ts_ricezione` e `ts_scrittura` li prende il cluster (D0005), non il client.
Altri campi, se servissero, si decidono insieme alle API (#30, #32).
"""

from uuid import UUID

from pydantic import BaseModel


class OrdineIn(BaseModel):
    id: UUID
