"""Prove dello script dei guasti F1-F4 con kubectl e la shell del nodo finti (nessun cluster).

    pytest -q harness/faults

La prova sul cluster vero (il SIGKILL arriva e il container riparte nello stesso pod) è descritta
nel diario: richiede kind e Docker.
"""

import json
from datetime import datetime, timezone

import pytest

import arresto

ID_A = "a" * 64
ID_B = "b" * 64


def pod(nome, uid="uid-1", nodo="kintsugi-worker2", riavvii=0, in_esecuzione=True, container_id=ID_A,
        container="api"):
    stato = {"running": {"startedAt": "2026-11-12T09:00:00Z"}} if in_esecuzione else {"waiting": {}}
    return {
        "metadata": {"name": nome, "uid": uid},
        "spec": {"nodeName": nodo},
        "status": {"containerStatuses": [{
            "name": container, "containerID": f"containerd://{container_id}",
            "restartCount": riavvii, "state": stato}]},
    }


class ShellFinta:
    """Risponde ai comandi con le righe date, in ordine, e li ricorda."""

    def __init__(self, *risposte):
        self.risposte = list(risposte)
        self.comandi = []
        self.chiusa = False

    def comando(self, riga):
        self.comandi.append(riga)
        return self.risposte.pop(0)

    def chiudi(self):
        self.chiusa = True


def test_si_colpisce_il_primo_pod_in_esecuzione_in_ordine_alfabetico():
    pods = {"items": [pod("api-c"), pod("api-a", in_esecuzione=False), pod("api-b", uid="uid-b")]}
    bersaglio = arresto.scegli_bersaglio(pods)
    assert (bersaglio.pod, bersaglio.pod_uid) == ("api-b", "uid-b")
    assert bersaglio.container_id == ID_A  # senza il prefisso containerd://


def test_un_pod_in_chiusura_non_si_colpisce():
    # Dopo un rollout il pod vecchio è ancora «running» ma sta terminando.
    vecchio = pod("api-a")
    vecchio["metadata"]["deletionTimestamp"] = "2026-11-12T09:40:00Z"
    assert arresto.scegli_bersaglio({"items": [vecchio, pod("api-b")]}).pod == "api-b"


def test_si_puo_scegliere_il_pod_per_nome():
    pods = {"items": [pod("api-a"), pod("api-b", nodo="kintsugi-worker")]}
    assert arresto.scegli_bersaglio(pods, "api-b").nodo == "kintsugi-worker"


@pytest.mark.parametrize("pods, nome", [({"items": []}, None),
                                        ({"items": [pod("api-a", in_esecuzione=False)]}, None),
                                        ({"items": [pod("api-a")]}, "api-z")])
def test_senza_un_pod_in_esecuzione_e_un_errore(pods, nome):
    with pytest.raises(arresto.ErroreGuasto, match="niente da colpire"):
        arresto.scegli_bersaglio(pods, nome)


def test_il_pid_si_legge_dal_nodo():
    shell = ShellFinta("8179")
    assert arresto.pid_nel_nodo(shell, ID_A) == 8179
    assert "crictl inspect" in shell.comandi[0] and "{{.info.pid}}" in shell.comandi[0]


@pytest.mark.parametrize("risposta", ["0", "1", "", "errore"])
def test_un_pid_assente_o_uguale_a_uno_e_un_errore(risposta):
    # PID 1 sarebbe il processo init del nodo: mai da colpire.
    with pytest.raises(arresto.ErroreGuasto, match="PID"):
        arresto.pid_nel_nodo(ShellFinta(risposta), ID_A)


def test_il_kill_ricontrolla_il_container_e_restituisce_gli_istanti():
    shell = ShellFinta("ok 1731402796.731000000 1731402796.731200000")
    orologio = iter([1731402796.730, 1731402796.734]).__next__
    istanti = arresto.manda_segnale(shell, [(8179, ID_A)], "KILL", orologio)
    assert istanti == {"prima": 1731402796.730, "dopo": 1731402796.734,
                       "nodo": 1731402796.731, "nodo_fine": 1731402796.7312}
    comando = shell.comandi[0]
    # Il PID deve essere ancora del container: altrimenti il kill non parte.
    assert comando.index(f"grep -q {ID_A} /proc/8179/cgroup") < comando.index("kill -KILL 8179")
    assert comando.index("date +%s.%N") < comando.index("kill -KILL") < comando.rindex("date +%s.%N")


