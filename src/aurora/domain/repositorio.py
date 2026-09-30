"""Única porta de leitura e escrita dos dados do condomínio.

Todas as funções recebem o apartamento como argumento de código: nas tools ele
vem do state da sessão (ver aurora.tools.contexto), nas rotas de verificação vem
da URL. Nenhuma função daqui é exposta diretamente ao modelo.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from aurora.infra.db import conectar

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


def data_valida(data: str) -> bool:
    if not isinstance(data, str) or not _RE_DATA.match(data):
        return False
    try:
        date.fromisoformat(data)
    except ValueError:
        return False
    return True


def listar_areas() -> list[dict[str, Any]]:
    with conectar() as con:
        rows = con.execute("SELECT id, nome, taxa FROM areas ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def taxa(area: str) -> Optional[float]:
    """Taxa da área em reais, ou None se a área não existe."""
    with conectar() as con:
        row = con.execute("SELECT taxa FROM areas WHERE id = ?", (area,)).fetchone()
    return None if row is None else float(row["taxa"])


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoReserva:
    status: str  # "criada" | "ja_existia" | "indisponivel"
    codigo: Optional[str] = None
    cobranca: float = 0.0


def listar_reservas(apartamento: str) -> list[dict[str, str]]:
    with conectar() as con:
        rows = con.execute(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND status = 'ativa' ORDER BY data, area",
            (apartamento,),
        ).fetchall()
    return [dict(r) for r in rows]


def data_ocupada(area: str, data: str) -> bool:
    """Diz apenas SE a data está ocupada. Nunca devolve dono nem código."""
    with conectar() as con:
        row = con.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ? AND status = 'ativa'",
            (area, data),
        ).fetchone()
    return row is not None


def _novo_codigo(con: sqlite3.Connection) -> str:
    """Gera um código e o registra em codigos_emitidos (PK) na transação aberta."""
    for _ in range(10):
        codigo = "RSV-" + "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(8))
        try:
            con.execute("INSERT INTO codigos_emitidos(codigo) VALUES (?)", (codigo,))
            return codigo
        except sqlite3.IntegrityError:
            continue  # colisão (improvável): tenta outro
    raise RuntimeError("Não foi possível gerar um código de reserva único.")


def _criar_reserva_sync(
    apartamento: str, area: str, data: str, call_id: Optional[str]
) -> ResultadoReserva:
    with conectar() as con:
        # BEGIN IMMEDIATE pega o lock de escrita já no início: escritores
        # concorrentes esperam (busy_timeout) em vez de falhar.
        con.execute("BEGIN IMMEDIATE")
        try:
            # Idempotência: a retomada de uma confirmação pode reexecutar a
            # mesma chamada de tool; o id da chamada identifica a gravação.
            if call_id:
                row = con.execute(
                    "SELECT codigo, cobranca FROM reservas WHERE origem_call = ?",
                    (call_id,),
                ).fetchone()
                if row:
                    con.execute("COMMIT")
                    return ResultadoReserva("ja_existia", row["codigo"], row["cobranca"])

            row = con.execute("SELECT taxa FROM areas WHERE id = ?", (area,)).fetchone()
            cobranca = float(row["taxa"]) if row else 0.0
            codigo = _novo_codigo(con)
            # Garantia 5: sem conferência prévia da agenda. Quem decide se a
            # data está livre é o índice único parcial ux_reserva_ativa_area_data,
            # avaliado pelo SQLite neste INSERT.
            con.execute(
                "INSERT INTO reservas(codigo, apartamento, area, data, cobranca, origem_call)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (codigo, apartamento, area, data, cobranca, call_id),
            )
            con.execute("COMMIT")
            return ResultadoReserva("criada", codigo, cobranca)
        except sqlite3.IntegrityError as e:
            con.execute("ROLLBACK")
            if "reservas.area" in str(e) and "reservas.data" in str(e):
                return ResultadoReserva("indisponivel")
            raise
        except BaseException:
            con.execute("ROLLBACK")
            raise


async def criar_reserva(
    apartamento: str, area: str, data: str, call_id: Optional[str]
) -> ResultadoReserva:
    return await asyncio.to_thread(_criar_reserva_sync, apartamento, area, data, call_id)


def _cancelar_reserva_sync(
    apartamento: str,
    area: Optional[str],
    data: Optional[str],
    codigo: Optional[str],
) -> dict[str, Any]:
    # Todo filtro começa pelo apartamento da sessão: reserva de outro
    # apartamento é indistinguível de reserva inexistente.
    filtros, params = ["apartamento = ?", "status = 'ativa'"], [apartamento]
    if area:
        filtros.append("area = ?")
        params.append(area)
    if data:
        filtros.append("data = ?")
        params.append(data)
    if codigo:
        filtros.append("codigo = ?")
        params.append(codigo.strip().upper())
    where = " AND ".join(filtros)

    with conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            rows = con.execute(
                f"SELECT codigo, area, data FROM reservas WHERE {where}", params
            ).fetchall()
            if len(rows) != 1:
                con.execute("COMMIT")
                if not rows:
                    return {"status": "nao_encontrada"}
                return {"status": "ambigua", "candidatas": [dict(r) for r in rows]}
            alvo = rows[0]
            # A linha nunca é apagada: o código continua ocupado (regra 5).
            con.execute(
                "UPDATE reservas SET status = 'cancelada', cancelada_em = datetime('now')"
                " WHERE codigo = ? AND apartamento = ? AND status = 'ativa'",
                (alvo["codigo"], apartamento),
            )
            con.execute("COMMIT")
            return {"status": "cancelada", **dict(alvo)}
        except BaseException:
            con.execute("ROLLBACK")
            raise


async def cancelar_reserva(
    apartamento: str,
    area: Optional[str] = None,
    data: Optional[str] = None,
    codigo: Optional[str] = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(_cancelar_reserva_sync, apartamento, area, data, codigo)


# ---------------------------------------------------------------------------
# Visitantes
# ---------------------------------------------------------------------------


def listar_visitantes(apartamento: str) -> list[dict[str, str]]:
    with conectar() as con:
        rows = con.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data, id",
            (apartamento,),
        ).fetchall()
    return [dict(r) for r in rows]


def _autorizar_visitante_sync(
    apartamento: str, nome: str, data: str, call_id: Optional[str]
) -> str:
    with conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            # ON CONFLICT(origem_call): reexecutar a mesma chamada aprovada
            # não gera uma segunda autorização.
            cur = con.execute(
                "INSERT INTO visitantes(apartamento, nome, data, origem_call)"
                " VALUES (?, ?, ?, ?) ON CONFLICT(origem_call) DO NOTHING",
                (apartamento, nome, data, call_id),
            )
            con.execute("COMMIT")
            return "autorizado" if cur.rowcount else "ja_existia"
        except BaseException:
            con.execute("ROLLBACK")
            raise


async def autorizar_visitante(
    apartamento: str, nome: str, data: str, call_id: Optional[str]
) -> str:
    return await asyncio.to_thread(_autorizar_visitante_sync, apartamento, nome, data, call_id)
