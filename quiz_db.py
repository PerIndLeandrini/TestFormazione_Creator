"""Accesso e importazione delle banche dati quiz in SQLite."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd


SCHEMA_VERSION = "1"
REQUIRED_COLUMNS = {
    "argomento",
    "codice",
    "domanda",
    "opzione_a",
    "opzione_b",
    "opzione_c",
    "opzione_d",
    "corretta",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            chiave TEXT PRIMARY KEY,
            valore TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS banche_dati (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            file_origine TEXT,
            attiva INTEGER NOT NULL DEFAULT 1 CHECK (attiva IN (0, 1)),
            creata_il TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            aggiornata_il TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS argomenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            banca_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            ordine INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (banca_id) REFERENCES banche_dati(id) ON DELETE CASCADE,
            UNIQUE (banca_id, nome)
        );

        CREATE TABLE IF NOT EXISTS domande (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            banca_id INTEGER NOT NULL,
            argomento_id INTEGER NOT NULL,
            codice TEXT NOT NULL,
            domanda TEXT NOT NULL,
            opzione_a TEXT NOT NULL,
            opzione_b TEXT NOT NULL,
            opzione_c TEXT NOT NULL,
            opzione_d TEXT NOT NULL,
            corretta TEXT NOT NULL CHECK (corretta IN ('A', 'B', 'C', 'D')),
            riferimento TEXT NOT NULL DEFAULT '',
            attiva INTEGER NOT NULL DEFAULT 1 CHECK (attiva IN (0, 1)),
            FOREIGN KEY (banca_id) REFERENCES banche_dati(id) ON DELETE CASCADE,
            FOREIGN KEY (argomento_id) REFERENCES argomenti(id) ON DELETE RESTRICT,
            UNIQUE (banca_id, codice)
        );

        CREATE INDEX IF NOT EXISTS idx_argomenti_banca
            ON argomenti (banca_id, ordine, nome);
        CREATE INDEX IF NOT EXISTS idx_domande_banca_argomento
            ON domande (banca_id, argomento_id, attiva);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata (chiave, valore) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_and_validate_csv(csv_path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                f"{csv_path.name}: colonne mancanti: {', '.join(sorted(missing))}"
            )
        rows = [{key: _clean(value) for key, value in row.items()} for row in reader]

    if not rows:
        raise ValueError(f"{csv_path.name}: nessuna domanda presente")

    seen_codes: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        required_values = REQUIRED_COLUMNS - {"argomento"}
        empty = sorted(name for name in required_values if not row.get(name))
        if not row.get("argomento"):
            empty.append("argomento")
        if empty:
            raise ValueError(
                f"{csv_path.name}, riga {row_number}: campi vuoti: {', '.join(empty)}"
            )
        row["corretta"] = row["corretta"].upper()
        if row["corretta"] not in {"A", "B", "C", "D"}:
            raise ValueError(
                f"{csv_path.name}, riga {row_number}: risposta corretta non valida"
            )
        if row["codice"] in seen_codes:
            raise ValueError(
                f"{csv_path.name}, riga {row_number}: codice duplicato {row['codice']}"
            )
        seen_codes.add(row["codice"])
    return rows


def import_csv(
    conn: sqlite3.Connection,
    csv_path: str | Path,
    bank_name: str | None = None,
) -> tuple[int, int]:
    """Importa o sostituisce atomicamente una banca. Ritorna (argomenti, domande)."""
    csv_path = Path(csv_path)
    rows = read_and_validate_csv(csv_path)
    bank_name = _clean(bank_name) or csv_path.stem

    with conn:
        existing = conn.execute(
            "SELECT id FROM banche_dati WHERE nome = ?", (bank_name,)
        ).fetchone()
        if existing:
            bank_id = int(existing["id"])
            conn.execute("DELETE FROM domande WHERE banca_id = ?", (bank_id,))
            conn.execute("DELETE FROM argomenti WHERE banca_id = ?", (bank_id,))
            conn.execute(
                """UPDATE banche_dati
                   SET file_origine = ?, attiva = 1, aggiornata_il = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (csv_path.name, bank_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO banche_dati (nome, file_origine) VALUES (?, ?)",
                (bank_name, csv_path.name),
            )
            bank_id = int(cursor.lastrowid)

        topic_ids: dict[str, int] = {}
        for topic_order, topic in enumerate(dict.fromkeys(row["argomento"] for row in rows)):
            cursor = conn.execute(
                "INSERT INTO argomenti (banca_id, nome, ordine) VALUES (?, ?, ?)",
                (bank_id, topic, topic_order),
            )
            topic_ids[topic] = int(cursor.lastrowid)

        conn.executemany(
            """
            INSERT INTO domande (
                banca_id, argomento_id, codice, domanda,
                opzione_a, opzione_b, opzione_c, opzione_d,
                corretta, riferimento
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    bank_id,
                    topic_ids[row["argomento"]],
                    row["codice"],
                    row["domanda"],
                    row["opzione_a"],
                    row["opzione_b"],
                    row["opzione_c"],
                    row["opzione_d"],
                    row["corretta"],
                    row.get("riferimento", ""),
                )
                for row in rows
            ],
        )

    return len(topic_ids), len(rows)


def import_directory(
    db_path: str | Path, csv_directory: str | Path
) -> list[tuple[str, int, int]]:
    csv_files: Iterable[Path] = sorted(Path(csv_directory).glob("*.csv"))
    results: list[tuple[str, int, int]] = []
    with connect(db_path) as conn:
        create_schema(conn)
        for csv_path in csv_files:
            topics, questions = import_csv(conn, csv_path)
            results.append((csv_path.stem, topics, questions))
    return results


def list_banks(db_path: str | Path) -> list[tuple[int, str, int]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT b.id, b.nome, COUNT(d.id) AS numero_domande
            FROM banche_dati b
            LEFT JOIN domande d ON d.banca_id = b.id AND d.attiva = 1
            WHERE b.attiva = 1
            GROUP BY b.id, b.nome
            HAVING COUNT(d.id) > 0
            ORDER BY b.nome COLLATE NOCASE
            """
        ).fetchall()
    return [(int(row["id"]), str(row["nome"]), int(row["numero_domande"])) for row in rows]


def list_topics(db_path: str | Path, bank_id: int) -> list[tuple[int, str, int]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.nome, COUNT(d.id) AS numero_domande
            FROM argomenti a
            LEFT JOIN domande d ON d.argomento_id = a.id AND d.attiva = 1
            WHERE a.banca_id = ?
            GROUP BY a.id, a.nome, a.ordine
            HAVING COUNT(d.id) > 0
            ORDER BY a.ordine, a.nome COLLATE NOCASE
            """,
            (bank_id,),
        ).fetchall()
    return [(int(row["id"]), str(row["nome"]), int(row["numero_domande"])) for row in rows]


def load_questions(
    db_path: str | Path, bank_id: int, topic_id: int | None = None
) -> pd.DataFrame:
    sql = """
        SELECT
            a.nome AS argomento,
            d.codice,
            d.domanda,
            d.opzione_a,
            d.opzione_b,
            d.opzione_c,
            d.opzione_d,
            d.corretta,
            d.riferimento
        FROM domande d
        JOIN argomenti a ON a.id = d.argomento_id
        WHERE d.banca_id = ? AND d.attiva = 1
    """
    params: list[int] = [bank_id]
    if topic_id is not None:
        sql += " AND d.argomento_id = ?"
        params.append(topic_id)
    sql += " ORDER BY d.id"

    with connect(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=params)