def test_piu_pid_si_uccidono_con_un_solo_comando_dopo_tutti_i_controlli():
    shell = ShellFinta("ok 1.0 1.1")
    arresto.manda_segnale(shell, [(101, ID_A), (102, ID_B)])
    assert len(shell.comandi) == 1
    comando = shell.comandi[0]
    assert comando.index(f"/proc/102/cgroup") < comando.index("kill -KILL 101 102")
    assert f"grep -q {ID_A} /proc/101/cgroup" in comando and f"grep -q {ID_B} /proc/102/cgroup" in comando


@pytest.mark.parametrize("risposta", ["fallito", "ok", "ok 1.0", ""])
def test_un_kill_non_riuscito_e_un_errore(risposta):
    with pytest.raises(arresto.ErroreGuasto, match="non è riuscito"):
        arresto.manda_segnale(ShellFinta(risposta), [(8179, ID_A)])


def kubectl_che_risponde(*pods_in_ordine):
    """Un kubectl finto: a ogni `get pod` restituisce il pod seguente della lista."""
    coda = list(pods_in_ordine)

    def kubectl(parametri):
        assert parametri[:2] == ["get", "pod"]
        return json.dumps(coda.pop(0) if len(coda) > 1 else coda[0])
    return kubectl


def bersaglio_di(p):
    return arresto.scegli_bersaglio({"items": [p]})


def test_si_aspetta_il_riavvio_nello_stesso_pod():
    prima = pod("api-a")
    kubectl = kubectl_che_risponde(prima, pod("api-a", riavvii=0, in_esecuzione=False),
                                   pod("api-a", riavvii=1, container_id=ID_B))
    stato = arresto.aspetta_riavvio(kubectl, bersaglio_di(prima), attesa_s=10, dormi=lambda _: None)
    assert stato["restartCount"] == 1 and stato["containerID"].endswith(ID_B)


def test_un_pod_ricreato_invece_che_riavviato_e_un_errore():
    prima = pod("api-a")
    kubectl = kubectl_che_risponde(pod("api-a", uid="uid-nuovo", riavvii=0))
    with pytest.raises(arresto.ErroreGuasto, match="ricreato"):
        arresto.aspetta_riavvio(kubectl, bersaglio_di(prima), attesa_s=10, dormi=lambda _: None)


def test_senza_riavvio_entro_l_attesa_e_un_errore():
    prima = pod("api-a")
    tempo = iter(range(100)).__next__
    with pytest.raises(arresto.ErroreGuasto, match="entro 3 s"):
        arresto.aspetta_riavvio(kubectl_che_risponde(prima), bersaglio_di(prima), attesa_s=3,
                                orologio=tempo, dormi=lambda _: None)


GUASTO = datetime(2026, 11, 12, 9, 13, 16, 730000, tzinfo=timezone.utc).timestamp()
F1 = arresto.GUASTI["F1"]


def guasto_finto(dopo):
    """kubectl che elenca un pod `api-a` e poi risponde `dopo`, shell che uccide, orologio fisso."""
    shell = ShellFinta("pronto", "8179", "uvicorn", f"ok {GUASTO + 0.001:.9f} {GUASTO + 0.0011:.9f}")
    orologio = iter([GUASTO, GUASTO + 0.004]).__next__

    def kubectl(parametri):
        if parametri[:2] == ["get", "pods"]:
            assert parametri[2:4] == ["-l", "app=api"]
            return json.dumps({"items": [pod("api-a")]})
        return json.dumps(dopo)
    return kubectl, shell, orologio


