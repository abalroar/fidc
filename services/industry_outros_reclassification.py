"""Documentary reclassification of the FIDC ``Outros`` bucket.

The module extends the Top 20 documentary curation to the long tail of funds
displayed as ``Outros`` on the ANBIMA type mix.  It never mutates official
ANBIMA or CVM fields: it reads the fund documents page by page and proposes an
analytical decision for the same five taxonomies already used by the project
(Tipo ANBIMA analítico, Foco ANBIMA analítico, Tabela II analítica and the
functional taxonomy N1/N2).

Classification is evidence driven.  Every family of receivables carries its own
regex vocabulary; matches are weighted by the section where they appear so that
definitions, investment policy and eligibility criteria outrank risk factors and
generic instrument lists.  A decision is only definitive when one family clearly
dominates the document; otherwise the fund keeps the official multicarteira
reading or stays in the review queue with an explicit reason.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence
import unicodedata


DISPLAY_TYPES: tuple[str, ...] = (
    "Fomento Mercantil",
    "Agro, Indústria e Comércio",
    "Financeiro",
    "Outros",
)
NAMED_DISPLAY_TYPES: tuple[str, ...] = DISPLAY_TYPES[:-1]

DECISION_STATUSES: tuple[str, ...] = (
    "aprovado",
    "em_revisao",
    "pendente",
    "rejeitado",
)


@dataclass(frozen=True)
class ReceivableFamily:
    """One economic family of receivables and its target taxonomy."""

    family_id: str
    label: str
    patterns: tuple[tuple[str, float], ...]
    tipo: str
    foco: str
    tabela_ii: str
    n1: str
    n2: str
    dominates: frozenset[str] = frozenset()


#: Sections whose wording actually defines the mandate.
POLICY_ANCHORS: tuple[str, ...] = (
    r"POLITICA DE INVESTIMENTO",
    r"CRITERIOS? DE ELEGIBILIDADE",
    r"DIREITOS? CREDITORIOS? ELEGIVEIS",
    r"CONDICOES? DE CESSAO",
    r"OBJETIVO (?:DO FUNDO|DA CLASSE|DA SUBCLASSE)",
    r"COMPOSICAO DA CARTEIRA",
    r"DEFINICOES",
    r"ANEXO (?:I{1,3}|IV|V|DESCRITIVO)",
    r"PUBLICO[ -]ALVO",
)

#: Sections that mention families without defining the mandate.
RISK_ANCHORS: tuple[str, ...] = (
    r"FATORES? DE RISCO",
    r"RISCOS? RELACIONADOS?",
    r"RISCO DE (?:CREDITO|MERCADO|LIQUIDEZ)",
    r"COBRANCA DOS? DIREITOS? CREDITORIOS? INADIMPLIDOS?",
)

POLICY_PAGE_MULTIPLIER = 2.0
RISK_PAGE_MULTIPLIER = 0.35
MAX_MATCHES_PER_PATTERN_PER_PAGE = 3

#: Below this score the document did not describe the mandate well enough.
MIN_DECISIVE_SCORE = 6.0
#: A definitive decision needs at least one decisive clause in a policy section.
APPROVAL_MIN_SCORE = 7.0
#: Families above this share of the leader count as competing mandates.
COMPETING_FAMILY_SHARE = 0.35
#: How much louder the generic vocabulary may be and still be absorbed by the
#: specific family that declares dominance over it.
DOMINANCE_TOLERANCE = 2.0
#: Dominance ratio required to close a decision automatically.
DOMINANT_RATIO = 1.6
#: Dominance ratio and score required to report high confidence.
HIGH_CONFIDENCE_RATIO = 2.5
HIGH_CONFIDENCE_SCORE = 12.0
#: Number of competing families that characterises a multicarteira mandate.
MULTICARTEIRA_FAMILY_COUNT = 4
#: Share of the competing score a single ANBIMA type needs to carry the
#: multicarteira reading out of ``Outros``.
MULTICARTEIRA_TYPE_SHARE = 0.6


RECEIVABLE_FAMILIES: tuple[ReceivableFamily, ...] = (
    ReceivableFamily(
        family_id="adquirencia",
        label="adquirência / arranjos de pagamento",
        patterns=(
            (r"ARRANJOS? DE PAGAMENTO", 3.0),
            (r"AGENDA(?:S)? DE RECEBIVEIS", 3.0),
            (r"SUBCREDENCIADORAS?", 3.0),
            (r"CREDENCIADORAS?", 2.5),
            (r"UNIDADES? DE RECEBIVEIS", 2.5),
            (r"INSTITUIDOR(?:A|ES)? DO ARRANJO", 2.5),
            (r"TRANSACOES? DE PAGAMENTO", 1.5),
            (r"REGISTRADORAS? DE RECEBIVEIS", 1.5),
        ),
        tipo="Financeiro",
        foco="Adquirência",
        tabela_ii="Adquirência",
        n1="Meios de Pagamento e Cartões",
        n2="Arranjos de pagamento/adquirência",
        dominates=frozenset({"recebiveis_comerciais", "cartao_emissor"}),
    ),
    ReceivableFamily(
        family_id="cartao_emissor",
        label="banco emissor / cartão de crédito",
        patterns=(
            (r"BANCOS? EMISSOR(?:ES)?", 3.0),
            (r"EMISSOR(?:ES|A|AS)? DE CARTAO", 3.0),
            (r"FATURAS? DE CARTAO", 3.0),
            (r"CARTAO DE CREDITO", 2.0),
            (r"CARTOES? DE CREDITO", 2.0),
            (r"CREDITO ROTATIVO", 1.5),
            (r"PARCELAMENTO DE FATURA", 2.0),
            (r"BANDEIRAS? (?:VISA|MASTERCARD|ELO)", 1.5),
        ),
        tipo="Financeiro",
        foco="Cartão de crédito",
        tabela_ii="Cartão de crédito",
        n1="Meios de Pagamento e Cartões",
        n2="Banco emissor/cartão de crédito",
        dominates=frozenset({"credito_pessoal"}),
    ),
    ReceivableFamily(
        family_id="consignado",
        label="crédito consignado",
        patterns=(
            (r"CREDITOS? CONSIGNADOS?", 3.0),
            (r"EMPRESTIMOS? CONSIGNADOS?", 3.0),
            (r"CONSIGNACAO EM FOLHA", 3.0),
            (r"MARGEM CONSIGNAVEL", 3.0),
            (r"\bINSS\b", 1.5),
            (r"AVERBACAO", 1.0),
        ),
        tipo="Financeiro",
        foco="Crédito Consignado",
        tabela_ii="Financeiro",
        n1="Crédito PF",
        n2="Consignado/INSS",
        dominates=frozenset(
            {"credito_pessoal", "ccb_giro", "recebiveis_comerciais", "setor_publico"}
        ),
    ),
    ReceivableFamily(
        family_id="fgts",
        label="FGTS / saque-aniversário",
        patterns=(
            (r"SAQUE[ -]ANIVERSARIO", 3.5),
            (r"FUNDO DE GARANTIA DO TEMPO DE SERVICO", 3.0),
            (r"\bFGTS\b", 2.0),
        ),
        tipo="Financeiro",
        foco="Crédito Pessoal",
        tabela_ii="Financeiro",
        n1="Crédito PF",
        n2="FGTS",
        dominates=frozenset({"credito_pessoal", "consignado", "setor_publico"}),
    ),
    ReceivableFamily(
        family_id="veiculos",
        label="financiamento de veículos",
        patterns=(
            (r"FINANCIAMENTOS? DE VEICULOS?", 3.5),
            (r"ALIENACAO FIDUCIARIA.{0,80}VEICULOS?", 3.0),
            (r"\bCDC\b.{0,40}VEICULOS?", 3.0),
            (r"MOTOCICLETAS?", 1.5),
            (r"VEICULOS? AUTOMOTORES?", 2.0),
            (r"CONCESSIONARIAS? DE VEICULOS?", 2.0),
        ),
        tipo="Financeiro",
        foco="Financiamento de Veículos",
        tabela_ii="Financeiro",
        n1="Crédito PF",
        n2="Auto/Veículos",
        dominates=frozenset({"credito_pessoal", "ccb_giro", "recebiveis_comerciais"}),
    ),
    ReceivableFamily(
        family_id="estudantil",
        label="crédito estudantil",
        patterns=(
            (r"CREDITOS? ESTUDANTIS?", 3.5),
            (r"FINANCIAMENTOS? ESTUDANTIS?", 3.5),
            (r"MENSALIDADES? (?:ESCOLARES?|ACADEMICAS?)", 3.0),
            (r"SEMESTRALIDADES?", 3.0),
            (r"INSTITUICOES? DE ENSINO", 2.0),
        ),
        tipo="Financeiro",
        foco="Crédito Pessoal",
        tabela_ii="Financeiro",
        n1="Crédito PF",
        n2="Crédito estudantil",
        dominates=frozenset({"credito_pessoal", "recebiveis_comerciais"}),
    ),
    ReceivableFamily(
        family_id="imobiliario",
        label="crédito imobiliário",
        patterns=(
            (r"CREDITOS? IMOBILIARIOS?", 3.0),
            (r"FINANCIAMENTOS? IMOBILIARIOS?", 3.0),
            (r"CEDULAS? DE CREDITO IMOBILIARIO", 3.0),
            (r"INCORPORACAO IMOBILIARIA", 2.5),
            (r"ALIENACAO FIDUCIARIA.{0,80}IMOVE(?:L|IS)", 2.5),
            (r"COMPRA E VENDA DE (?:IMOVE(?:L|IS)|UNIDADES? AUTONOMAS?)", 2.5),
            (r"LOTEAMENTOS?", 2.0),
        ),
        tipo="Financeiro",
        foco="Crédito Imobiliário",
        tabela_ii="Imobiliário",
        n1="Imobiliário",
        n2="Imobiliário",
        dominates=frozenset({"ccb_giro", "credito_corporativo", "recebiveis_comerciais"}),
    ),
    ReceivableFamily(
        family_id="agro",
        label="agronegócio",
        patterns=(
            (r"CEDULAS? DE PRODUTO RURAL", 3.5),
            (r"\bCPR\b", 2.5),
            (r"\bCDCA\b", 2.5),
            (r"CADEIAS? PRODUTIVAS? DO AGRONEGOCIO", 3.0),
            (r"PRODUTORES? RURAIS?", 2.5),
            (r"INSUMOS? AGRICOLAS?", 2.5),
            (r"AGRONEGOCIO", 2.0),
            (r"\bSAFRAS?\b", 1.5),
        ),
        tipo="Agro, Indústria e Comércio",
        foco="Agronegócio",
        tabela_ii="Agronegócio",
        n1="Agro",
        n2="Agro",
        dominates=frozenset({"recebiveis_comerciais", "credito_corporativo"}),
    ),
    ReceivableFamily(
        family_id="energia_infra",
        label="energia e infraestrutura",
        patterns=(
            (r"ENERGIA ELETRICA", 3.0),
            (r"DISTRIBUIDORAS? DE ENERGIA", 3.0),
            (r"GERACAO DISTRIBUIDA", 3.0),
            (r"\bCCEE\b", 2.5),
            (r"CONCESSIONARIAS? DE (?:SERVICO PUBLICO|SANEAMENTO|ENERGIA)", 2.5),
            (r"SANEAMENTO BASICO", 2.5),
            (r"PROJETOS? DE INFRAESTRUTURA", 2.5),
            (r"TELECOMUNICACOES", 1.5),
        ),
        tipo="Agro, Indústria e Comércio",
        foco="Infraestrutura",
        tabela_ii="Serviços",
        n1="Infra/Energia",
        n2="Energia/infra",
        dominates=frozenset({"recebiveis_comerciais", "credito_corporativo"}),
    ),
    ReceivableFamily(
        family_id="precatorios",
        label="precatórios e requisitórios contra entes públicos",
        patterns=(
            (r"PRECATORIOS?", 3.5),
            (r"REQUISICOES? DE PEQUENO VALOR", 3.0),
            (r"\bRPV\b", 2.5),
            (r"OFICIOS? REQUISITORIOS?", 3.0),
        ),
        tipo="Outros",
        foco="Poder Público",
        tabela_ii="Ações judiciais",
        n1="Judicial/Precatórios/NPL",
        n2="Precatórios/direitos judiciais",
        dominates=frozenset({"npl", "setor_publico", "direitos_judiciais"}),
    ),
    ReceivableFamily(
        family_id="direitos_judiciais",
        label="direitos judiciais privados",
        patterns=(
            (r"CREDITOS? JUDICIAIS?", 3.0),
            (r"HONORARIOS? (?:SUCUMBENCIAIS?|ADVOCATICIOS?)", 2.5),
            (r"ACOES? JUDICIAIS?.{0,120}TRANSITAD", 2.5),
            (r"CREDITOS? LITIGIOSOS?", 2.5),
        ),
        tipo="Outros",
        foco="Recuperação",
        tabela_ii="Ações judiciais",
        n1="Judicial/Precatórios/NPL",
        n2="Precatórios/direitos judiciais",
        dominates=frozenset({"npl"}),
    ),
    ReceivableFamily(
        family_id="npl",
        label="créditos inadimplidos / NPL",
        patterns=(
            (r"CREDITOS? INADIMPLIDOS?", 3.0),
            (r"NON[ -]?PERFORMING", 3.0),
            (r"\bNPL\b", 3.0),
            (r"RECUPERACAO DE CREDITOS?", 2.5),
            (r"CARTEIRAS? INADIMPLIDAS?", 3.0),
            (r"CREDITOS? VENCIDOS? E NAO PAGOS?", 2.5),
            (r"CREDITOS? EM ATRASO", 2.0),
            (r"SPECIAL SITUATIONS?", 2.5),
        ),
        tipo="Outros",
        foco="Recuperação",
        tabela_ii="N/D",
        n1="Judicial/Precatórios/NPL",
        n2="Não padronizado/NPL",
    ),
    ReceivableFamily(
        family_id="setor_publico",
        label="receitas e dívidas do poder público",
        patterns=(
            (r"DIVIDA ATIVA", 3.0),
            (r"CREDITOS? (?:CONTRA|EM FACE) (?:D)?[AO]S? (?:FAZENDA|ENTES? PUBLICOS?|"
             r"ESTADOS?|MUNICIPIOS?|UNIAO)", 3.0),
            (r"ROYALTIES", 2.0),
            (r"RECEITAS? PUBLICAS?", 2.5),
            (r"CESSAO DE RECEITAS? (?:TRIBUTARIAS?|ORCAMENTARIAS?)", 3.0),
        ),
        tipo="Outros",
        foco="Poder Público",
        tabela_ii="Setor público",
        n1="Multissetorial / Outros",
        n2="Multicarteira outros",
    ),
    ReceivableFamily(
        family_id="risco_sacado",
        label="risco sacado / fornecedores",
        patterns=(
            (r"RISCO SACADO", 3.5),
            (r"CONFIRMING", 3.0),
            (r"ANTECIPACAO A FORNECEDORES", 3.0),
            (r"FORNECEDORES? HOMOLOGADOS?", 2.5),
        ),
        tipo="Agro, Indústria e Comércio",
        foco="Recebíveis Comerciais",
        tabela_ii="Comercial",
        n1="Crédito PJ",
        n2="Risco sacado/fornecedores",
        dominates=frozenset({"recebiveis_comerciais"}),
    ),
    ReceivableFamily(
        family_id="fomento_mercantil",
        label="fomento mercantil / factoring",
        patterns=(
            (r"FOMENTO MERCANTIL", 3.5),
            (r"FACTORING", 3.0),
            (r"EMPRESAS? DE FOMENTO", 3.0),
        ),
        tipo="Fomento Mercantil",
        foco="Fomento Mercantil",
        tabela_ii="Factoring",
        n1="Crédito PJ",
        n2="Recebíveis comerciais/multissetorial",
        dominates=frozenset({"recebiveis_comerciais"}),
    ),
    ReceivableFamily(
        family_id="ccb_giro",
        label="CCB e capital de giro",
        patterns=(
            (r"CEDULAS? DE CREDITO BANCARIO", 3.0),
            (r"\bCCB\b", 2.0),
            (r"CAPITAL DE GIRO", 2.5),
            (r"EMPRESTIMOS? (?:A|PARA) (?:PESSOAS? JURIDICAS?|EMPRESAS)", 2.0),
        ),
        tipo="Financeiro",
        foco="Multicarteira Financeiro",
        tabela_ii="Financeiro",
        n1="Crédito PJ",
        n2="CCB/Notas comerciais/Capital de giro",
    ),
    ReceivableFamily(
        family_id="credito_corporativo",
        label="crédito corporativo / mercado de capitais",
        patterns=(
            (r"DEBENTURES?", 2.5),
            (r"NOTAS? COMERCIAIS?", 2.5),
            (r"NOTAS? PROMISSORIAS? COMERCIAIS?", 2.5),
            (r"CREDITO CORPORATIVO", 2.5),
        ),
        tipo="Agro, Indústria e Comércio",
        foco="Crédito Corporativo",
        tabela_ii="Financeiro",
        n1="Crédito PJ",
        n2="Crédito privado/mercado de capitais",
    ),
    ReceivableFamily(
        family_id="credito_pessoal",
        label="crédito pessoal / consumo",
        patterns=(
            (r"CREDITOS? PESSOAIS?", 2.5),
            (r"EMPRESTIMOS? PESSOAIS?", 2.5),
            (r"CREDITO DIRETO AO CONSUMIDOR", 2.5),
            (r"CREDIARIO", 2.5),
            (r"BUY NOW,? PAY LATER", 2.5),
            (r"\bBNPL\b", 2.5),
        ),
        tipo="Financeiro",
        foco="Crédito Pessoal",
        tabela_ii="Financeiro",
        n1="Crédito PF",
        n2="Crédito pessoal/consumo",
    ),
    ReceivableFamily(
        family_id="recebiveis_comerciais",
        label="recebíveis comerciais / multissetorial",
        patterns=(
            (r"DUPLICATAS?", 2.5),
            (r"VENDAS? MERCANTIS?", 2.5),
            (r"NOTAS? FISCAIS? (?:DE|E) (?:VENDA|SERVICOS?|FATURAS?)", 2.0),
            (r"COMPRA E VENDA MERCANTIL", 2.5),
            (r"FORNECIMENTO DE BENS E SERVICOS", 2.0),
        ),
        tipo="Agro, Indústria e Comércio",
        foco="Recebíveis Comerciais",
        tabela_ii="Comercial",
        n1="Crédito PJ",
        n2="Recebíveis comerciais/multissetorial",
    ),
)

FAMILY_BY_ID: Mapping[str, ReceivableFamily] = {
    family.family_id: family for family in RECEIVABLE_FAMILIES
}

MULTICARTEIRA_BY_TYPE: Mapping[str, tuple[str, str, str, str]] = {
    "Financeiro": (
        "Multicarteira Financeiro",
        "Financeiro",
        "Multissetorial / Outros",
        "Multicarteira financeiro",
    ),
    "Agro, Indústria e Comércio": (
        "Multicarteira Agro, Indústria e Comércio",
        "N/D",
        "Multissetorial / Outros",
        "Multicarteira outros",
    ),
    "Fomento Mercantil": (
        "Fomento Mercantil",
        "Factoring",
        "Crédito PJ",
        "Recebíveis comerciais/multissetorial",
    ),
    "Outros": (
        "Multicarteira Outros",
        "N/D",
        "Multissetorial / Outros",
        "Multicarteira outros",
    ),
}

CEDENT_PATTERNS: tuple[str, ...] = (
    r"(?:CEDENTES?|ORIGINADOR(?:ES|A|AS)?)[^.]{0,220}?CNPJ[^.]{0,60}",
    r"CNPJ[^.]{0,60}?(?:CEDENTES?|ORIGINADOR(?:ES|A|AS)?)[^.]{0,120}",
    r"(?:CEDENTE|ORIGINADOR)\s+(?:E|SERA|SAO|SERAO)\s+[^.]{0,180}",
)

FIF_PATTERNS: tuple[str, ...] = (
    r"FUNDO DE INVESTIMENTO FINANCEIRO",
    r"CLASSE (?:UNICA )?(?:DE )?(?:RENDA FIXA|MULTIMERCADO|ACOES)",
)
#: Wording that only a receivables fund carries.
ASSIGNMENT_PATTERNS: tuple[str, ...] = (
    r"CRITERIOS? DE ELEGIBILIDADE",
    r"CONDICOES? DE CESSAO",
    r"DIREITOS? CREDITORIOS? ELEGIVEIS",
    r"CONTRATOS? DE CESSAO",
    r"\bCEDENTES?\b",
    r"DOCUMENTOS? COMPROBATORIOS?",
)
FIC_PATTERNS: tuple[str, ...] = (
    r"FUNDO DE INVESTIMENTO EM COTAS DE FUNDOS? DE INVESTIMENTO EM DIREITOS? CREDITORIOS?",
    r"APLICAR(?:A|AO)?.{0,120}COTAS DE (?:OUTROS )?(?:FUNDOS?|FIDC)",
)


def fold_text(value: object) -> str:
    """Uppercase, strip diacritics and collapse whitespace for matching."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).upper().strip()


