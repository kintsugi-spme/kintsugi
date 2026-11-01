# 2026-11-01 — Revisione della PR #21

**Chi:** Francesco · **Fase:** F1 · **Durata:** 2 h · **Issue:** #11, #20

## Cosa abbiamo fatto

Gianmarco ha chiesto modifiche alla PR #21 con 12 commenti. Li abbiamo discussi uno per uno e corretti nel documento.

| Punto | Esito |
|---|---|
| Fermo del blocco (guasto F7) | 4 s con le sonde veloci e 31 s con le standard: conta la readiness, che esclude la copia dal Service. La liveness riavvia la copia e non entra nel fermo |
| Figura del fermo | Vale per una sola copia: didascalia corretta, tolta la sigla F7 dalle etichette |
| Previsioni del guasto F2 | Interruzione 3–9 s (era 3–5 s), completamento 6–18 s (era 6–10 s) |
| Previsioni del guasto F3 | Fermo 7–21 s (era 7–20 s), falliti 700–2100 (erano 700–2000) |
| Tempo di servizio S | Aggiunto alla tabella delle ipotesi |
| Persi in V4a | ≤ 0,1·λ, invece di ≤ 10 valido solo per λ = 100 |
| Timeout di scrittura del worker | 1,5 s scritto in D0003; la deadline dell'API resta in D0008 |
| H4 | Riscritta: con l'arresto del solo processo la replica non accorcia necessariamente il fermo; il vantaggio atteso è nella perdita del nodo, che non si misura |
| Failover di V4 | Scritto come ipotesi, con un'eccezione in D0016 se non parte |
| Ripristino | Un $t_r$ per l'accettazione e uno per il completamento |
| Sigle | «fase Fn» e «guasto Fn», perché fasi e guasti usano le stesse sigle |

I punti 1–3 dell'issue #20 sono chiusi. Restano aperti i punti 4–6.

## Perché

- **Readiness in `05-guasti.tex`:** non basta sostituire la parola, perché il kubelet riavvia con la liveness. Il testo ora descrive entrambe le sonde.
- **H4:** l'ipotesi precedente contraddiceva la previsione di RQ4. Parlare della perdita del nodo come vantaggio atteso, e non come risultato, evita un'affermazione che l'esperimento non verifica: D0006 esclude V4 dal guasto F6 e dichiara come limite la perdita del nodo del database.
- **Due ripristini:** con un solo $t_r$ il fermo di accettazione di V3 nel guasto F4 sarebbe uguale a quello di completamento, mentre la previsione è 0.
- **«Dal guasto in poi»:** se una misura non si interrompe mai, $t_r = t_g$ e il fermo è esattamente 0.

## Comandi e configurazione

```bash
cd docs && make
```

## Risultato

- Previsioni, parametri e definizioni ora concordano.
- Da fare per chiudere M1: approvazione di Gianmarco, poi tag `m1`; #10 (valori principali).

## Problemi e soluzioni

- Il piano B per il failover di V4 si scontra con il divieto di `kubectl delete pod` di D0016: è ammesso solo come eccezione per V4, da usare se il failover non parte.
- L'effetto della cancellazione forzata non è stato verificato sulla documentazione di CloudNativePG: va controllato prima della campagna.

## Limiti dello strumento emersi

- CloudNativePG: uccidendo il processo principale del pod, Kubernetes può riavviare il container nello stesso pod prima che l'operatore avvii il failover. È un'ipotesi da verificare nella fase F4.