def test_tutto_il_guasto_con_kubectl_e_shell_finti():
    kubectl, shell, orologio = guasto_finto(pod("api-a", riavvii=1, container_id=ID_B))
    scritti = []
    risultato = arresto.provoca(kubectl, lambda _: shell, F1, None, attesa_s=10,
                                scrivi=scritti.append, orologio=orologio)
    assert shell.comandi[0] == "echo pronto" and shell.chiusa
    assert scritti[-1] == risultato and risultato["riavviati_nello_stesso_pod"] is True
    assert (risultato["guasto"], risultato["segnale"]) == ("F1", "SIGKILL")
    assert risultato["ts_guasto"] == "2026-11-12T09:13:16.730+00:00"
    assert risultato["ts_conferma"] == "2026-11-12T09:13:16.734+00:00"
    assert risultato["incertezza_s"] == pytest.approx(0.004)
    assert risultato["ts_nodo"] == "2026-11-12T09:13:16.731+00:00"
    [b] = risultato["bersagli"]
    assert (b["pod"], b["pid_nel_nodo"], b["processo"], b["riavvii"], b["riavvii_dopo"]) \
        == ("api-a", 8179, "uvicorn", 0, 1)
    assert b["container_id_dopo"] == ID_B
    json.dumps(risultato)  # si scrive così com'è in guasto.json


def test_senza_riavvio_l_istante_del_guasto_resta_scritto():
    # Il kill è avvenuto: il run ha bisogno di t_g anche se il container non riparte.
    kubectl, shell, orologio = guasto_finto(pod("api-a", riavvii=0, in_esecuzione=False))
    scritti = []
    with pytest.raises(arresto.ErroreGuasto, match="back-off"):
        arresto.provoca(kubectl, lambda _: shell, F1, None, attesa_s=0.6,
                        scrivi=scritti.append, orologio=orologio)
    assert scritti[0]["ts_guasto"] == "2026-11-12T09:13:16.730+00:00"
    assert scritti[-1]["riavviati_nello_stesso_pod"] is False and "entro 0.6 s" in scritti[-1]["errore"]


def test_la_shell_si_chiude_anche_se_il_kill_fallisce():
    shell = ShellFinta("pronto", "8179", "uvicorn", "fallito")
    scritti = []
    with pytest.raises(arresto.ErroreGuasto):
        arresto.provoca(lambda _: json.dumps({"items": [pod("api-a")]}), lambda _: shell, F1,
                        None, attesa_s=10, scrivi=scritti.append)
    assert shell.chiusa and scritti == []  # nessun kill, nessun guasto da registrare


@pytest.mark.parametrize("nome,selettore,container", [("F2", "app=worker", "worker"), ("F3", "app=coda", "rabbitmq"),
                                                      ("F4", "app=db", "postgres")])
def test_ogni_guasto_ha_il_suo_selettore_e_il_suo_container(nome, selettore, container):
    g = arresto.GUASTI[nome]
    assert (g.selettore, g.container, g.segnale) == (selettore, container, "KILL")
    assert g.tutti == (nome == "F2")


def test_toxiproxy_non_e_mai_un_bersaglio():
    # Anche se il selettore lo prendesse, il container non è quello del guasto F4 (#93).
    pods = {"items": [pod("toxiproxy-a", container="toxiproxy")]}
    with pytest.raises(arresto.ErroreGuasto, match="container postgres"):
        arresto.scegli_bersagli(pods, "postgres")
    assert not any(g.selettore == "app=toxiproxy" for g in arresto.GUASTI.values())


def test_con_f2_si_prendono_tutti_i_worker_e_un_worker_fermo_e_un_errore():
    pods = {"items": [pod("worker-b", container="worker"), pod("worker-a", container="worker")]}
    assert [b.pod for b in arresto.scegli_bersagli(pods, "worker", tutti=True)] == ["worker-a", "worker-b"]
    pods["items"].append(pod("worker-c", container="worker", in_esecuzione=False))
    with pytest.raises(arresto.ErroreGuasto, match="worker-c"):
        arresto.scegli_bersagli(pods, "worker", tutti=True)


