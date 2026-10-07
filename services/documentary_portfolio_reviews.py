"""Publish explicit, source-backed reviews for selected saved portfolios only."""
from __future__ import annotations

from datetime import datetime
from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

import pandas as pd

from services.deep_dive_store import list_deep_dives
from services.document_curation_contract import COMPARISON_TITLES, finalize_document_curation
from services.document_curation_comparison import CELL_REFERENCES_SUBTITLE
from services.portfolio_store import PortfolioRecord, portfolio_basket_signature
from services.regulatory_knowledge import document_inventory_rows, format_cnpj, load_regulatory_knowledge, normalize_cnpj


REVIEW_DIR = Path('data/regulatory_profiles/documentary_comparisons')
COMMON_ROWS = {
    'comparison_eligibility': ['Natureza dos recebíveis', 'Originador/endossante', 'Devedor', 'Garantia', 'Elegibilidade', 'Concentração'],
    'comparison_protection': ['Subordinação mínima', 'Gatilhos de avaliação/liquidação', 'Reserva de caixa', 'Derivativos/hedge', 'PDD'],
    'comparison_mechanics': ['Alocação mínima', 'Pool/revolvência', 'Duração/público-alvo', 'Cessão/recompra', 'Coobrigação', 'Waterfall'],
    'comparison_emissions': ['Classes/séries', 'Remuneração', 'Volume/VNU', 'Ofertas'],
    'comparison_payments': ['Carência', 'Juros/amortização', 'Vencimento'],
    'comparison_costs': ['Administração', 'Gestão', 'Custódia'],
    'comparison_monitoring': ['Alocação/subordinação IME', 'Inadimplência/PDD IME', 'Controles documentais', 'Competência IME'],
}
EMISSION_COLUMNS = ['Fundo', 'CNPJ', 'Cota/Classe', 'Tipo', 'Data deliberação', 'Data emissão / 1ª integralização', 'Data encerramento/oferta', 'Quantidade', 'Volume', 'VNU', 'Remuneração', 'Juros/remuneração', 'Amortização principal', 'Status/evidência', 'Fonte', 'Status curadoria']
CRITERIA_COLUMNS = ['Fundo', 'CNPJ', 'Critério', 'Chave', 'Limite/regra', 'Monitorabilidade IME', 'Métrica IME / proxy', 'Condição de alerta sugerida', 'Observação técnica', 'Fonte', 'Status curadoria']
COST_COLUMNS = ['Fundo', 'CNPJ', 'Item', 'Percentual a.a.', 'Mínimo mensal', 'Fonte', 'Versão vigente / base documental', 'Mudanças relevantes', 'Status curadoria']
_MISSING = {'', '-', '—', 'n/d', 'nan', 'none', 'null'}


def _text(value: object, fallback: str = 'Não informado nas fontes consultadas') -> str:
    return str(value).strip() if value is not None and str(value).strip().lower() not in _MISSING else fallback


def _slug(value: str) -> str:
    folded = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '_', folded.lower()).strip('_')


