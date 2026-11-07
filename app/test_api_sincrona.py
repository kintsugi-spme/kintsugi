"""L'API sincrona (V1, V2) contro un PostgreSQL vero. Si salta se non c'è, quindi non gira nella CI.

Il database si avvia come in `test_db.py`:

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/kintsugi pytest test_api_sincrona.py

Ogni prova svuota le due tabelle: usare solo un database di prova.
"""

import os
import statistics
import time
import uuid
from datetime import datetime, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from config import da_ambiente
from main import crea_app

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="serve un PostgreSQL: imposta TEST_DATABASE_URL")

SERVICE_TIME_S = 0.2


@pytest.fixture
def database():
    with psycopg.connect(URL, autocommit=True) as c:
        nome = c.execute("SELECT current_database()").fetchone()[0]
        # Difesa: le prove svuotano le tabelle, quindi solo su un database di prova.
        assert nome.startswith("kintsugi"), f"database {nome!r}: usa un database di prova"
        c.execute("TRUNCATE ordini, duplicati")
        yield c


def sfasamento_s(connessione):
    """Di quanto l'orologio del database è avanti rispetto a quello di questo processo.

    ts_ricezione viene dall'orologio dell'API, ts_scrittura da quello del database (D0005). Se
    l'API gira sul Mac e il database in Docker, gli orologi sono due e qui differivano di ~12 ms.
    """
    campioni = []
    for _ in range(5):
        prima = datetime.now(timezone.utc)
        del_database = connessione.execute("SELECT clock_timestamp()").fetchone()[0]
        dopo = datetime.now(timezone.utc)
        campioni.append((del_database - (prima + (dopo - prima) / 2)).total_seconds())
    return statistics.median(campioni)


def client(service_time_s=0.0):
    env = {"MODE": "sync", "DATABASE_URL": URL, "DEADLINE_S": "1.5", "SERVICE_TIME_S": str(service_time_s)}
    return TestClient(crea_app(da_ambiente(env)))


def test_senza_carico_il_tempo_end_to_end_e_il_tempo_di_servizio(database):
    """Criterio 2 di M2: ts_scrittura - ts_ricezione vale il tempo di servizio, entro pochi ms."""
    with client(SERVICE_TIME_S) as c:
        c.post("/ordini", json={"id": str(uuid.uuid4())})  # riscalda il pool
        id_ordine = uuid.uuid4()
        inizio = time.perf_counter()
        risposta = c.post("/ordini", json={"id": str(id_ordine)})
        durata = time.perf_counter() - inizio
    assert risposta.status_code == 201
    end_to_end = database.execute(
        "SELECT extract(epoch FROM ts_scrittura - ts_ricezione) FROM ordini WHERE id = %s", (id_ordine,)
    ).fetchone()[0]
    end_to_end = float(end_to_end) - sfasamento_s(database)
    assert SERVICE_TIME_S <= end_to_end < SERVICE_TIME_S + 0.01, f"end-to-end {end_to_end:.4f} s"
    assert SERVICE_TIME_S <= durata < SERVICE_TIME_S + 0.05


def test_lo_stesso_ordine_due_volte_e_salvato_una_volta_e_contato(database):
    ordine = {"id": str(uuid.uuid4())}
    with client() as c:
        risposte = [c.post("/ordini", json=ordine).status_code for _ in range(2)]
    # Al doppio si risponde come al primo (D0004): l'ordine è salvato.
    assert risposte == [201, 201]
    assert database.execute("SELECT count(*) FROM ordini").fetchone()[0] == 1
    assert database.execute("SELECT count(*) FROM duplicati").fetchone()[0] == 1
