"""Prove dello script del guasto F1 con kubectl e la shell del nodo finti (nessun cluster).

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


def pod(nome, uid="uid-1", nodo="kintsugi-worker2", riavvii=0, in_esecuzione=True, container_id=ID_A):
    stato = {"running": {"startedAt": "2026-11-12T09:00:00Z"}} if in_esecuzione else {"waiting": {}}
    return {
        "metadata": {"name": nome, "uid": uid},
        "spec": {"nodeName": nodo},
        "status": {"containerStatuses": [{
            "name": "api", "containerID": f"containerd://{container_id}",
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


def test_il_kill_ricontrolla_il_container_e_restituisce_i_tre_istanti():
    shell = ShellFinta("ok 1731402796.731000000")
    orologio = iter([1731402796.730, 1731402796.734]).__next__
    istanti = arresto.manda_sigkill(shell, 8179, ID_A, orologio)
    assert istanti == {"prima": 1731402796.730, "dopo": 1731402796.734, "nodo": 1731402796.731}
    comando = shell.comandi[0]
    # Il PID deve essere ancora del container: altrimenti il kill non parte.
    assert comando.index(f"grep -q {ID_A} /proc/8179/cgroup") < comando.index("kill -KILL 8179")
    assert comando.index("date +%s.%N") < comando.index("kill -KILL")


@pytest.mark.parametrize("risposta", ["fallito", "ok", ""])
def test_un_kill_non_riuscito_e_un_errore(risposta):
    with pytest.raises(arresto.ErroreGuasto, match="non è riuscito"):
        arresto.manda_sigkill(ShellFinta(risposta), 8179, ID_A)


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


def guasto_finto(dopo):
    """kubectl che elenca un pod `api-a` e poi risponde `dopo`, shell che uccide, orologio fisso."""
    shell = ShellFinta("pronto", "8179", f"ok {GUASTO + 0.001:.9f}")
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
    risultato = arresto.provoca(kubectl, lambda _: shell, "app=api", None, attesa_s=10,
                                scrivi=scritti.append, orologio=orologio)
    assert shell.comandi[0] == "echo pronto" and shell.chiusa
    assert scritti[-1] == risultato and risultato["riavviato_nello_stesso_pod"] is True
    assert risultato["ts_guasto"] == "2026-11-12T09:13:16.730+00:00"
    assert risultato["ts_conferma"] == "2026-11-12T09:13:16.734+00:00"
    assert risultato["incertezza_s"] == pytest.approx(0.004)
    assert risultato["ts_nodo"] == "2026-11-12T09:13:16.731+00:00"
    assert (risultato["pod"], risultato["pid_nel_nodo"], risultato["riavvii"], risultato["riavvii_dopo"]) \
        == ("api-a", 8179, 0, 1)
    assert risultato["container_id_dopo"] == ID_B
    json.dumps(risultato)  # si scrive così com'è in guasto.json


def test_senza_riavvio_l_istante_del_guasto_resta_scritto():
    # Il kill è avvenuto: il run ha bisogno di t_g anche se il container non riparte.
    kubectl, shell, orologio = guasto_finto(pod("api-a", riavvii=0, in_esecuzione=False))
    scritti = []
    with pytest.raises(arresto.ErroreGuasto, match="back-off"):
        arresto.provoca(kubectl, lambda _: shell, "app=api", None, attesa_s=0.6,
                        scrivi=scritti.append, orologio=orologio)
    assert scritti[0]["ts_guasto"] == "2026-11-12T09:13:16.730+00:00"
    assert scritti[-1]["riavviato_nello_stesso_pod"] is False and "entro 0.6 s" in scritti[-1]["errore"]


def test_la_shell_si_chiude_anche_se_il_kill_fallisce():
    shell = ShellFinta("pronto", "8179", "fallito")
    scritti = []
    with pytest.raises(arresto.ErroreGuasto):
        arresto.provoca(lambda _: json.dumps({"items": [pod("api-a")]}), lambda _: shell, "app=api",
                        None, attesa_s=10, scrivi=scritti.append)
    assert shell.chiusa and scritti == []  # nessun kill, nessun guasto da registrare
