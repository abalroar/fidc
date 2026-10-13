"""Comparable documentary rows: one catalog for every fund and every basket.

Each row is answered per fund by a short, typed fact read from the documents.
Patterns only locate candidate passages for the reader; they never decide the
answer. ``module`` restricts a row to fund types where it is meaningful.
"""
from __future__ import annotations

from dataclasses import dataclass

FUND_TYPES = (
    "Consignado público", "Consignado privado", "FGTS", "Cartão/adquirência", "Agro/FIAGRO", "FIC",
    "Veículos", "Crédito pessoal", "Duplicatas/multicedente", "Imobiliário", "Precatórios", "Cash sweep",
    "Educacional", "Energia solar", "Outros",
)


@dataclass(frozen=True)
class Row:
    id: str
    section: str
    label: str
    definition: str
    unit: str = "text"          # pct | brl | days | months | text | entity | enum | list
    module: str = "core"        # core or one of MODULE_TYPES keys
    ime: str = ""               # IME monitoring key (see services.documentary_facts)
    numeric: bool = False       # peers use numeric value when True
    patterns: tuple[str, ...] = ()
    docs: str = "regulation"    # regulation | issuance | any


SECTIONS = (
    "Recebíveis e originação",
    "Elegibilidade e concentração",
    "Estrutura e proteção",
    "Eventos e fluxo",
    "Custos e remuneração",
    "Prestadores e governança",
)

# Fund types for which a module applies.
MODULE_TYPES = {
    "consignado": {"Consignado público", "Consignado privado", "FGTS"},
    "cartao": {"Cartão/adquirência"},
    "agro": {"Agro/FIAGRO"},
    "garantia_real": {"Veículos", "Imobiliário", "Energia solar"},
    "multicedente": {"Duplicatas/multicedente"},
    "fic": {"FIC"},
}