def _page_multiplier(folded_page: str) -> float:
    has_policy = any(re.search(anchor, folded_page) for anchor in POLICY_ANCHORS)
    if has_policy:
        return POLICY_PAGE_MULTIPLIER
    if any(re.search(anchor, folded_page) for anchor in RISK_ANCHORS):
        return RISK_PAGE_MULTIPLIER
    return 1.0


def _snippet(folded_page: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 180)
    end = min(len(folded_page), match.end() + 320)
    return folded_page[start:end]


@dataclass(frozen=True)
class FamilyEvidence:
    family_id: str
    score: float
    page: int
    document_label: str
    snippet: str
    matched_pattern: str


def score_families(
    documents: Sequence[tuple[str, Sequence[str]]],
    *,
    np_prior: bool = False,
) -> dict[str, FamilyEvidence]:
    """Score every receivable family over the folded pages of all documents."""

    scores: dict[str, float] = {}
    best: dict[str, tuple[float, int, str, str, str]] = {}
    for document_label, pages in documents:
        for page_number, page in enumerate(pages, start=1):
            folded = fold_text(page)
            if not folded:
                continue
            multiplier = _page_multiplier(folded)
            for family in RECEIVABLE_FAMILIES:
                for pattern, weight in family.patterns:
                    matches = list(re.finditer(pattern, folded))
                    if not matches:
                        continue
                    capped = min(len(matches), MAX_MATCHES_PER_PATTERN_PER_PAGE)
                    contribution = capped * weight * multiplier
                    scores[family.family_id] = (
                        scores.get(family.family_id, 0.0) + contribution
                    )
                    candidate = (
                        weight * multiplier,
                        page_number,
                        document_label,
                        _snippet(folded, matches[0]),
                        pattern,
                    )
                    current = best.get(family.family_id)
                    if current is None or candidate[0] > current[0]:
                        best[family.family_id] = candidate
    if np_prior:
        for family_id in ("npl", "precatorios"):
            if family_id in scores:
                scores[family_id] *= 1.25
    return {
        family_id: FamilyEvidence(
            family_id=family_id,
            score=round(score, 3),
            page=best[family_id][1],
            document_label=best[family_id][2],
            snippet=best[family_id][3][:900],
            matched_pattern=best[family_id][4],
        )
        for family_id, score in scores.items()
        if family_id in best
    }


