# Database delle domande

Le banche dei quiz sono memorizzate nel file SQLite `quiz_database.db`.
Il programma legge direttamente questo file; i CSV nella cartella
`banche_dati_quiz` restano disponibili come sorgenti di importazione e backup.

## Aggiornare il database dai CSV

Da terminale, nella cartella del progetto:

```bash
python importa_quiz_csv.py
```

Lo script valida ogni CSV prima di importarlo. Se una banca con lo stesso nome
esiste già, viene sostituita in una singola transazione; le altre banche non
vengono modificate.

Il nome della banca deriva dal nome del file senza `.csv`. La colonna
`argomento` può contenere uno o più valori: nell'app sarà possibile usare tutte
le domande della banca oppure filtrare un singolo argomento.

## Struttura

- `banche_dati`: elenco delle banche disponibili;
- `argomenti`: argomenti appartenenti a ciascuna banca;
- `domande`: quesiti, quattro opzioni, soluzione e riferimento.

I codici delle domande devono essere univoci all'interno della stessa banca.
