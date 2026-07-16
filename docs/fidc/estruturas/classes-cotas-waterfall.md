# Fundo, classe, subclasse, série, cota e cascata de pagamentos

## A hierarquia da RCVM 175

Resolução da Comissão de Valores Mobiliários (RCVM) 175:

- **Fundo**
  - É o veículo e o nível de governança. Pode abrigar uma ou mais classes da mesma categoria.
  - **Classe A: patrimônio segregado A**
    - Reúne ativos, passivos, despesas e cotistas vinculados à Classe A.
    - **Subclasse sênior**
      - Tem a prioridade definida no regulamento.
      - **Série 1**, se admitida
        - **Cotas da Série 1:** frações patrimoniais detidas pelos investidores.
      - **Série 2**, se admitida
        - **Cotas da Série 2**
    - **Subclasse mezanino**
      - Subordina-se à sênior e tem prioridade sobre a camada indicada abaixo dela.
      - Em classe fechada, suas cotas também podem ser organizadas em séries quando as condições normativas e documentais forem atendidas.
    - **Subclasse subordinada**
      - Fica abaixo das demais nos direitos definidos pelo regulamento.
  - **Classe B: patrimônio segregado B**
    - Possui carteira e obrigações próprias. Não cobre automaticamente a Classe A.

Essa hierarquia serve para responder **qual carteira gera o caixa**, **qual patrimônio responde pela dívida** e **qual cota recebe resultado ou perda em cada ordem**.

## Subordinação vem primeiro na análise

- **Sênior:** não se subordina às demais subclasses para amortização, resgate e apropriação de resultados, conforme o regulamento.
- **Mezanino:** fica abaixo da sênior e acima de outra subclasse subordinada especificada.
- **Subordinada:** fica abaixo das demais nos direitos definidos.
- **Júnior:** nome de mercado para a camada mais subordinada. Confirme a designação jurídica no documento.

O **índice de subordinação contratual** é a relação mínima, em percentual, entre o valor computável da subclasse indicada e o **patrimônio líquido (PL)** da classe:

`índice de subordinação = valor computável da subclasse / PL da classe`

O documento precisa definir **qual subclasse**, **qual valor**, **qual data**, **qual frequência** e **qual consequência**. A aproximação do painel:

`(PL mezanino + PL subordinado residual) / PL total reportado`

é uma convenção analítica. Pode divergir do contrato por séries, ajustes, valores negativos, classes múltiplas e regras específicas.

## Série não é subclasse

- **Subclasse:** muda a posição econômica ou política das cotas dentro da classe.
- **Série:** organiza cotas de uma subclasse admitida em classe fechada e pode diferenciar prazo, amortização ou índice referencial nas condições do Anexo II.
- **Emissão:** ato que cria determinado lote de cotas. Não é um nível patrimonial.
- **Oferta:** processo de distribuir essas cotas. Também não é um nível patrimonial.
- **Tranche:** rótulo econômico. Antes de usar, identifique se o documento está falando de subclasse, série, emissão ou faixa analítica.

## Três ordens diferentes

- **Cascata de pagamentos, ou waterfall de caixa:** diz como o caixa disponível paga despesas, reservas, remuneração, amortização e outras obrigações.
- **Apropriação de resultados:** diz como valorização e desvalorização são atribuídas às subclasses.
- **Absorção de perdas:** diz como a perda reduz o valor patrimonial de cada camada.

Essas ordens se relacionam, mas não são iguais. Subordinação não permite afirmar que “os primeiros X% de perda” serão sempre absorvidos antes da sênior: despesas, composição da carteira, índice vigente e regras de caixa alteram o efeito.

## Tradução do regime anterior

| Documento anterior pode dizer | Função provável | Leitura sob a arquitetura atual |
|---|---|---|
| **classe ou cotas seniores** | camada prioritária | subclasse sênior, após conferir a adaptação |
| **cotas subordinadas mezanino** | camada intermediária | subclasse mezanino |
| **cotas subordinadas júnior** | camada residual | subclasse subordinada |
| **série sênior** | diferenciação de prazo ou remuneração | série dentro da subclasse admitida no documento vigente |
| **fundo como único patrimônio** | conjunto patrimonial anterior | pode corresponder hoje a uma classe; não presuma |

## Perguntas para o analista

- **Proteção:** qual é a subordinação contratual e qual é a subordinação efetiva hoje?
- **Cobertura:** ativos elegíveis e reservas cobrem passivos, despesas e juros acumulados?
- **Tempo:** qual série amortiza primeiro e a carteira produz caixa na mesma data?
- **Liberação:** a camada subordinada pode ser amortizada antes do fim da estrutura?
- **Gatilhos:** quais eventos retêm caixa, encerram reinvestimento ou mudam prioridade?
- **Nova emissão:** novas cotas diluem proteção, votos ou remuneração de alguma camada?

**Subordinação é proteção de crédito, não caixa.** Uma classe pode ter colchão patrimonial e ainda enfrentar falta de liquidez na data de pagamento.

## Informe Mensal e documentos

- **O reporte ajuda a observar:** patrimônio líquido, valores de cotas e movimentações no nível informado.
- **A Tabela X.2 pode listar:** subclasses e séries. Essas linhas não são novos fundos.
- **O regulamento e o instrumento de emissão definem:** cascata de pagamentos, índice contratual, remuneração, amortização, correção de desenquadramento, votos e prioridade.

Base normativa: Resolução CVM 175, Parte Geral, arts. 5º e 14; Anexo Normativo II, arts. 2º, 8º e 13. Verificação: **16/07/2026**.