def _apply_dominance(scores: Mapping[str, float]) -> dict[str, float]:
    """Remove families that are a generic restatement of a more specific one.

    Dominance is declared pair by pair and expresses an economic relation, not a
    numeric one: a CCB is the instrument that formalizes vehicle financing, and
    ``entes públicos`` appear in every payroll-loan regulation.  Whenever the
    specific family clears the decisive threshold it therefore absorbs the
    generic one even when the generic vocabulary is repeated more often.
    """

    present = {
        family_id
        for family_id, score in scores.items()
        if score >= MIN_DECISIVE_SCORE
    }
    dominated: set[str] = set()
    for family_id in present:
        for weaker in FAMILY_BY_ID[family_id].dominates:
            if weaker == family_id or weaker not in scores:
                continue
            if scores[weaker] <= scores[family_id] * DOMINANCE_TOLERANCE:
                dominated.add(weaker)
    return {
        family_id: score
        for family_id, score in scores.items()
        if family_id not in dominated
    }


def find_cedent_evidence(documents: Sequence[tuple[str, Sequence[str]]]) -> str:
    for document_label, pages in documents:
        for page_number, page in enumerate(pages, start=1):
            folded = fold_text(page)
            if not folded:
                continue
            for pattern in CEDENT_PATTERNS:
                match = re.search(pattern, folded)
                if match:
                    return (
                        f"{document_label} p. {page_number}: "
                        f"{folded[match.start():match.end()][:400]}"
                    )
    return ""


