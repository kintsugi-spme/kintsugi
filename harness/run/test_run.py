"""Prove di `run.py`: la sequenza temporale (quando iniettare, quando fermarsi) con un orologio e un carico finti.

    pytest -q harness/run

Nessun cluster e nessun JMeter: `Finto` fa avanzare un orologio a ogni attesa e produce le richieste del carico
al ritmo chiesto, con il guasto come finestra di richieste fallite. Il run vero (V2, F1, W1) è nel diario.
"""

import json
from datetime import datetime, timezone

import pytest

import run

INIZIO = datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc).timestamp()
RUN = {"riscaldamento_min": 1, "riferimento_min": 1, "guasto_al_minuto": 2, "osservazione_dopo_ripristino_min": 2,
       "ripristino_secondi_consecutivi": 5, "tetto_min": 10, "tetto_min_f6_e_w2": 15, "senza_guasti_min": 5}


def piano(guasto="F1", carico="W1", versione="V2"):
    return run.Piano(versione, carico, guasto, 1, 20.0 if carico != "W2" else None, 20.0 if carico == "W2" else None, RUN, 99.0)


class FintoCarico:
    def __init__(self, amb, ritmo=20.0, ritardo_avvio=0.6, durata_propria=None):
        self.amb, self.ritmo = amb, ritmo
        self.primo = amb.t + ritardo_avvio  # JMeter parte con un po' di ritardo
        self.durata_propria = durata_propria
        self.consegnate = 0
        self.fermato = False

    def nuove(self):
        righe = []
        while True:
            ts = self.primo + self.consegnate / self.ritmo
            if ts + 0.05 > self.amb.t:
                break
            if self.durata_propria is not None and ts > self.primo + self.durata_propria:
                break
            guasto = self.amb.guasto_alle is not None and self.amb.guasto_alle <= ts < self.amb.guasto_alle + self.amb.durata_guasto
            righe.append((ts, not guasto, 0.05))
            self.consegnate += 1
        return righe if not self.fermato else []

    def vivo(self):
        if self.fermato:
            return False
        return self.durata_propria is None or self.amb.t < self.primo + self.durata_propria

    def ferma(self):
        self.fermato = True
        self.amb.fermato_alle = self.amb.t

    def attendi(self):
        return 0


class FintoGuasto:
    """Lo script del guasto: finisce quando il guasto è fatto (o subito, se è uscito male) e dà il suo codice di uscita."""

    def __init__(self, amb, codice=0):
        self.amb, self.codice = amb, codice

    def vivo(self):
        if self.codice != 0:
            return False  # si è fermato subito (per esempio non ha trovato il PID)
        return self.amb.t < self.amb.guasto_alle + 1

    def attendi(self):
        return self.codice


