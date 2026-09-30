"""Modelos Gemini com retry para erros transitórios (cota e indisponibilidade)."""

from __future__ import annotations

from google.adk.models import Gemini
from google.genai import types

_RETRY = types.HttpRetryOptions(
    attempts=6,
    initial_delay=2.0,
    max_delay=30.0,
    exp_base=2.0,
    http_status_codes=[408, 429, 500, 502, 503, 504],
)


def gemini(nome: str) -> Gemini:
    return Gemini(model=nome, retry_options=_RETRY)
