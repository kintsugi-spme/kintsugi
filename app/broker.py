"""Collegamento a RabbitMQ per l'API della versione con la coda (D0002).

Regole di D0002 realizzate qui:
  - coda durevole e messaggi persistenti: sopravvivono al riavvio di RabbitMQ;
  - conferma di pubblicazione (publisher confirm): `pubblica` torna solo quando RabbitMQ ha
    confermato di aver preso in carico il messaggio, e solleva un errore se non lo conferma.

La connessione si apre alla prima pubblicazione, non all'avvio: con il broker spento l'API deve
partire lo stesso e le sonde rispondere (D0007). Una volta aperta, la connessione si ripristina
da sola se il broker si ferma e riparte.

Le code si dichiarano solo con `dichiara_code`, che usano sia l'API sia il worker: RabbitMQ rifiuta
una seconda dichiarazione con argomenti diversi, quindi gli argomenti stanno in un posto solo.
"""

import asyncio

import aio_pika

NOME_CODA = "ordini"


async def dichiara_code(canale: aio_pika.abc.AbstractChannel, nome_coda: str = NOME_CODA) -> aio_pika.abc.AbstractQueue:
    """Dichiara la coda degli ordini e la sua coda dei falliti, entrambe durevoli (D0002).

    Un messaggio rifiutato senza rimetterlo in coda (`reject(requeue=False)`) passa da solo nella
    coda dei falliti: è RabbitMQ a spostarlo, in un passo solo, quindi un worker che si spegne a
    metà non lo lascia in tutte e due le code (D0003).
    """
    falliti = f"{nome_coda}.falliti"
    await canale.declare_queue(falliti, durable=True)
    return await canale.declare_queue(
        nome_coda,
        durable=True,
        arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": falliti},
    )


class BrokerNonDisponibile(Exception):
    """Il broker non è configurato o non si riesce a raggiungerlo."""


class Broker:
    def __init__(self, url: str | None, nome_coda: str = NOME_CODA):
        self._url = url
        self._nome_coda = nome_coda
        self._connessione: aio_pika.abc.AbstractRobustConnection | None = None
        self._canale: aio_pika.abc.AbstractChannel | None = None
        self._blocco = asyncio.Lock()

    async def _canale_pronto(self) -> aio_pika.abc.AbstractChannel:
        if self._url is None:
            raise BrokerNonDisponibile("BROKER_URL non impostato")
        async with self._blocco:
            if self._canale is None or self._canale.is_closed:
                try:
                    self._connessione = await aio_pika.connect_robust(self._url)
                    # Le conferme di pubblicazione sono attive per impostazione predefinita.
                    canale = await self._connessione.channel()
                    await dichiara_code(canale, self._nome_coda)
                except BaseException:
                    await self.chiudi()
                    raise
                self._canale = canale
            return self._canale

    async def pubblica(self, corpo: bytes) -> None:
        """Mette un messaggio persistente in coda e aspetta la conferma del broker."""
        canale = await self._canale_pronto()
        messaggio = aio_pika.Message(
            body=corpo,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await canale.default_exchange.publish(messaggio, routing_key=self._nome_coda)

    async def chiudi(self) -> None:
        connessione, self._connessione, self._canale = self._connessione, None, None
        if connessione is not None:
            await connessione.close()