class Finto(run.Ambiente):
    def __init__(self, esito_reset=None, durata_guasto=4.3, carico_che_non_parte=False, durata_propria=None,
                 codice_guasto=0, guasto_senza_json=False, coda_vuota_dopo=None, broker_muto=False, json_subito=False):
        self.t = INIZIO
        self.esito_reset = esito_reset or {"durata_s": 12.0, "problemi": []}
        self.durata_guasto = durata_guasto
        self.carico_che_non_parte = carico_che_non_parte
        self.durata_propria = durata_propria
        self.codice_guasto, self.guasto_senza_json = codice_guasto, guasto_senza_json
        self.coda_vuota_dopo = coda_vuota_dopo  # secondi dopo il guasto in cui l'arretrato di `ordini` è smaltito (None: nessun ordine in attesa)
        self.broker_muto = broker_muto
        self.json_subito = json_subito  # guasto.json c'è prima del guasto, come se lo script l'avesse scritto e poi fosse uscito male
        self.controlli_coda: list[float] = []  # quando è stata guardata la coda
        self.guasto_alle = None
        self.guasto_avviato_a = None
        self.carico = None
        self.fermato_alle = None
        self.chiamate = []

    def orologio(self):
        return self.t

    def dormi(self, secondi):
        self.t += secondi

    def reset(self, piano):
        self.chiamate.append("reset")
        if isinstance(self.esito_reset, Exception):
            raise self.esito_reset
        return self.esito_reset

    def avvia_carico(self, piano, cartella):
        self.chiamate.append("carico")
        self.carico = FintoCarico(self, durata_propria=self.durata_propria)
        if self.carico_che_non_parte:
            self.carico.fermato = True
        return self.carico

    def avvia_guasto(self, piano, cartella, alle):
        self.chiamate.append("guasto")
        self.guasto_avviato_a = self.t
        self.guasto_alle = alle
        return FintoGuasto(self, self.codice_guasto)

    def ts_guasto(self, cartella):
        if self.guasto_senza_json:
            return None
        if self.json_subito and self.guasto_alle is not None:
            return self.guasto_alle
        return self.guasto_alle if self.guasto_alle is not None and self.t >= self.guasto_alle else None

    def ordini_in_attesa(self):
        self.controlli_coda.append(self.t)
        if self.broker_muto:
            return None
        if self.coda_vuota_dopo is None or self.t >= self.guasto_alle + self.coda_vuota_dopo:
            return 0
        return 1400

    def dopo_il_run(self, piano, cartella):
        self.chiamate.append("analisi")
        return {"esportazione": 0, "fermo": 0, "ritmo": 0}


def esegui(tmp_path, amb, p=None, **opzioni):
    cartella = tmp_path / "data" / "locale" / "20261127-100000-prova"
    r = run.Run(p or piano(), amb, cartella, opzioni.get("host"), opzioni.get("commit"))
    codice = r.esegui()
    return codice, r, json.loads((cartella / "meta.json").read_text())


def test_il_guasto_e_al_minuto_2_del_carico_e_il_run_finisce_due_minuti_dopo_il_ripristino(tmp_path):
    amb = Finto()
    codice, r, meta = esegui(tmp_path, amb)
    t0 = amb.carico.primo
    assert codice == 0 and meta["stato"] == "completato"
    assert amb.guasto_alle == pytest.approx(t0 + 120)  # il minuto 2 dalla prima richiesta
    assert amb.guasto_avviato_a == pytest.approx(t0 + 120 - run.ANTICIPO_GUASTO_S, abs=1.5)  # lo script ha il tempo di prepararsi
    ripristino = datetime.fromisoformat(meta["ripristino_accettazione"]).timestamp()
    assert ripristino == pytest.approx(t0 + 124.3, abs=0.1)  # il fermo dura 4,3 s
    assert meta["fine_osservazione"]["motivo"] == "ripristino più osservazione"
    assert amb.fermato_alle == pytest.approx(ripristino + 120, abs=1.5)  # non il tetto di 10 minuti
    assert amb.fermato_alle - t0 < 60 * RUN["tetto_min"]
    assert amb.chiamate == ["reset", "carico", "guasto", "analisi"]  # prima il reset, il guasto in mezzo, poi l'analisi


def test_il_ripristino_si_riconosce_durante_il_run_con_la_regola_di_fermo_py(tmp_path):
    # un fermo più lungo sposta il ripristino e quindi la fine del run
    amb = Finto(durata_guasto=40)
    _, _, meta = esegui(tmp_path, amb)
    t0 = amb.carico.primo
    assert datetime.fromisoformat(meta["ripristino_accettazione"]).timestamp() == pytest.approx(t0 + 160, abs=0.1)
    assert amb.fermato_alle == pytest.approx(t0 + 160 + 120, abs=1.5)


def test_senza_ripristino_il_run_si_ferma_al_tetto(tmp_path):
    amb = Finto(durata_guasto=1e9)
    _, _, meta = esegui(tmp_path, amb)
    assert meta["fine_osservazione"]["motivo"] == "tetto raggiunto: ripristino non avvenuto"
    assert amb.fermato_alle == pytest.approx(amb.carico.primo + 600, abs=1.5)
    assert "ripristino_accettazione" not in meta and meta["stato"] == "completato"  # run valido, «non ripristinato»


