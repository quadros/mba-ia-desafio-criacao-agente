"""Especialista de regulamento: acionado pelo concierge como AgentTool.

Como AgentTool, ele roda num Runner próprio com InMemorySessionService: o texto
do capítulo que a tool devolve fica só no contexto isolado dele, e à sessão
principal chega apenas a resposta final curta (Garantia 4).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from aurora.agents.modelos import gemini
from aurora.config import MODELO_ESPECIALISTAS
from aurora.tools.regulamento_tools import TOOLS_REGULAMENTO

INSTRUCAO = """\
Você responde dúvidas sobre o regulamento interno do Residencial Aurora.

- Sempre chame consultar_regulamento com o tema da pergunta em poucas palavras.
  Se o capítulo devolvido não tratar do assunto, use ler_capitulo com o numeral
  certo da lista de capítulos disponíveis.
- Responda somente com base no texto devolvido pela tool. Se ele não responder à
  pergunta, diga que o regulamento não trata disso.
- Responda em no máximo três frases, só com o que foi perguntado, citando o
  artigo (ex.: "Art. 22, II"). Nunca transcreva o capítulo nem trate de outros
  assuntos do regulamento.
"""

regulamento_especialista = LlmAgent(
    name="regulamento_especialista",
    model=gemini(MODELO_ESPECIALISTAS),
    description=(
        "Responde dúvidas sobre as regras do regulamento interno do condomínio "
        "(horários, piscina, barulho, animais, mudanças, obras, garagem, lixo, "
        "multas etc.). Envie a pergunta do morador em 'request'."
    ),
    instruction=INSTRUCAO,
    tools=TOOLS_REGULAMENTO,
)
