-- Schema del database di Kintsugi (PostgreSQL).
--
-- Si esegue una sola volta, all'avvio di un database vuoto: docker-compose monta questo file
-- in /docker-entrypoint-initdb.d/ (issue #35); su Kubernetes (fase F3) Kustomize ne fa un
-- ConfigMap per il PostgreSQL di V1-V3 e per CloudNativePG di V4. Per questo il file sta qui:
-- Kustomize non legge file fuori da deploy/k8s/base, e così lo schema resta uno solo.
--
-- Gli istanti seguono D0005: entrambi vengono dal cluster, mai dal client.
--   ts_ricezione  lo prende l'API quando arriva la richiesta
--   ts_scrittura  lo prende il database quando inserisce la riga

CREATE TABLE ordini (
    -- Identificativo scelto dal client (UUID). La chiave primaria lo fa accettare una volta
    -- sola (D0004). Un secondo arrivo dello stesso identificativo non inserisce nulla e si
    -- registra in `duplicati` (qui sotto): lo fa `salva_ordine` in app/db.py.
    id            uuid        PRIMARY KEY,

    ts_ricezione  timestamptz NOT NULL,

    -- clock_timestamp() e non now(): now() è l'inizio della transazione e accorcerebbe i tempi.
    ts_scrittura  timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Ogni arrivo di un identificativo già presente (D0004): così i doppi si contano e non solo
-- si scartano.
-- Non c'è una chiave esterna verso `ordini`: un doppio va registrato anche se, dopo un
-- failover con replica asincrona (V4a), l'ordine originale non fosse più presente.
CREATE TABLE duplicati (
    n            bigserial   PRIMARY KEY,
    id           uuid        NOT NULL,
    ts_arrivo    timestamptz NOT NULL DEFAULT clock_timestamp(),
    ricevuto_da  text        NOT NULL   -- nome del pod (o del processo) che ha ricevuto il doppio
);