def test_senza_guasto_il_run_dura_senza_guasti_min(tmp_path):
    amb = Finto()
    codice, _, meta = esegui(tmp_path, amb, piano(guasto=None))
    assert codice == 0 and "guasto" not in amb.chiamate
    assert meta["fine_osservazione"]["motivo"] == "durata senza guasti"
    assert amb.fermato_alle == pytest.approx(amb.carico.primo + 300, abs=1.5)


def test_w2_senza_guasto_dura_quanto_il_suo_profilo(tmp_path):
    amb = Finto(durata_propria=720)  # 12 minuti: la fine della finestra del costo
    _, _, meta = esegui(tmp_path, amb, piano(guasto=None, carico="W2"))
    assert meta["fine_osservazione"]["motivo"] == "il carico è finito da solo"
    assert amb.t - amb.carico.primo == pytest.approx(720, abs=3)


def test_con_il_reset_fallito_il_run_non_parte_e_meta_dice_perche(tmp_path):
    amb = Finto(esito_reset={"durata_s": 9.0, "problemi": ["api-1 sta sul nodo dati, D0006 lo vuole su calcolo"]})
    codice, _, meta = esegui(tmp_path, amb)
    assert codice == 2
    assert amb.chiamate == ["reset"]  # niente carico, niente guasto
    assert meta["stato"] == "reset fallito"
    assert "D0006 lo vuole su calcolo" in meta["motivo"]
    assert meta["reset"]["problemi"] and meta["versione"] == "V2"


def test_un_reset_che_si_interrompe_con_un_errore_ferma_il_run(tmp_path):
    amb = Finto(esito_reset=run.modulo_reset.ErroreReset("i pod non spariscono entro 180 s"))
    codice, _, meta = esegui(tmp_path, amb)
    assert codice == 2 and meta["stato"] == "reset fallito" and "180 s" in meta["motivo"]
    assert amb.chiamate == ["reset"]


def test_se_jmeter_non_invia_nulla_il_run_finisce_con_errore(tmp_path):
    amb = Finto(carico_che_non_parte=True)
    codice, _, meta = esegui(tmp_path, amb)
    assert codice == 1 and meta["stato"] == "errore" and "nessuna richiesta" in meta["motivo"]
    assert "guasto" not in amb.chiamate


def test_un_errore_a_meta_ferma_comunque_il_carico(tmp_path):
    class Rotto(Finto):
        def ts_guasto(self, cartella):
            raise RuntimeError("guasto.json illeggibile")

    amb = Rotto()
    with pytest.raises(RuntimeError):
        esegui(tmp_path, amb)
    assert amb.carico.fermato  # JMeter non resta acceso
    meta = json.loads(next((tmp_path / "data").rglob("meta.json")).read_text())
    assert meta["stato"] == "errore" and "illeggibile" in meta["motivo"]


def test_meta_ha_commit_computer_configurazione_e_parametri(tmp_path):
    host = {"nome": "mac", "memoria_gib": 16.0, "docker_memoria_gib": 8.0}
    commit = {"hash": "abc123", "modificato": False}
    _, _, meta = esegui(tmp_path, Finto(), piano(), host=host, commit=commit)
    assert meta["commit"] == commit and meta["host"] == host
    assert meta["versione"] == "V2" and meta["guasto"] == "F1" and meta["carico"] == {"nome": "W1", "ritmo": 20.0, "mu1": None}
    assert meta["ripetizione"] == 1 and meta["parametri_run"]["guasto_al_minuto"] == 2
    assert meta["run_id"] == "20261127-100000-prova" and meta["analisi"] == {"esportazione": 0, "fermo": 0, "ritmo": 0}


