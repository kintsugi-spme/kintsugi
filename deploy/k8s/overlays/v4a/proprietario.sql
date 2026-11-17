-- CloudNativePG esegue lo schema come superutente: le tabelle passano all'utente dell'app, come nella base,
-- dove le crea direttamente lui. Cambiando il proprietario della tabella cambia anche quello della sua
-- sequenza (`duplicati.n`).
ALTER TABLE ordini OWNER TO kintsugi;
ALTER TABLE duplicati OWNER TO kintsugi;
