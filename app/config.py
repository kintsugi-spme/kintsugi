"""Configurazione dell'applicazione.

Si legge solo dalle variabili d'ambiente (D0012): le cinque versioni usano lo stesso
codice e la stessa immagine, cambiano solo queste variabili e i manifest.

    MODE            sync | async    come si riceve un ordine (D0001). Obbligatoria.
    ROLE            api | worker    che cosa fa questo processo. Predefinito: api.
    SERVICE_TIME_S  secondi         tempo di servizio aggiunto a ogni ordine. Predefinito: 0.
    DEADLINE_S      secondi         dopo quanto l'API risponde 503 (D0008). Nessun predefinito:
                                    il valore sta in config/parametri.yaml (tempi.deadline_api_s)
                                    e lo passano docker-compose e i manifest.
    DATABASE_URL    indirizzo       PostgreSQL.
    BROKER_URL      indirizzo       RabbitMQ.

Con ROLE=worker i due indirizzi sono obbligatori: senza, il worker non avrebbe nulla da fare e lo
farebbe in silenzio. Per l'API restano facoltativi finché non li rendono tali #30 e #31.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

MODI = ("sync", "async")
RUOLI = ("api", "worker")


class ErroreConfigurazione(ValueError):
    """Una variabile d'ambiente manca o ha un valore non valido."""


@dataclass(frozen=True)
class Config:
    mode: str
    role: str
    service_time_s: float
    deadline_s: float | None
    database_url: str | None
    broker_url: str | None

    def riassunto(self) -> str:
        """Una riga per il log di avvio. Gli indirizzi non si stampano: possono contenere la password."""
        return (
            f"mode={self.mode} role={self.role} service_time_s={self.service_time_s} "
            f"deadline_s={self.deadline_s} "
            f"database={'impostato' if self.database_url else 'non impostato'} "
            f"broker={'impostato' if self.broker_url else 'non impostato'}"
        )


def _scelta(env: Mapping[str, str], nome: str, ammessi: tuple[str, ...], predefinito: str | None) -> str:
    valore = env.get(nome, predefinito)
    if valore is None:
        raise ErroreConfigurazione(f"{nome} manca (valori ammessi: {', '.join(ammessi)})")
    if valore not in ammessi:
        raise ErroreConfigurazione(f"{nome}={valore!r} non valido (valori ammessi: {', '.join(ammessi)})")
    return valore


def _secondi(env: Mapping[str, str], nome: str, predefinito: float | None) -> float | None:
    grezzo = env.get(nome)
    if grezzo is None:
        return predefinito
    try:
        valore = float(grezzo)
    except ValueError:
        raise ErroreConfigurazione(f"{nome}={grezzo!r} non è un numero di secondi") from None
    if valore < 0:
        raise ErroreConfigurazione(f"{nome}={grezzo!r} è negativo")
    return valore


def da_ambiente(env: Mapping[str, str] | None = None) -> Config:
    """Legge la configurazione da `env` (predefinito: le variabili d'ambiente del processo)."""
    env = os.environ if env is None else env
    mode = _scelta(env, "MODE", MODI, None)
    role = _scelta(env, "ROLE", RUOLI, "api")
    if mode == "sync" and role == "worker":
        # V1, V2 e V4 non hanno la coda: non c'è nessun worker da avviare.
        raise ErroreConfigurazione("ROLE=worker richiede MODE=async: con MODE=sync non c'è nessuna coda")
    database_url = env.get("DATABASE_URL") or None
    broker_url = env.get("BROKER_URL") or None
    if role == "worker":
        mancanti = [nome for nome, valore in (("DATABASE_URL", database_url), ("BROKER_URL", broker_url)) if not valore]
        if mancanti:
            raise ErroreConfigurazione(f"ROLE=worker richiede {' e '.join(mancanti)}")
    return Config(
        mode=mode,
        role=role,
        service_time_s=_secondi(env, "SERVICE_TIME_S", 0.0),
        deadline_s=_secondi(env, "DEADLINE_S", None),
        database_url=database_url,
        broker_url=broker_url,
    )