def read_review(cnpj: str, review_dir: Path = REVIEW_DIR) -> dict:
    path = review_dir / f'{cnpj}.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    if normalize_cnpj(payload.get('cnpj', '')) != cnpj:
        raise ValueError(f'Identidade divergente no parecer {path}')
    if not payload.get('reviewed_at') or not isinstance(payload.get('facts'), dict):
        raise ValueError(f'Parecer sem data ou fatos auditados: {path}')
    reading = datetime.fromisoformat(payload['reviewed_at'].replace('Z', '+00:00'))
    if reading.tzinfo is None:
        raise ValueError(f'Data de leitura sem fuso: {path}')
    if not payload.get('sources_reviewed') and not payload.get('scope_note'):
        raise ValueError(f'Parecer sem fontes ou lacuna de acesso explícita: {path}')
    for theme, facts in payload['facts'].items():
        if theme not in COMPARISON_TITLES or not isinstance(facts, dict):
            raise ValueError(f'Tema inválido no parecer {path}: {theme}')
        for criterion, fact in facts.items():
            if not isinstance(fact, dict) or _text(fact.get('value'), '') == '' or _text(fact.get('source'), '') == '':
                raise ValueError(f'Fato sem valor textual/fonte: {path}, {criterion}')
    payload.setdefault('metrics', {name: payload[name] for name in ('inventory_count', 'pdf_count', 'pages_analyzed', 'downloaded_count', 'analyzable_pages') if name in payload})
    metrics = payload['metrics']
    if metrics.get('inventory_count', metrics.get('documents_inventoried')) == 0 and (payload.get('inventory_error') or payload.get('warnings') or not payload.get('sources_reviewed')):
        metrics['inventory_count'] = 'Inventário indisponível; consultar lacuna de acesso'
    return payload


def review_source(review: dict) -> str:
    sources = review.get('sources_reviewed') or []
    entries = [f"ID {s.get('document_id', 'não informado')} · {s.get('date', 'data não informada')} · {s.get('path', s.get('text_path', 'arquivo não informado'))}" for s in sources]
    return '; '.join(entries) or _text(review.get('scope_note'), 'Consulta Fundos.NET sem documento acessível; conferir inventário do CNPJ')


def get_fact(review: dict, theme: str, criterion: str) -> dict:
    fact = review.get('facts', {}).get(theme, {}).get(criterion)
    if fact:
        return {'value': _text(fact.get('value')), 'source': _text(fact.get('source')), 'note': _text(fact.get('note'), 'Conclusão limitada às fontes identificadas nesta leitura')}
    aliases = {
        'Gatilhos de avaliação/liquidação': ('Eventos de avaliação', 'Liquidação antecipada'),
        'Reserva de caixa': ('Reserva de despesas',),
        'Remuneração': ('Remuneração sênior', 'Remuneração mezanino', 'Remuneração subordinada'),
        'Volume/VNU': ('Volume / quantidade', 'VNU / preço'),
        'Juros/amortização': ('Juros / pagamentos', 'Amortização programada'),
        'Alocação/subordinação IME': ('Alocação via IME', 'Subordinação via IME'),
        'Controles documentais': ('Concentração / elegibilidade',),
    }
    found = [(name, review.get('facts', {}).get(theme, {}).get(name)) for name in aliases.get(criterion, ())]
    found = [(name, item) for name, item in found if item]
    if found:
        return {'value': '; '.join(name + ': ' + _text(item.get('value')) for name,item in found), 'source': '; '.join(_text(item.get('source')) for _,item in found), 'note': '; '.join(_text(item.get('note')) for _,item in found)}
    return {'value': 'Não localizado nas fontes acessíveis desta leitura', 'source': review_source(review), 'note': _text(review.get('scope_note'), 'Lacuna documental; não representa ausência de regra contratual')}


def enrich_cached_ime(reviews: dict[str, dict]) -> tuple[dict[str, dict], pd.DataFrame]:
    """Keep cached observations separate from documentary conclusions and live IME."""
    from scripts.build_deep_dive_package import best_ime_cache_for_cnpj, performance_rows_from_ime_cache
    enriched, rows = deepcopy(reviews), []
    for cnpj, review in enriched.items():
        cache = best_ime_cache_for_cnpj(cnpj)
        fact = {'value': 'Sem competência IME carregada em cache local', 'source': 'Inventário de .cache/fundonet em ' + datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat(), 'note': 'Leitura documental preservada. Carregar competência no Monitoramento para avaliar enquadramento.'}
        if cache:
            observed = performance_rows_from_ime_cache(cache, pd.Series({'cnpj': cnpj, 'fundo': review['label'], 'grupo': 'Carteiras selecionadas'}))
            if observed:
                rows.extend(observed)
                fact = {'value': 'Cache local: ' + str(cache['_latest_comp']) + '; selecionar competência para monitorar', 'source': str(Path(cache['_path']).relative_to(Path.cwd())), 'note': 'Dado offline do IME; não representa atualização ao vivo nem comprovação dos critérios jurídicos.'}
        if fact['value'].startswith('Sem competência'):
            rows.append({'cnpj': cnpj, 'fundo': review['label'], 'competencia': 'Sem competência IME carregada', 'indicador': 'Lacuna IME', 'valor': 'Sem dado IME carregado nesta leitura', 'unidade': 'Não aplicável à lacuna', 'observacao': fact['note'], 'cache_folder': 'Cache não localizado ou sem métricas utilizáveis'})
        review.setdefault('facts', {}).setdefault('comparison_monitoring', {})['Competência IME'] = fact
    return enriched, pd.DataFrame(rows)


