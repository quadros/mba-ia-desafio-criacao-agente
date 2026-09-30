"""Consulta ao regulamento interno por capítulo.

O arquivo dados/regulamento.md só é lido aqui. Nenhuma tool devolve o
regulamento inteiro: a unidade de recuperação é UM capítulo, escolhido de forma
determinística por palavras-chave (sem embeddings).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from google.adk.tools import FunctionTool

from aurora.config import REGULAMENTO_PATH

_RE_CAPITULO = re.compile(r"^## Capítulo ([IVXLC]+): (.+)$", re.MULTILINE)

# Sinônimos que o morador usa e que nem sempre aparecem no texto do capítulo.
# Chave: numeral do capítulo; valor: termos (já sem acento e minúsculos).
_SINONIMOS: dict[str, tuple[str, ...]] = {
    "III": ("barulho", "silencio", "som", "musica", "festa", "ruido", "vizinho"),
    "IV": ("piscina", "nadar", "natacao", "deck"),
    "V": ("academia", "brinquedoteca", "playground", "ginastica", "musculacao"),
    "VI": ("salao", "churrasqueira", "churrasco", "quadra", "reserva", "reservar"),
    "VII": ("visita", "visitante", "portaria", "porteiro", "entrega", "delivery", "encomenda"),
    "VIII": ("cachorro", "cao", "gato", "pet", "animal", "animais"),
    "IX": ("mudanca", "mudar", "caminhao"),
    "X": ("obra", "reforma", "pedreiro", "furadeira"),
    "XI": ("garagem", "vaga", "carro", "moto", "bicicleta", "veiculo"),
    "XII": ("lixo", "reciclagem", "coleta", "residuo"),
    "XIII": ("multa", "penalidade", "infracao", "advertencia"),
}

_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "que", "para", "por", "com", "um", "uma", "ao", "aos", "se",
    "ate", "qual", "quais", "como", "quando", "pode", "posso", "horas", "hora",
}


@dataclass(frozen=True)
class Capitulo:
    numeral: str
    titulo: str
    texto: str
    titulo_norm: str
    texto_norm: str


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _termos(texto: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _normalizar(texto)) if t not in _STOPWORDS]


@lru_cache(maxsize=1)
def _capitulos() -> tuple[Capitulo, ...]:
    conteudo = REGULAMENTO_PATH.read_text(encoding="utf-8")
    marcas = list(_RE_CAPITULO.finditer(conteudo))
    capitulos = []
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(conteudo)
        texto = conteudo[m.start():fim].strip()
        titulo = m.group(2).strip()
        capitulos.append(
            Capitulo(m.group(1), titulo, texto, _normalizar(titulo), _normalizar(texto))
        )
    return tuple(capitulos)


def _pontuar(cap: Capitulo, termos: list[str]) -> float:
    pontos = 0.0
    sinonimos = _SINONIMOS.get(cap.numeral, ())
    for t in termos:
        if len(t) < 3:
            continue
        raiz = t[:5]  # tolera plural e flexões simples
        if t in sinonimos or any(s.startswith(raiz) for s in sinonimos):
            pontos += 6
        if raiz in cap.titulo_norm:
            pontos += 4
        pontos += min(cap.texto_norm.count(raiz), 5) * 0.5
    return pontos


def consultar_regulamento(tema: str) -> dict[str, Any]:
    """Busca no regulamento interno o capítulo que trata do tema e devolve só ele.

    Args:
        tema: assunto da dúvida em poucas palavras, por exemplo 'horário da piscina
            aos domingos' ou 'barulho depois das 22h'.
    """
    termos = _termos(tema or "")
    ranking = sorted(
        ((_pontuar(c, termos), c) for c in _capitulos()),
        key=lambda par: par[0],
        reverse=True,
    )
    if not ranking or ranking[0][0] <= 0:
        return {
            "status": "sem_resultado",
            "capitulos_disponiveis": [f"{c.numeral}: {c.titulo}" for c in _capitulos()],
            "mensagem": "Nenhum capítulo corresponde ao tema. Use ler_capitulo com um numeral.",
        }
    melhor = ranking[0][1]
    return {"status": "ok", "capitulo": f"{melhor.numeral}: {melhor.titulo}", "texto": melhor.texto}


def ler_capitulo(numeral: str) -> dict[str, Any]:
    """Lê um único capítulo do regulamento pelo numeral romano (ex.: 'IV').

    Use só quando consultar_regulamento não encontrar o capítulo certo.

    Args:
        numeral: numeral romano do capítulo, de 'I' a 'XIV'.
    """
    alvo = (numeral or "").strip().upper()
    for c in _capitulos():
        if c.numeral == alvo:
            return {"status": "ok", "capitulo": f"{c.numeral}: {c.titulo}", "texto": c.texto}
    return {
        "status": "nao_encontrado",
        "capitulos_disponiveis": [f"{c.numeral}: {c.titulo}" for c in _capitulos()],
    }


consultar_regulamento_tool = FunctionTool(consultar_regulamento)
ler_capitulo_tool = FunctionTool(ler_capitulo)

TOOLS_REGULAMENTO = [consultar_regulamento_tool, ler_capitulo_tool]
