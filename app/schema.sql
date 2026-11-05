-- Schema del database di Kintsugi (PostgreSQL).
--
-- Si esegue una sola volta, all'avvio di un database vuoto: docker-compose monta questo file
-- in /docker-entrypoint-initdb.d/ (issue #35); su Kubernetes lo si porta nel database allo
-- stesso modo (fase F3).
--
-- Gli istanti seguono D0005: entrambi vengono dal cluster, mai dal client.
--   ts_ricezione  lo prende l'API quando arriva la richiesta
--   ts_scrittura  lo prende il database quando inserisce la riga

CREATE TABLE ordini (
    -- Identificativo scelto dal client (UUID). La chiave primaria lo fa accettare una volta
    -- sola (D0004); la tabella dei doppi e l'inserimento «se esiste non fare nulla» sono
    -- nella issue #29.
    id            uuid        PRIMARY KEY,

    ts_ricezione  timestamptz NOT NULL,

    -- clock_timestamp() e non now(): now() è l'inizio della transazione e accorcerebbe i tempi.
    ts_scrittura  timestamptz NOT NULL DEFAULT clock_timestamp()
);
