"""Reject primary passages that answer a different credit question.

This is a relevance gate, not a legal interpretation or numeric extractor. A
rejected passage leaves the question unresolved. It never creates N/A or a limit.
"""
from __future__ import annotations

import re
import unicodedata
import hashlib
from pathlib import Path
from typing import Any

from services.documentary_criteria_catalog import CRITERIA

VALIDATOR_REVISION = 6


def validation_fingerprint() -> str:
    """Fingerprint executable guards and the criterion identity catalog for resume."""
    digest = hashlib.sha256(Path(__file__).read_bytes())
    digest.update(repr(CRITERIA).encode('utf-8'))
    return digest.hexdigest()


def _fold(text: object) -> str:
    plain = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(char for char in plain if not unicodedata.combining(char)).casefold().split())


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text))


def _result(valid: bool, reason: str) -> dict[str, Any]:
    return {"valid": valid, "reason": reason}


_WORDS = {row[0]: tuple(_fold(word) for word in row[3]) for row in CRITERIA}
_OPERATIVE = r"devera|deverao|deve(?:m)?\b|sera(?:o)?\b|pode(?:ra|rao)?\b|vedad|permitid|corresponde|consiste|representad|originad|decorrent|destinad|nao (?:ha|havera)|nao ser|fara jus|nao fara jus|obrigad|assegurad|incid|cobrad|pag[ao]|constitui|constituem|limitad|calculad|adquirid|mantid|alocad|exig|fixad"
_DETAIL = r"\d\s*%|r\$|\d{1,2}/\d{1,2}/\d{4}|mensal|trimestral|semestral|anual|diaria|dias uteis|dias corridos|pro rata|pro-rata|sequencial|parcela unica|valor patrimonial|nao (?:ha|havera)|nao ser|nao fara jus|vedad|proibid|dispensad"
_CREDIT_TYPES = r"\bccbs?\b|\bcccs?\b|\bcprs?\b|duplicata|cedula|emprestimo|financiamento|consignad|cartao|saque.aniversario|fgts|servicos educacionais|precatorio|credito (?:judicial|imobiliario)|direitos creditorios do agronegocio|recebiveis (?:comerciais|de cartao)|venda(?: e compra)? (?:mercantil|a prazo|de produto)|prestacao de servicos|credito (?:pessoal|estudantil)|notas? (?:comerciais?|promissoria)|contratos? de (?:credito|emprestimo|financiamento|arrendamento|prestacao|venda|locacao|consumo)|debenture"
_ENTITY = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|(?<!\d)\d{14}(?!\d)|banco (?!central|custodiante|comercial|multiplo\b|depositario|sacado|devedor|registrador|correspondente)[a-z]+(?: [a-z]+)?|[a-z]+(?: [a-z]+){0,3} (?:dtvm|distribuidora|ltda\b|s\.a\b|s/a\b)"
_GOVERNANCE = r"assembleia|quorum|maioria dos votos|convocacao|deliberar|deliberacoes|compet(?:e|encia)|alterar o regulamento"


def _explicit_investment_floor(text: str) -> bool:
    """Keep a salary denominator from borrowing an unrelated investment duty."""
    for sentence in re.split(r"(?<!\d)\.(?!\d)|[;!?]", text):
        duty = r"(?:fundo|classe).{0,90}(?:(?:devera|deve\b|tera de|tem de).{0,60}(?:manter|aplicar|alocar|investir)|mantera|aplicara|alocara|investira)"
        if (_has(sentence, duty)
                and _has(sentence, r"direitos creditorios|\bdc\b|creditos elegiveis|recebiveis")
                and _has(sentence, r"patrimonio liquido|\bpl\b")
                and _has(sentence, r"minim|pelo menos|nao inferior|parcela minima|alocacao minima")
                and _has(sentence, r"\d\s*%|cinquenta|sessenta e sete")):
            return True
    return False


def _explicit_credit_nature(text: str) -> bool:
    """A file, report or endoso title does not identify the underlying credit."""
    descriptions = (
        r"(?:direitos creditorios|creditos|recebiveis).{0,100}(?:representad|originad|decorrent|oriund|provenient|constitu[ií]d|consist).{0,180}(?:" + _CREDIT_TYPES + r")",
        r"(?:\bccbs?\b|cedulas? de credito bancario).{0,100}(?:represent|originad|decorrent|oriund|provenient).{0,180}(?:emprestimo|financiamento|consignad|credito pessoal|capital de giro)",
        r"(?:fundo|classe).{0,90}(?:adquirira|devera adquirir|podera adquirir|adquire).{0,100}(?:emprestimos? consignad|financiamentos? estudant|recebiveis de cartao|creditos imobiliari)",
    )
    return any(_has(text, pattern) for pattern in descriptions)


