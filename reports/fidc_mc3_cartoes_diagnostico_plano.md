# FIDC Mercado Crédito III - Cartões

## Classificação da interação
🔴 Complexo (nova sub-aba inteira + múltiplos blocos de cálculo + cenários + waterfall + métricas).

## ETAPA 1 — Diagnóstico (sem implementação)

### a) Abas e modelos FIDC existentes

**Workbook Excel existente no repositório (`Modelo_Publico.xlsm`):**
- Fluxo Base
- BMF
- Holidays
- Vencimentário

**Modelos FIDC no motor Python (`services/fidc_model/engine.py`):**
- `legacy_percent` (perda esperada/inesperada percentual)
- `npl90_provision` (NPL 90+ com lag + provisão/cobertura)
- `migration_matrix` (migração mensal por buckets até 90+)

### b) Descrição dos modelos atuais

#### 1) `legacy_percent`
- **Inputs-chave**: perda esperada am, perda inesperada am, carteira.
- **Waterfall Sr/Sub**: realizado no loop principal do engine (pagamentos SEN/MEZZ e residual SUB).
- **PDD**: não modela estoque explícito de NPL90/provisão; trata despesa por percentual.
- **Duration**: calculada por funções de métricas (Macaulay + lookup pré-DI).
- **Hard-coded vs parametrizado**: altamente parametrizado, mas sem tracking explícito de estoque de inadimplência.
- **Limitação p/ MC3**: insuficiente para regra de PDD = 100% sobre Over90 + Reneg por estoque/cenário.

#### 2) `npl90_provision`
- **Inputs-chave**: perda de ciclo, lag até NPL90, cobertura mínima NPL90, LGD.
- **Waterfall Sr/Sub**: fluxo econômico mensal com despesas de perda/provisão afetando residual da SUB.
- **PDD**: modela `provisao_saldo`, `npl90_estoque`, entrada em NPL, write-off, cobertura.
- **Duration**: já integrada ao conjunto de métricas do motor.
- **Hard-coded vs parametrizado**: parametrizado; fórmulas econômicas fixas no engine.
- **Limitação p/ MC3**: não traz nativamente “Reneg” separado + teto de maturação Over90 por safra (40%) como input explícito.

#### 3) `migration_matrix`
- **Inputs-chave**: probabilidades de migração entre buckets (adimplente→1-30→31-60→61-90→90+), LGD, cobertura mínima.
- **Waterfall Sr/Sub**: mesmo framework do engine, com perdas via migração.
- **PDD**: provisão com base no bucket 90+ e reforço de cobertura.
- **Duration**: idem.
- **Hard-coded vs parametrizado**: mais flexível para comportamento de atraso por faixas.
- **Limitação p/ MC3**: maior complexidade/calibração para um caso de proposta com inputs já definidos em NPL agregado.

### c) Referências da aba `Portfolio - Cartão de Crédito` (linhas 26-46, 50-69, 82-87)

- **Status**: essa aba **não foi localizada** no arquivo `Modelo_Publico.xlsm` presente neste repositório (somente 4 abas listadas acima).
- **Implicação**: não foi possível mapear as referências pedidas (linhas 26-46 parcelado, 50-69 NPLs, 82-87 reneg) com evidência local.
- **Ação proposta**: na implementação, usar referência cruzada direta **assim que** você disponibilizar a versão da planilha que contenha essa aba (ou indicar arquivo alternativo/caminho).

---

## ETAPA 2 — Plano de adaptação (para aprovação)

### 1) Modelo-base escolhido
**Escolha**: `npl90_provision`.

**Justificativa curta**:
- Já possui lógica de NPL 90+, lag, provisão, cobertura e write-off.
- Menor gap para incorporar PDD de 100% sobre Over90+Reneg e cenários Base/Realista/Choque.
- Mantém comparabilidade com a metodologia econômica já usada no projeto.

### 2) Lista de adaptações necessárias
1. Criar sub-aba `FIDC_MC3_Cartoes` no workbook alvo com blocos funcionais.
2. Parametrizar inputs editáveis (amarelo) + named ranges obrigatórios.
3. Implementar cronograma mensal de 7 meses + cauda de liquidação.
4. Implementar parcelas equânimes (PMT) e dinâmica de carteira/caixa.
5. Implementar waterfall Sr/Sub mensal com custo Sr = CDI + spread.
6. Implementar PDD: 100% de (Over90 + Reneg), com trilhas por cenário.
7. Implementar cenário choque (22,1%) e subcenário histórico (~36%), respeitando teto de maturação Over90/safra = 40%.
8. Implementar métricas: pico carteira, duration Macaulay (meses e dias úteis), TIR Sub, subordinação mínima, cobertura PDD/NPL.
9. Quadro-resumo topo com 3 cenários lado a lado + gráfico carteira/sub.
10. Garantir 100% fórmula Excel (sem hard-code de resultados) e links cruzados para aba Portfolio.

### 3) Layout proposto da sub-aba `FIDC_MC3_Cartoes`
- **Bloco 1**: Inputs editáveis.
- **Bloco 2**: Cronograma originação/amortização.
- **Bloco 3**: Waterfall Sr/Sub mensal.
- **Bloco 4**: PDD e provisões.
- **Bloco 5**: Métricas (Duration, Pico, TIR).
- **Bloco 6**: Cenários (Base / Realista / Choque).
- **Bloco 7**: Quadro-resumo executivo.

### 4) Mapa de fórmulas-chave
- **Parcela equânime**: `=PMT(taxa_aa/12; n_parcelas; -carteira_ini)`
- **Macaulay Duration**: `=SOMARPROD(periodos; FC_descontados)/SOMA(FC_descontados)`
- **Choque 2σ**: `=npl_atual + choque_2sigma`
- **PDD**: `=pdd_pct*(npl_over90 + estoque_reneg)`
- **Limite maturação safra**: `=MIN(npl_safra_calculado; 40%)`

### 5) Premissas que precisam de validação
1. CDI de referência (curva mensal fixa vs série projetada mensal).
2. Interpretação de “taxa 13%-14% a.m.”: yield bruto da carteira ou taxa contratual efetiva líquida de custos.
3. Tratamento de renegociação: entra integralmente em Over90+Reneg no mês corrente ou com defasagem.
4. Definição exata da cauda de liquidação (n meses fixos ou até carteira zerar por critério).
5. Convenção de dias úteis para duration em dias (21 fixo por mês vs calendário real útil).
6. TIR Sub: periodicidade mensal com anualização equivalente ou TIR direta anual.
7. Subcenário histórico: usar 36,3% pontual ou arredondar para 36% conforme seu texto.

### 6) Riscos e pontos cegos
- Sem prepayment explícito pode superestimar duration e caixa tardio.
- Sem curva de cura/roll-back pode superestimar perdas permanentes.
- Dependência de aba `Portfolio - Cartão de Crédito` (não localizada nesta cópia) impede vinculação imediata.
- Sem custos adicionais (servicer, admin, impostos) pode inflar residual da SUB.
- Sensibilidade alta ao lag de reconhecimento de NPL e regra de write-off.

## Próximo passo
Paro aqui, conforme solicitado. Aguardo sua aprovação para implementar a ETAPA 3.
