# Diagnóstico do Dashboard de Monitoramento FIDC

Data: 11/04/2026

## Objetivo

Mapear a aba de monitoramento a partir do código implementado, não da intenção histórica, e registrar as principais limitações analíticas para comprador de cotas seniores.

## Fonte de verdade

- Código de montagem dos dados: `services/fundonet_dashboard.py`
- Camada nova de monitoramento por risco: `services/fidc_monitoring.py`
- UI da aba: `tabs/tab_fidc_ime.py`
- Navegação principal: `app.py`
- Fonte primária dos dados: XML/IME da CVM normalizado em `informes_wide.csv` e `estruturas_lista.csv`
- Fonte complementar conceitual e documental: `docs/fidc/*` e documentos primários revalidados em `docs/fidc/_data/document_index.json`

## Inventário resumido do dashboard anterior

| Bloco | Builder principal | Origem dominante | Output |
| --- | --- | --- | --- |
| Visão geral | `_build_summary` | IME/CVM + cálculos internos | cards de PL, direitos, subordinação, inadimplência, liquidez |
| Ativo e carteira | `_build_asset_history`, `_build_composition_latest_df`, `_build_segment_latest_df` | APLIC_ATIVO, CART_SEGMT, LIQUIDEZ | séries e tabelas de composição |
| Inadimplência | `_build_default_history`, `_build_default_buckets_latest_df` | CRED_EXISTE, DICRED, COMPMT_DICRED | séries e aging |
| Cotas e remuneração | `_build_quota_pl_history`, `_build_return_history`, `_build_return_summary`, `_build_performance_vs_benchmark_latest_df` | DESC_SERIE_CLASSE, RENT_MES, DESEMP | PL por classe, retorno e benchmark |
| Eventos | `_build_event_history`, `_build_event_summary_latest_df` | CAPTA_RESGA_AMORTI | emissões, resgates e amortizações |
| Tabelas CVM | `_build_holder_latest_df`, `_build_rate_negotiation_latest_df` | NUM_COTISTAS, TAXA_NEGOC_DICRED_MES | cotistas e taxa de cessão |

Observação: o inventário detalhado, variável por variável, foi centralizado em `build_current_dashboard_inventory_df()` e é exibido na própria aba em “Inventário do dashboard atual”.

## Achados principais

### 1. O dashboard antigo estava organizado por bloco técnico do XML, não por bloco de risco

Isso melhora a rastreabilidade para desenvolvimento, mas piora a leitura para investidor. Um comprador de cota sênior tende a ler o fundo em sequência de risco:

1. crédito
2. estrutura
3. liquidez/funding
4. risco operacional/contratual

### 2. Havia risco arquitetural de colapsar ausência em zero cedo demais

O pipeline original usava séries numéricas com `fillna(0)` em etapas históricas sensíveis. Isso é perigoso porque transforma “campo ausente / histórico inexistente” em “zero econômico”, o que contamina:

- séries históricas
- razões
- deltas futuros
- interpretação visual

Correção adotada: a camada histórica principal passou a usar séries nullable em `_numeric_series_nullable()` e as composições mais sensíveis passaram a respeitar `NaN` com `min_count=1`.

### 3. O dashboard misturava três camadas sem separação explícita

- dado bruto do IME
- transformação de código
- interpretação econômica

Essa mistura dificultava a auditoria da métrica. A reestruturação passou a materializar a memória de cálculo em `risk_metrics_df`, com:

- fonte
- transformação
- variável final
- fórmula
- pipeline
- interpretação
- limitação
- estado do dado

### 4. O IME cobre apenas parte do risco que importa para a cota sênior

O dashboard antigo mostrava bem o que vinha do IME, mas não deixava suficientemente explícito o que estava fora dele. Para análise real de FIDC, continuam dependentes de fonte complementar:

- índice de cobertura
- relação mínima e covenants equivalentes
- reservas e excesso de spread
- cedente, originador, devedor e coobrigação
- eventos de avaliação e liquidação antecipada
- rating e público-alvo
- verificação de lastro

Esses gaps agora aparecem explicitamente em `coverage_gap_df`.

### 5. Algumas métricas do IME são proxies, não equivalentes econômicos perfeitos

Pontos que exigem cautela:

- `Inadimplência / direitos creditórios`: proxy contábil do IME; não substitui política de perda esperada.
- `Liquidez imediata` e `Liquidez até 30 dias`: o preenchimento do IME pode se comportar como bucket ou horizonte cumulativo.
- `Concentração setorial proxy`: não substitui concentração por devedor, cedente ou sacado.
- `Resgate solicitado`: há divergência observada entre `VL_PAGO` e `VL_COTAS` no XML real; a leitura é operacional, não jurídica.

## Conclusão diagnóstica

O problema principal não era apenas visual. Era estrutural:

- a ordem de leitura não refletia a lógica de risco do investidor;
- a memória de cálculo não estava materializada de forma auditável;
- faltava separação explícita entre métrica IME, proxy e camada fora do IME;
- havia risco real de zero artificial no histórico.

A reestruturação passou a tratar isso com quatro artefatos canônicos:

- `risk_metrics_df`
- `coverage_gap_df`
- `mini_glossary_df`
- `current_dashboard_inventory_df`
