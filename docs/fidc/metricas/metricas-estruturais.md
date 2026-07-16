# Métricas estruturais e de liquidez

Esta é uma **ordem de leitura sugerida** para a cota protegida. A família do recebível pode mudar a prioridade. Toda métrica precisa indicar **pergunta, fórmula, nível, data, unidade e fonte**.

**PL** significa **patrimônio líquido**. Em toda razão, use o PL da classe correta.

## 1. Subordinação

- **Pergunta:** quanto patrimônio está abaixo da camada analisada na prioridade contratual?
- **Índice contratual:** `valor computável da subclasse subordinada / PL da classe`.
- **Aproximação pelo Informe Mensal:** `(PL mezanino + PL subordinado residual) / PL total reportado`.
- **Por que importa:** é a primeira camada patrimonial disponível para absorver resultados e perdas na ordem definida.
- **Limitação:** a aproximação pode não reproduzir a fórmula do regulamento, a série aplicável, os ajustes ou a data do teste.

## 2. Cobertura de ativos

- **Pergunta:** os ativos admitidos no teste cobrem as obrigações protegidas?
- **Forma geral:** `ativos elegíveis ajustados / obrigações protegidas`.
- **Numerador:** direitos que entram no teste depois de descontos, limites e exclusões.
- **Denominador:** principal, remuneração, despesas, reservas ou outros passivos definidos.
- **Por que importa:** conecta qualidade e quantidade dos ativos à obrigação que a classe precisa honrar.
- **Limitação:** “1,20x” em dois fundos só é comparável depois de reconciliar numerador, passivo, data e consequência.

## 3. Concentração

- **Pergunta:** qual evento isolado pode atingir parcela material da carteira?
- **Forma geral:** `exposição computável ao fator i / base contratual`.
- **Fatores comuns:** devedor, grupo econômico, cedente, originador, garantidor, convênio, arranjo, setor, região, produto ou vencimento.
- **Por que importa:** uma carteira com milhares de contratos pode continuar dependente de um único pagador, prestador ou canal.
- **Limitação:** concentração no maior segmento da Tabela II não substitui concentração por contraparte.

## 4. Liquidez e descasamento

### Caixa disponível

- **Pergunta:** há caixa utilizável para as saídas da janela?
- **Fórmula:** `caixa e ativos líquidos admitidos / saídas previstas na janela`.
- **Por que importa:** proteção patrimonial não paga uma obrigação se o dinheiro chegar depois.
- **Limitação:** reserva vinculada ou conta bloqueada pode não estar disponível para qualquer uso.

### Descasamento médio de prazo

- **Pergunta:** o principal da carteira chega antes ou depois das obrigações das cotas?
- **Fórmula simplificada:** `vida média ponderada dos ativos - prazo médio ponderado das obrigações`.
- **Por que importa:** descasamento positivo, também chamado de *gap* de prazo, pode exigir caixa, venda, refinanciamento ou extensão.
- **Limitação:** a diferença de médias não substitui uma projeção de caixa por data. Taxa, índice e moeda exigem testes separados.

### Vida média ponderada, ou Weighted Average Life (WAL)

- **O que significa:** tempo médio para receber o principal esperado, ponderado pelo valor recebido em cada data.
- **Fórmula:** `WAL = Σ(principal esperado no tempo t × tempo t) / Σ(principal esperado)`.
- **Unidade:** dias, meses ou anos.
- **Quando é importante:** carteiras longas, cotas com amortização programada, pré-pagamento relevante e estruturas com descasamento.
- **Quando é secundária:** em carteiras já inadimplidas, a recuperação líquida e o tempo até caixa podem ser mais informativos que um cronograma contratual original.
- **Limitação:** atraso, pré-pagamento, recuperação e reinvestimento mudam o fluxo esperado. WAL não é **duração financeira, ou duration**, e não mede sozinho sensibilidade a taxa.

## 5. Alocação e elegibilidade

- **Pergunta:** qual parcela do patrimônio está aplicada nos direitos que a regra admite?
- **Convenção simples:** `direitos creditórios computáveis / PL da classe`.
- **Por que importa:** baixa alocação pode reduzir geração de receita e indicar formação inicial da carteira, ou *ramp-up*, amortização ou dificuldade de originação.
- **Limitação:** o art. 44 da Resolução da Comissão de Valores Mobiliários (RCVM) 175 usa critério e prazo próprios; metas contratuais podem usar direitos elegíveis, valor presente ou exclusões diferentes.

Formação inicial não é sinônimo de toda queda de alocação.

## 6. Reservas

- **Pergunta:** a reserva tem saldo suficiente para sua finalidade?
- **Fórmula:** `ativos elegíveis da reserva / necessidade-alvo`.
- **O que definir:** reserva de despesas, liquidez, amortização ou outra; alvo; ativo admitido; saque; recomposição; beneficiário.
- **Por que importa:** cria caixa ou proteção para um uso específico.
- **Limitação:** caixa livre não é reserva e uma reserva para despesas não cobre automaticamente perda de crédito.

## 7. Excesso de margem financeira

- **O que significa:** margem que sobra depois da receita da carteira pagar perdas, despesas, custo das cotas e outros encargos. Também é chamada de **excesso de spread**, sendo *spread* a margem adicional entre taxas ou fluxos.
- **Aproximação por período:** `receita da carteira - perdas - despesas - custo das cotas protegidas - outros encargos`.
- **Por que importa:** pode recompor proteção, financiar reserva ou absorver deterioração antes de atingir a cota.
- **Limitação:** “taxa média da carteira menos referência de remuneração” ignora atraso, pré-pagamento, despesas e calendário. A expressão literal não apareceu nos 15 regulamentos usados para prevalência; aqui ela é uma inferência analítica.

## 8. Patrimônio líquido como escala

- **Fórmula:** `ativos reconhecidos - passivos reconhecidos`.
- **Uso:** dimensiona a classe, serve de base para várias razões e ajuda a reconciliar cotas.
- **Limitação:** PL alto não prova qualidade, liquidez ou subordinação. Somar classes para ranking do fundo não torna patrimônios fungíveis.

## Limites e controles contratuais: como não comparar errado

- **Limite ou controle contratual, também chamado de guardrail:** teste que limita aquisição, composição, desempenho, reserva ou pagamento e aciona uma consequência definida.
- **Sempre capture:** fórmula, coorte ou janela, data, exclusões, limite, prazo de correção e consequência.
- **Inadimplência na primeira obrigação, ou First Payment Default (FPD):** é indicador de originação e fica na página de desempenho e nas famílias em que é útil, não como métrica estrutural universal.
- **DCV:** não é alias de diluição. A revisão não encontrou expansão ou fórmula recorrente e auditável para essa sigla no corpus; leia a definição do documento antes de usá-la.
- **Índice de refinanciamento:** não tem fórmula canônica no corpus. Pode medir saldo ou operações refinanciadas sobre uma base contratual, mas o numerador e o denominador precisam vir do instrumento específico.
- **Um limite observado:** é exemplo daquela estrutura, não parâmetro de mercado.

## O que o Informe Mensal captura

- **Diretamente ou por aproximação:** PL, composição, faixas de atraso, fluxos, cotas e alguns saldos de liquidez.
- **Exige documento e base operacional:** cobertura contratual, ativos elegíveis ajustados, reservas, cascata de pagamentos, WAL projetado, concentração granular e estado de gatilhos.

Fontes: Resolução CVM 175; padrão do Informe Mensal; documentos primários e metodologia analítica do corpus. Verificação: **16/07/2026**.