def build_comparisons(portfolio: PortfolioRecord, reviews: dict[str, dict]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, str]]:
    labels, mapping = [], {}
    for fund in portfolio.funds:
        label = _text(reviews[fund.cnpj].get('label'), fund.display_name)
        if label in mapping:
            label += f' ({format_cnpj(fund.cnpj)})'
        labels.append(label); mapping[label] = fund.cnpj
    tables, evidence = {}, []
    for theme in COMPARISON_TITLES:
        criteria = list(COMMON_ROWS[theme])
        for fund in portfolio.funds:
            for criterion in reviews[fund.cnpj].get('facts', {}).get(theme, {}):
                if criterion not in criteria:
                    criteria.append(criterion)
        rows = []
        for criterion in criteria:
            row = {'Critério': criterion}
            for label, fund in zip(labels, portfolio.funds):
                fact = get_fact(reviews[fund.cnpj], theme, criterion)
                row[label] = fact['value']
                evidence.append({'Tabela': theme, 'Critério': criterion, 'CNPJ': fund.cnpj, 'Valor': fact['value'], 'Fonte': fact['source'], 'Nota': fact['note']})
            rows.append(row)
        tables[theme] = pd.DataFrame(rows)
    return tables, pd.DataFrame(evidence), mapping


def _monitoring(criterion: str) -> tuple[str, str, str]:
    known = {
        'Alocação mínima': ('credit_rights_allocation_min', 'direto com validação', 'Direitos creditórios / PL; validar ativo elegível, período e denominador'),
        'Subordinação mínima': ('subordination_ratio_min', 'monitoravel com ressalva', 'Cotas subordinadas e mezanino / PL; reconciliar subclasse e fórmula contratual'),
        'Concentração': ('concentration_limits', 'nao_monitoravel', 'Sem granularidade pública por cedente/devedor/grupo econômico'),
        'Elegibilidade': ('eligibility_criteria_text', 'nao_monitoravel', 'Controle individual de lastro, devedor e critérios contratuais'),
        'Derivativos/hedge': ('permitted_hedges', 'parcial', 'Posição agregada em derivativos; não comprova finalidade/elegibilidade'),
        'Reserva de caixa': ('minimum_cash_ratio', 'parcial', 'Disponibilidades; requer despesas futuras, cronograma e waterfall'),
        'Cessão/recompra': ('repurchase_indemnity', 'parcial', 'Recompras / Crédito; motivo e indenização exigem contratos'),
        'PDD': ('pdd_coverage_min', 'parcial', 'PDD / Crédito e PDD / Vencidos; validar definição contratual'),
        'Gatilhos de avaliação/liquidação': ('documentary_evaluation_liquidation', 'parcial', 'Aging e PDD agregados; eventos e denominadores precisam de controle documental'),
    }
    return known.get(criterion, ('documentary_' + _slug(criterion), 'nao_monitoravel', 'Controle documental; IME público não replica a regra jurídica'))


