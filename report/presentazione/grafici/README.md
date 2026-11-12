# Grafici per la presentazione

Schemi da riusare nelle slide dell'orale (fase F8). Si modificano con draw.io (app desktop o diagrams.net) aprendo `kintsugi.drawio`; le immagini PNG accanto sono le esportazioni delle sue pagine.

| Pagina di `kintsugi.drawio` | Immagine | Che cosa mostra |
|---|---|---|
| Visione d'insieme | `visione-d-insieme.png` | Il cluster kind sul Mac: i tre nodi, i pod al loro posto (D0006), il percorso di un ordine e dove colpisce ogni guasto F1-F7 |
| Kubernetes | `kubernetes.png` | Come funziona lo strumento: control plane (API server, etcd, scheduler, controller manager) e nodo worker (kubelet, containerd, kube-proxy) |
| Codice | `codice.png` | I moduli dell'app a strati, con le funzioni e le classi principali e chi usa chi |

Gli stessi schemi di Kubernetes e dei moduli sono anche nei PDF, in TikZ: `docs/figure/kubernetes.tex` e la figura dei moduli in `docs/sintesi/06-codice.tex`. Se uno schema cambia qui, va cambiato anche lì (e viceversa).

Dopo una modifica, le immagini si riesportano da questa cartella:

```bash
D=/Applications/draw.io.app/Contents/MacOS/draw.io
"$D" -x -f png -s 2 -p 0 -o visione-d-insieme.png kintsugi.drawio
"$D" -x -f png -s 2 -p 1 -o kubernetes.png kintsugi.drawio
"$D" -x -f png -s 2 -p 2 -o codice.png kintsugi.drawio
```
