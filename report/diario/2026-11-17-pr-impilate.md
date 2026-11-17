# 2026-11-17 — Regola per le PR impilate

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 0,5 h · **Issue:** nessuna (regola di lavoro decisa da Gianmarco)

## Cosa abbiamo fatto

- `CONTRIBUTING.md`: il punto 4 non vieta più ogni base diversa da `main`; nuova sezione «PR impilate (stack)» con la regola generale: PR 1, …, n, con la i-esima che ha bisogno della (i−1)-esima; stesso proprietario per tutte; la 1 punta a `main` e ogni altra al branch della precedente; si fondono in ordine crescente nella PR 1 e solo la 1 va in `main`.
- `.github/workflows/controlli.yml`: la verifica «La PR punta a main» accetta una base diversa solo se è il branch di un'altra PR aperta dello stesso autore.
- `.github/pull_request_template.md`: la voce della checklist cita le PR impilate.

## Perché

Con il divieto, una PR che dipendeva da un'altra doveva aspettare la fusione, e il lavoro successivo restava fermo. Impilate, si scrivono e si rivedono tutte subito. La regola del proprietario unico evita lo stack «1 a me, 2 a te, 3 a me»: chi ha lo stack decide l'ordine e risolve i conflitti. Senza cambiare anche la verifica, ogni PR impilata avrebbe la spunta rossa.

## Comandi e configurazione

```bash
gh api "repos/kintsugi-spme/kintsugi/pulls?state=open&head=kintsugi-spme:feat/k8s-overlay-v3" --jq '.[0].user.login // empty'
```

## Risultato

- Il comando che usa la verifica restituisce l'autore della PR aperta che ha quel branch come testa, e niente se non ce n'è.
- Il file `controlli.yml` resta YAML valido. La verifica vera si vede solo su una PR: una PR con base diversa da `main` che parte da un branch con questo file.

## Problemi e soluzioni

- Per una PR che non punta a `main`, GitHub esegue il file dei controlli del suo branch di base, non quello di `main`: finché i branch di uno stack non contengono questa modifica, la vecchia verifica resta rossa sulle PR impilate. Passa dopo che lo stack è stato aggiornato con `main`.

## Limiti dello strumento emersi

- GitHub Actions: il file dei controlli di una PR è quello che risulta dalla fusione con il suo branch di base. Cambiare una regola dei controlli su `main` non cambia le PR già aperte verso altri branch.