def analytical_rows(reviews: dict[str, dict], funds: list) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    criteria, emissions, costs = [], [], []
    for fund in funds:
        review = reviews[fund.cnpj]; identity = {'Fundo': fund.display_name, 'CNPJ': format_cnpj(fund.cnpj)}
        for theme in ('comparison_eligibility', 'comparison_protection', 'comparison_mechanics'):
            names = list(dict.fromkeys(COMMON_ROWS[theme] + list(review.get('facts', {}).get(theme, {}))))
            for name in names:
                fact = get_fact(review, theme, name); key, monitorability, proxy = _monitoring(name)
                if fact['value'].startswith(('Não localizado', 'Não informado', 'Não confirmado', 'Sem documento', 'Sem acesso', 'Regulamento não acessível', 'Lacuna')):
                    monitorability, proxy = 'nao_monitoravel', 'Lacuna documental: obter regra antes de definir métrica ou alerta'
                if name in ('Alocação mínima', 'Subordinação mínima') and any(term in fact['value'].lower() for term in ('não localizado', 'não transcrito', 'não confirmado')):
                    monitorability, proxy = 'nao_monitoravel', 'Limite contratual pendente; o IME pode informar saldos, mas não comprova enquadramento'
                criteria.append({**identity, 'Critério': name, 'Chave': key, 'Limite/regra': fact['value'], 'Monitorabilidade IME': monitorability, 'Métrica IME / proxy': proxy, 'Condição de alerta sugerida': 'Validar fórmula e competência antes de ativar alerta; regra/lacuna: ' + fact['value'], 'Observação técnica': fact['note'], 'Fonte': fact['source'], 'Status curadoria': _text(review.get('document_status'), 'Leitura documental com lacunas explícitas')})
        detailed = review.get('emissions_rows') or []
        if not detailed:
            classes = get_fact(review, 'comparison_emissions', 'Classes/séries')
            pay = get_fact(review, 'comparison_payments', 'Juros/amortização')
            remuneration = get_fact(review, 'comparison_emissions', 'Remuneração')
            volume = get_fact(review, 'comparison_emissions', 'Volume/VNU')
            detailed = [{'Cota/Classe': classes['value'], 'Remuneração': remuneration['value'], 'Volume': volume['value'], 'Amortização principal': pay['value'], 'Juros/remuneração': pay['value'], 'Fonte': '; '.join(dict.fromkeys([classes['source'], remuneration['source'], volume['source'], pay['source']])), 'Status/evidência': 'Resumo documental; individualização por série não localizada nesta leitura'}]
        for item in detailed:
            emissions.append({column: _text(identity.get(column, item.get(column)), 'Spread final não localizado' if column == 'Remuneração' else 'Não informado nas fontes consultadas') for column in EMISSION_COLUMNS})
        detailed_costs = deepcopy(review.get('costs_rows') or [])
        seen = {row.get('Item') for row in detailed_costs}
        for item in COMMON_ROWS['comparison_costs']:
            if item not in seen:
                fact = get_fact(review, 'comparison_costs', item)
                detailed_costs.append({'Item': item, 'Percentual a.a.': fact['value'], 'Mínimo mensal': 'Ver regra e mínimo na descrição documental' if 'R$' in fact['value'] else 'Mínimo mensal não individualizado nas fontes consultadas', 'Fonte': fact['source'], 'Versão vigente / base documental': fact['note']})
        for item in detailed_costs:
            costs.append({column: _text(identity.get(column, item.get(column))) for column in COST_COLUMNS})
    return pd.DataFrame(criteria, columns=CRITERIA_COLUMNS), pd.DataFrame(emissions, columns=EMISSION_COLUMNS), pd.DataFrame(costs, columns=COST_COLUMNS)


