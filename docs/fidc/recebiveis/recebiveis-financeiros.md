# Famílias de recebíveis e diferenças de risco

O rótulo da carteira deve ser lido em três camadas:

- **Segmento oficial da Tabela II do Informe Mensal:** classificação regulatória agregada.
- **Abertura financeira da Tabela II:** detalhamento F1 a F8 quando o bloco Financeiro domina.
- **Taxonomia funcional documental:** descrição da mecânica encontrada no regulamento e nos contratos, como consignado, risco sacado, meios de pagamento ou crédito inadimplido.

- **Natureza das fórmulas:** são referências analíticas, salvo quando o texto diz **contratual**.
- **O contrato prevalece:** um regulamento pode mudar base, janela, exclusões, nível de agregação e consequência.
- **Limite da evidência:** o corpus sustenta a recorrência de elegibilidade, concentração e ordem de recursos, mas não um limite numérico universal.

## <span class="fidc-family-name">Crédito consignado</span>

- **O que gera o pagamento:** o tomador é o devedor; empregador, Instituto Nacional do Seguro Social (INSS) ou ente conveniado normalmente desconta e repassa a parcela.
- **Riscos que vêm primeiro:** margem consignável, vínculo ou benefício, averbação, portabilidade, fraude, fila operacional, convênio e continuidade do repasse.
- **Indicadores prioritários:**
  - **Atraso superior a N dias, ou Inadimplência Over N:** `saldo com atraso superior a N dias / saldo da base`. Mostra o atraso acumulado após o corte e precisa separar falha do tomador de falha de repasse.
  - **Falha de averbação:** `contratos rejeitados ou não averbados / contratos enviados para averbação`. É uma métrica operacional, se a base estiver disponível, e antecipa créditos que podem nascer sem o desconto esperado.
  - **Desvio de repasse:** `(valor esperado descontado - valor conciliado recebido) / valor esperado descontado`. Ajuda a localizar dinheiro retido ou não conciliado pelo agente de repasse.
  - **Concentração por convênio ou pagador:** `exposição ao convênio / carteira elegível`. Uma carteira com muitos tomadores pode depender de um único canal de desconto.
- **Testes, limites contratuais e documentos:** Cédula de Crédito Bancário (CCB), autorização, averbação, cessão ou endosso, regras de portabilidade e conta de recebimento.
- **Por que esses indicadores vêm antes:** o risco operacional do desconto e do repasse pode dominar antes mesmo de a inadimplência econômica do tomador aparecer.

## <span class="fidc-family-name">Crédito pessoal e financiamento digital</span>

- **O que gera o pagamento:** renda e liquidez do tomador, normalmente sem desconto automático ou garantia suficiente para substituir sua capacidade de pagamento.
- **Riscos que vêm primeiro:** seleção, canal, fraude, carteira jovem, renegociação e capacidade de cobrança.
- **Indicadores prioritários:**
  - **Inadimplência na primeira obrigação, ou First Payment Default (FPD):** `exposição inadimplida na primeira obrigação / exposição elegível da coorte`. É convenção operacional; a revisão não localizou definição literal de FPD nos 95 regulamentos vigentes e 52 relatórios de classificação de risco varridos.
  - **Inadimplência por safra:** `saldo em atraso da coorte / exposição da mesma coorte`. Evita comparar uma carteira recém-originada com outra já madura.
  - **Taxa de migração, ou roll rate:** `saldo que migrou da faixa i para a faixa j / saldo inicial na faixa i`. Mostra a direção do atraso.
  - **Taxa de cura:** `saldo que voltou ao estado adimplente / saldo elegível em atraso no início`. Renegociação deve ser identificada à parte.
  - **Recuperação líquida:** `(caixa recuperado - custos de cobrança) / exposição em recuperação`. Mede o resultado depois da inadimplência.
- **Testes, limites contratuais e documentos:** política de crédito, antifraude, pontuação de crédito, ou *score*, exceções, dados usados, canal, CCB, cobrança e critérios de renegociação.
- **Por que esses indicadores vêm antes:** a qualidade da originação aparece por coorte e migração antes de ficar evidente no saldo agregado do fundo.

## <span class="fidc-family-name">Crédito corporativo e empresas de médio porte</span>

