# Achados financeiros e limites da apresentação da carteira

Registro da revisão de Carteira e dos seus arquivos. Cálculos, cobertura e regras de competência foram preservados. O ponto 2 recebe uma correção isolada do perímetro documental do Excel da carteira; nenhum valor financeiro foi recalculado para resolver estes achados.

## 1. Participação sênior do bloco analítico é um complemento

**Evidência:** `services/fidc_analytical_slide.py::build_slide_data` lê `vl_cotas_subordinadas` de `vehicle_monthly.csv.gz`, calcula `subordinated_pct_pl = sub / pl` e atribui `senior_pct_pl = 1 - subordinated_pct_pl`.

**Impacto:** o complemento depende do perímetro do campo de subordinadas. Se ele representa somente subordinadas estritas, o resultado pode incluir mezanino e outros grupos de cotas. A fórmula, isoladamente, não comprova a participação da classe sênior. O mesmo campo alimenta o PPT analítico e a aba Snapshot do Excel.

**Tratamento nesta rodada:** fórmula e valores conservados; ambiguidade registrada. O indicador requer leitura como proxy até a reconciliação por classe.

**Decisão futura:** confrontar o campo de origem com a soma por macroclasse e definir uma apresentação que identifique sênior, mezanino, subordinada estrita e diferenças de reconciliação. Qualquer mudança de valor deve ter teste financeiro e commit próprio.

## 2. Perímetro da aba RDB corrigido no Excel da carteira

**Evidência:** o comportamento padrão de `services/fidc_analytical_slide.py::build_fidc_analytical_xlsx_bytes` prepara Snapshot, Emissões e Validações a partir dos fundos recebidos e copia todas as linhas de `RDB_EVIDENCE` para a aba RDB. O download Cloudwalk de 11 fundos trouxe 10 registros de fundos MT de fora da cesta.

**Impacto:** a aba RDB pode incluir fundos de outras carteiras. Seus registros não comprovam a existência de RDB nos fundos selecionados e precisam ser interpretados pelo CNPJ de cada linha.

**Tratamento nesta rodada:** correção opt-in `portfolio_mode=True`, exclusiva do fluxo da carteira. A aba RDB conserva todos os registros documentais dos CNPJs exatos selecionados, com seus campos originais, e inclui uma linha explícita de “Não localizado” e N/D por fundo sem registro no cadastro consultado. A Metodologia registra os CNPJs alheios excluídos e as lacunas. Snapshot, Emissões, Validações, o produtor financeiro e o comportamento padrão dos outros consumidores permanecem iguais.

**Limite e decisão futura:** ausência no cadastro documental consultado não comprova inexistência de RDB. Ampliar a curadoria exige leitura dos documentos dos CNPJs sem registro. Uma eventual aplicação do recorte a outros consumidores deve ser autorizada e validada separadamente.

## 3. Filtro histórico conserva o snapshot original

**Evidência:** `services/fundonet_dashboard.py::filter_dashboard_to_competencias` filtra os históricos e atualiza `latest_competencia` e `fund_info`, mas mantém `summary`. Quando nenhuma competência intersecta a seleção, retorna o dashboard original, incluindo seu histórico completo.

**Impacto:** a janela dos gráficos pode ter referência diferente dos indicadores de posição. Uma seleção sem interseção também pode conservar um histórico fora da janela solicitada. Rotular todos os componentes com a última competência do histórico filtrado atribuiria uma data incorreta ao snapshot.

**Tratamento nesta rodada:** regra preservada. `tabs/portfolio_page.py::_render_portfolio_analysis_surface` guarda o snapshot e sua referência antes do filtro; o contexto da cesta e os cabeçalhos identificam a posição, e o gráfico informa seu histórico efetivo. Esse cuidado de apresentação não modifica a regra de fallback.

**Decisão futura:** definir o comportamento esperado para janelas sem interseção e para snapshots fora da janela. Alterar a composição do snapshot ou seu valor requer aprovação financeira e testes com os mesmos filtros.

## 4. Universo completo pode impedir gráficos do consolidado Cloudwalk

**Evidência:** `services/meli_credit_monitor_visuals.py::_chart_base` conserva apenas linhas com `universe_complete=True`. `services/meli_credit_monitor.py::build_monitor_base` produz os indicadores e qualificadores; `build_cohort_matrix` também exige cobertura completa. A elegibilidade do monitor e a avaliação de competência comum são contratos distintos.

**Impacto:** no consolidado Cloudwalk, podem existir informes e valores mensais parciais sem competências elegíveis para determinado gráfico. Um gráfico vazio não explica essa diferença entre disponibilidade de dados e universo comparável.

**Tratamento nesta rodada:** critério original conservado. `services/portfolio_chart_display.py::render_portfolio_series` explica a ausência de universo completo e oferece os valores parciais com seus qualificadores. Zero válido, ausência e observação não zero continuam separados; valores pequenos e negativos preservam o gráfico quando elegíveis.

**Decisão futura:** avaliar se o universo do monitor deve acompanhar a obrigação de reporte e a elegibilidade cadastral de cada CNPJ. A decisão precisa manter os denominadores, tratar ausências explicitamente e ser validada em carteiras com inadimplência real.

## 5. Janela anual inclui uma competência de âncora

**Evidência:** `services/ime_period.py::display_month_count_for_period` retorna `months + 1` para presets anuais múltiplos de 12. `tabs/tab_mercado_livre.py::_display_window_bounds` utiliza esse contrato ao delimitar a janela visual.

**Impacto:** o rótulo 12M pode produzir 13 competências disponíveis, incluindo a mesma competência do ano anterior. A quantidade efetivamente exibida também depende da cobertura e dos cortes do componente. A âncora de apresentação e a quantidade de meses usada na rentabilidade acumulada precisam ser lidas separadamente.

**Tratamento nesta rodada:** regra e lookback conservados. A ajuda explica a âncora, e o histórico do gráfico informa as competências exibidas.

**Decisão futura:** decidir entre explicitar o rótulo “12M + âncora” ou adotar outro contrato de exibição. Uma revisão da quantidade de pontos deve preservar as bases necessárias para YoY e os acumulados compostos existentes.