def replace_selected_rows(path: Path, rows: pd.DataFrame, selected: set[str]) -> None:
    previous = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() and path.stat().st_size else pd.DataFrame()
    if not previous.empty:
        if 'CNPJ' not in previous:
            raise ValueError(f'Arquivo sem identidade CNPJ: {path}')
        previous = previous[~previous['CNPJ'].map(normalize_cnpj).isin(selected)]
    # Keep every old value for other CNPJs, while making new missing fields explicit.
    columns = list(dict.fromkeys(list(previous.columns) + list(rows.columns)))
    selected_rows = rows.reindex(columns=columns, fill_value='Não informado nas fontes consultadas').map(_text)
    combined = pd.concat([previous, selected_rows], ignore_index=True, sort=False).fillna('')
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)


def publish_profiles(reviews: dict[str, dict], funds: list, root: Path = Path('.')) -> None:
    selected = set(reviews)
    criteria, emissions, costs = analytical_rows(reviews, funds)
    profiles = root / 'data/regulatory_profiles'
    for path, frame in [('all_fidcs_criteria_monitoraveis_ime.csv', criteria), ('all_fidcs_cotas_emissoes_pagamentos.csv', emissions), ('structural_costs.csv', costs), ('documentary_review_criteria_monitoraveis_ime.csv', criteria), ('documentary_review_cotas_emissoes_pagamentos.csv', emissions)]:
        replace_selected_rows(profiles / path, frame, selected)
    reports = root / 'reports'
    inventory, status = [], []
    for fund in funds:
        review = reviews[fund.cnpj]
        knowledge = load_regulatory_knowledge(fund.cnpj, base_dir=root/'data/regulatory_knowledge')
        if knowledge:
            inventory.extend({'Fundo': fund.display_name, 'CNPJ': format_cnpj(fund.cnpj), **row} for row in document_inventory_rows(knowledge))
            payload = knowledge.payload
            payload.setdefault('historical_heuristic_criteria', deepcopy(payload.get('criteria', [])))
            payload.setdefault('historical_heuristic_emissions', deepcopy(payload.get('emissions', [])))
            fund_criteria = criteria[criteria.CNPJ.map(normalize_cnpj).eq(fund.cnpj)]
            payload['criteria'] = [{'name': row['Critério'], 'canonical_key': row['Chave'], 'threshold_display': row['Limite/regra'], 'source_document': row['Fonte'], 'notes': row['Observação técnica'], 'monitoring_mapping': {'status': row['Monitorabilidade IME'], 'ime_metric': row['Métrica IME / proxy'], 'rationale': row['Observação técnica']}} for _,row in fund_criteria.iterrows()]
            fund_emissions = emissions[emissions.CNPJ.map(normalize_cnpj).eq(fund.cnpj)]
            payload['emissions'] = [{'date': row['Data deliberação'], 'event': row['Status/evidência'], 'series_or_class': row['Cota/Classe'], 'amount_display': row['Volume'], 'remuneration': row['Remuneração'], 'amortization_schedule': row['Amortização principal'], 'source_document': row['Fonte'], 'notes': row['Status curadoria']} for _,row in fund_emissions.iterrows()]
            payload['documentary_review'] = deepcopy(review)
            payload['reviewed_at'] = review['reviewed_at']
            payload['documentary_review_file'] = f'data/regulatory_profiles/documentary_comparisons/{fund.cnpj}.json'
            (root/'data/regulatory_knowledge'/f'{fund.cnpj}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        metrics = review.get('metrics') or {}
        status.append({'Fundo': fund.display_name, 'CNPJ': format_cnpj(fund.cnpj), 'Documentos inventariados': metrics.get('inventory_count', metrics.get('documents_inventoried', 'Inventário indisponível')), 'Critérios curados': len(criteria[criteria.CNPJ.map(normalize_cnpj)==fund.cnpj]), 'Emissões/eventos curados': len(emissions[emissions.CNPJ.map(normalize_cnpj)==fund.cnpj]), 'Status curadoria': _text(review.get('document_status')), 'Data de leitura': review['reviewed_at']})
    replace_selected_rows(reports/'regulatory_document_inventory.csv', pd.DataFrame(inventory, columns=['Fundo', 'CNPJ', 'Data', 'Tipo', 'Documento', 'Espécie', 'Arquivo', 'ID CVM']), selected)
    replace_selected_rows(reports/'all_fidcs_regulatory_curation_status.csv', pd.DataFrame(status), selected)
    matrix = criteria.rename(columns={'Limite/regra': 'Limite', 'Monitorabilidade IME': 'Monitoramento', 'Métrica IME / proxy': 'Métrica IME sugerida', 'Observação técnica': 'Comentário'})
    replace_selected_rows(reports/'regulatory_criteria_matrix.csv', matrix, selected)
    timeline = emissions.rename(columns={'Cota/Classe': 'Classe/Série', 'Data deliberação': 'Data', 'Status/evidência': 'Evento', 'Amortização principal': 'Amortização/Vencimento'})
    replace_selected_rows(reports/'regulatory_emissions_timeline.csv', timeline, selected)


def _findings(portfolio: PortfolioRecord, reviews: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for fund in portfolio.funds:
        review = reviews[fund.cnpj]
        findings = review.get('key_findings') or []
        if findings:
            for finding in findings:
                if len(rows) >= 4: break
                if len(portfolio.funds) > 1 and any(row['Tema'].startswith(review['label'] + ' ·') for row in rows): break
                rows.append({'Tema': (review['label'] + ' · ' if len(portfolio.funds)>1 else '') + _text(finding.get('Tema'), 'Estrutura'), 'Conclusão': _text(finding.get('Conclusão'))})
        if len(rows) >= 4: break
    for theme, criterion in [('comparison_eligibility', 'Natureza dos recebíveis'), ('comparison_protection', 'Subordinação mínima'), ('comparison_mechanics', 'Alocação mínima')]:
        if len(rows)>=3: break
        fund=portfolio.funds[0]
        rows.append({'Tema': criterion, 'Conclusão': reviews[fund.cnpj]['label'] + ': ' + get_fact(reviews[fund.cnpj], theme, criterion)['value']})
    rows.append({'Tema': 'Base da leitura', 'Conclusão': 'Regras conforme as versões documentais identificadas nas fontes. O nome da carteira preserva o cadastro; versões posteriores ao período do nome devem ser tratadas pela sua própria data.'})
    return pd.DataFrame(rows[:5], columns=['Tema', 'Conclusão'])


def publish_portfolio(portfolio: PortfolioRecord, reviews: dict[str, dict], output_root: Path = Path('data/deep_dives'), cached_ime: pd.DataFrame | None = None):
    relevant = {fund.cnpj: reviews[fund.cnpj] for fund in portfolio.funds}
    existing = [manifest for manifest in list_deep_dives(output_root) if manifest.portfolio_id == portfolio.id]
    if len(existing)>1:
        raise ValueError(f'Mais de um pacote próprio para a carteira {portfolio.id}; resolver explicitamente')
    package_id = existing[0].deep_dive_id if existing else 'carteira_' + _slug(portfolio.name) + '_' + portfolio.id[:8]
    package_dir = output_root / package_id
    tables, evidence, mapping = build_comparisons(portfolio, relevant)
    criteria, emissions, costs = analytical_rows(relevant, list(portfolio.funds))
    now = max((review['reviewed_at'] for review in relevant.values()), key=lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')))
    manifest = {'schema_version': 1, 'deep_dive_id': package_id, 'title': 'Curadoria ' + portfolio.name, 'subtitle': 'Comparativos documentais, emissões e controles IME', 'portfolio_id': portfolio.id, 'portfolio_signature': portfolio_basket_signature(portfolio.funds), 'generated_at': now, 'source': 'CVM/Fundos.NET e documentos locais identificados; revisão por CNPJ', 'confidentiality': 'Uso interno', 'funds': [{'cnpj': fund.cnpj, 'name': fund.display_name, 'short_name': relevant[fund.cnpj]['label']} for fund in portfolio.funds], 'comparison_columns': mapping, 'tables': [{'id': name, 'title': title, 'source_file': f'tables/{name}.csv', 'first_column': first, 'kind': 'source_table'} for name,title,first in [('comparison_main','Comparativo principal','Nome'),('emissions','Emissões e calendário','Fundo'),('thresholds','Critérios monitoráveis e qualitativos','Fundo'),('structural_costs','Custos estruturais','Fundo')]], 'audit': {'warnings': list(dict.fromkeys(['Leitura das fontes acessíveis indicadas por CNPJ; inventário completo não implica leitura integral de cada registro.', 'Competência IME e datas documentais devem ser conferidas separadamente; o nome da carteira não fixa a versão do regulamento.'] + [warning for review in relevant.values() for warning in review.get('warnings', [])]))}}
    manifest['tables'].append({'id': 'comparison_evidence', 'title': 'Fontes e notas dos comparativos', 'source_file': 'evidence/comparison_sources.csv', 'first_column': 'Tabela', 'kind': 'source_table', 'subtitle': CELL_REFERENCES_SUBTITLE})
    manifest['tables'].append({'id': 'document_coverage', 'title': 'Cobertura e lacunas documentais por CNPJ', 'source_file': 'evidence/document_coverage.csv', 'first_column': 'Fundo', 'kind': 'source_table'})
    (package_dir/'tables').mkdir(parents=True, exist_ok=True); (package_dir/'evidence').mkdir(exist_ok=True)
    for name, frame in tables.items(): frame.to_csv(package_dir/f'tables/{name}.csv', index=False)
    main = pd.concat([table.rename(columns={'Critério':'Nome'}).assign(Nome=lambda df: COMPARISON_TITLES[name] + ' · ' + df.Nome) for name,table in tables.items()], ignore_index=True)
    main.to_csv(package_dir/'tables/comparison_main.csv', index=False)
    _findings(portfolio, relevant).to_csv(package_dir/'tables/key_findings.csv', index=False)
    emissions.to_csv(package_dir/'tables/emissions.csv', index=False); criteria.to_csv(package_dir/'tables/thresholds.csv', index=False); costs.to_csv(package_dir/'tables/structural_costs.csv', index=False)
    evidence.to_csv(package_dir/'evidence/comparison_sources.csv', index=False)
    performance = cached_ime[cached_ime.cnpj.map(normalize_cnpj).isin(relevant)] if cached_ime is not None and not cached_ime.empty else pd.DataFrame([{'cnpj': cnpj, 'fundo': review['label'], 'competencia': 'Sem competência IME carregada', 'indicador': 'Lacuna IME', 'valor': 'Sem dado IME carregado nesta leitura', 'observacao': 'Revisão documental preservada'} for cnpj,review in relevant.items()])
    performance.to_csv(package_dir/'evidence/performance_metrics_enriched.csv', index=False)
    pd.DataFrame([{'CNPJ': fund.cnpj, 'Fundo': fund.display_name, 'Data de leitura': relevant[fund.cnpj]['reviewed_at'], 'Status documental': _text(relevant[fund.cnpj].get('document_status')), 'Escopo de leitura': _text(relevant[fund.cnpj].get('scope_note')), 'Fontes consultadas': review_source(relevant[fund.cnpj]), 'Contagens declaradas / unidade original': json.dumps(relevant[fund.cnpj].get('metrics', {}), ensure_ascii=False), 'Lacunas e divergências': '; '.join(relevant[fund.cnpj].get('warnings', [])) or 'Consultar qualificações por célula em comparison_sources.csv'} for fund in portfolio.funds]).to_csv(package_dir/'evidence/document_coverage.csv', index=False)
    (package_dir/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return finalize_document_curation(package_dir, portfolio, output_root=output_root, reading_at=now)