@pytest.mark.parametrize("p, motivo", [
    (piano(guasto="F6"), "F6 non c'è"),
    (piano(guasto="F2", versione="V2"), "non si fa su V2"),
    (piano(guasto="F7", versione="V3"), "non si fa su V3"),
    (piano(versione="V4A"), "V1, V2 e V3"),
    (run.Piano("V2", "W1", "F1", 1, None, None, RUN, 99), "vuole --ritmo"),
    (run.Piano("V3", "W2", None, 1, None, None, RUN, 99), "vuole --mu1"),
])
def test_un_piano_che_non_ha_senso_e_rifiutato(p, motivo):
    with pytest.raises(run.ErroreRun):
        run.controlla_piano(p)


def test_piani_validi():
    for p in (piano(), piano("F4", versione="V3"), piano("F2", versione="V3"), piano("F5"), piano("F7"), piano(None, "W2", "V3")):
        run.controlla_piano(p)


def test_il_tetto_e_piu_lungo_per_w2_e_per_f6():
    assert piano().tetto_s == 600
    assert piano(None, "W2", "V3").tetto_s == 900
    assert piano("F6", versione="V2").tetto_s == 900


def test_quando_fermarsi():
    p, t0 = piano(), INIZIO
    assert run.quando_fermarsi(p, t0 + 130, t0, None) is None  # guasto in corso, niente ripristino
    assert run.quando_fermarsi(p, t0 + 200, t0, t0 + 125) is None  # ripristinato da 75 s: ancora 45 s da osservare
    assert run.quando_fermarsi(p, t0 + 245, t0, t0 + 125) == "ripristino più osservazione"
    assert run.quando_fermarsi(p, t0 + 600, t0, None).startswith("tetto raggiunto")
    assert run.quando_fermarsi(piano(None), t0 + 299, t0, None) is None
    assert run.quando_fermarsi(piano(None), t0 + 300, t0, None) == "durata senza guasti"


def test_il_ripristino_dopo_il_tetto_conta_il_tetto():
    # ripristinato a 590 s: il run non può durare altri 120 s, finisce al tetto di 600
    assert run.quando_fermarsi(piano(), INIZIO + 600, INIZIO, INIZIO + 590) == "tetto raggiunto"


def test_il_lettore_del_jtl_legge_solo_le_righe_complete(tmp_path):
    jtl = tmp_path / "jmeter.jtl"
    intestazione = "timeStamp,elapsed,label,responseCode,responseMessage,threadName,success,id\n"
    riga1 = '1795770000500,52,POST /ordini,201,"Created, ok",t 1-1,true,a\n'
    riga2 = "1795770000600,2000,POST /ordini,Non HTTP response code: java.net.SocketTimeoutException,Read timed out,t 1-2,false,b\n"
    lettore = run.LettoreJtl(jtl)
    assert lettore.nuove() == []  # il file non c'è ancora
    jtl.write_text(intestazione + riga1 + riga2[:30])  # la seconda riga è a metà
    assert lettore.nuove() == [(1795770000.5, True, 0.052)]
    with open(jtl, "a") as f:
        f.write(riga2[30:])
    assert lettore.nuove() == [(1795770000.6, False, 2.0)]  # esito «timeout»: non riuscita
    assert lettore.nuove() == []
    with open(jtl, "a") as f:
        f.write("riga rotta\n" + riga1)
    assert lettore.nuove() == [(1795770000.5, True, 0.052)]  # la riga che non si legge si salta


def test_l_id_del_run_ha_data_versione_guasto_carico_e_ripetizione():
    ora = datetime(2026, 11, 27, 10, 5, 30, tzinfo=timezone.utc)
    assert run.id_del_run(piano(), ora) == "20261127-100530-V2-F1-W1-r1"
    assert run.id_del_run(piano(None, "W2", "V3"), ora) == "20261127-100530-V3-nessuno-W2-r1"


