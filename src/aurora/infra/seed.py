"""Restauração dos dados iniciais a partir de dados/*.json (somente leitura).

Uso:
    uv run aurora-reset             # volta reservas e visitantes ao estado dos JSON
    uv run aurora-reset --sessoes   # idem e também apaga todas as sessões
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from typing import Any

from aurora.config import DADOS_DIR, SESSIONS_DB_PATH
from aurora.infra.db import conectar, criar_schema


def _ler_json(nome: str) -> list[dict[str, Any]]:
    with open(DADOS_DIR / nome, encoding="utf-8") as f:
        return json.load(f)


def _carregar(con: sqlite3.Connection) -> None:
    """Recria reservas e visitantes a partir dos JSON, dentro da transação aberta."""
    con.execute("DELETE FROM reservas")
    con.execute("DELETE FROM visitantes")

    for apto in _ler_json("apartamentos.json"):
        con.execute(
            "INSERT INTO apartamentos(numero, morador) VALUES (?, ?)"
            " ON CONFLICT(numero) DO UPDATE SET morador = excluded.morador",
            (apto["numero"], apto["morador"]),
        )
    for area in _ler_json("areas.json"):
        con.execute(
            "INSERT INTO areas(id, nome, taxa) VALUES (?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET nome = excluded.nome, taxa = excluded.taxa",
            (area["id"], area["nome"], float(area["taxa"])),
        )
    taxas = {r["id"]: r["taxa"] for r in con.execute("SELECT id, taxa FROM areas")}
    for r in _ler_json("reservas.json"):
        con.execute(
            "INSERT INTO reservas(codigo, apartamento, area, data, cobranca)"
            " VALUES (?, ?, ?, ?, ?)",
            (r["codigo"], r["apartamento"], r["area"], r["data"], taxas.get(r["area"], 0)),
        )
        # codigos_emitidos nunca é limpa: um código emitido antes de uma
        # restauração continua reservado e não é reaproveitado (regra 5).
        con.execute("INSERT OR IGNORE INTO codigos_emitidos(codigo) VALUES (?)", (r["codigo"],))
    for v in _ler_json("visitantes.json"):
        con.execute(
            "INSERT INTO visitantes(apartamento, nome, data) VALUES (?, ?, ?)",
            (v["apartamento"], v["nome"], v["data"]),
        )


def restaurar() -> None:
    criar_schema()
    with conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            _carregar(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def semear_se_vazio() -> None:
    """Usado na subida da API: cria o schema e só semeia um banco novo.

    Nunca restaura um banco que já tem dados, para que reiniciar a API não
    desfaça reservas, cancelamentos e visitantes gravados antes (Garantia 3).
    """
    criar_schema()
    with conectar() as con:
        vazio = con.execute("SELECT COUNT(*) FROM areas").fetchone()[0] == 0
    if vazio:
        restaurar()


def apagar_sessoes() -> None:
    for sufixo in ("", "-wal", "-shm", "-journal"):
        caminho = SESSIONS_DB_PATH.with_name(SESSIONS_DB_PATH.name + sufixo)
        caminho.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaura os dados iniciais do condomínio.")
    parser.add_argument(
        "--sessoes",
        action="store_true",
        help="também apaga todas as sessões (conversas) gravadas",
    )
    args = parser.parse_args()
    restaurar()
    print("Reservas e visitantes restaurados a partir de dados/*.json.")
    if args.sessoes:
        apagar_sessoes()
        print("Sessões apagadas.")


if __name__ == "__main__":
    main()
