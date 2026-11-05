import pytest

from config import ErroreConfigurazione, da_ambiente
from main import crea_app


def test_mode_sync_con_i_predefiniti():
    c = da_ambiente({"MODE": "sync"})
    assert (c.mode, c.role) == ("sync", "api")
    assert c.service_time_s == 0.0
    assert c.deadline_s is None
    assert c.database_url is None and c.broker_url is None


def test_mode_async_api_e_worker():
    assert da_ambiente({"MODE": "async"}).role == "api"
    assert da_ambiente({"MODE": "async", "ROLE": "worker"}).role == "worker"


def test_legge_tutte_le_variabili():
    c = da_ambiente({
        "MODE": "async",
        "SERVICE_TIME_S": "0.25",
        "DEADLINE_S": "1.5",
        "DATABASE_URL": "postgresql://db/kintsugi",
        "BROKER_URL": "amqp://broker",
    })
    assert c.service_time_s == 0.25
    assert c.deadline_s == 1.5
    assert c.database_url == "postgresql://db/kintsugi"
    assert c.broker_url == "amqp://broker"


def test_mode_obbligatoria():
    with pytest.raises(ErroreConfigurazione, match="MODE manca"):
        da_ambiente({})


@pytest.mark.parametrize("env, messaggio", [
    ({"MODE": "ibrido"}, "MODE='ibrido'"),
    ({"MODE": "sync", "ROLE": "cuoco"}, "ROLE='cuoco'"),
    ({"MODE": "sync", "ROLE": "worker"}, "richiede MODE=async"),
    ({"MODE": "sync", "SERVICE_TIME_S": "tanto"}, "SERVICE_TIME_S='tanto'"),
    ({"MODE": "sync", "DEADLINE_S": "-1"}, "DEADLINE_S='-1'"),
])
def test_valori_non_validi(env, messaggio):
    with pytest.raises(ErroreConfigurazione, match=messaggio):
        da_ambiente(env)


def test_il_riassunto_non_stampa_gli_indirizzi():
    c = da_ambiente({"MODE": "sync", "DATABASE_URL": "postgresql://utente:segreta@db/k"})
    assert "segreta" not in c.riassunto()
    assert "database=impostato" in c.riassunto()


def test_crea_app_tiene_la_configurazione():
    c = da_ambiente({"MODE": "async", "ROLE": "worker"})
    assert crea_app(c).state.config is c
