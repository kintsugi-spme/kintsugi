"""Prove di `reset.py` senza il cluster: un Kubernetes finto con lo stato che conta (pod, righe, code, toxic).

    pytest -q harness/reset

La prova vera (SIGKILL a mano su V2 e V3, posizione sbagliata provocata, 100 ordini su V1 subito dopo) è
descritta nel diario: richiede kind e Docker.
"""

import json

import pytest

import reset

DATI, CALCOLO = "nodo-dati", "nodo-calcolo"
NODI = {"items": [{"metadata": {"name": DATI, "labels": {reset.RUOLO: "dati"}}},
                  {"metadata": {"name": CALCOLO, "labels": {reset.RUOLO: "calcolo"}}},
                  {"metadata": {"name": "nodo-cp", "labels": {}}}]}


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr(reset.time, "sleep", lambda s: None)


class ClusterFinto:
    """Quanto basta di kubectl per il reset: scale, rollout, exec, get pods/nodes/--raw. Registra i comandi."""

    def __init__(self, versione: reset.Versione, calcolo_su=CALCOLO, toxic_resistente=False, truncate_inutile=False):
        self.versione = versione
        self.copie = {d: n for d, (n, _) in versione.attesi().items()}
        self.generazione = {d: 0 for d in self.copie}
        self.calcolo_su = calcolo_su
        self.righe = {"ordini": 50, "duplicati": 3}
        self.code = {"ordini": 7, "ordini.falliti": 2} if versione.worker else {}
        self.toxic = ["latenza"]
        self.toxic_resistente = toxic_resistente
        self.truncate_inutile = truncate_inutile
        self.registro: list[str] = []

    def nodo(self, deployment: str) -> str:
        return DATI if self.versione.attesi()[deployment][1] == "dati" else self.calcolo_su

    def pod(self, deployment: str, i: int) -> dict:
        return {"metadata": {"name": f"{deployment}-g{self.generazione[deployment]}-{i}", "labels": {"app": deployment}},
                "spec": {"nodeName": self.nodo(deployment)},
                "status": {"containerStatuses": [{"restartCount": 0}], "conditions": [{"type": "Ready", "status": "True"}]}}

    def __call__(self, args: list[str]) -> str:
        self.registro.append(" ".join(args))
        if args[:2] == ["get", "pods"]:
            scelti = args[3].split("(")[1].rstrip(")").split(",")
            return json.dumps({"items": [self.pod(d, i) for d in self.copie if d in scelti for i in range(self.copie[d])]})
        if args[:2] == ["get", "nodes"]:
            return json.dumps(NODI)
        if args[:2] == ["get", "--raw"]:
            return json.dumps({"name": "postgres", "toxics": [{"name": t} for t in self.toxic]})
        if args[0] == "scale":
            copie = int(args[1].split("=")[1])
            for d in (a.split("/")[1] for a in args[2:]):
                if self.copie[d] == 0 and copie > 0:
                    self.generazione[d] += 1  # pod nuovi, con nomi nuovi
                self.copie[d] = copie
        elif args[:2] == ["rollout", "restart"]:
            for d in (a.split("/")[1] for a in args[2:]):
                self.generazione[d] += 1
                if d == "toxiproxy" and not self.toxic_resistente:
                    self.toxic = []  # ricreato dal ConfigMap, senza ritardi
        elif args[0] == "exec" and "psql" in args:
            if "TRUNCATE ordini, duplicati" in args and not self.truncate_inutile:
                self.righe = {t: 0 for t in self.righe}
            if "-tAc" in args:
                return f"{self.righe[args[-1].split()[-1]]}\n"
        elif args[0] == "exec" and "list_queues" in args:
            return "Timeout: 60.0 seconds ...\nListing queues for vhost / ...\nname\tmessages\n" + \
                   "".join(f"{q}\t{n}\n" for q, n in self.code.items())
        elif args[0] == "exec" and "purge_queue" in args:
            self.code[args[-1]] = 0
        return ""

    def indice(self, pezzo: str) -> int:
        return next(i for i, c in enumerate(self.registro) if pezzo in c)


V3 = reset.Versione("v3", 3, 3)
V2 = reset.Versione("v2", 3, 0)
V1 = reset.Versione("v1", 1, 0)


def esegui(cluster, **opzioni):
    return reset.Reset(cluster, cluster.versione, **opzioni).esegui()


def test_i_passi_sono_nell_ordine_giusto():
    c = ClusterFinto(V3)
    esegui(c)
    spegni = c.indice("scale --replicas=0 deployment/api deployment/worker")
    database = c.indice("rollout restart deployment/db deployment/coda")
    pulisci = c.indice("TRUNCATE")
    coda = c.indice("purge_queue ordini")
    toxiproxy = c.indice("rollout restart deployment/toxiproxy")
    accendi = c.indice("scale --replicas=3 deployment/api")
    # nessuno scrive mentre si pulisce; il database è pronto prima dell'API; Toxiproxy si ricrea dopo il database
    assert spegni < database < pulisci < toxiproxy < accendi
    assert database < coda < toxiproxy


