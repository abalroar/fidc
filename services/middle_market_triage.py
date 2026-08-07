"""Triagem de prováveis clientes Middle Market entre os cedentes declarados.

A pergunta é quem, entre os cedentes que os FIDCs declaram no Informe Mensal,
tem porte de Middle Market — o cliente que o banco atenderia por essa mesa.

O julgamento sai do **cadastro da Receita Federal**: capital social, CNAE,
situação cadastral e natureza jurídica.  Nada é inferido do nome; um cedente
sem cadastro resolvido fica ``Não avaliado``, e não "provavelmente não".

Três exclusões vêm antes de qualquer faixa de capital, porque descrevem quem
não é cliente Middle por definição:

* **o próprio veículo** — FIDCs cedendo para FIDCs são estrutura, não cliente;
* **instituição financeira de grande porte** — banco múltiplo ou comercial é
  contraparte, não Middle;
* **pessoa física** — CPF no lugar do CNPJ é cedente pulverizado.

A faixa de capital social é uma proxy, e é declarada como tal: ela separa o
microempreendedor da corporação, não substitui o faturamento, que a Receita
não publica.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


#: Faixa de capital social, em reais.  Abaixo do piso é micro/pequeno demais
#: para uma mesa de Middle; acima do teto é corporate, atendido por outra mesa.
CAPITAL_MINIMO = 1_000_000.0
CAPITAL_MAXIMO = 500_000_000.0

PROVAVEL = "Provável Middle"
IMPROVAVEL = "Improvável Middle"
NAO_AVALIADO = "Não avaliado"

#: CNAEs de banco múltiplo, comercial, caixa econômica e cooperativa de
#: crédito de grande porte.  São contrapartes, não clientes.
_CNAE_BANCO = {"6421200", "6422100", "6423900", "6424701", "6424702", "6424703", "6424704"}
#: CNAE de fundo de investimento — o cedente é o próprio veículo.
_CNAE_FUNDO = {"6470101", "6470102", "6470103"}

_NOME_FUNDO = re.compile(
    r"FUNDO DE INVESTIMENTO|FIDC|FIC[ -]?FIDC|SECURITIZADORA", re.IGNORECASE
)
_NOME_BANCO = re.compile(r"\bBANCO\b|CAIXA ECONOMICA|\bBNDES\b", re.IGNORECASE)


def fold(text: str) -> str:
    norma = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in norma if not unicodedata.combining(ch)).upper()


@dataclass(frozen=True)
class Triagem:
    """O veredito sobre um cedente, e o que o sustenta."""

    documento: str
    razao_social: str
    classificacao: str
    motivo: str
    capital_social: float | None
    cnae: str
    porte: str
    uf: str

    @property
    def provavel(self) -> bool:
        return self.classificacao == PROVAVEL


def _texto(valor: object) -> str:
    """Campo de cadastro ausente chega como NaN, e NaN não é string."""

    if valor is None or valor != valor:  # NaN
        return ""
    return str(valor).strip()


def _numero(valor: object) -> float | None:
    if valor is None or valor == "" or valor != valor:
        return None
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def triar(
    documento: str,
    *,
    razao_social: str = "",
    cnae: object = "",
    cnae_descricao: str = "",
    capital_social: object = None,
    porte: str = "",
    situacao: str = "",
    uf: str = "",
) -> Triagem:
    """Classifica um cedente pelo cadastro, sem olhar para o nome do fundo."""

    doc = re.sub(r"\D", "", str(documento or ""))
    capital = _numero(capital_social)
    codigo = re.sub(r"\D", "", str(cnae or ""))
    nome = _texto(razao_social)
    situacao = _texto(situacao)
    base = dict(
        documento=doc,
        razao_social=nome,
        capital_social=capital,
        cnae=_texto(cnae_descricao),
        porte=_texto(porte),
        uf=_texto(uf),
    )

    if len(doc) == 11:
        return Triagem(**base, classificacao=IMPROVAVEL, motivo="pessoa física")
    if codigo in _CNAE_FUNDO or _NOME_FUNDO.search(nome):
        return Triagem(**base, classificacao=IMPROVAVEL, motivo="o cedente é um fundo")
    if codigo in _CNAE_BANCO or _NOME_BANCO.search(nome):
        return Triagem(
            **base, classificacao=IMPROVAVEL, motivo="instituição financeira de grande porte"
        )
    if not nome:
        return Triagem(**base, classificacao=NAO_AVALIADO, motivo="cadastro não resolvido")
    if situacao and fold(situacao) != "ATIVA":
        return Triagem(**base, classificacao=IMPROVAVEL, motivo=f"situação {situacao.lower()}")
    if capital is None:
        return Triagem(
            **base, classificacao=NAO_AVALIADO, motivo="capital social não publicado"
        )
    if capital < CAPITAL_MINIMO:
        return Triagem(
            **base,
            classificacao=IMPROVAVEL,
            motivo=f"capital social de R$ {capital:,.0f} abaixo do piso".replace(",", "."),
        )
    if capital > CAPITAL_MAXIMO:
        return Triagem(
            **base,
            classificacao=IMPROVAVEL,
            motivo=f"capital social de R$ {capital:,.0f} acima do teto".replace(",", "."),
        )
    return Triagem(
        **base,
        classificacao=PROVAVEL,
        motivo=f"capital social de R$ {capital:,.0f} na faixa, cadastro ativo".replace(
            ",", "."
        ),
    )


__all__ = [
    "CAPITAL_MAXIMO",
    "CAPITAL_MINIMO",
    "IMPROVAVEL",
    "NAO_AVALIADO",
    "PROVAVEL",
    "Triagem",
    "fold",
    "triar",
]
