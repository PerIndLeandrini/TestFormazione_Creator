"""Importa tutti i CSV della cartella banche_dati_quiz nel database SQLite."""

from __future__ import annotations

import argparse
from pathlib import Path

from quiz_db import import_directory


BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cartella",
        type=Path,
        default=BASE_DIR / "banche_dati_quiz",
        help="Cartella contenente i CSV (default: banche_dati_quiz)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=BASE_DIR / "quiz_database.db",
        help="File SQLite di destinazione (default: quiz_database.db)",
    )
    args = parser.parse_args()

    results = import_directory(args.database, args.cartella)
    if not results:
        raise SystemExit(f"Nessun CSV trovato in {args.cartella}")

    total = 0
    for bank, topics, questions in results:
        total += questions
        print(f"OK {bank}: {questions} domande, {topics} argomenti")
    print(f"Database aggiornato: {args.database}")
    print(f"Totale: {len(results)} banche, {total} domande")


if __name__ == "__main__":
    main()
