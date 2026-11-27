"""Prove dello script del guasto F5 con kubectl, la shell del nodo e Toxiproxy finti (nessun cluster)."""

import json
from datetime import datetime, timezone

import pytest

import latenza

INIZIO = datetime(2026, 11, 26, 11, 0, 0, tzinfo=timezone.utc).timestamp()
ID = "c" * 64


def pod_toxiproxy():
    return {"metadata": {"name": "toxiproxy-a", "uid": "u"}, "spec": {"nodeName": "kintsugi-worker"},
            "status": {"podIP": "10.244.2.7", "containerStatuses": [{
                "name": "toxiproxy", "containerID": f"containerd://{ID}", "restartCount": 0,
                "state": {"running": {}}}]}}


def kubectl(parametri):
    assert parametri[:4] == ["get", "pods", "-l", "app=toxiproxy"]
    return json.dumps({"items": [pod_toxiproxy()]})


class Toxiproxy:
    """Una shell nel nodo che esegue i curl verso un Toxiproxy finto: ricorda i toxic e i comandi."""

    def __init__(self, toxic=(), muore_dopo=None, aggiunta_fallisce=False):
        self.toxic = list(toxic)
        self.comandi = []
        self.chiusa = False
        self.muore_dopo = muore_dopo
        self.aggiunta_fallisce = aggiunta_fallisce
        self.ora_nodo = INIZIO + 0.001

    def comando(self, riga):
        if self.muore_dopo is not None and len(self.comandi) >= self.muore_dopo:
            raise latenza.ErroreGuasto("la shell nel nodo si è chiusa")
        self.comandi.append(riga)
        return esegui_toxiproxy(self, riga)

    def chiudi(self):
        self.chiusa = True


def esegui_toxiproxy(stato, riga):
    if riga == "echo pronto":
        return "pronto"
    if "-X POST" in riga:
        if stato.aggiunta_fallisce:
            return "fallito"
        corpo = json.loads(riga.split("-d '", 1)[1].split("'", 1)[0])
        stato.toxic.append(corpo["name"])
        return f"ok {stato.ora_nodo}"
    if "-X DELETE" in riga:
        nome = riga.rsplit("/", 1)[1].split()[0]
        if nome not in stato.toxic:
            return "fallito"
        stato.toxic.remove(nome)
        return f"ok {stato.ora_nodo + 60}"
    assert "/proxies/postgres/toxics" in riga
    return json.dumps([{"name": t} for t in stato.toxic])


def orologio_da(*valori):
    coda = list(valori)
    return lambda: coda.pop(0) if len(coda) > 1 else coda[0]


def test_il_toxic_e_una_latenza_sulle_risposte_del_database():
    t = latenza.toxic(200)
    assert (t["type"], t["stream"], t["toxicity"]) == ("latency", "downstream", 1.0)
    assert t["attributes"] == {"latency": 200, "jitter": 0}


def test_i_comandi_parlano_con_l_api_di_toxiproxy_e_leggono_l_ora_del_nodo_prima():
    aggiungi = latenza.comando_aggiungi("10.244.2.7", 200)
    assert "http://10.244.2.7:8474/proxies/postgres/toxics" in aggiungi
    assert aggiungi.index("date +%s.%N") < aggiungi.index("curl")
    assert '"latency":200' in aggiungi
    assert latenza.comando_togli("10.244.2.7").endswith(
        "http://10.244.2.7:8474/proxies/postgres/toxics/latenza_f5 && echo \"ok $t\" || echo fallito")