- **O que gera o pagamento:** caixa da empresa, fluxo de contrato comercial ou ativo dado em garantia. *Middle market* é o termo da abertura da Tabela II para empresas de médio porte e não define sozinho porte ou qualidade de crédito.
- **Riscos que vêm primeiro:** concentração por grupo, dependência de poucos contratos, vencimento concentrado, garantia, governança financeira e descumprimento cruzado de dívida.
- **Indicadores prioritários:**
  - **Concentração por devedor ou grupo:** `exposição computável ao grupo / base contratual`. É central porque um único evento pode atingir parte material da classe.
  - **Cobertura de ativos:** `ativos elegíveis ajustados / obrigações protegidas`. O contrato deve dizer quais ativos, descontos e passivos entram.
  - **Cobertura do serviço da dívida, ou Debt Service Coverage Ratio (DSCR):** `caixa disponível para a dívida / principal e juros do período`, quando o crédito depende do fluxo de uma empresa ou projeto.
  - **Diluição comercial:** `cancelamentos, devoluções e abatimentos / originação sujeita à diluição`. Importa quando o recebível depende de entrega, aceite ou disputa comercial.
  - **Concentração de vencimentos:** `exposição que vence na janela / carteira`. Ajuda a testar se o caixa do devedor e a amortização das cotas coincidem.
- **Testes, limites contratuais e documentos:** demonstrações, compromissos financeiros, ou *covenants*, garantias, vencimento cruzado, ou *cross-default*, contratos de fornecimento e conta controlada.
- **Por que esses indicadores vêm antes:** a perda tende a ser menos pulverizada e mais sensível a um devedor, contrato ou data.

## <span class="fidc-family-name">Veículos</span>

- **O que gera o pagamento:** renda do tomador; a alienação fiduciária pode criar uma fonte adicional de recuperação se tiver sido constituída e registrada.
- **Riscos que vêm primeiro:** fraude documental, valor e liquidez do bem, seguro, localização, retomada, custo e prazo de venda.
- **Indicadores prioritários:**
  - **Relação entre saldo e valor da garantia, ou Loan-to-Value (LTV):** `saldo devedor / valor elegível do veículo`. Quanto maior a relação, menor a margem econômica para custos e desvalorização.
  - **Over por safra:** `saldo acima do corte de atraso / saldo da safra`. Separa originação recente de carteira madura.
  - **Recuperação líquida do bem:** `(preço de venda - retomada - guarda - venda - tributos) / saldo inadimplido`. O valor de tabela não é recuperação.
  - **Tempo de recuperação:** média ou distribuição dos dias entre inadimplência, retomada e caixa líquido. Proteção sem liquidez pode chegar tarde.
  - **Pré-pagamento:** `principal pago antes do cronograma / saldo elegível`. Afeta receita e vida média.
- **Testes, limites contratuais e documentos:** CCB, registro da garantia, seguro, política de retomada, laudo ou base de valor e critérios de elegibilidade do veículo.
- **Por que esses indicadores vêm antes:** a severidade da perda depende tanto do crédito quanto da execução e liquidez da garantia.

## <span class="fidc-family-name">Imobiliário financeiro</span>

- **O que gera o pagamento:** venda, aluguel, fluxo corporativo ou pagamento do tomador, conforme a operação. As aberturas empresarial e residencial da Tabela II não explicam sozinhas essa fonte.
- **Riscos que vêm primeiro:** estágio de obra, licenças, prioridade da garantia, orçamento, vendas, concentração e descasamento de prazo.
- **Indicadores prioritários:**
  - **Loan-to-Value (LTV), relação saldo-valor:** `exposição / valor elegível do imóvel ou projeto`. O laudo, a data e o desconto precisam ser conhecidos.
  - **Loan-to-Cost (LTC), relação saldo-custo:** `exposição financiada / custo total do projeto`. Ajuda a medir quanto do custo é financiado pela dívida.
  - **Cobertura de fluxo:** `recebíveis ou caixa elegível ajustado / serviço da dívida`. Deve refletir distratos, despesas e prioridade do fluxo.
  - **Avanço físico versus financeiro:** `percentual concluído / percentual do orçamento consumido`. Um projeto pode gastar mais rápido do que constrói.
  - **Descasamento de prazo, ou gap:** `vida média dos ativos - prazo médio das obrigações`. Sinaliza necessidade de refinanciamento ou venda de ativo.
