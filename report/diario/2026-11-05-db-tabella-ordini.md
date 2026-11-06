# 2026-11-05 — Database: tabella degli ordini

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 0,5 h · **Issue:** #28

## Cosa abbiamo fatto

Aggiunto `deploy/k8s/base/schema.sql`, lo script che crea la tabella `ordini` in un database vuoto:

| Colonna | Tipo | Cosa contiene |
|---|---|---|
| `id` | `uuid`, chiave primaria | identificativo scelto dal client (D0004) |
| `ts_ricezione` | `timestamptz`, obbligatorio | istante in cui l'API riceve la richiesta (D0005) |
| `ts_scrittura` | `timestamptz`, obbligatorio, predefinito `clock_timestamp()` | istante dell'inserimento nel database (D0005) |

Lo script è pensato per essere eseguito una sola volta, all'avvio del database: con `docker-compose` (#35) si monta in `/docker-entrypoint-initdb.d/`; su Kubernetes (fase F3) Kustomize ne fa un ConfigMap, per il PostgreSQL di V1–V3 e per CloudNativePG di V4.

## Perché

**`clock_timestamp()` e non `now()`.** `now()` è l'istante di inizio della transazione e accorcerebbe il tempo end-to-end (D0005). Con `clock_timestamp()` come valore predefinito, chi inserisce non deve ricordarsi di passare l'istante.

**La chiave primaria sta qui, non nella #29.** D0004 vuole l'identificativo come chiave primaria. Una tabella nata senza chiave e corretta dopo costringerebbe la #29 a modificare il `CREATE TABLE` di questa PR. Alla #29 restano la tabella dei doppi e l'inserimento «se esiste non fare nulla» (`ON CONFLICT DO NOTHING`).

**Il file sta in `deploy/k8s/base/`, non in `app/`.** Era in `app/`; Francesco, nella revisione della PR, ha provato che Kustomize rifiuta i file fuori dalla propria cartella (`file ... is not in or below deploy/k8s/base`). Lasciarlo in `app/` avrebbe obbligato a tenere due copie dello schema, e lo avrebbe fatto entrare nell'immagine dell'app, che non lo usa. Da `deploy/k8s/base/` lo leggono Kustomize e `docker-compose` (#35), quindi il file è uno solo.

**Solo tre colonne.** I documenti definiscono dell'ordine soltanto l'identificativo e i due istanti. Altri campi, se servono, si decidono con le API (#30, #32).

**Nessuna verifica `ts_scrittura >= ts_ricezione` nella tabella.** Se un orologio fosse sfasato l'inserimento fallirebbe, e perderemmo proprio l'ordine che serve a misurare lo sfasamento.

## Comandi e configurazione

```bash
docker run -d --rm --name kintsugi-pg-prova -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=kintsugi -v "$PWD/deploy/k8s/base/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro" postgres:17-alpine
docker exec -i kintsugi-pg-prova psql -U postgres -d kintsugi
docker stop kintsugi-pg-prova
```

## Risultato

Provato su PostgreSQL 17.11 e 18.6, con gli stessi risultati (i numeri qui sotto sono della 17.11; sulla 18.6: 0,2547 s e −0,0014 s):

- la tabella viene creata all'avvio con le tre colonne e la chiave primaria;
- **criterio della #28:** con 0,25 s tra la ricezione e l'inserimento, `ts_scrittura - ts_ricezione` vale 0,2527 s, positivo e uguale al tempo reale;
- con `now()` la stessa differenza sarebbe −0,0012 s: è il motivo della scelta;
- lo stesso identificativo due volte è rifiutato (`duplicate key value violates unique constraint`);
- senza `ts_ricezione` l'inserimento è rifiutato.

## Problemi e soluzioni

- **Versione di PostgreSQL non fissata nei documenti.** Ho provato con la 17 (`postgres:17-alpine`, 17.11) e con la 18 (`postgres:18-alpine`, 18.6). Controllato il 05/11/2026: PostgreSQL supporta le versioni dalla 14 alla 18 (la 14 finisce il 12/11/2026; la 19 è ancora candidata al rilascio); CloudNativePG 1.30.1 supporta PostgreSQL dalla 14 alla 18 e usa la 18.6 come immagine predefinita. La versione va scelta una volta per tutti gli ambienti con la #35 (`docker-compose`) e per V4.
- **CloudNativePG e Kubernetes 1.37:** la 1.30.x dichiara supportati Kubernetes 1.34–1.36 e 1.37 solo «testato, ma non supportato». I nodi di kind usano la 1.37.0, quindi la compatibilità va verificata all'installazione di V4 (fase F3), come già previsto per KEDA (D0015).
- **Container di prova usa e getta:** fermato e rimosso a fine prova (`--rm`); resta solo l'immagine scaricata.

## Limiti dello strumento emersi

- **La prova è manuale:** non c'è un test automatico sullo schema. Il primo test automatico con un database vero arriva con `docker-compose` (#35) e la verifica di M2 (#38).
- **Gli istanti dell'API non sono ancora verificati:** qui ho simulato `ts_ricezione` dentro il database. Che arrivi davvero dall'API, con lo stesso orologio del database, si controlla con #30 e #32.