# --- l'arretrato in V3 e V5 e il guasto che non parte (revisione della #148) ---

def test_in_v3_il_run_aspetta_l_arretrato_oltre_i_due_minuti(tmp_path):
    # l'accettazione non si ferma (fermo 0): il ripristino è subito, ma la coda si svuota 170 s dopo il guasto
    amb = Finto(durata_guasto=0, coda_vuota_dopo=170)
    codice, _, meta = esegui(tmp_path, amb, piano(guasto="F4", versione="V3"))
    assert codice == 0 and meta["stato"] == "completato"
    assert meta["fine_osservazione"]["motivo"] == "ripristino più osservazione"
    assert meta["fine_osservazione"]["ordini_in_attesa"] == 0
    assert amb.fermato_alle - amb.guasto_alle == pytest.approx(170, abs=run.INTERVALLO_CONTROLLO_CODA_S + 1.5)  # non 120


def test_la_coda_si_guarda_solo_dopo_i_due_minuti_e_ogni_pochi_secondi(tmp_path):
    amb = Finto(durata_guasto=0, coda_vuota_dopo=200)
    esegui(tmp_path, amb, piano(guasto="F4", versione="V3"))
    assert min(amb.controlli_coda) >= amb.guasto_alle + 120 - 1.5  # prima non si disturba il broker
    pause = [b - a for a, b in zip(amb.controlli_coda, amb.controlli_coda[1:])]
    assert all(p >= run.INTERVALLO_CONTROLLO_CODA_S - 0.01 for p in pause)


def test_senza_ordini_in_attesa_il_run_di_v3_finisce_come_prima(tmp_path):
    amb = Finto(durata_guasto=0)  # nessun ordine aspetta mai
    _, _, meta = esegui(tmp_path, amb, piano(guasto="F4", versione="V3"))
    assert amb.fermato_alle - amb.guasto_alle == pytest.approx(120, abs=1.5)
    assert meta["fine_osservazione"]["ordini_in_attesa"] == 0


def test_se_l_arretrato_non_si_smaltisce_il_run_si_ferma_al_tetto(tmp_path):
    amb = Finto(durata_guasto=0, coda_vuota_dopo=1e9)
    _, _, meta = esegui(tmp_path, amb, piano(guasto="F4", versione="V3"))
    assert meta["fine_osservazione"]["motivo"] == "tetto raggiunto"
    assert meta["fine_osservazione"]["ordini_in_attesa"] == 1400  # il perché sta in meta.json
    assert amb.fermato_alle == pytest.approx(amb.carico.primo + 600, abs=1.5)


def test_un_broker_che_non_risponde_non_vale_come_nessun_ordine_in_attesa(tmp_path):
    amb = Finto(durata_guasto=0, broker_muto=True)
    _, _, meta = esegui(tmp_path, amb, piano(guasto="F4", versione="V3"))
    assert meta["fine_osservazione"]["motivo"] == "tetto raggiunto"
    assert meta["fine_osservazione"]["ordini_in_attesa"] is None


def test_in_v2_non_si_guarda_la_coda(tmp_path):
    amb = Finto()
    _, _, meta = esegui(tmp_path, amb)
    assert amb.controlli_coda == [] and "ordini_in_attesa" not in meta["fine_osservazione"]


def test_senza_guasto_su_v3_non_si_guarda_la_coda_durante_il_run(tmp_path):
    # il run dura 5 minuti fissi; la coda la aspetta l'esportazione
    amb = Finto(coda_vuota_dopo=1e9)
    amb.guasto_alle = amb.t
    _, _, meta = esegui(tmp_path, amb, piano(guasto=None, versione="V3"))
    assert amb.controlli_coda == [] and meta["fine_osservazione"]["motivo"] == "durata senza guasti"


