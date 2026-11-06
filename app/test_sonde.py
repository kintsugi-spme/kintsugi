import socket
import time

import pytest
from fastapi.testclient import TestClient

from config import da_ambiente
from main import crea_app

# Su queste porte non risponde nessuno: è come avere database e broker spenti.
SPENTI = {"DATABASE_URL": "postgresql://127.0.0.1:1/kintsugi", "BROKER_URL": "amqp://127.0.0.1:1"}

# Timeout delle sonde (D0007): una sonda deve rispondere in una frazione di questo tempo.
# Che non provi a collegarsi lo verifica il test sui socket, non il tempo: un indirizzo
# rifiutato fallisce subito.
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


@pytest.mark.parametrize("percorso", ["/healthz", "/readyz"])
def test_le_sonde_non_aprono_connessioni(monkeypatch, percorso):
    # I tentativi si annotano invece di far lanciare un errore: una sonda che contatta il
    # database e ignora l'errore (try/except) rispondrebbe 200 e passerebbe gli altri test.
    tentativi = []
    # Con `with` il client avvia subito il suo ciclo di eventi: su Windows asyncio usa
    # `connect` per crearlo, quindi l'intercettazione parte solo dopo.
    with TestClient(crea_app(da_ambiente({"MODE": "sync", **SPENTI}))) as client:
        monkeypatch.setattr(socket.socket, "connect", lambda self, *a, **k: tentativi.append(a))
        client.get(percorso)
    assert tentativi == [], "la sonda ha provato a collegarsi"