ROWS: tuple[Row, ...] = (
    # Recebíveis e originação
    Row("fund_type", SECTIONS[0], "Tipo de fundo", "Classificação do fundo pelo lastro e pela estrutura.", "enum"),
    Row("receivables", SECTIONS[0], "Recebível", "Instrumento adquirido e sua origem econômica.", "text",
        patterns=(r"direitos creditorios (elegiveis )?(serao|sao|consistem|decorrentes|representados|originados|oriundos)",
                  r"politica de investimento", r"natureza dos direitos creditorios", r"[“\"]direitos creditorios[”\"]")),
    Row("originator", SECTIONS[0], "Originador / concedente", "Quem concede o crédito na origem.", "entity",
        patterns=(r"[“\"]originador(a|es|as)?[”\"]", r"originad[oa]s? (por|pel[oa]|no ambito)", r"concedid[oa]s? (por|pel[oa])", r"\boriginador")),
    Row("assignor", SECTIONS[0], "Cedente / endossante", "Quem cede ou endossa os créditos à classe.", "entity",
        patterns=(r"[“\"]cedentes?[”\"]", r"[“\"]endossantes?[”\"]", r"\bcedentes? (significa|sera|e a|e o|sao)", r"\bendossantes? (significa|sera|e a|e o|sao)")),
    Row("debtor", SECTIONS[0], "Devedor final", "Perfil de quem paga o crédito.", "text",
        patterns=(r"[“\"]devedor(es)?[”\"]", r"[“\"]sacad[oa]s?[”\"]", r"devedores? (sao|serao|significa)", r"sacados? (sao|serao|significa)")),
    Row("recourse", SECTIONS[0], "Coobrigação e recompra", "Se o cedente responde pelo crédito e como recompra.", "text",
        patterns=(r"coobrigacao", r"direito de regresso", r"recompra (compulsoria|obrigatoria)", r"resolucao da cessao", r"opcao de venda")),
    # Elegibilidade e concentração
    Row("eligibility", SECTIONS[1], "Elegibilidade (diferenciais)", "Condições objetivas que distinguem os créditos aceitos.", "list",
        patterns=(r"criterios de elegibilidade", r"condicoes de cessao", r"condicoes de aquisicao")),
    Row("debtor_limit", SECTIONS[1], "Limite por devedor", "Exposição máxima a um mesmo devedor ou grupo.", "pct", numeric=True,
        patterns=(r"mesmo devedor", r"por devedor", r"devedor.{0,60}(nao podera|limitad|exceder|superior)", r"mesmo grupo economico")),
    Row("assignor_limit", SECTIONS[1], "Limite por cedente", "Exposição máxima a um mesmo cedente ou originador.", "pct", numeric=True,
        patterns=(r"mesmo cedente", r"por cedente", r"mesmo endossante", r"mesmo originador")),
    Row("term_max", SECTIONS[1], "Prazo máximo do crédito", "Prazo máximo individual ou médio dos créditos.", "text",
        patterns=(r"prazo (maximo|de vencimento|remanescente)", r"prazo medio", r"vencimento final")),
    Row("allocation", SECTIONS[1], "Alocação mínima em DC", "Mínimo do PL em direitos creditórios.", "pct", ime="allocation", numeric=True,
        patterns=(r"no minimo.{0,80}(patrimonio liquido|pl).{0,120}direitos creditorios", r"direitos creditorios.{0,120}no minimo",
                  r"alocacao minima", r"(cinquenta|sessenta e sete|cinquenta e um)")),
    # Estrutura e proteção
    Row("quota_structure", SECTIONS[2], "Estrutura de cotas", "Camadas de cotas e preferência entre elas.", "enum",
        patterns=(r"subclasses?", r"cotas seniores", r"cotas subordinadas (mezanino|junior)", r"classe unica", r"pari passu")),
    Row("sub_senior", SECTIONS[2], "Subordinação mínima da sênior", "Colchão mínimo abaixo da sênior, em % do PL.", "pct", ime="sub_senior", numeric=True,
        patterns=(r"indice de subordinacao", r"razao de subordinacao", r"relacao minima", r"subordinacao minima",
                  r"cotas subordinadas.{0,100}(no minimo|minimo de|equivalente)")),
    Row("sub_mezz", SECTIONS[2], "Subordinação mínima da mezanino", "Colchão mínimo abaixo da mezanino, em % do PL.", "pct", ime="sub_mezz", numeric=True,
        patterns=(r"subordinacao mezanino", r"razao de subordinacao mezanino", r"cotas (subordinadas )?mezanino.{0,100}(no minimo|minimo)")),
    Row("sub_check", SECTIONS[2], "Apuração · cura", "Frequência de apuração e prazo para reenquadrar.", "text",
        patterns=(r"apurad[oa] (diariamente|mensalmente|todo dia)", r"desenquadramento.{0,120}(dias uteis|dias)", r"reenquadr", r"prazo de cura")),
    Row("reserve", SECTIONS[2], "Reserva de caixa", "Reserva de liquidez, despesas ou amortização.", "text",
        patterns=(r"reserva de (caixa|liquidez|despesas|encargos|amortizacao|pagamento)", r"[“\"]reserva")),
    Row("pdd", SECTIONS[2], "PDD", "Critério de provisão e curva por atraso, quando houver.", "text",
        patterns=(r"provisao para (devedores duvidosos|perdas)", r"\bpdd\b", r"perdas esperadas", r"provisionamento", r"dias de atraso")),
    # Eventos e fluxo
    Row("eval_triggers", SECTIONS[3], "Gatilhos de avaliação", "Eventos numéricos que suspendem compras ou levam à AGC.", "text",
        patterns=(r"eventos? de avaliacao", r"evento de avaliacao")),
    Row("liquidation", SECTIONS[3], "Eventos de liquidação", "Hipóteses de liquidação antecipada.", "text",
        patterns=(r"eventos? de liquidacao", r"liquidacao antecipada")),
    Row("revolving", SECTIONS[3], "Revolvência", "Período em que recebimentos compram novos créditos.", "text",
        patterns=(r"periodo de investimento", r"revolvencia", r"periodo de revolv", r"reinvest", r"novas aquisicoes")),
    Row("amortization", SECTIONS[3], "Amortização das cotas", "Regime e calendário de amortização.", "text",
        patterns=(r"amortizac(ao|oes) (das|de) cotas", r"regime (sequencial|pro.rata)", r"amortizacao sequencial", r"cronograma de amortizacao", r"carencia")),
    # Custos e remuneração
    Row("admin_fee", SECTIONS[4], "Taxa de administração", "Percentual, base e mínimo mensal.", "text",
        patterns=(r"taxa de administracao",)),
    Row("mgmt_fee", SECTIONS[4], "Taxa de gestão", "Percentual, base e mínimo mensal.", "text",
        patterns=(r"taxa de gestao",)),
    Row("perf_fee", SECTIONS[4], "Taxa de performance", "Benchmark e percentual sobre o excedente.", "text",
        patterns=(r"taxa de performance",)),
    Row("target_senior", SECTIONS[4], "Remuneração-alvo sênior", "Meta de rentabilidade da cota sênior.", "text", docs="issuance",
        patterns=(r"meta de (rentabilidade|remuneracao)", r"benchmark", r"rentabilidade alvo", r"remuneracao.{0,40}senior",
                  r"(di|cdi) ?\+", r"\+ ?\d+[,.]\d+ ?%")),
    Row("target_mezz", SECTIONS[4], "Remuneração-alvo mezanino", "Meta de rentabilidade da cota mezanino.", "text", docs="issuance",
        patterns=(r"mezanino.{0,160}(meta|benchmark|rentabilidade|remuneracao)",)),
    # Prestadores e governança
    Row("administrator", SECTIONS[5], "Administrador", "Administrador fiduciário.", "entity",
        patterns=(r"[“\"]administrador(a)?[”\"]\s*:", r"administrador(a)?[”\"]?,? (e|sera|significa)", r"administracao fiduciaria", r"\badministrador(a)? fiduciari")),
    Row("manager", SECTIONS[5], "Gestor", "Gestor da carteira.", "entity",
        patterns=(r"[“\"]gestor(a)?[”\"]\s*:", r"\bgestor(a)?[”\"]?,? (e|sera|significa)", r"gestao da carteira", r"\bgestora?\b")),
    Row("custodian", SECTIONS[5], "Custodiante", "Custodiante dos direitos creditórios.", "entity",
        patterns=(r"[“\"]custodiante[”\"]\s*:", r"\bcustodiante\b")),
    Row("servicer", SECTIONS[5], "Agente de cobrança", "Quem cobra os créditos inadimplidos.", "entity",
        patterns=(r"agente de cobranca", r"agente de (retencao|recebimento)", r"cobranca (ordinaria|extraordinaria|judicial)")),
    Row("investors", SECTIONS[5], "Público-alvo", "Investidores autorizados.", "enum",
        patterns=(r"publico.alvo", r"investidores (profissionais|qualificados)")),
    Row("duration", SECTIONS[5], "Prazo da classe", "Prazo de duração e forma de condomínio.", "text",
        patterns=(r"prazo de duracao", r"prazo indeterminado", r"condominio (fechado|aberto)")),
    # Módulos por tipo
    Row("payroll", SECTIONS[0], "Convênio e averbação", "Convênio, órgão e mecanismo de desconto.", "text", module="consignado",
        patterns=(r"convenio", r"averbac", r"consignante", r"dataprev", r"margem consignavel", r"saque.aniversario")),
    Row("age_limit", SECTIONS[1], "Idade do devedor", "Idade máxima do devedor na emissão ou no vencimento.", "text", module="consignado",
        patterns=(r"\bidade\b", r"anos.{0,30}(meses|dias)")),
    Row("installment_min", SECTIONS[1], "Parcela mínima", "Valor mínimo da parcela ou do crédito.", "brl", module="consignado", numeric=True,
        patterns=(r"parcela.{0,60}(minim|superior a|inferior a|r\$)", r"valor minimo")),
    Row("card_receivables", SECTIONS[0], "URs e arranjos", "Unidades de recebíveis, arranjos e registradora.", "text", module="cartao",
        patterns=(r"unidades? de recebiveis", r"\burs?\b", r"registradora", r"arranjos? de pagamento", r"subcredenciador")),
    Row("card_lock", SECTIONS[1], "Trava e domicílio", "Mecanismo que direciona o fluxo à classe.", "text", module="cartao",
        patterns=(r"trava", r"domicilio", r"conta vinculada", r"conta centralizadora", r"conta escrow")),
    Row("dilution", SECTIONS[2], "Diluição e chargeback", "Tratamento de cancelamentos, chargebacks e devoluções.", "text", module="cartao",
        patterns=(r"diluicao", r"chargeback", r"cancelamento", r"contestac")),
    Row("agro_backing", SECTIONS[0], "Lastro agro", "CPR, CRA, CDCA ou outros títulos do agronegócio.", "text", module="agro",
        patterns=(r"\bcpr\b", r"cedula de produto rural", r"\bcra\b", r"\bcdca\b", r"certificado de recebiveis do agronegocio")),
    Row("collateral", SECTIONS[2], "Garantias", "Garantias dos créditos e sua constituição.", "text", module="agro",
        patterns=(r"garantias?", r"penhor", r"alienacao fiduciaria", r"\baval\b", r"cessao fiduciaria")),
    Row("real_collateral", SECTIONS[2], "Garantia real e LTV", "Bem dado em garantia e relação crédito/garantia.", "text", module="garantia_real",
        patterns=(r"alienacao fiduciaria", r"\bltv\b", r"loan to value", r"veiculo", r"imovel", r"hipoteca")),
    Row("sacado_limit", SECTIONS[1], "Limite por sacado", "Exposição máxima a um mesmo sacado.", "pct", module="multicedente", numeric=True,
        patterns=(r"mesmo sacado", r"por sacado", r"sacado.{0,60}(nao podera|limitad|exceder)")),
    Row("investee", SECTIONS[0], "Classe investida", "Classe ou fundo investido pelo FIC e subclasse adquirida.", "entity", module="fic",
        patterns=(r"classe investida", r"fundo investido", r"cotas (do|da|de) .{0,80}(fidc|fundo de investimento em direitos)")),
    Row("investee_share", SECTIONS[1], "Alocação na investida", "Mínimo do PL em cotas da classe investida.", "pct", module="fic", numeric=True,
        patterns=(r"(no minimo|ate) .{0,30}%.{0,120}cotas", r"cotas da classe investida.{0,80}%")),
)

ROW_BY_ID = {row.id: row for row in ROWS}


def rows_for_types(fund_types: set[str]) -> tuple[Row, ...]:
    """Core rows plus every module present among the given fund types."""
    modules = {module for module, types in MODULE_TYPES.items() if types & fund_types}
    return tuple(row for row in ROWS if row.module == "core" or row.module in modules)


def row_applies(row: Row, fund_type: str) -> bool:
    return row.module == "core" or fund_type in MODULE_TYPES.get(row.module, set())