def detect_perimeter(documents: Sequence[tuple[str, Sequence[str]]]) -> str:
    """Return a perimeter proposal when the document is not a FIDC regulation.

    A FIF regulation may still mention ``direitos creditórios`` — it can hold
    FIDC quotas.  What it never has is the machinery of an assignment: eligible
    receivables, assignment conditions, an assignor or eligibility criteria.
    """

    header = " ".join(
        fold_text(page) for _label, pages in documents for page in pages[:3]
    )
    body = " ".join(
        fold_text(page) for _label, pages in documents for page in pages
    )
    if not body:
        return ""
    is_fif = any(re.search(pattern, header) for pattern in FIF_PATTERNS)
    has_assignment = any(
        re.search(pattern, body) for pattern in ASSIGNMENT_PATTERNS
    )
    if is_fif and not has_assignment:
        return (
            "O documento declara fundo de investimento financeiro sem direitos "
            "creditórios; validar o enquadramento no cadastro CVM antes de "
            "retirar o CNPJ do ranking de FIDC."
        )
    return ""


def detect_fic_fidc(documents: Sequence[tuple[str, Sequence[str]]]) -> bool:
    joined = " ".join(
        fold_text(page) for _label, pages in documents for page in pages[:20]
    )
    return any(re.search(pattern, joined) for pattern in FIC_PATTERNS)


