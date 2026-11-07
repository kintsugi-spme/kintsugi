"""Accesso a PostgreSQL: il salvataggio di un ordine (D0004, D0005).

`salva_ordine` è l'unico percorso di scrittura, uguale per l'API sincrona e per il worker
(D0012): così il confronto tra le versioni è equo e i doppi si contano nello stesso modo.
Il SQL è scritto a mano perché servono `ON CONFLICT DO NOTHING` e `clock_timestamp()`.
La tabella e i vincoli sono in `deploy/k8s/base/schema.sql`.
"""

from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

# D0010: 5 connessioni per pod, uguale per API e worker e per tutte le versioni.
CONNESSIONI_PER_POD = 5

# Una sola istruzione, quindi atomica:
#   1. prova a inserire l'ordine; se l'identificativo esiste già, non fa nulla (`nuovo` è vuoto);
#   2. solo in quel caso registra l'arrivo in `duplicati` e restituisce l'identificativo.
# Con due richieste contemporanee con lo stesso identificativo, la seconda aspetta la prima:
# una sola inserisce, l'altra trova il conflitto e finisce tra i doppi.
SALVA_ORDINE = """
WITH nuovo AS (
    INSERT INTO ordini (id, ts_ricezione)
    VALUES (%(id)s, %(ts_ricezione)s)
    ON CONFLICT (id) DO NOTHING
    RETURNING id
)
INSERT INTO duplicati (id, ricevuto_da)
SELECT %(id)s, %(ricevuto_da)s
WHERE NOT EXISTS (SELECT 1 FROM nuovo)
RETURNING id
"""


async def salva_ordine(
    connessione: AsyncConnection, id: UUID, ts_ricezione: datetime, ricevuto_da: str
) -> bool:
    """Salva l'ordine. Restituisce True se è nuovo, False se era un doppio (registrato in `duplicati`).

    Al doppio si risponde come al primo (D0004): per il cliente l'ordine è salvato, ed è vero.
    `ricevuto_da` è il nome del pod o del processo che lo ha ricevuto.
    """
    async with connessione.transaction():
        cursore = await connessione.execute(
            SALVA_ORDINE, {"id": id, "ts_ricezione": ts_ricezione, "ricevuto_da": ricevuto_da}
        )
        era_un_doppio = await cursore.fetchone() is not None
    return not era_un_doppio


def crea_pool(url: str) -> AsyncConnectionPool:
    """Il pool di connessioni di un pod (D0010), da aprire con `await pool.open(wait=False)`.

    Non si collega alla creazione: con il database spento il processo parte lo stesso e le sonde
    rispondono (D0007). Prima di consegnare una connessione il pool controlla che sia viva e
    ricrea quelle morte, così dopo il riavvio del database non si usano connessioni vecchie.
    """
    return AsyncConnectionPool(
        url,
        min_size=CONNESSIONI_PER_POD,
        max_size=CONNESSIONI_PER_POD,
        open=False,
        check=AsyncConnectionPool.check_connection,
    )
