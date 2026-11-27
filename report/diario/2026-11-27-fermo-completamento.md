# 2026-11-27 — Fermo e ripristino del completamento

**Chi:** Gianmarco · **Fase:** F4 · **Durata:** 2 h · **Issue:** #124 · **PR:** #146

## Cosa e perché

`analysis/fermo.py` calcolava solo il fermo dell'accettazione. In V3 e V5, con il database fermo, l'API accetta ma non si salva nulla: l'accettazione non vede il guasto e la misura che conta è quando gli ordini tornano a salvarsi. Ora lo script, se trova `db.csv`, stampa anche il fermo del completamento e una riga `servizio` con il più tardivo dei due. Tre scelte non ovvie:

- **L'istante del guasto cambia con l'orologio.** L'accettazione parte da `ts_guasto` (orologio del computer, come `client.csv`); il completamento da `ts_nodo` (orologio del cluster, come `db.csv`). Sottrarli tra loro falserebbe il fermo dello sfasamento, che il 12/11 era di 12-148 ms (D0005).
- **Un ordine accettato e mai salvato non ha `ts_ricezione`.** Si usa l'istante di invio del client più lo sfasamento `ts_nodo - ts_guasto` e conta come non completato. Gli ordini rifiutati (non `2xx`) e mai salvati non sono stati ricevuti e non contano.
- **Il fermo del completamento non coincide con la durata del fermo del database.** Con il database fermo 30 s e il limite di 2 s, il completamento riparte quando arrivano ordini che si salvano entro 2 s: 28,1 s, non 30 (dati costruiti nei test).

## Risultato

Run vero, lanciato con il `run.py` della #122: V3, guasto F4 (SIGKILL al container `postgres`), W1 a **20 ordini/s**, kind sul Mac da 16 GB. Prova di funzionamento, non misura ufficiale (D0013).

| | Previsione (capitolo «Previsioni», F4 su V3) | Run vero |
|---|---|---|
| Fermo dell'accettazione | 0 | **0 s**, nessuna richiesta fallita |
| Fermo del completamento | da 10 a 36 s | **1,715 s** con il limite di 2 s; 34 ordini non completati entro 2 s |
| Ordini nella coda dei falliti | 0 | 0; tutti i 4806 ordini accettati sono nel database (`categorie.py`: «completato in tempo») |

Con `--sensibilita` lo stesso run dà un fermo del completamento di **3,312 s** con il limite di 1 s (66 ordini non completati) e di **0 s** con 5 s.

**Il confronto giusto con la previsione** (correzione di Francesco nella revisione). L'intervallo da 10 a 36 s non viene dall'esempio 3 del capitolo (database fermo 30 s, 100 ordini/s) ma dalla riga «Guasto F4 su V3»: (D₀ + R) · μ/(μ − λ) ≈ 2 · (5-18 s), cioè D₀ + R tra 5 e 18 s e un fattore μ/(μ − λ) = 2 (carico al 50 % della capacità). Nel run vero i numeri sono altri:

- **D₀ + R è circa 3 s**, sotto i 5-18 s ipotizzati: il container è ripartito dopo 0,26 s e tra due scritture nel database c'è stato un buco di 3,07 s (ritardo massimo di un ordine 3,12 s).
- **Il fattore è circa 1,5**: 3 worker da circa 20 ordini/s danno μ ≈ 60 ordini/s e λ è 20, quindi 60/(60 − 20) = 1,5.
- **Con questi valori la formula dà 3,07 · 1,5 ≈ 4,6 s.** Il fermo misurato dipende dal limite di completamento (stesso run, `--limite`):

| Limite | 0,1 s | 0,5 s | 1 s | 2 s | 5 s |
|---|---|---|---|---|---|
| Fermo del completamento | 4,72 s | 4,07 s | 3,31 s | 1,72 s | 0 s |

Con un limite quasi nullo il fermo misurato è vicino alla formula (4,7 s contro 4,6 s); con i 2 s di D0008 è più corto, perché un ordine che aspetta meno di 2 s conta come completato. È uno **scarto di definizione**, non di modello: la formula della previsione non toglie il limite. Va scritto nel report. La previsione non si cambia: il confronto vero si fa a fine campagna, con il ritmo di F4 e il fermo del database che l'infrastruttura darà.

## Problemi e limiti

- Il limite di 2 s misura il tempo in coda, non se l'ordine è andato a buon fine: i 34 ordini oltre il limite sono nel database e `categorie.py` li conta «completato in tempo», perché quella categoria guarda solo se l'API ha risposto `2xx` e l'ordine è stato salvato. Il fermo del completamento cambia con il limite: `--sensibilita` lo ricalcola con 1 s e 5 s.
