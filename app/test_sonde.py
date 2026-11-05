import time

import pytest
from fastapi.testclient import TestClient

from config import da_ambiente
from main import crea_app

# Su queste porte non risponde nessuno: è come avere database e broker spenti.
SPENTI = {"DATABASE_URL": "postgresql://127.0.0.1:1/kintsugi", "BROKER_URL": "amqp://127.0.0.1:1"}

# Timeout delle sonde (D0007). Una sonda che provasse a collegarsi resterebbe ferma ben oltre.
TIMEOUT_SONDA_S = 1.0


@pytest.mark.parametrize("modo", [
    {"MODE": "sync"},
    {"MODE": "async"},
    {"MODE": "async", "ROLE": "worker"},
])
@pytest.mark.parametrize("percorso, stato", [("/healthz", "vivo"), ("/readyz", "pronto")])
def test_sonde_rispondono_con_database_e_broker_spenti(modo, percorso, stato):
    client = TestClient(crea_app(da_ambiente(modo | SPENTI)))
    inizio = time.perf_counter()
    risposta = client.get(percorso)
    durata = time.perf_counter() - inizio
    assert risposta.status_code == 200
    assert risposta.json() == {"stato": stato}
    assert durata < TIMEOUT_SONDA_S / 10
