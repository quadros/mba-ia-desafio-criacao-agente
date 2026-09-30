"""Conexão com o banco de domínio (SQLite) e DDL."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from aurora.config import DB_PATH

DDL = """
CREATE TABLE IF NOT EXISTS apartamentos (
  numero   TEXT PRIMARY KEY,
  morador  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS areas (
  id    TEXT PRIMARY KEY,
  nome  TEXT NOT NULL,
  taxa  REAL NOT NULL CHECK (taxa >= 0)
);

CREATE TABLE IF NOT EXISTS reservas (
  codigo        TEXT PRIMARY KEY,
  apartamento   TEXT NOT NULL REFERENCES apartamentos(numero),
  area          TEXT NOT NULL REFERENCES areas(id),
  data          TEXT NOT NULL
                CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
  status        TEXT NOT NULL DEFAULT 'ativa'
                CHECK (status IN ('ativa', 'cancelada')),
  cobranca      REAL NOT NULL DEFAULT 0,
  origem_call   TEXT UNIQUE,
  criada_em     TEXT NOT NULL DEFAULT (datetime('now')),
  cancelada_em  TEXT
);

-- Regra 1 / Garantia 5: no máximo uma reserva ATIVA por área e data. O SQLite
-- avalia este índice no próprio INSERT, então a exclusividade vale no instante
-- da gravação, e não numa conferência feita antes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_ativa_area_data
  ON reservas(area, data) WHERE status = 'ativa';

CREATE TABLE IF NOT EXISTS visitantes (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  apartamento  TEXT NOT NULL REFERENCES apartamentos(numero),
  nome         TEXT NOT NULL,
  data         TEXT NOT NULL,
  origem_call  TEXT UNIQUE,
  criado_em    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Regra 5: todo código já emitido fica registrado aqui para sempre (inclusive
-- de reservas canceladas e de antes de uma restauração), e a PK impede repetir.
CREATE TABLE IF NOT EXISTS codigos_emitidos (
  codigo TEXT PRIMARY KEY
);
"""


def _abrir() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: as transações são controladas explicitamente
    # (BEGIN IMMEDIATE), sem o BEGIN implícito do módulo sqlite3.
    con = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    con = _abrir()
    try:
        yield con
    finally:
        con.close()


def criar_schema() -> None:
    with conectar() as con:
        con.executescript(DDL)
