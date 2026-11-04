# 2026-11-04 — Controlli automatici sulle pull request

**Chi:** Francesco · **Fase:** F1 (documenti) · **Durata:** ? h · **Issue:** #41 (parte 2, controlli sui documenti)

## Cosa abbiamo fatto

Aggiunto `.github/workflows/controlli.yml`, un flusso di GitHub Actions che parte a ogni pull request e a ogni fusione su `main`, con tre controlli:

| Controllo | Cosa verifica | Come |
|---|---|---|
| La PR punta a `main` | la base della PR è `main` | script di una riga nel flusso |
| Numeri coerenti | i numeri marcati nei Markdown coincidono con `config/parametri.yaml` | `python docs/scripts/parametri.py controlla` (lo stesso di `make controlla`) |
| I PDF compilano | il documento di architettura e la relazione di sintesi si compilano senza errori | `parametri.py genera` e poi `latexmk` tramite `xu-cheng/latex-action` |

I due PDF restano scaricabili dalla pagina del controllo (artefatto `pdf`), così chi rivede una PR può leggerli senza compilare. Aggiunti il badge nel README e un paragrafo in `docs/README.md`.

## Perché

Il totale dei run è passato da 245 a 250 a 220 in due giorni ed era scritto in 7 file: basta dimenticarne uno perché il documento si contraddica. La #41 chiedeva che una PR che lascia un numero diverso o rompe la compilazione diventi rossa prima di essere unita. Il controllo sulla base copre il caso della #24 (PR impilata fusa senza revisione).

## Comandi e configurazione

Nessun comando locale: il flusso gira su GitHub. In locale restano `make` e `make controlla` in `docs/`.

## Risultato

Da verificare sulla pagina della PR: il flusso deve risultare verde sui tre controlli.

## Problemi e soluzioni

- **Non provato in locale:** su questo computer manca PyYAML e non ho `make`, quindi il flusso è stato scritto senza un'esecuzione di prova; la verifica è la prima esecuzione su GitHub.
- **Controllo rosso non ancora provato:** non è stata aperta una PR sbagliata apposta per vedere il rosso.

## Limiti dello strumento emersi

- **Il controllo sulla base non può bloccare il pulsante «Merge»:** le regole di `main` valgono solo per le PR che puntano a `main`. Una PR verso un altro branch vede il controllo rosso, ma GitHub la lascia fondere. Serve la regola umana: non si fonde con un controllo rosso.
- **Controlli non ancora obbligatori:** per renderli obbligatori su `main` vanno aggiunti ai «controlli richiesti» della regola `require-peer-review`, e solo dopo che hanno girato almeno una volta (altrimenti GitHub non li mostra). È una modifica alle impostazioni, da fare dopo la fusione.
- **Parte sul codice della #41 non fatta:** test e controlli sui manifest arrivano con la fase F2; la #41 resta aperta.
