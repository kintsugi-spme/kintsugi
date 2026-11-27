"""Prove di `esporta.py` senza il cluster: un kubectl finto con lo stato che conta (database, code, eventi).

    pytest -q harness/esporta

La prova vera (un run su V3, ordini messi apposta nella coda dei falliti) è descritta nel diario: richiede kind.
"""

import csv
import json
from datetime import datetime, timezone

import pytest

import esporta

DA = datetime(2026, 11, 27, 9, 0, 0, tzinfo=timezone.utc)
A = datetime(2026, 11, 27, 9, 10, 0, tzinfo=timezone.utc)
ID = [f"00000000-0000-4000-8000-{k:012d}" for k in range(6)]


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr(esporta.time, "sleep", lambda s: None)


def leggi(percorso):
    with open(percorso, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class ClusterFinto:
    """Un cluster con V3 (o V1/V2 senza coda). Gli ordini 0-3 sono nel database, il 4 e il 5 nella coda dei falliti."""

    def __init__(self, con_coda=True, primario=None, prometheus_rotto=False, categorie_codice=0):
        self.con_coda = con_coda
        self.primario = primario
        self.prometheus_rotto = prometheus_rotto
        self.righe_db = [(ID[k], f"2026-11-27 09:01:0{k}.100000+00", f"2026-11-27 09:01:0{k}.150000+00") for k in range(4)]
        self.falliti = [json.dumps({"id": ID[4], "ts_ricezione": "2026-11-27T09:01:04+00:00"}),
                        json.dumps({"id": ID[5].upper(), "ts_ricezione": "2026-11-27T09:01:05+00:00"}), "non è json"]
        self.in_coda = 0
        self.registro: list[str] = []
        self.categorie_codice = categorie_codice

    def indice(self, pezzo: str) -> int:
        return next(i for i, c in enumerate(self.registro) if pezzo in c)

    def categorie(self, cartella):
        self.registro.append("categorie.py")
        return self.categorie_codice, "5 ordini inviati; categorie in categorie.csv"

    def __call__(self, args, input=None):
        self.registro.append(" ".join(args))
        if args[:2] == ["get", "deployment/coda"]:
            return "deployment.apps/coda\n" if self.con_coda else ""
        if args[:2] == ["get", "pods"] and "cnpg.io/instanceRole=primary" in args:
            return f"pod/{self.primario}\n" if self.primario else ""
        if "psql" in args:
            sql = args[-1]
            if "from ordini" in sql and "count" in sql:
                return "n\n" + str(len(self.righe_db)) + "\n"
            if "from ordini" in sql:
                return "id,ts_ricezione,ts_scrittura\n" + "".join(",".join(r) + "\n" for r in self.righe_db)
            if "from duplicati" in sql:
                return "id\n" + ID[1] + "\n"
        if args[:3] == ["exec", "-i", "deploy/worker"]:
            modo = args[-1]
            letti = list(self.falliti)
            if modo == "sposta":
                self.falliti = []
                for corpo in letti:
                    try:
                        self.righe_db.append((json.loads(corpo)["id"].lower(), "2026-11-27 09:09:00+00", "2026-11-27 09:09:01+00"))
                    except ValueError:
                        pass
            return "righe di avvio\n" + json.dumps(letti) + "\n"
        if "list_queues" in args:
            return f"Timeout: 60.0 seconds ...\nname\tmessages\nordini\t{self.in_coda}\nordini.falliti\t{len(self.falliti)}\n"
        if args[:3] == ["get", "events", "-o"]:
            return json.dumps({"items": [
                {"type": "Normal", "reason": "Killing", "message": "Stopping\ncontainer api", "count": 1,
                 "involvedObject": {"kind": "Pod", "name": "api-1"}, "lastTimestamp": "2026-11-27T09:05:00Z"},
                {"type": "Normal", "reason": "Created", "message": "Created container", "count": 2,
                 "involvedObject": {"kind": "Pod", "name": "api-2"}, "lastTimestamp": "2026-11-27T08:00:00Z"},
            ]})
        if args[:3] == ["get", "pods", "-o"]:
            return json.dumps({"items": [{"metadata": {"name": "api-2"}, "status": {"conditions": [
                {"type": "Ready", "status": "True", "lastTransitionTime": "2026-11-27T09:05:10Z"}]}}]})
        if args[:2] == ["get", "--raw"]:
            if self.prometheus_rotto:
                raise OSError("Prometheus non risponde")
            return json.dumps({"status": "success", "data": {"result": [
                {"metric": {"__name__": "rabbitmq_detailed_queue_messages_ready", "queue": "ordini", "job": "rabbitmq"},
                 "values": [[1795770000, "3"], [1795770005, "0"]]}]}})
        raise AssertionError(f"comando non previsto: {args}")


def esporta_tutto(cartella, cluster, **opzioni):
    return esporta.Esporta(cluster, cartella, DA, A, categorie=cluster.categorie, **opzioni).esegui()


def test_i_file_di_data_readme_ci_sono_con_le_colonne_giuste(tmp_path):
    esito = esporta_tutto(tmp_path, ClusterFinto())
    assert esito["problemi"] == []
    assert [r["id"] for r in leggi(tmp_path / "db.csv")][:2] == [ID[0], ID[1]]
    assert set(leggi(tmp_path / "db.csv")[0]) == {"id", "ts_ricezione", "ts_scrittura"}
    assert [r["id"] for r in leggi(tmp_path / "duplicati.csv")] == [ID[1]]
    assert set(leggi(tmp_path / "events.csv")[0]) == set(esporta.COLONNE_EVENTI)
    assert set(leggi(tmp_path / "prometheus.csv")[0]) == set(esporta.COLONNE_PROMETHEUS)
    assert (tmp_path / "esportazione.json").is_file()


def test_falliti_e_db_si_esportano_prima_della_rielaborazione(tmp_path):
    cluster = ClusterFinto()
    esporta_tutto(tmp_path, cluster)
    # db.csv, i falliti letti, poi lo spostamento nella coda; categorie.py per ultimo
    assert cluster.indice("from ordini order by") < cluster.indice("python - leggi") < cluster.indice("python - sposta")
    assert cluster.indice("python - sposta") < cluster.indice("get events") < cluster.registro.index("categorie.py")
    # e quello che è stato esportato è lo stato di prima: i falliti non sono in db.csv
    assert {r["id"] for r in leggi(tmp_path / "db.csv")} == set(ID[:4])
    assert [r["id"] for r in leggi(tmp_path / "falliti.csv")] == [ID[4], ID[5]]  # in minuscolo, l'illeggibile no


def test_la_rielaborazione_si_conta_a_parte(tmp_path):
    cluster = ClusterFinto()
    esito = esporta_tutto(tmp_path, cluster)
    assert esito["rielaborati"] == {"spostati": 3, "salvati": 2, "ancora_in_coda": 0}
    assert esito["falliti"] == 2 and esito["falliti_illeggibili"] == 1
    assert json.loads((tmp_path / "esportazione.json").read_text())["rielaborati"]["salvati"] == 2


def test_senza_rielaborazione_i_falliti_restano_dove_sono(tmp_path):
    cluster = ClusterFinto()
    esporta_tutto(tmp_path, cluster, rielabora=False)
    assert not any("sposta" in c for c in cluster.registro)
    assert len(cluster.falliti) == 3


@pytest.mark.parametrize("versione", ["V1/V2 (nessuna coda)"])
def test_senza_la_coda_falliti_csv_ha_solo_l_intestazione(tmp_path, versione):
    cluster = ClusterFinto(con_coda=False)
    esito = esporta_tutto(tmp_path, cluster)
    assert esito["problemi"] == []
    assert (tmp_path / "falliti.csv").read_text() == "id,ts_ricezione\n"
    assert not any("deploy/worker" in c or "list_queues" in c for c in cluster.registro)
    assert esito["rielaborati"]["spostati"] == 0


def test_in_v4_si_legge_dal_primario_del_momento(tmp_path):
    cluster = ClusterFinto(con_coda=False, primario="db-2")
    esporta_tutto(tmp_path, cluster)
    assert any(c.startswith("exec pod/db-2 -c postgres -- env PGTZ=UTC psql") for c in cluster.registro)
    assert not any("deploy/db" in c for c in cluster.registro)


def test_il_database_si_legge_in_utc_e_non_da_toxiproxy():
    comando = esporta.Esporta(ClusterFinto(), None, DA, A).comando_psql()
    assert comando[:3] == ["exec", "deploy/db", "--"] and "PGTZ=UTC" in comando


def test_categorie_con_anomalie_fa_fallire_l_esportazione_ma_i_file_ci_sono(tmp_path):
    esito = esporta_tutto(tmp_path, ClusterFinto(categorie_codice=1))
    assert esito["problemi"] == ["categorie: categorie.py ha trovato delle anomalie: il run va esaminato"]
    assert (tmp_path / "db.csv").is_file() and (tmp_path / "prometheus.csv").is_file()


def test_prometheus_irraggiungibile_non_ferma_gli_altri_passi(tmp_path):
    esito = esporta_tutto(tmp_path, ClusterFinto(prometheus_rotto=True))
    assert [p.split(":")[0] for p in esito["problemi"]] == ["prometheus"]
    assert (tmp_path / "events.csv").is_file() and "categorie" in esito


def test_se_il_database_non_si_legge_la_rielaborazione_non_parte(tmp_path):
    class Rotto(ClusterFinto):
        def __call__(self, args, input=None):
            if "psql" in args:
                raise OSError("database irraggiungibile")
            return super().__call__(args, input)

    cluster = Rotto()
    esito = esporta_tutto(tmp_path, cluster)
    assert esito["problemi"][0].startswith("db:")
    assert not any("sposta" in c for c in cluster.registro)  # i falliti non devono diventare «completati»


def test_il_tempo_di_ogni_passo_e_scritto(tmp_path):
    esito = esporta_tutto(tmp_path, ClusterFinto())
    assert set(esito["secondi_per_passo"]) == {"db", "falliti", "rielaborazione", "eventi", "prometheus", "categorie"}
    assert esito["durata_s"] >= 0


def test_gli_eventi_nell_intervallo_con_il_pronto_dei_pod():
    cluster = ClusterFinto()
    righe = esporta.righe_eventi(json.loads(cluster(["get", "events", "-o", "json"])),
                                 json.loads(cluster(["get", "pods", "-o", "json"])), DA, A)
    assert [(r[0], r[2]) for r in righe] == [("2026-11-27T09:05:00.000+00:00", "Killing"),
                                              ("2026-11-27T09:05:10.000+00:00", "Ready")]  # Created delle 8:00 è fuori
    assert righe[0][4] == "Stopping container api" and righe[0][5] == "1"


def test_le_serie_di_prometheus_diventano_una_riga_per_misura():
    risposta = {"status": "success", "data": {"result": [
        {"metric": {"__name__": "m", "queue": "ordini", "job": "rabbitmq"}, "values": [[1795770000, "3"], [1795770005, "0"]]}]}}
    assert esporta.righe_prometheus(risposta) == [
        ["2026-11-27T09:00:00.000+00:00", "m", "job=rabbitmq;queue=ordini", "3"],
        ["2026-11-27T09:00:05.000+00:00", "m", "job=rabbitmq;queue=ordini", "0"]]
    with pytest.raises(esporta.ErroreEsportazione, match="boom"):
        esporta.righe_prometheus({"status": "error", "error": "boom"})


def test_l_intestazione_di_psql_deve_essere_quella_attesa():
    with pytest.raises(esporta.ErroreEsportazione, match="inattesa"):
        esporta.csv_di_psql("altra,intestazione\n1,2\n", esporta.COLONNE_DB)
    assert esporta.csv_di_psql("id\nabc\n", ["id"]) == [["abc"]]


def test_l_intervallo_del_run_ha_i_margini(tmp_path):
    (tmp_path / "client.csv").write_text(
        "ts_invio,id,esito,tempo_risposta_s\n2026-11-27T09:00:10+00:00,a,201,0.1\n2026-11-27T09:05:10+00:00,b,201,0.1\n")
    da, a = esporta.intervallo_del_run(tmp_path)
    assert da == datetime(2026, 11, 27, 8, 55, 10, tzinfo=timezone.utc)
    assert a == datetime(2026, 11, 27, 9, 6, 10, tzinfo=timezone.utc)
    with pytest.raises(esporta.ErroreEsportazione, match="manca"):
        esporta.intervallo_del_run(tmp_path / "altra")


def test_i_messaggi_illeggibili_si_contano_a_parte():
    righe, illeggibili = esporta.messaggi_falliti(['{"id": "ABC", "ts_ricezione": "t"}', "x", '{"id": 1}'])
    assert righe == [["abc", "t"]] and illeggibili == 2