@dataclass(frozen=True)
class Decision:
    decision_status: str
    tipo: str
    foco: str
    tabela_ii: str
    n1: str
    n2: str
    confidence: str
    rationale: str
    evidence: str
    pages: str
    family_scores: str
    limitation: str
    reason: str


def _format_scores(scores: Mapping[str, float]) -> str:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return "; ".join(
        f"{FAMILY_BY_ID[family_id].label}={score:.1f}"
        for family_id, score in ordered[:6]
    )


def _evidence_text(
    evidences: Mapping[str, FamilyEvidence], family_ids: Iterable[str]
) -> tuple[str, str]:
    chosen = [evidences[family_id] for family_id in family_ids if family_id in evidences]
    if not chosen:
        return "", "N/D"
    text = " | ".join(
        f"{item.document_label} p. {item.page} "
        f"[{FAMILY_BY_ID[item.family_id].label}]: {item.snippet}"
        for item in chosen[:3]
    )
    pages = ", ".join(
        f"{item.document_label} p. {item.page}" for item in chosen[:3]
    )
    return text[:4000], pages


def decide(
    documents: Sequence[tuple[str, Sequence[str]]],
    *,
    official_type: str,
    np_prior: bool = False,
    readable: bool = True,
) -> Decision:
    """Turn the scored evidence into one of the four decision statuses."""

    if not readable or not documents:
        return Decision(
            decision_status="pendente",
            tipo="",
            foco="",
            tabela_ii="",
            n1="",
            n2="",
            confidence="baixa",
            rationale=(
                "Nenhum documento com camada de texto foi obtido; a leitura "
                "documental não pôde ser concluída."
            ),
            evidence="",
            pages="N/D",
            family_scores="",
            limitation=(
                "Regulamento ausente no FundosNet ou PDF sem texto extraível."
            ),
            reason="Reprocessar quando houver documento legível.",
        )

    perimeter = detect_perimeter(documents)
    raw_scores = score_families(documents, np_prior=np_prior)
    scores = {
        family_id: evidence.score for family_id, evidence in raw_scores.items()
    }
    effective = _apply_dominance(scores)
    ranked = sorted(effective.items(), key=lambda item: item[1], reverse=True)
    score_text = _format_scores(effective)
    cedent = find_cedent_evidence(documents)

    if perimeter:
        evidence_text, pages = _evidence_text(raw_scores, [item[0] for item in ranked])
        return Decision(
            decision_status="rejeitado",
            tipo="",
            foco="",
            tabela_ii="",
            n1="",
            n2="",
            confidence="media",
            rationale=(
                "A hipótese de reclassificação de FIDC é incorreta para este "
                "CNPJ: o documento descreve um fundo de investimento financeiro."
            ),
            evidence=evidence_text,
            pages=pages,
            family_scores=score_text,
            limitation=perimeter,
            reason=perimeter,
        )

    if not ranked or ranked[0][1] < MIN_DECISIVE_SCORE:
        evidence_text, pages = _evidence_text(
            raw_scores, [item[0] for item in ranked]
        )
        return Decision(
            decision_status="em_revisao",
            tipo=official_type or "Outros",
            foco=MULTICARTEIRA_BY_TYPE.get(
                official_type or "Outros", MULTICARTEIRA_BY_TYPE["Outros"]
            )[0],
            tabela_ii="N/D",
            n1="Multissetorial / Outros",
            n2="Multicarteira outros",
            confidence="baixa",
            rationale=(
                "O documento foi lido integralmente, mas nenhuma família de "
                "direitos creditórios atingiu evidência suficiente na definição "
                "do lastro, na política de investimento ou nos critérios de "
                "elegibilidade."
            ),
            evidence=evidence_text,
            pages=pages,
            family_scores=score_text,
            limitation=(
                "O regulamento não individualiza o lastro em cláusula decisiva."
            ),
            reason=(
                "Confirmar o lastro predominante com prospecto, suplemento ou "
                "anexo descritivo antes de reclassificar."
            ),
        )

    leader_id, leader_score = ranked[0]
    competing = [
        family_id
        for family_id, score in ranked
        if score >= COMPETING_FAMILY_SHARE * leader_score
    ]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
    ratio = leader_score / runner_score if runner_score else float("inf")
    evidence_text, pages = _evidence_text(raw_scores, competing)
    if cedent:
        evidence_text = f"{evidence_text} || CEDENTE/ORIGINADOR: {cedent}"[:4600]

    if len(competing) >= MULTICARTEIRA_FAMILY_COUNT:
        type_scores: dict[str, float] = {}
        for family_id in competing:
            family = FAMILY_BY_ID[family_id]
            type_scores[family.tipo] = type_scores.get(family.tipo, 0.0) + effective[
                family_id
            ]
        total = sum(type_scores.values())
        dominant_type, dominant_score = max(
            type_scores.items(), key=lambda item: item[1]
        )
        if total and dominant_score / total >= MULTICARTEIRA_TYPE_SHARE:
            foco, tabela_ii, n1, n2 = MULTICARTEIRA_BY_TYPE[dominant_type]
            return Decision(
                decision_status="aprovado",
                tipo=dominant_type,
                foco=foco,
                tabela_ii=tabela_ii,
                n1=n1,
                n2=n2,
                confidence="media",
                rationale=(
                    f"O mandato enumera {len(competing)} famílias de direitos "
                    f"creditórios, mas {dominant_score / total:.0%} da evidência "
                    f"pertence ao tipo {dominant_type}; a leitura multicarteira "
                    "é fechada dentro desse tipo."
                ),
                evidence=evidence_text,
                pages=pages,
                family_scores=score_text,
                limitation=(
                    "Mandato multicarteira: a materialidade por família depende "
                    "da carteira observada em cada competência."
                ),
                reason="",
            )
        foco, tabela_ii, n1, n2 = MULTICARTEIRA_BY_TYPE["Outros"]
        return Decision(
            decision_status="aprovado",
            tipo="Outros",
            foco=foco,
            tabela_ii=tabela_ii,
            n1=n1,
            n2=n2,
            confidence="media",
            rationale=(
                f"O mandato enumera {len(competing)} famílias de direitos "
                "creditórios sem predominância de um único tipo ANBIMA; a "
                "classificação multicarteira Outros é a leitura correta."
            ),
            evidence=evidence_text,
            pages=pages,
            family_scores=score_text,
            limitation=(
                "Mandato multicarteira sem predominância mensurável no documento."
            ),
            reason="",
        )

    family = FAMILY_BY_ID[leader_id]
    if ratio >= DOMINANT_RATIO and leader_score >= APPROVAL_MIN_SCORE:
        confidence = (
            "alta"
            if ratio >= HIGH_CONFIDENCE_RATIO and leader_score >= HIGH_CONFIDENCE_SCORE
            else "media"
        )
        return Decision(
            decision_status="aprovado",
            tipo=family.tipo,
            foco=family.foco,
            tabela_ii=family.tabela_ii,
            n1=family.n1,
            n2=family.n2,
            confidence=confidence,
            rationale=(
                f"A família {family.label} domina a definição do lastro "
                f"(escore {leader_score:.1f} contra {runner_score:.1f} da "
                "família seguinte), com as ocorrências concentradas em "
                "definições, política de investimento e critérios de "
                "elegibilidade."
            ),
            evidence=evidence_text,
            pages=pages,
            family_scores=score_text,
            limitation=(
                "A conclusão descreve o mandato permitido pelo regulamento; a "
                "materialidade efetiva depende da carteira da competência."
            ),
            reason="",
        )

    return Decision(
        decision_status="em_revisao",
        tipo=family.tipo,
        foco=family.foco,
        tabela_ii=family.tabela_ii,
        n1=family.n1,
        n2=family.n2,
        confidence="baixa",
        rationale=(
            f"A família {family.label} lidera a evidência documental "
            f"(escore {leader_score:.1f}), mas a família seguinte permanece "
            f"próxima ({runner_score:.1f}); a predominância não é conclusiva."
        ),
        evidence=evidence_text,
        pages=pages,
        family_scores=score_text,
        limitation=(
            "Duas famílias concorrentes com evidência comparável no mesmo "
            "regulamento."
        ),
        reason=(
            "Medir a materialidade por família na carteira antes de fechar a "
            "reclassificação."
        ),
    )
