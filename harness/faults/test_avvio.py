"""Prove delle parti di `avvio.py` che non hanno bisogno del cluster.

    pytest -q harness/faults

La misura vera (SIGKILL, riavvio e pronto sul cluster) è descritta nel diario: richiede kind e Docker.
"""

from datetime import datetime, timezone

import avvio


def istante(testo: str) -> float:
    return datetime.fromisoformat(testo).astimezone(timezone.utc).timestamp()


def test_istante_del_log_con_nanosecondi():
    log = ("2026-11-18T09:00:00.100000000Z INFO: avvio\n"
           "2026-11-18T09:00:01.234567891Z INFO: Application startup complete.\n")
    assert avvio.istante_del_log(log, "startup complete") == istante("2026-11-18T09:00:01.234567+00:00")


def test_istante_del_log_con_frazione_senza_zeri_finali():
    # kubectl toglie gli zeri in coda: «.5» vuol dire mezzo secondo
    assert avvio.istante_del_log("2026-11-18T09:00:00.5Z pronto", "pronto") == istante("2026-11-18T09:00:00.5+00:00")
    assert avvio.istante_del_log("2026-11-18T09:00:00Z pronto", "pronto") == istante("2026-11-18T09:00:00+00:00")


def test_istante_del_log_senza_la_riga():
    assert avvio.istante_del_log("2026-11-18T09:00:00Z altro", "pronto") is None
    assert avvio.istante_del_log("", "pronto") is None


def pod(riavvii=0, in_esecuzione=True, pronto=True):
    return {"status": {
        "containerStatuses": [{"restartCount": riavvii, "state": {"running": {}} if in_esecuzione else {"waiting": {}}}],
        "conditions": [{"type": "Ready", "status": "True" if pronto else "False"}],
    }}


def test_non_conta_finche_il_container_non_e_ripartito():
    # dopo il kill il pod può risultare ancora pronto con il vecchio container
    assert avvio.stato_del_container(pod(riavvii=0, pronto=True), 0) == (False, False)
    assert avvio.stato_del_container(pod(riavvii=1, in_esecuzione=False, pronto=False), 0) == (False, False)


def test_ripartito_ma_non_ancora_pronto_e_poi_pronto():
    assert avvio.stato_del_container(pod(riavvii=1, pronto=False), 0) == (True, False)
    assert avvio.stato_del_container(pod(riavvii=1, pronto=True), 0) == (True, True)


def test_pod_nuovo_mai_riavviato_con_soglia_meno_uno():
    # per scegliere il pod da colpire si cerca uno `Ready` con restartCount 0
    assert avvio.stato_del_container(pod(riavvii=0, pronto=True), -1) == (True, True)


def test_riassunto_e_tabella():
    assert avvio.riassunto([3.0, 1.0, 2.0]) == (2.0, 1.0, 3.0)
    riga = avvio.tabella("db", {"riavvio": [1.0, 2.0, 3.0], "pronto": [4.5], "evento": []})
    assert riga.splitlines() == ["| db | riavvio | 3 | 2,0 | 1,0 | 3,0 |", "| db | pronto | 1 | 4,5 | 4,5 | 4,5 |"]
