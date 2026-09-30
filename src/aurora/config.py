"""Configuração central: caminhos, nomes fixos do runtime e modelos."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

# O AI Studio é o padrão; só usa Vertex se o .env pedir explicitamente.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
if not os.environ["GOOGLE_GENAI_USE_VERTEXAI"]:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"


def _env(nome: str, padrao: str) -> str:
    valor = os.environ.get(nome, "").strip()
    return valor or padrao


def _caminho(nome: str, padrao: Path) -> Path:
    valor = os.environ.get(nome, "").strip()
    if not valor:
        return padrao
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else RAIZ / caminho


DADOS_DIR = RAIZ / "dados"
REGULAMENTO_PATH = DADOS_DIR / "regulamento.md"

DB_PATH = _caminho("AURORA_DB_PATH", RAIZ / "var" / "aurora.db")
SESSIONS_DB_PATH = _caminho("AURORA_SESSIONS_DB_PATH", RAIZ / "var" / "sessions.db")

# Constantes: precisam ser iguais entre reinícios para que get_session encontre
# as sessões persistidas. O apartamento vive no state da sessão, não no user_id.
APP_NAME = "residencial_aurora"
USER_ID = "morador"

MODELO_PRINCIPAL = _env("AURORA_MODELO_PRINCIPAL", "gemini-2.5-flash")
MODELO_ESPECIALISTAS = _env("AURORA_MODELO_ESPECIALISTAS", "gemini-2.5-flash")
