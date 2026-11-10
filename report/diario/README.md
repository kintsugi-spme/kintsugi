# Diario di bordo

Una voce per sessione di lavoro e per ogni commit rilevante, in un file `AAAA-MM-GG-argomento.md` scritto copiando `_template.md`. Per un commit, basta un riassunto schematico breve: cosa è cambiato e perché, poche righe. È la base della "descrizione dettagliata delle operazioni, con limiti e difficoltà degli strumenti" richiesta dal professore: si scrive a ridosso del lavoro, non a memoria dopo.

I **limiti degli strumenti** emersi si raccolgono anche nella tabella qui sotto, che confluisce nel documento di architettura (`docs/`).

## Limiti degli strumenti emersi

| Data | Strumento | Limite | Impatto sulle misure | Voce del diario |
|---|---|---|---|---|
| 27/10/2026 | TikZ (`patterns`) con pdfTeX | Il riempimento tratteggiato produce un PDF che i lettori basati su Poppler non leggono | Nessuno sulle misure; figure del documento da compilare senza `patterns` | [2026-10-27](2026-10-27-revisione-documento.md) |
| 27/10/2026 | Mac ARM (locale) contro istanze `m5` x86 (AWS) | I due ambienti hanno architetture di CPU diverse | Nessuno sulle misure locali; da dichiarare nel confronto locale/AWS (RQ6) | [2026-10-27](2026-10-27-accettazione-decisioni.md) |
| 05/11/2026 | Docker Desktop (archivio di immagini classico) | Non costruisce né conserva in locale un'immagine con più architetture (`Multi-platform build is not supported for the docker driver`) | Nessuno sulle misure: in locale si usa solo arm64; arm64 e amd64 si verificano nella CI | [2026-11-05](2026-11-05-immagine.md) |
| 07/11/2026 | aiormq (client di RabbitMQ usato da aio-pika) | Quando il broker cade scrive nel log una traccia completa dell'errore a livello di avviso | Nessuno sulle misure; log del worker rumorosi durante F3 | [2026-11-07](2026-11-07-worker.md) |
| 07/11/2026 | Immagine `rabbitmq` | Un comando di RabbitMQ eseguito con `docker exec` prima dell'avvio del server crea `.erlang.cookie` con i permessi di root e il server non parte (`eacces`) | Nessuno sulle misure; il controllo di prontezza va fatto sulla porta o sul log (docker-compose, Kubernetes) | [2026-11-07](2026-11-07-worker.md) |
| 07/11/2026 | psycopg 3.3 | Una query annullata con il server che non risponde (database congelato) impiega fino a 10 s a terminare (5 s per annullarla, 5 s di attesa), tempi non configurabili | Nessuno: l'API risponde `503` alla deadline senza aspettare la fine del lavoro annullato | [2026-11-07](2026-11-07-api-sincrona.md) |
| 07/11/2026 | Docker Desktop | L'orologio della macchina virtuale era indietro di 11,6 ms rispetto a macOS | Nessuno se API e database sono nel cluster (stessa macchina virtuale, D0005); da correggere nei test con l'API sul Mac | [2026-11-07](2026-11-07-api-sincrona.md) |
| 07/11/2026 | Docker Desktop | `docker stop` senza `-t` concede meno dei 10 s documentati prima di SIGKILL: circa 1,5 s su un Mac e 3,2 s su un altro; con `-t 10` si torna a 10 s | Nessuno sulle misure; un'API o un worker con richieste in corso può uscire con codice 137. Per `docker-compose` (#35) fissare `stop_grace_period` | [2026-11-07](2026-11-07-review-pr-60-61-62.md) |
| 10/11/2026 | `parametri.py controlla` | Legge anche i Markdown non versionati (per esempio `CLAUDE.md`): un marcatore scritto lì fa fallire il controllo in locale ma non nella CI | Nessuno sulle misure; in locale il controllo può dare un esito diverso dalla CI | [2026-11-10](2026-11-10-documenti-rimasti-indietro.md) |
