# 2026-11-10 — Documenti rimasti indietro

**Chi:** Francesco · **Fase:** F2 · **Durata:** 0,5 h · **Issue:** #69

## Cosa abbiamo fatto

Tre file descrivevano il repository com'era a fine ottobre. Li abbiamo riportati allo stato reale, senza toccare codice, parametri, decisioni o previsioni.

| File | Cosa non era più vero | Ora |
|---|---|---|
| `README.md` | Badge «F1 Architettura»; sezione 6.3 «In arrivo con M2–M4»; `GET /metrics` elencato come esistente; cartelle vuote descritte come piene | Badge tolto (lo stato si legge dalle milestone, già collegate nella sezione 7); nuova sezione 6.3 con `make v1/v2/v3`, il client e i test; `/metrics` segnato «arriva con M4»; nella struttura, «da F3» e «da F4» sulle cartelle ancora vuote |
| `docs/README.md` | «Un unico PDF»; parti `[DA COMPLETARE]`; «tre controlli» della CI; `main-sintesi.tex` e `sintesi/` assenti dalla struttura | Due PDF; frase tolta (non ce ne sono più); i controlli sui documenti più i test dell'app e l'immagine; struttura completa |
| `config/README.md` | Uso dei parametri in `app/` e `deploy/` «da decidere» | `deploy/compose/Makefile` (deadline) e `harness/client/cliente.py` (timeout) li leggono già: «in uso»; restano «da decidere» i manifest Kubernetes |

## Perché

Chi apre il repository dal README trovava una fase sbagliata e nessun comando per provare l'app, che invece esiste da M2. Il badge di stato è stato tolto e non aggiornato: scritto a mano, sarebbe rimasto indietro di nuovo alla prossima milestone.

## Comandi e configurazione

```bash
python3 docs/scripts/parametri.py controlla
```

## Risultato

`controlla`: 9 numeri controllati, tutti corretti. I comandi della nuova sezione 6.3 sono quelli usati il 10/11 per rifare la verifica dei criteri di M2.

## Problemi e soluzioni

- **`CLAUDE.md` era il file più indietro** (fase F1, cartelle «vuote», 245 run, vecchio indirizzo del repository), ma è in `.gitignore`: ognuno ha la sua copia. Quella di Francesco è aggiornata; non fa parte di questa PR.

## Limiti dello strumento emersi

- **`parametri.py controlla` legge anche i Markdown non versionati** (per esempio `CLAUDE.md`): un marcatore di esempio scritto lì fa fallire il controllo in locale, ma non nella CI, dove il file non c'è. Nessun effetto sulle misure.
