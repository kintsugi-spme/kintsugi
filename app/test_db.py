"""Prove contro un PostgreSQL vero con lo schema caricato. Nella CI girano con quello del job «Test dell'app»; in locale si saltano se non c'è.

    docker run -d --rm --name kintsugi-pg -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust \
        -e POSTGRES_DB=kintsugi -v "$PWD/deploy/k8s/base/schema.sql:/docker-entrypoint-initdb.d/01.sql:ro" \
        postgres:18-alpine
    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/kintsugi pytest test_db.py

Ogni prova svuota le due tabelle: usare solo un database di prova.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from db import salva_ordine

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="serve un PostgreSQL: imposta TEST_DATABASE_URL")


def con_database(prova):
    """Esegue `prova(connessione)` su un database appena svuotato e restituisce i conteggi."""

    async def esegui():
        async with await psycopg.AsyncConnection.connect(URL) as c:
            nome = (await (await c.execute("SELECT current_database()")).fetchone())[0]
            # Difesa: le prove svuotano le tabelle, quindi solo su un database di prova.
            assert nome.startswith("kintsugi"), f"database {nome!r}: usa un database di prova"
            await c.execute("TRUNCATE ordini, duplicati")
            await c.commit()
            await prova(c)
            return (
                (await (await c.execute("SELECT count(*) FROM ordini")).fetchone())[0],
                (await (await c.execute("SELECT count(*) FROM duplicati")).fetchone())[0],
            )

    return asyncio.run(esegui())


ADESSO = datetime.now(timezone.utc)


def test_il_primo_arrivo_e_nuovo():
    risultati = []

    async def prova(c):
        risultati.append(await salva_ordine(c, uuid.uuid4(), ADESSO, "pod-a"))

    assert con_database(prova) == (1, 0)
    assert risultati == [True]


def test_lo_stesso_identificativo_due_volte_da_una_riga_e_un_doppio():
    """Criterio della #29."""
    id_ordine = uuid.uuid4()
    risultati = []

    async def prova(c):
        risultati.append(await salva_ordine(c, id_ordine, ADESSO, "pod-a"))
        risultati.append(await salva_ordine(c, id_ordine, ADESSO, "pod-b"))

    assert con_database(prova) == (1, 1)
    assert risultati == [True, False]


def test_il_doppio_registra_identificativo_e_chi_lo_ha_ricevuto():
    id_ordine = uuid.uuid4()
    righe = []

    async def prova(c):
        await salva_ordine(c, id_ordine, ADESSO, "pod-a")
        await salva_ordine(c, id_ordine, ADESSO, "pod-b")
        righe.extend(await (await c.execute("SELECT id, ricevuto_da, ts_arrivo FROM duplicati")).fetchall())

    con_database(prova)
    assert [(r[0], r[1]) for r in righe] == [(id_ordine, "pod-b")]
    assert righe[0][2] >= ADESSO


def test_tre_arrivi_lasciano_una_riga_e_due_doppi():
    id_ordine = uuid.uuid4()

    async def prova(c):
        for pod in ("pod-a", "pod-b", "pod-c"):
            await salva_ordine(c, id_ordine, ADESSO, pod)

    assert con_database(prova) == (1, 2)


def test_ordini_diversi_non_sono_doppi():
    async def prova(c):
        for _ in range(5):
            assert await salva_ordine(c, uuid.uuid4(), ADESSO, "pod-a") is True

    assert con_database(prova) == (5, 0)


def test_venti_arrivi_contemporanei_dello_stesso_ordine_ne_salvano_uno_solo():
    id_ordine = uuid.uuid4()
    risultati = []

    async def prova(_):
        async def uno(numero):
            async with await psycopg.AsyncConnection.connect(URL) as c:
                risultati.append(await salva_ordine(c, id_ordine, ADESSO, f"pod-{numero}"))

        await asyncio.gather(*(uno(n) for n in range(20)))

    assert con_database(prova) == (1, 19)
    assert risultati.count(True) == 1 and risultati.count(False) == 19
