# 2026-11-04 — Revisione delle PR #47 e #48, controllo finale e tag m1

**Chi:** Gianmarco · **Fase:** F1 · **Durata:** 4 h · **Issue:** #11 (previsioni e tag `m1`); PR #47 e #48 (revisione)

## Cosa abbiamo fatto

**PR #47 (repository pronto per i contributi esterni: regole di contributo, CODEOWNERS, codice di condotta).** Ho controllato che quanto scritto corrispondesse alle impostazioni di GitHub: regole di `main` (un'approvazione, nuova approvazione dopo un push, conversazioni risolte, niente force-push né cancellazione), Discussions attive, etichette, moduli delle issue «Problema» e «Attività», file citati e permessi dei due proprietari del CODEOWNERS. Ho lasciato una review con 5 commenti sulle righe:

| Punto | Esito |
|---|---|
| Codice di condotta | Nessuno dei due autori ha un'email pubblica sul profilo GitHub, quindi le segnalazioni non avevano un destinatario: aggiunti nel file i contatti di entrambi |
| Aiuto esterno | Ho controllato il regolamento universitario: è ammesso solo dopo la presentazione del progetto. `CONTRIBUTING.md` e README ora lo dicono; le etichette `good first issue` e `help wanted` sono state tolte dalle cinque issue di M2 (#26, #27, #28, #29, #36) e si rimettono dopo la presentazione |
| Prefisso dei branch | `ci/` mancava dall'elenco di `CONTRIBUTING.md` e del README, ma la PR #48 usa `ci/controlli-documenti`: aggiunto |
| CODEOWNERS | Il commento diceva che `config/parametri.yaml` non cambia dopo `m1`: non è vero, i suoi valori possono cambiare dopo F4 (banco di prova) e allora cambiano gli altri capitoli, non le previsioni. Congelato è solo il capitolo delle previsioni, che non usa quel file: tolta la riga |
| Diario | «Durata: ? h» compilata |

**PR #48 (controlli automatici sulle PR).** I tre controlli erano verdi sulla PR: la PR punta a `main`, i numeri coincidono con `config/parametri.yaml`, i due PDF compilano. Ho provato in locale il caso rosso, che Francesco non aveva provato: cambiando in `README.md` un numero marcato da 220 a 221, `parametri.py controlla` scrive «trovato 221, atteso 220» ed esce con errore. Ho lasciato una review con 1 commento (la durata nel diario) e ho proposto di far passare i comandi dal Makefile (`make -C docs controlla` e `make -C docs parametri`), così i controlli automatici e `make` in locale fanno la stessa cosa.

**Controllo finale e tag `m1`.** Con le due PR unite (`main` a `59955f1`) ho compilato i due PDF (51 e 19 pagine, senza errori né riferimenti non definiti) e lanciato `make controlla` (9 numeri corretti). Ho confrontato il testo dei PDF, parola per parola, con quello di `6fb447d` (prima delle PR #42–#45, #47 e #48): cambia solo ciò che era voluto, cioè l'indirizzo del repository, la regola «guasto F4 / fase F4», il titolo «Parametri», le voci tolte dal glossario, i nomi `worker1` e `worker2`, la frase su AWS e le frasi sulle sonde. Il capitolo delle previsioni è identico. Cercati e non trovati: il vecchio indirizzo, `worker-1`, `worker-2`, `kintsugi-worker` fuori dai due punti ammessi, AZ, HPA, IQR, «Parametri proposti», segnaposto. Le 17 schede di decisione sono accettate. Francesco ha messo il tag annotato `m1` su `59955f1` alle 12:11; l'issue #11 e la milestone M1 sono chiuse.

## Perché

- **Controllo dopo l'unione, prima di fidarsi del tag:** dopo `m1` le previsioni non si correggono; le due PR non toccano i `.tex`, ma entrano nel commit del tag.
- **Confronto del testo dei PDF:** mostra le differenze oggettive, invece di affidarsi alla lettura.
- **Prova del caso rosso:** un controllo che non è mai stato visto fallire non dimostra di funzionare.
- **Aiuto esterno dopo la presentazione:** è la condizione posta dal regolamento; con le etichette le issue sarebbero state trovabili da chi cerca un primo contributo.

## Comandi e configurazione

```bash
git archive origin/main | tar -x -C copia-pulita   # copia di main, senza toccare la cartella di lavoro
cd copia-pulita/docs
make parametri && make controlla                   # genera le macro e controlla i 9 numeri
make                                               # compila i due PDF
pdftotext -layout main.pdf main.txt                # testo dei PDF, da confrontare con quello di 6fb447d
gh api repos/kintsugi-spme/kintsugi/rulesets       # regole attive
git ls-remote --tags origin                        # il tag m1 su origin
```

## Risultato

- PR #47 e #48 unite in `main` (`59955f1`); controlli automatici verdi su `main`.
- Tag `m1` su `59955f1`; issue #11 e milestone M1 chiuse (20 issue chiuse).
- Documento tecnico di 51 pagine e relazione di sintesi di 19.

## Problemi e soluzioni

- **Prima prova del caso rosso senza effetto:** `sed` di macOS non accetta l'indirizzo `0,/re/`, il numero non è stato cambiato e il controllo è rimasto verde. Rifatta con Python: il controllo diventa rosso.
- **Errore 502 di GitHub nell'invio delle review:** quella sulla #48 era stata pubblicata comunque. Ho controllato l'elenco delle review prima di riprovare, per non duplicarla.

## Limiti dello strumento emersi

- **Il tag `m1` non è protetto:** le regole attive riguardano solo il branch `main`. `CONTRIBUTING.md` dice che il tag non si sposta e non si cancella, ma nulla lo impedisce: va creata una regola per i tag.
- **I controlli automatici non sono ancora obbligatori per il merge:** vanno aggiunti ai controlli richiesti della regola di `main`.
- **Il controllo dei PDF verifica che compilino, non che siano privi di avvisi:** nel documento tecnico restano 4 avvisi di impaginazione e 6 righe che sporgono, già presenti prima. Il controllo dei numeri vede solo quelli marcati nei file Markdown.
- **Il CODEOWNERS chiede la revisione ma non la rende obbligatoria** (`require_code_owner_review` è falso).