- **Testes, limites contratuais e documentos:** matrícula, registro, avaliação, orçamento, medição de obra, conta vinculada, licença e contrato de venda ou locação.
- **Por que esses indicadores vêm antes:** valor de garantia sem prioridade, liquidez ou conclusão de obra pode não proteger a cota no momento necessário.

## <span class="fidc-family-name">Cartão de crédito e meios de pagamento</span>

- **O que gera o pagamento:** depende do direito cedido. Pode vir do portador, emissor, credenciador, subcredenciador, estabelecimento ou de uma agenda de liquidação.
- **Riscos que vêm primeiro:** cancelamento, contestação ou reversão de transação, chamada de *chargeback*, conciliação, antecipação, registro, agenda, arranjo e concentração operacional.
- **Indicadores prioritários:**
  - **Diluição:** `cancelamentos + devoluções + descontos + disputas + chargebacks / volume sujeito a esses eventos`. Chargeback é a reversão ou contestação de uma transação.
  - **Diferença de conciliação:** `valor esperado - valor liquidado e identificado`, em moeda e como percentual da agenda. Mostra descasamento operacional antes de classificá-lo como perda.
  - **Concentração no arranjo ou participante:** `exposição ao participante / carteira elegível`. A pulverização por transação pode esconder dependência de uma infraestrutura.
  - **Atraso e refinanciamento:** use coorte, janela e base definidas somente quando o produto inclui financiamento ao portador.
  - **Prazo de liquidação:** distribuição dos dias entre transação, agenda e caixa. Antecipação altera custo e duração.
- **Testes, limites contratuais e documentos:** contrato do arranjo, registro da agenda, regras de *chargeback*, conta de recebimento, cessão e identificação do devedor do direito concreto.
- **Siglas contratuais:** **DCV não é alias de diluição**. Nenhuma expansão recorrente da sigla foi identificada nos 95 regulamentos vigentes e 52 relatórios de classificação de risco varridos. Só use DCV quando o próprio documento definir o índice. O mesmo cuidado vale para “índice de refinanciamento”.
- **Por que esses indicadores vêm antes:** o recebível pode ser reduzido ou desviado por evento operacional sem inadimplência tradicional do pagador.

## <span class="fidc-family-name">Risco sacado e financiamento de fornecedores</span>

- **O que gera o pagamento:** obrigação comercial do comprador perante o fornecedor, financiada ou antecipada dentro de um programa. *Supplier finance* é o termo em inglês para financiamento de fornecedores.
- **Riscos que vêm primeiro:** reconhecimento da dívida, entrega, aceite, devolução, prazo estendido e concentração no comprador âncora.
- **Indicadores prioritários:**
  - **Concentração no comprador:** `exposição ao comprador ou grupo / carteira elegível`.
  - **Diluição comercial:** `devoluções + descontos + disputas / compras ou recebíveis sujeitos`.
  - **Exceção de aceite:** `títulos sem aceite ou confirmação válida / títulos testados`.
  - **Extensão de prazo:** `prazo atual - prazo original`, acompanhada em dias e por coorte.
  - **Cobertura de ativos:** `recebíveis elegíveis ajustados / obrigações protegidas`.
- **Testes, limites contratuais e documentos:** pedido, nota fiscal, prova de entrega, aceite, programa de fornecedores, cessão e remédios por vício.
- **Por que esses indicadores vêm antes:** muitos fornecedores não eliminam a concentração econômica em um único comprador.

## <span class="fidc-family-name">Créditos inadimplidos</span>

- **O que é:** **Non-Performing Loan (NPL)** é crédito inadimplido ou problemático segundo a definição usada. É taxonomia funcional, não segmento oficial da Tabela II.
- **Riscos que vêm primeiro:** documentação, prescrição, litigância, garantia, prioridade, custo, tempo de cobrança e preço de aquisição.
- **Indicadores prioritários:**
  - **Recuperação sobre preço:** `caixa recuperado líquido / preço de aquisição da carteira`. Mede retorno operacional do comprador, mas não a recuperação do devedor sobre o valor de face.
  - **Recuperação sobre exposição:** `caixa recuperado líquido / saldo ou valor de face definido`. Use a mesma base entre carteiras.
  - **Tempo até caixa:** média, mediana e distribuição dos meses entre aquisição, ação de cobrança e recebimento.
  - **Custo de cobrança:** `custos jurídicos e operacionais / caixa recuperado bruto`.
  - **Concentração por processo, devedor ou garantia:** `exposição ao fator / base da carteira`.