def validate_primary_clause(criterion_id: str, text: str) -> dict[str, Any]:
    """Validate whether an intact passage substantively addresses its criterion."""
    criterion = str(criterion_id)
    value = _fold(text)
    if criterion not in _WORDS:
        return _result(False, "Critério sem regra de validação de conteúdo nesta versão.")
    if not value:
        return _result(False, "Trecho vazio.")
    if len(re.findall(r"\[\s*(?:●|•|\.{2,}|x|a preencher)\s*\]", str(text), flags=re.I)) >= 2:
        return _result(False, "O trecho pertence a formulário ou suplemento com campos ainda sem preenchimento.")
    if _has(value, r"anexo de cada classe.{0,90}dispoe.{0,100}(?:respectivas|respectivos)"):
        return _result(False, "A cláusula enumera assuntos de anexos sem transcrever suas regras.")
    if criterion in {"quota_classes", "perimeter"} and _has(value, r"classe (?:de cotas )?(?:unica|unica de cotas)|subclasses?[: ]+(?:senior|seniores|mezanino|subordinad)"):
        return _result(True, "O trecho declara a classe ou composição das subclasses.")
    if len(re.findall(r"\.{4,}|…{2,}", str(text))) >= 2 or _has(value, r"^(?:sumario|indice geral)\b"):
        return _result(False, "O trecho é um sumário de títulos e páginas.")
    if len(value) < 35 and not _has(value, _OPERATIVE + "|" + _DETAIL):
        return _result(False, "O trecho contém somente um título ou rótulo.")
    if _has(value, r"(?:conforme|definid[ao]|previst[ao]|estabelecid[ao]).{0,60}(?:anexo|apendice|suplemento|capitulo|contrato)") and not _has(value, _DETAIL + "|" + _OPERATIVE):
        return _result(False, "A cláusula remete a outro documento sem transcrever uma regra específica.")

    if criterion in {"admin_fee", "management_fee", "performance_fee", "custody_fee"}:
        keyword = {"admin_fee": r"taxa de administracao", "management_fee": r"taxa de gestao",
                   "performance_fee": r"taxa de performance|taxa de desempenho", "custody_fee": r"taxa de (?:custodia|escrituracao)|remuneracao do custodiante"}[criterion]
        if not _has(value, keyword):
            return _result(False, "O trecho não identifica a taxa correspondente ao critério.")
        denial = r"nao (?:ha|havera|possui)|nao ser[a-z ]{0,30}cobrad|nao fara jus|sem (?:cobranca de |)taxa de performance|vedad[a-z ]{0,50}cobranca"
        charge = r"fara jus|devida|(?:taxa|remuneracao).{0,55}(?:correspondente|correspondera|equivalente)|sera cobrada|pagara|incidira|calculada|remuneracao.{0,70}(?:r\$|%)"
        if _has(value, _GOVERNANCE) and not _has(value, denial + "|" + charge):
            return _result(False, "A menção à taxa trata de competência ou quórum para aprovar alterações.")
        if _has(value, denial):
            return _result(True, "A cláusula estabelece expressamente a ausência de cobrança da taxa.")
        if _has(value, r"fundos? investidores?.{0,100}(?:acordo|remuneracao)|montantes devidos a fundos? investidores?") and not _has(value, r"(?:fundo|classe) pagara|gestor[ao]?.{0,40}fara jus"):
            return _result(False, "O trecho trata de repasse ou acordo com fundos investidores.")
        if not _has(value, charge) or not _has(value, r"\d|benchmark|exced|valorizacao|patrimonio|di\b|cdi|ipca|igp|rentabilidade"):
            return _result(False, "A menção à taxa não especifica cobrança, remuneração ou regra de cálculo.")
        return _result(True, "A cláusula apresenta uma regra de cobrança ou cálculo da taxa.")

    if criterion == "allocation":
        if _has(value, r"remunerac|remunerar|(?:taxa|comissao).{0,60}(?:administracao|gestao|custodia|retencao|cobranca)|servicos.{0,60}(?:retencao|cobranca)") and not _explicit_investment_floor(value):
            return _result(False, "O percentual remunera um prestador; o PL alocado é base da cobrança, sem obrigação explícita de investimento na mesma cláusula.")
        if _has(value, r"fundos? (?:que|de investimento.{0,80}que) (?:apli|inv)|(?:considera|entende).{0,50}fundos? de investimento") and not _has(value, r"(?:fundo|classe).{0,60}(?:devera|tera|mantera)"):
            return _result(False, "O percentual descreve a categoria de um fundo ou ativo investido.")
        if not _has(value, r"direitos creditorios|\bdc\b|creditos elegiveis|recebiveis") or not _has(value, r"patrimonio liquido|\bpl\b"):
            return _result(False, "A cláusula não estabelece alocação em direitos creditórios com base no patrimônio líquido.")
        if not _has(value, r"\d\s*%|cinquenta|sessenta e sete|parcela minima|alocacao minima"):
            return _result(False, "O trecho não apresenta piso de alocação.")
        if _has(value, r"(?:garantia|saldo devedor|cotas emitidas|convocacao|votos|taxa de administracao)") and not _has(value, r"alocacao minima|(?:fundo|classe).{0,110}(?:devera|tera|mantera|deve)|patrimonio liquido.{0,70}(?:mantid|alocad|aplicad|representad)"):
            return _result(False, "O percentual se refere a garantia, votação, taxa ou outro denominador.")
        if not _has(value, r"alocacao minima|parcela minima|minimo|superior a|pelo menos|devera.{0,100}(?:manter|alocar|investir|aplicar)"):
            return _result(False, "O trecho não especifica obrigação mínima de alocação da classe.")
        return _result(True, "O trecho apresenta piso, ativo e base de alocação.")

    if criterion == "receivables":
        if _has(value, r"(?:receber|preparar|fornecer|enviar|elaborar).{0,70}(?:o |os |um |uma |)(?:arquivo (?:de )?(?:bloqueio|financiamento)|relatorio de performance|termo de endosso)|obrigacoes do (?:gestor|agente).{0,180}(?:arquivo|relatorio)") and not _explicit_credit_nature(value):
            return _result(False, "O trecho lista tarefas de recebimento de arquivos, relatórios ou endosso, sem descrever a modalidade e origem dos créditos.")
        if _has(value, r"ativos? recuperad|da recuperacao|excussao|adjudicad|dados em pagamento") and not _has(value, r"direitos creditorios.{0,80}(?:originad|decorrent|representad)"):
            return _result(False, "O trecho trata de ativos recuperados após cobrança ou execução.")
        if not _has(value, _CREDIT_TYPES + r"|cotas.{0,100}(?:classe|fundo) investid"):
            return _result(False, "O trecho descreve a política genericamente, sem caracterizar o crédito adquirido.")
        if _has(value, r"apos a originacao|ofertar os direitos creditorios|procedimento.{0,60}(?:cessao|aquisicao)") and not _has(value, r"\bccbs?\b|\bcccs?\b|\bcprs?\b|duplicata|cedula|consignad|cartao|fgts|educacion|estudant|imobiliari|credito pessoal|capital de giro|venda(?: e compra)? (?:mercantil|a prazo|de produto)|prestacao de servicos|agroindustr|agronegocio|cotas.{0,100}(?:classe|fundo) investid"):
            return _result(False, "O trecho descreve oferta, cessão ou aquisição de crédito sem identificar sua modalidade e origem.")
        if _has(value, r"amortizacao.{0,100}(?:extraordinaria|seniores)|alteracoes? dos criterios|deliberacoes?.{0,100}politica de investimento") and not _has(value, r"direitos creditorios.{0,70}(?:originad|decorrent|representad)|aquisicao.{0,80}(?:" + _CREDIT_TYPES + r")"):
            return _result(False, "A cláusula regula amortização ou governança, sem descrever a origem do lastro.")
        return _result(True, "O trecho caracteriza instrumentos, origem ou atividade geradora dos recebíveis.")

    if criterion == "providers":
        roles = r"administrador(?:a)?|administrad[ao]|administracao(?: fiduciaria)?|gestor(?:a)?|gerid[ao]|gestao|custodiante|custodia"
        if not _has(value, roles):
            return _result(False, "O trecho não identifica o papel de administrador, gestor ou custodiante.")
        if _has(value[:400], r"eventos? de (?:avaliacao|liquidacao)|fatores de risco"):
            return _result(False, "O trecho cita prestadores em gatilhos ou riscos, sem identificar sua contratação e papel.")
        affiliation = r"(?:^|;\s*)(?:\d+[.)]\s*)?(?:administrador(?:a)?|gestor(?:a)?|custodiante)\s*[:\-]|[“\"'](?:administrador(?:a)?|gestor(?:a)?|gestor ou gestora|custodiante)[”\"']|(?:fundo|classe).{0,70}(?:administrad[ao]|gerid[ao]) (?:pela|pelo|por)|(?:administracao|gestao|custodia).{0,65}(?:exercida|realizada)|(?:na qualidade de|como) (?:administrador(?:a)?|gestor(?:a)?|custodiante) (?:do fundo|da classe)"
        table_role = r"^[“\"']?(?:administrador(?:a)?|gestor(?:a)?|gestor ou|custodiante|cogestor(?:a)?)[”\"']?\s+(?!podera|devera|sera|nao|calcul|tem |compete |pode |e responsavel|fica ).{0,140}(?:" + _ENTITY + r")"
        named_contract = r"como gestor(?:a)? (?:da carteira|do fundo)|representad[ao] por sua (?:gestor[ao]|administrador[ao])|instituicao administrador[ao] (?:do|da)|na qualidade de administrador[ao] do [a-z]|(?:ambas|ambos) na qualidade de prestadores de servic.{0,20}essenciais (?:do|da)|\(\s*(?:administrad[ao] (?:pela|pelo|por)|administrador(?:a)?|gestor(?:a)?)(?:\s|\))|(?:administrador(?:a)?|gestor(?:a)?|custodiante) (?:do|da) [a-z]"
        affiliation = affiliation + "|" + table_role + "|" + named_contract
        # Layout tables may split a role label and its identity across columns.
        table_lines = any(_has(_fold(line), table_role) for line in str(text).splitlines())
        uppercase_role_label = bool(re.search(r"(?m)^\s*(?:ADMINISTRADOR(?:A)?|GESTOR(?:A)?|CUSTODIANTE)\b", str(text))) and _has(value, r"cnpj")
        if _has(value, r"prestadores.{0,80}pre.aprovad|prestadores.{0,100}poderao ser") and not _has(value, r"(?:fundo|classe).{0,70}(?:administrad[ao]|gerid[ao]) (?:pela|pelo|por)|(?:administracao|gestao|custodia).{0,65}(?:exercida|realizada)"):
            return _result(False, "O trecho lista prestadores possíveis ou pré-aprovados para substituição, sem identificar o prestador contratado.")
        if _has(value, r"agencia(?:s)? classificadora(?:s)? de risco|auditores independentes|revisao das demonstracoes") and not _has(value, affiliation):
            return _result(False, "O trecho lista auditoras ou agências possíveis; administrador e gestor são citados sem identificar seu próprio prestador.")
        if not _has(value, affiliation) and not table_lines and not uppercase_role_label:
            return _result(False, "Os nomes ou CNPJs citados não estão vinculados à contratação como administrador, gestor ou custodiante do fundo.")
        if not _has(value, r"(?:" + roles + r").{0,220}(?:" + _ENTITY + r")|(?:" + _ENTITY + r").{0,160}(?:administrad|gestor|gerid|custod)"):
            return _result(False, "O trecho descreve obrigações ou assembleias sem identificar o prestador.")
        return _result(True, "O trecho vincula um prestador identificado ao seu papel.")

    if criterion == "investee":
        if _has(value[:400], r"eventos? de (?:avaliacao|liquidacao)|fatores de risco"):
            return _result(False, "A referência a cotas aparece em eventos ou riscos próprios, sem definir investimento em outro fundo ou classe.")
        if not _has(value, r"fundos? investidos?|classes? investidas?|cotas.{0,120}(?:outros? fundos?|fundos? de investimento|fundos? de investimentos?|classes? de (?:fundos?|investimento)|\bfidcs?\b)"):
            return _result(False, "O trecho trata das cotas ou reservas do próprio fundo, sem identificar investimento em outro fundo ou classe.")
        if not _has(value, r"invest|aplic|adquir|aloc|mant|permitid|vedad|exclusiv|carteira|destinad|objetivo"):
            return _result(False, "A classe ou fundo citado não está vinculado à política de investimento ou à posição investida.")
        return _result(True, "O trecho define fundo ou classe investida, ou regra explícita de investimento em suas cotas.")

    if criterion == "rating":
        if _has(value, r"cotas.{0,70}(?:outros fundos|fundos investidos)|rating.{0,60}(?:devedor|sacado|emissor dos ativos|instituicoes financeiras)|classificacao.{0,60}ativos de liquidez") and not _has(value, r"cotas (?:seniores|subordinadas|mezanino).{0,100}(?:classific|rating|rebaix)|(?:classific|rating|rebaix).{0,120}cotas (?:seniores|subordinadas|mezanino)"):
            return _result(False, "A classificação citada pertence ao devedor, ativo de liquidez ou fundo investido.")
        if not _has(value, r"cotas|subclasse|serie|rating.{0,40}(?:fidc|fundo)"):
            return _result(False, "A menção à agência não estabelece rating ou política de classificação das cotas.")
        if not _has(value, r"(?:classific|rating|rebaix|downgrade|dispens|agencia|avaliad)"):
            return _result(False, "O trecho não apresenta classificação ou gatilho de rating.")
        if _has(value, r"(?:intermediacao|custos|despesas).{0,200}agencia") and not _has(value, r"(?:cotas|subclasse|serie).{0,100}(?:avaliad|classific|rating|rebaix)"):
            return _result(False, "O trecho lista despesas ou serviços que podem ser contratados.")
        return _result(True, "O trecho trata de classificação, dispensa ou downgrade das cotas.")

    if criterion == "guarantee":
        credit = r"direitos creditorios|creditos|recebiveis|\bccb|devedor|sacado|\bcpr"
        collateral = r"alienacao fiduciaria|cessao fiduciaria|garantias? reais?|hipoteca|\baval\b|fianca|penhor|devedor solidario"
        if _has(value, r"(?:garantia|onus|gravame|penhora).{0,250}(?:sem (?:o )?conhecimento|desconhecid)") and not _has(value, r"(?:creditos|direitos creditorios|ccbs?).{0,100}(?:deverao contar|deverao ter|garantidos por|contam com)"):
            return _result(False, "O trecho trata de ônus ou garantias preexistentes desconhecidos, sem constituir garantia em favor do fundo.")
        if _has(value, r"questionamento.{0,100}(?:validade|eficacia)|cessao.{0,80}(?:pode|podera).{0,30}questionad|eventos que podem afetar a cessao") and not _has(value, r"(?:creditos|direitos creditorios|ccbs?).{0,100}(?:deverao contar|deverao ter|garantidos por|contam com)"):
            return _result(False, "O trecho descreve risco de contestação da cessão, sem estabelecer garantia dos créditos.")
        if _has(value, r"nao contam.{0,160}(?:garantia|fgc)|nao (?:constitui|representa).{0,100}garantia de rentabilidade") and not _has(value, r"(?:sem|ausencia de|nao contam).{0,80}garantias? reais?.{0,40}(?:devedor|credito)|(?:" + credit + r").{0,100}(?:" + collateral + r")"):
            return _result(False, "O trecho contém aviso sobre investimento, rentabilidade ou FGC.")
        if _has(value, r"cotas subordinadas.{0,180}(?:alienacao fiduciaria|penhor|gravame)") and not _has(value, r"direitos creditorios.{0,100}(?:" + collateral + r")"):
            return _result(False, "A garantia mencionada recai sobre cotas, e não sobre os créditos da carteira.")
        if _has(value, r"(?:gestor|administrador).{0,120}contratacao.{0,180}agente de cobranca") and not _has(value, r"(?:ccb|creditos|direitos creditorios).{0,80}(?:deverao contar|garantidos|garantias)"):
            return _result(False, "O trecho lista prestadores que podem atuar na cobrança.")
        if not _has(value, credit) or not _has(value, collateral):
            return _result(False, "O trecho não especifica garantia dos créditos ou sua constituição.")
        if _has(value, r"risco.{0,80}(?:registro|validade|eficacia)|eventuais garantias|garantias que eventualmente") and not _has(value, r"devera|deverao|garantidos|garantida|devidamente constituida|registro.{0,80}(?:obrigatorio|devera)"):
            return _result(False, "O trecho descreve riscos ou garantias eventuais sem definir o lastro garantido.")
        return _result(True, "O trecho descreve garantia dos créditos, constituição ou ausência expressa de garantia real.")

    if criterion == "payments":
        if not _has(value, r"cotas|cotistas|senior|seniores|mezanino|subordinad|data de amortizacao|cash sweep"):
            return _result(False, "O vencimento ou pagamento citado pertence aos direitos creditórios ou despesas.")
        if _has(value, r"(?:chamada|integralizacao|subscricao).{0,80}(?:capital|cotas)|cotistas.{0,60}(?:integraliz|aport)") and not _has(value, r"amortiz|resgat|pagamento de juros|cash sweep"):
            return _result(False, "O trecho regula aporte ou integralização pelos cotistas.")
        if _has(value, r"provisao|devedores duvidosos|estudo.{0,100}risco de credito") and not _has(value, r"(?:cotas|cotistas).{0,80}(?:amortiz|juros|resgat)"):
            return _result(False, "O trecho trata de PDD ou avaliação do crédito, sem calendário das cotas.")
        if not _has(value, r"amortiz|resgat|pagamento de juros|vencimento|cash sweep"):
            return _result(False, "O trecho não descreve pagamento, amortização ou vencimento das cotas.")
        if _has(value, r"(?:suplemento|apendice).{0,80}(?:devera conter|seguintes informacoes)|devera conter.{0,200}cronograma"):
            return _result(False, "A cláusula enumera informações exigidas em suplemento ainda sem transcrever o calendário.")
        if not _has(value, _DETAIL + r"|fator de amortizacao|percentual de amortizacao|ordem de prioridade|recursos disponiveis|solicitacao.{0,60}amortiz"):
            return _result(False, "O trecho remete ao calendário ou vencimento, sem periodicidade ou mecânica específica.")
        return _result(True, "O trecho estabelece pagamento ou mecânica de amortização das cotas.")

    if criterion == "changes":
        if _has(value, r"poder[a-z ]{0,40}alterad|independentemente de.{0,80}assembleia|compete.{0,100}alterar") and not _has(value, r"(?:aprovou|deliberou|foi aprovad|resolvem aprovar|deliberaram|fica alterad|nova redacao|passa a vigorar|substitui|ficando)"):
            return _result(False, "A cláusula prevê hipóteses futuras de alteração, sem registrar uma alteração realizada.")
        if not _has(value, r"aprov|deliber|nova redacao|aditamento|alteracao.{0,80}(?:clausula|item|anexo|regulamento)|passa a vigorar"):
            return _result(False, "O trecho não documenta uma alteração material realizada.")
        return _result(True, "O trecho documenta uma alteração ou deliberação identificável.")

    if criterion == "collection_account":
        if _has(value[:400], r"eventos? de (?:avaliacao|liquidacao)|risco de|fatores de risco"):
            return _result(False, "A conta é citada em eventos ou riscos; o trecho não estabelece sua titularidade e fluxo operacional.")
        account = r"conta (?:vinculada|de arrecadacao|escrow|de cobranca)|conta de titularidade"
        mechanism = r"(?:recursos|valores|pagamentos|direitos creditorios).{0,180}(?:serao|sera|devera|deverao|depositad|creditad|transferid|pagos).{0,250}(?:" + account + r")|(?:" + account + r").{0,150}(?:sera|devera|mantida|aberta|movimentada|titularidade).{0,140}(?:titularidade|fundo|classe|cedente|deposit|transfer|movimenta)"
        if not _has(value, mechanism):
            return _result(False, "O trecho não define destino dos pagamentos, titularidade ou movimentação da conta.")
        return _result(True, "O trecho estabelece titularidade ou fluxo de recebimento e transferência da conta.")

    if criterion == "cross_default":
        default = r"inadimplemento cruzado|cross default|regime de administracao especial|raet|intervencao|recuperacao judicial|falencia|insolvencia|liquidacao extrajudicial"
        if not _has(value, default) or not _has(value, r"evento.{0,20}(?:avaliacao|liquidacao)|liquidacao antecipada|vencimento antecipado|inadimplemento cruzado|cross default"):
            return _result(False, "O trecho menciona insolvência ou cobrança como risco, sem gatilho contratual de avaliação ou vencimento.")

    if criterion == "replacement" and _has(value[:400], r"eventos? de (?:avaliacao|liquidacao)"):
        return _result(False, "A renúncia ou falta de substituição aparece como gatilho; a cláusula não descreve o procedimento de troca.")

    if criterion == "audit" and _has(value, r"encerramento|liquidacao da (?:classe|fundo)") and not _has(value, r"anual|exercicio social|demonstracoes.{0,70}(?:auditad|auditadas|exercicio)|opiniao|parecer.{0,40}(?:sem ressalva|com ressalva)"):
        return _result(False, "A auditoria citada se limita ao encerramento, sem auditoria periódica ou parecer das demonstrações do fundo.")

    if criterion == "debtor" and _has(value[:400], r"eventos? de (?:avaliacao|liquidacao)|fatores de risco"):
        return _result(False, "A menção ao devedor é incidental a eventos ou riscos, sem caracterizar quem compõe o lastro.")

    if criterion == "pdd" and not _has(value, r"\bpdd\b|devedores duvidosos|perdas (?:esperadas|estimadas)|provis.{0,80}(?:direitos? creditorios?|creditos?|atraso|inadimpl|perdas)|(?:direitos? creditorios?|creditos?).{0,120}provis|reducao.{0,25}valor (?:recuperavel|de recuperacao)"):
        return _result(False, "O provisionamento citado pertence a despesas ou cotas, sem metodologia de perdas dos créditos.")
    if criterion == "pdd":
        method = r"faixa.{0,35}atraso|matriz de (?:perdas|provisao)|curva de (?:perdas|provisao)|historico de perdas|perdas.{0,35}(?:probabilidade|expectativa|estimativa)|(?:atraso|inadimpl).{0,130}(?:\d\s*%|provisao|provisionad)|(?:calculad|reconhecid|provisionad|estimad).{0,150}(?:atraso|garantia|rating|probabilidade|valor presente|curva|perdas|devedor|creditos)|(?:valor recuperavel|valor de recuperacao).{0,90}(?:calcul|estim|avali)|contagio"
        if _has(value, r"(?:metodologia|metodo|politica|criterios?).{0,100}(?:descrita|descritos|prevista|nota explicativa)|(?:conforme|nos termos).{0,80}nota explicativa") and not _has(value, method):
            return _result(False, "A passagem remete a nota ou metodologia sem transcrever critérios de mensuração das perdas.")
        if _has(value, r"renegoci|desconto|recompra") and _has(value, r"limitad|no maximo|montante da (?:pdd|provisao)|valor da (?:pdd|provisao)") and not _has(value, method):
            return _result(False, "A PDD limita desconto ou renegociação; o trecho não descreve como a provisão é calculada.")
        if not _has(value, method) and not _has(value, r"nao (?:sera|devera|havera).{0,65}(?:provisao|provisionamento)|sem constituicao de provisao"):
            return _result(False, "O trecho informa saldo ou ocorrência de provisão, sem critérios de mensuração das perdas dos créditos.")

    if criterion in {"evaluation", "liquidation", "legacy_events"}:
        if _has(value, r"nao (?:ha|havera|existem|existirao).{0,45}eventos? de (?:avaliacao|liquidacao)"):
            return _result(True, "O trecho declara expressamente a ausência de eventos adicionais neste escopo.")
        trigger = r"inadimpl|descumpr|nao observancia|nao realizacao|nao.{0,70}(?:pagamento|substitui|recompos|entrega|cumpr|instalacao)|verificacao.{0,100}(?:indice|desenquadr|irregular|inconsisten|falha)|(?:indice|razao|taxa|patrimonio|subordinacao|concentracao).{0,100}(?:superior|inferior|exced|atingir|abaixo|acima|menor|maior)|falencia|insolvencia|intervencao|recuperacao judicial|liquidacao extrajudicial|renuncia|descredenciamento|rebaixamento|deixe de|cessacao|interrupcao|violacao|dissolucao|extincao|(?:termino|cancelamento|suspensao).{0,70}(?:convenio|contrato|operacao)|determinacao da cvm|alteracao.{0,70}(?:controle|prestadores|legislacao|politica|regulamentacao)|impossibilidade.{0,80}(?:aquisicao|pagamento)|distribuicao.{0,90}desacordo"
        if not _has(value, trigger):
            return _result(False, "O trecho cita eventos, responsáveis pela verificação ou deliberações posteriores, sem transcrever um gatilho concreto.")

    if criterion == "waterfall":
        if _has(value[:500], r"risco(?:s)? decorrente|risco de|fatores de risco"):
            return _result(False, "O trecho é um aviso de risco ou remissão, sem sequência operacional de pagamentos.")
        markers = re.findall(r"\(\s*(?:[ivx]{1,6}|[a-z]|\d{1,2})\s*\)|(?:^|\s)(?:[a-z]|\d{1,2})\s*[)]|primeiramente|em primeiro lugar|em segundo lugar|em seguida", value)
        recipients = sum(_has(value, pattern) for pattern in (r"despesas|encargos|custos", r"reserva", r"cotas|cotistas", r"derivativ|hedge|swap"))
        if len(markers) < 2 or recipients < 2 or not _has(value, r"seguinte ordem|ordem.{0,35}(?:abaixo|a seguir|:)|(?:prioridade|alocacao de recursos).{0,30}:|primeir.{0,200}segund"):
            return _result(False, "A ordem de alocação é apenas citada ou remetida a outro capítulo, sem sequência de pagamentos transcrita.")

    if criterion in {"quota_grace", "quota_maturity"}:
        if not _has(value, r"cotas|cotistas|subclasse|data de resgate|periodo de carencia de (?:principal|juros)"):
            return _result(False, "O prazo citado pertence ao crédito ou ao devedor, sem identificar carência ou vencimento das cotas.")
        if criterion == "quota_grace" and not _has(value, r"carencia|juros.{0,80}(?:amortiz|principal)"):
            return _result(False, "O trecho não especifica carência das cotas.")
        if criterion == "quota_maturity" and not _has(value, r"vencimento|resgate|prazo (?:final|de duracao)"):
            return _result(False, "O trecho não especifica vencimento ou resgate das cotas.")
        if not _has(value, r"\d|meses|anos|dias|nao (?:ha|havera)|sem carencia|indeterminado|parcela unica|ultima data|data final"):
            return _result(False, "O prazo remete a outro instrumento sem duração ou data expressa.")
        if _has(value, r"(?:conforme|definid[ao]).{0,30}(?:apendice|suplemento)") and not _has(value, r"\d|nao (?:ha|havera)|indeterminado|sem carencia"):
            return _result(False, "A carência ou vencimento é remetida a suplemento sem conteúdo transcrito.")
        return _result(True, "O trecho identifica prazo, ausência de carência ou vencimento específico das cotas.")

    context = {
        "ticket": (_CREDIT_TYPES + r"|devedor|sacado|contrato", r"valor|limite|r\$|\d\s*%"),
        "term": (_CREDIT_TYPES + r"|direitos creditorios|creditos|contrato", r"prazo|carencia|vencimento|dias|meses"),
        "concentration": (r"cedente|devedor|sacado|grupo economico|emissor|contraparte", r"limite|concentracao|\d\s*%|vedad"),
        "subordination": (r"subordin|cotas mezanino", r"indice|razao|relacao|minim|\d\s*%"),
        "coverage": (r"cobertura", r"razao|indice|\d|calcul|divisa"),
        "junior_release": (r"cotas subordinadas|junior|juniores", r"amortiz|liberacao|resgat"),
        "liquidity_reserve": (r"reserva de (?:liquidez|amortizacao|pagamento)", r"constitu|mant|calcul|equiv|correspond|saldo|valor|minim|\d"),
        "expense_reserve": (r"reserva de (?:despesas|encargos)", r"constitu|mant|calcul|equiv|correspond|saldo|valor|minim|\d"),
        "pdd": (r"provis|pdd|perdas esperadas", r"calcul|politica|metodol|criteri|percent|faixa|dias|valor|reduca|curva|reconhec"),
        "aging_trigger": (r"indice de (?:atraso|inadimplencia|rolagem)|atraso90|rolagem90|over", r"\d|limite|evento|calcul|dias|percent"),
        "dilution": (r"diluicao|chargeback|cancelamento dos direitos", r"limite|indice|calcul|cancel|indeniz|reposi|recompra|evento"),
        "repurchase": (r"recompra|indeniz|resolucao da cessao", r"cedente|originador|endossante|direitos creditorios|creditos|cessionario"),
        "coobligation": (r"coobrig|regresso", r"direitos creditorios|creditos|cedente|originador|endossante|devedor"),
        "evaluation": (r"evento.{0,12}avaliacao", r"\d|caso|hipotese|constitui|ocorrencia|descumpr|incorr|verifica"),
        "liquidation": (r"evento.{0,12}liquidacao|liquidacao antecipada", r"\d|caso|hipotese|constitui|ocorrencia|descumpr|incorr|verifica"),
        "cure": (r"cura|dias uteis consecutivos|verificacoes consecutivas|desalavancagem", r"\d|prazo|reincid|consecutiv"),
        "cross_default": (r"inadimplemento cruzado|cross default|regime de administracao especial|raet|intervencao|liquidacao extrajudicial|insolvencia|recuperacao judicial|falencia", r"cedente|devedor|originador|endossante|evento|liquidacao|classe|fundo"),
        "waterfall": (r"ordem de (?:alocacao|prioridade|pagamento)", r"primeir|segund|\(i\)|\(a\)|despesas|encargos|pagamento|reservas|cotas"),
        "sequential": (r"sequencial|pro-rata|pro rata|aceleracao de vencimento", r"cotas|amortiz|pagamento|senior|seniores|mezanino"),
        "revolving": (r"revolv|periodo de investimento|periodo de desinvestimento", r"\d|inicia|encerr|termin|data|durante|aquisicao|prazo|decorr|limit|venc"),
        "sale": (r"alienacao|venda|cessao|carteira residual", r"direitos creditorios|creditos|recebiveis|ativos|carteira"),
        "enforcement": (r"cartorio|registro das garantias|busca e apreensao|execucao das garantias|recuperacao", r"garantia|credito|ccb|devedor|cedente"),
        "servicing": (r"agente de cobranca|servicer|cobranca extraordinaria|politica de cobranca", r"contrat|responsavel|devera|proced|prazo|\d|cnpj|atuar|inadimpl"),
        "collection_account": (r"conta (?:vinculada|de arrecadacao|escrow|de cobranca)", r"deposit|transfer|receb|pagamento|movimenta|domicili|titular|recursos|cnpj"),
        "collateral_check": (r"verificacao.{0,20}lastro|amostragem|documentos comprobatorios", r"\d|trimestral|mensal|integralidade|amostra|valid|verific|comprov"),
        "hedge": (r"derivativ|hedge|swap", r"finalidade|protecao|limit|vedad|permitid|exposicao|risco de taxa|descasamento|contrat|garantia"),
        "hedge_priority": (r"reserva de mtm|reserva de derivativos|ajustes de derivativos|marcacao a mercado", r"hedge|swap|derivativ|prioridade|reserva|contraparte"),
        "replacement": (r"substitui|renuncia|destitu|resili", r"administrador|administradora|gestor|gestora|custodiante|agente de cobranca"),
        "remuneration": (r"remuneracao|rentabilidade|benchmark|cdi|taxa di", r"cotas|senior|seniores|mezanino|subordinad"),
        "issue_volume": (r"valor nominal unitario|vnu|volume total|valor total da emissao|quantidade de cotas", r"\d|r\$|cotas|emissao"),
        "quorum": (r"quorum|maioria.{0,30}votos|assembleia especial", r"\d|maioria|qualquer numero|unanim|votos|totalidade|materia|deliber"),
        "related_parties": (r"partes relacionadas|conflito de interesse", r"permitid|vedad|aprov|politica|condicao|pode|devera|gestor|cedente"),
        "audit": (r"auditor independente|demonstracoes (?:contabeis|financeiras)", r"cnpj|ltda|s\.a|exercicio|anual|prazo|\d|parecer|opiniao|auditad"),
        "tax_allocation": (r"tribut|tratamento tributario|entidade de investimento", r"\d\s*%|sessenta e sete|prazo|lei|aliquota"),
        "investee": (r"classe investida|fundo investido|fundos investidos|cotas (?:do|de|da|desta)", r"cnpj|\d\s*%|mezanino|subordinad|limite|vedad|exclusiv|permitid"),
        "perimeter": (r"classe|subclasse|patrimonio segregado|responsabilidade limitada", r"responsabilidade|patrimonio|senior|seniores|mezanino|subordinad|limitad|segregad"),
        "res175": (r"resolucao cvm.{0,10}175|adaptacao|anexo normativo ii", r"adapt|regid|constitu|deliber|aprov|observ|nos termos|atend|conformidade"),
        "originator": (r"originador|originadora|cedente|endossante", _ENTITY + r"|pessoas juridicas|pessoas fisicas|instituicoes financeiras|plataforma|grupo|originad|empresa"),
        "debtor": (r"devedor|sacado|consignad", r"pessoa|trabalhador|empregado|aposentado|pensionista|inss|fgts|aluno|estudant|empresa|contratante|consumidor|cnpj"),
        "eligibility": (r"elegibilidade|condicoes de (?:cessao|aquisicao)|elegiveis", _CREDIT_TYPES + r"|\d|devedor|cedente|vencimento|performad|inadimpl"),
        "legacy_events": (r"eventos? de (?:avaliacao|liquidacao)|liquidacao antecipada", r"hipotese|ocorrencia|descumpr|constitui|caso|verific|\d|inadimpl|insolv"),
        "duration_investors": (r"fundo|classe|cotas|cotistas|publico.alvo|investidor", r"profissiona|qualificad|prazo de duracao|indeterminado|anos|meses|publico em geral"),
        "quota_classes": (r"cotas|classe|subclasse|serie", r"classe unica|senior|seniores|mezanino|subordinad|junior|juniores|classe a|classe b|subclasse a|subclasse b"),
        "offers": (r"oferta|distribuicao|anuncio de (?:inicio|encerramento)|emissao de cotas", r"anuncio|cvm/sre|registro.{0,20}oferta|dispensa|encerramento|rito|emissao|valor total|\d"),
    }
    patterns = context.get(criterion)
    if patterns and not all(_has(value, pattern) for pattern in patterns):
        return _result(False, "A menção encontrada não especifica objeto e condição próprios deste critério.")
    if criterion == "offers" and _has(value, r"anuncio de (?:inicio|encerramento)") and _has(value, r"cvm/sre/|registro.{0,30}\d"):
        return _result(True, "O anúncio identifica a fase da oferta e seu registro.")
    if criterion == "remuneration" and not _has(value, r"\d\s*%|cdi|taxa di|ipca|igp|valor patrimonial|patrimonial|spread|equivalente|fator|nao.{0,30}meta"):
        return _result(False, "A menção à rentabilidade não define remuneração ou benchmark das cotas.")
    if criterion in {"ticket", "term", "subordination", "coverage", "liquidity_reserve", "expense_reserve", "pdd"} and _has(value, _GOVERNANCE) and not _has(value, r"(?:limite|indice|reserva|provisao).{0,100}(?:calcul|equiv|correspond|minim|maxim|\d\s*%)"):
        return _result(False, "O trecho trata de competência da assembleia, sem transcrever a regra do indicador.")
    if not _has(value, _OPERATIVE + "|" + _DETAIL) and len(value) < 160:
        return _result(False, "O trecho menciona o tema sem apresentar condição ou mecânica específica.")
    return _result(True, "A cláusula contém objeto e condição específicos do critério; números e vigência exigem validação própria.")