def test_quando_fermarsi_con_la_coda():
    p = piano(guasto="F4", versione="V3")
    t0, t_r = 1000.0, 1120.0
    dopo = t_r + 120
    assert run.quando_fermarsi(p, dopo, t0, t_r, in_attesa=0) == "ripristino più osservazione"
    assert run.quando_fermarsi(p, dopo, t0, t_r, in_attesa=5) is None
    assert run.quando_fermarsi(p, dopo, t0, t_r, in_attesa=None) is None  # «non so» non vuol dire che nessuno aspetta
    assert run.quando_fermarsi(p, t0 + 600, t0, t_r, in_attesa=5) == "tetto raggiunto"
    assert run.quando_fermarsi(p, dopo - 1, t0, t_r, in_attesa=0) is None  # i due minuti restano


def test_se_lo_script_del_guasto_esce_male_il_run_non_e_completato(tmp_path):
    amb = Finto(codice_guasto=1)
    codice, _, meta = esegui(tmp_path, amb)
    assert codice == 3
    assert meta["stato"] == "guasto fallito" and "codice 1" in meta["motivo"] and "guasto.txt" in meta["motivo"]
    assert meta["guasto_codice_uscita"] == 1
    assert meta["fine_osservazione"]["motivo"] == "guasto fallito"
    assert amb.fermato_alle - amb.carico.primo < 120  # non si aspetta il tetto di 10 minuti
    assert amb.chiamate[-1] == "analisi"  # i dati si esportano lo stesso, per capire cosa è successo


def test_il_codice_di_uscita_conta_anche_se_guasto_json_c_e(tmp_path):
    amb = Finto(codice_guasto=1, json_subito=True)
    codice, _, meta = esegui(tmp_path, amb)
    assert codice == 3 and meta["stato"] == "guasto fallito" and "codice 1" in meta["motivo"]


def test_uno_script_che_esce_bene_ma_senza_guasto_json_e_un_guasto_fallito(tmp_path):
    amb = Finto(guasto_senza_json=True)
    codice, _, meta = esegui(tmp_path, amb)
    assert codice == 3 and meta["stato"] == "guasto fallito" and "guasto.json non c'è" in meta["motivo"]
    assert meta["guasto_codice_uscita"] == 0


def test_un_guasto_riuscito_salva_il_codice_di_uscita(tmp_path):
    _, _, meta = esegui(tmp_path, Finto())
    assert meta["guasto_codice_uscita"] == 0 and meta["stato"] == "completato"


def test_un_processo_reale_che_esce_male_da_il_suo_codice(tmp_path):
    # è quello che `run.py` guarda per sapere se lo script del guasto è riuscito
    import sys
    processo = run.ProcessoReale([sys.executable, "-c", "import sys; print('non trovo il PID'); sys.exit(3)"], tmp_path / "guasto.txt")
    assert processo.attendi(10) == 3 and not processo.vivo()
    assert "non trovo il PID" in (tmp_path / "guasto.txt").read_text()


def test_gli_ordini_in_attesa_sono_i_pronti_non_quelli_in_lavorazione():
    # con il carico acceso ci sono sempre ordini in lavorazione: la coda «vuota» del tutto non arriva (visto in un run vero)
    class Broker(run.AmbienteReale):
        def kubectl(self, parametri):
            return "Timeout: 60.0 seconds ...\nname\tmessages_ready\tmessages_unacknowledged\nordini\t0\t3\nordini.falliti\t7\t0\n"

    assert Broker().ordini_in_attesa() == 0

    class SenzaCoda(run.AmbienteReale):
        def kubectl(self, parametri):
            return "name\tmessages_ready\tmessages_unacknowledged\n"

    assert SenzaCoda().ordini_in_attesa() is None  # la coda non c'è nell'elenco: non si sa


def test_un_kubectl_che_fallisce_vuol_dire_non_so():
    class Rotto(run.AmbienteReale):
        def kubectl(self, parametri):
            raise run.subprocess.CalledProcessError(1, "kubectl")

    assert Rotto().ordini_in_attesa() is None