def test_tutto_il_guasto_aggiunge_aspetta_e_toglie():
    shell = Toxiproxy()
    scritti, attese = [], []
    r = latenza.provoca(kubectl, lambda nodo: shell, None, 200, 60, lambda d: scritti.append(dict(d)),
                        orologio=orologio_da(INIZIO, INIZIO + 0.004, INIZIO + 0.01, INIZIO + 60, INIZIO + 60.005),
                        dormi=attese.append)
    assert shell.comandi[0] == "echo pronto" and shell.chiusa
    assert attese == [pytest.approx(59.99)]  # fino a 60 s dall'inizio, non dalla fine della chiamata
    assert r["ts_guasto"] == "2026-11-26T11:00:00.000+00:00" and r["incertezza_s"] == pytest.approx(0.004)
    assert r["ts_fine"] == "2026-11-26T11:01:00.000+00:00" and r["incertezza_fine_s"] == pytest.approx(0.005)
    assert r["ts_nodo"] == "2026-11-26T11:00:00.001+00:00"
    assert (r["pod"], r["nodo"], r["latenza_ms"], r["durata_s"]) == ("toxiproxy-a", "kintsugi-worker", 200, 60)
    assert r["toxic_dopo"] == [] and r["interrotto"] is False
    # L'inizio si scrive subito, prima dell'attesa: il run ne ha bisogno anche se lo script muore.
    assert "ts_guasto" in scritti[0] and "ts_fine" not in scritti[0]
    assert scritti[-1] == r
    json.dumps(r)


def test_interrotto_a_meta_la_latenza_si_toglie_lo_stesso():
    shell = Toxiproxy()
    scritti = []

    def ctrl_c(_secondi):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        latenza.provoca(kubectl, lambda nodo: shell, None, 200, 60, scritti.append,
                        orologio=orologio_da(INIZIO), dormi=ctrl_c)
    assert shell.toxic == [] and shell.chiusa
    assert scritti[-1]["interrotto"] is True and scritti[-1]["toxic_dopo"] == []


def test_con_la_shell_morta_la_latenza_si_toglie_con_un_docker_exec_nuovo():
    shell = Toxiproxy(muore_dopo=3)  # pronto, elenco, aggiunta: poi la shell non risponde più
    nuove = []

    def ripiego(nodo, riga):
        nuove.append(nodo)
        return esegui_toxiproxy(shell, riga)
    r = latenza.provoca(kubectl, lambda nodo: shell, ripiego, 200, 60, lambda d: None,
                        orologio=orologio_da(INIZIO), dormi=lambda _: None)
    assert shell.toxic == [] and r["toxic_dopo"] == []
    assert nuove == ["kintsugi-worker", "kintsugi-worker"]  # DELETE e rilettura


def test_un_toxic_gia_presente_ferma_il_guasto_prima_di_cominciare():
    shell = Toxiproxy(toxic=["vecchio"])
    with pytest.raises(latenza.ErroreGuasto, match="già dei toxic"):
        latenza.provoca(kubectl, lambda nodo: shell, None, 200, 60, lambda d: None)
    assert not any("-X POST" in c for c in shell.comandi) and shell.chiusa


def test_un_aggiunta_fallita_non_scrive_un_guasto():
    shell = Toxiproxy(aggiunta_fallisce=True)
    scritti = []
    with pytest.raises(latenza.ErroreGuasto, match="non è riuscita"):
        latenza.provoca(kubectl, lambda nodo: shell, lambda n, r: esegui_toxiproxy(shell, r), 200, 60,
                        scritti.append)
    assert scritti == [] and shell.toxic == []


def test_un_toxic_che_resta_e_un_errore():
    class Resistente(Toxiproxy):
        def comando(self, riga):
            if "-X DELETE" in riga:
                self.comandi.append(riga)
                return "fallito"
            return super().comando(riga)
    shell = Resistente()
    with pytest.raises(latenza.ErroreGuasto, match="ancora dei toxic: latenza_f5"):
        latenza.provoca(kubectl, lambda nodo: shell, lambda n, r: "fallito" if "DELETE" in r else
                        esegui_toxiproxy(shell, r), 200, 60, lambda d: None, dormi=lambda _: None)


def test_i_valori_predefiniti_vengono_da_parametri_yaml():
    pytest.importorskip("yaml")
    guasti = latenza.leggi_guasti()
    assert guasti["f5_latenza_ms"] > 0 and guasti["f5_durata_s"] > 0