def test_f2_uccide_tutti_i_worker_con_un_comando_per_nodo_e_aspetta_ogni_riavvio():
    """Tre worker su due nodi: due comandi di kill, istanti dal primo all'ultimo, tre riavvii."""
    worker = {"worker-a": ("kintsugi-worker2", "a" * 64), "worker-b": ("kintsugi-worker2", "b" * 64),
              "worker-c": ("kintsugi-worker", "c" * 64)}
    shell = {"kintsugi-worker": ShellFinta("pronto", "303", "uvicorn", f"ok {GUASTO + 0.012:.6f} {GUASTO + 0.0121:.6f}"),
             "kintsugi-worker2": ShellFinta("pronto", "101", "uvicorn", "102", "uvicorn",
                                            f"ok {GUASTO + 0.001:.6f} {GUASTO + 0.0012:.6f}")}

    def kubectl(parametri):
        if parametri[:2] == ["get", "pods"]:
            assert parametri[2:4] == ["-l", "app=worker"]
            return json.dumps({"items": [pod(n, uid=n, nodo=nd, container_id=c, container="worker")
                                         for n, (nd, c) in worker.items()]})
        n = parametri[2]
        return json.dumps(pod(n, uid=n, nodo=worker[n][0], riavvii=1, container_id="d" * 64, container="worker"))

    orologio = iter([GUASTO, GUASTO + 0.004, GUASTO + 0.005, GUASTO + 0.015]).__next__
    risultato = arresto.provoca(kubectl, shell.__getitem__, arresto.GUASTI["F2"], None, attesa_s=10,
                                scrivi=lambda _: None, orologio=orologio)
    assert [c for c in shell["kintsugi-worker2"].comandi if "kill" in c] == [
        f"grep -q {'a' * 64} /proc/101/cgroup 2>/dev/null && grep -q {'b' * 64} /proc/102/cgroup 2>/dev/null"
        " && t=$(date +%s.%N) && kill -KILL 101 102 && echo \"ok $t $(date +%s.%N)\" || echo fallito"]
    assert all(s.chiusa for s in shell.values())
    assert risultato["incertezza_s"] == pytest.approx(0.015)  # dal primo comando alla fine dell'ultimo
    assert risultato["ts_nodo"] == "2026-11-12T09:13:16.731+00:00"
    assert risultato["ts_nodo_ultimo"] == "2026-11-12T09:13:16.742+00:00"
    assert [b["pod"] for b in risultato["bersagli"]] == ["worker-a", "worker-b", "worker-c"]
    assert all(b["riavvii_dopo"] == 1 for b in risultato["bersagli"])
    assert risultato["riavviati_nello_stesso_pod"] is True


def test_con_f2_il_pod_non_si_sceglie(monkeypatch, tmp_path):
    monkeypatch.setattr(arresto.sys, "argv", ["arresto.py", "--cartella", str(tmp_path), "--guasto", "F2",
                                              "--pod", "worker-a"])
    with pytest.raises(SystemExit) as uscita:
        arresto.main()
    assert uscita.value.code == 2


class ProcessoBloccato:
    """Un `docker exec` che non esce da solo: `wait` con timeout scade finché non lo si uccide."""

    def __init__(self):
        self.stdin = self
        self.ucciso = False

    def close(self):
        pass

    def wait(self, timeout=None):
        if timeout is not None and not self.ucciso:
            raise arresto.subprocess.TimeoutExpired("docker exec", timeout)

    def kill(self):
        self.ucciso = True


def test_una_shell_che_non_si_chiude_si_uccide_senza_errore():
    # Il kill è già partito: un errore qui farebbe perdere gli istanti del guasto.
    shell = arresto.ShellNelNodo.__new__(arresto.ShellNelNodo)
    shell._processo = ProcessoBloccato()
    shell.chiudi()
    assert shell._processo.ucciso


def test_senza_docker_o_kubectl_si_esce_con_un_messaggio(monkeypatch, tmp_path, capsys):
    def manca(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "kubectl")

    monkeypatch.setattr(arresto.subprocess, "run", manca)
    monkeypatch.setattr(arresto.sys, "argv", ["arresto.py", "--cartella", str(tmp_path)])
    with pytest.raises(SystemExit) as uscita:
        arresto.main()
    assert uscita.value.code == "errore: programma non trovato: kubectl (servono docker e kubectl)"
    assert not (tmp_path / "guasto.json").exists()
