# Sistemazione del sito dopo l'export

Dopo ogni export da Obsidian (Webpage HTML Export) va lanciato:

    python3 tools/postprocess.py "<cartella del sito>" "<cartella del vault>"

Lo script:
- comprime le immagini PNG pesanti in `allegati/`
- rimette i grafici del plugin Graphs (interattivi, con il codice del plugin in `extra/graphs-plugin.js`)
- ricostruisce le colonne di Advanced Multi Column
- aggiunge a ogni pagina `extra/site.css` (scorrimento, colonne, grafici) e `extra/site.js`

Si può rilanciare quante volte si vuole: quello che è già sistemato non cambia.