- **Testes, limites contratuais e documentos:** cadeia dominial, processo, prescrição, garantia, laudo, honorários, contrato de cobrança e critérios de baixa.
- **Por que esses indicadores vêm antes:** FPD e originação perdem relevância depois da compra de uma carteira já inadimplida; recuperação líquida, custo e duração passam ao centro.

## <span class="fidc-family-name">Comercial, industrial e serviços</span>

- **O que gera o pagamento:** compra de mercadoria, produção ou prestação de serviço.
- **Indicadores prioritários:**
  - **Diluição:** `cancelamentos, devoluções, descontos e disputas / originação sujeita`.
  - **Concentração de compradores:** `exposição ao comprador ou grupo / carteira elegível`.
  - **Atraso por safra ou cliente:** `saldo vencido / base comparável`.
  - **Exceção documental:** `itens sem nota, entrega, aceite ou contrato válido / itens testados`.
- **Por que esses indicadores vêm antes:** a obrigação pode ser reduzida por falha de entrega ou disputa antes de se transformar em inadimplência simples.

## <span class="fidc-family-name">Agronegócio</span>

- **O que gera o pagamento:** produção, venda, armazenagem ou fluxo rural, frequentemente documentado por **Cédula de Produto Rural (CPR)**.
- **Indicadores prioritários:**
  - **Cobertura da garantia:** `valor elegível após desconto / exposição protegida`.
  - **Concentração por cultura, região e safra:** `exposição ao fator / carteira elegível`.
  - **Cobertura de produção:** `produção ou estoque elegível / obrigação física ou financeira`.
  - **Descasamento de calendário:** diferença entre colheita, venda, vencimento do crédito e amortização das cotas.
- **Por que esses indicadores vêm antes:** clima, commodity, armazenagem e ciclo produtivo podem atingir vários devedores ao mesmo tempo.

## <span class="fidc-family-name">Imobiliário, factoring, setor público e ações judiciais</span>

- **Imobiliário como segmento oficial:** avalie registro, prioridade, obra, venda, locação, LTV, cobertura de fluxo e prazo. Não confunda automaticamente com as aberturas imobiliárias do bloco Financeiro.
- **Fomento mercantil, reportado como Factoring:** confirme a natureza reportada, coobrigação, concentração, diluição e atraso. O nome da atividade não prova direito de regresso.
- **Setor público:** acompanhe ente e órgão pagador, empenho, liquidação, orçamento, cessão, precatório e duração. Concentração no poder público não elimina risco jurídico e temporal.
- **Ações judiciais:** acompanhe estágio, recurso, trânsito, probabilidade de recebimento, honorários, prazo, cessão e concentração por tese ou devedor.
- **Fórmulas comuns:** `exposição ao fator / carteira`, `caixa recuperado líquido / base definida` e `prazo esperado - prazo das obrigações`, sempre com a base declarada.

## <span class="fidc-family-name">Marcas e patentes</span>

- **O que analisar:** titularidade, validade, licença, concentração no pagador, fluxo de remunerações pelo uso da propriedade intelectual, ou *royalties*, e método de avaliação.
- **Indicadores possíveis:** `royalties líquidos / obrigações do período`, concentração por licenciado e variação do valor avaliado.
- **Limitação do corpus:** esse segmento oficial não tinha população classificável na competência 202605. O glossário não atribui prevalência contratual a essa família.

## O que o Informe Mensal não resolve

- A Tabela II e as aberturas financeiras mostram valores agregados.
- Distribuição por idade do atraso, provisão e fluxos ajudam a localizar desempenho, mas não revelam devedor econômico, garantia, coobrigação, canal, convênio, contestação de transação, custo de recuperação ou regra do limite contratual.
- Fórmula, limite, frequência, correção e consequência de um teste exigem regulamento, instrumento e base operacional.

Fontes: **Resolução da Comissão de Valores Mobiliários (RCVM) 175**, Anexo Normativo II; padrão oficial do Informe Mensal; documentos primários e metodologia do corpus de 100 fundos. Verificação: **16/07/2026**.