def test_reset_su_v3_dopo_un_run_sporco_non_da_problemi():
    c = ClusterFinto(V3)
    risultato = esegui(c)
    assert risultato["problemi"] == []
    assert c.righe == {"ordini": 0, "duplicati": 0}
    assert c.code == {"ordini": 0, "ordini.falliti": 0}
    assert c.toxic == []
    assert risultato["durata_s"] >= 0


@pytest.mark.parametrize("versione", [V1, V2])
def test_v1_e_v2_non_toccano_la_coda(versione):
    c = ClusterFinto(versione)
    assert esegui(c)["problemi"] == []
    assert not any("rabbitmqctl" in comando or "deployment/coda" in comando or "deploy/coda" in comando
                   for comando in c.registro)


def test_posizione_sbagliata_e_segnalata():
    # per esempio `kubectl cordon` del nodo calcolo: l'API riparte su `dati`
    c = ClusterFinto(V2, calcolo_su=DATI)
    problemi = esegui(c)["problemi"]
    assert len(problemi) == 3
    assert all("D0006 lo vuole su calcolo" in p for p in problemi)


def test_toxic_rimasto_e_segnalato():
    problemi = esegui(ClusterFinto(V2, toxic_resistente=True))["problemi"]
    assert problemi == ["Toxiproxy ha ancora dei toxic: latenza"]


def test_tabelle_non_svuotate_sono_segnalate():
    problemi = esegui(ClusterFinto(V2, truncate_inutile=True))["problemi"]
    assert "la tabella ordini ha 50 righe, ne servono 0" in problemi


def test_l_ingresso_deve_rispondere_tre_volte_di_fila():
    risposte = iter([False, True, False, True, True, True])
    c = ClusterFinto(V1)
    esegui(c, ingresso="http://prova", risponde=lambda url: next(risposte))
    assert list(risposte) == []  # ha chiesto finché non ha avuto tre sì di fila


def test_ingresso_che_non_risponde_da_errore(monkeypatch):
    monkeypatch.setattr(reset, "ATTESA_S", 0)
    ore = iter(range(0, 1000, 30))
    monkeypatch.setattr(reset.time, "monotonic", lambda: next(ore))
    with pytest.raises(reset.ErroreReset, match="non risponde"):
        esegui(ClusterFinto(V1), ingresso="http://prova", risponde=lambda url: False)


def pod(nome, app="api", nodo=CALCOLO, riavvii=0, pronto=True, chiusura=False):
    p = {"metadata": {"name": nome, "labels": {"app": app}}, "spec": {"nodeName": nodo},
         "status": {"containerStatuses": [{"restartCount": riavvii}],
                    "conditions": [{"type": "Ready", "status": "True" if pronto else "False"}]}}
    if chiusura:
        p["metadata"]["deletionTimestamp"] = "2026-11-25T10:00:00Z"
    return p


def controlla(pods, versione=V1, prima=frozenset()):
    return reset.controlla_pod({"items": pods}, NODI, versione, set(prima))


def sani():
    return [pod("db-1", "db", DATI), pod("toxiproxy-1", "toxiproxy", DATI), pod("api-1")]


def test_pod_sani_nessun_problema():
    assert controlla(sani()) == []


def test_riavvii_diversi_da_zero():
    assert controlla([*sani()[:2], pod("api-1", riavvii=2)]) == ["api-1 ha 2 riavvii, ne servono 0"]


def test_pod_di_prima_del_reset():
    assert controlla(sani(), prima={"api-1"}) == ["api-1 è un pod di prima del reset: non è stato ricreato"]


def test_pod_in_chiusura_e_copia_in_meno():
    problemi = controlla([*sani()[:2], pod("api-1", chiusura=True)])
    assert "api-1 è ancora in chiusura" in problemi
    assert "api: 0 copie, ne servono 1" in problemi


def test_pod_non_pronto_e_numero_di_copie_sbagliato():
    problemi = controlla([*sani(), pod("api-2", pronto=False)])
    assert "api-2 non è pronto" in problemi
    assert "api: 2 copie, ne servono 1" in problemi


def test_componente_che_la_versione_non_ha():
    assert controlla([*sani(), pod("worker-1", "worker")]) == ["worker: c'è un componente che questa versione non ha"]


def test_coda_con_titoli_e_avvisi():
    uscita = "Timeout: 60.0 seconds ...\nListing queues for vhost / ...\nname\tmessages\nordini\t12\nordini.falliti\t0\n"
    assert reset.messaggi_per_coda(uscita) == {"ordini": 12, "ordini.falliti": 0}
    assert reset.messaggi_per_coda("") == {}


def test_versioni_attese_dai_parametri():
    parametri = {"versioni": {"copie_api": 3, "worker_v3": 3}}
    assert reset.versione_attesa("v1", parametri) == reset.Versione("v1", 1, 0)
    assert reset.versione_attesa("v2", parametri) == reset.Versione("v2", 3, 0)
    assert reset.versione_attesa("v3", parametri) == reset.Versione("v3", 3, 3)
    with pytest.raises(reset.ErroreReset, match="V4 e V5"):
        reset.versione_attesa("v4a", parametri)
