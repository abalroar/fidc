# Atraso, provisão, perda, recuperação e baixa contábil

Para uma carteira de crédito em curso, leia nesta ordem:

1. **atraso, distribuição por idade e Over N** para medir o estoque atual;
2. **migração, cura e renegociação** para entender a direção;
3. **safra e inadimplência na primeira obrigação, ou First Payment Default (FPD)**, para testar a qualidade da originação;
4. **provisão e perda esperada** para avaliar o reconhecimento prospectivo;
5. **perda realizada e baixa** para reconciliar o impacto efetivo;
6. **recuperação** para medir o caixa após a inadimplência;
7. **cobertura de provisão** como razão auxiliar.

Em **Non-Performing Loan (NPL)**, ou crédito já inadimplido, recuperação líquida, custo e tempo podem vir antes de FPD.

## 1. Atraso, distribuição por idade e Over N

- **Atraso:** diferença entre a data de vencimento e a data de pagamento.
- **Inadimplência:** classificação de não pagamento segundo uma regra definida.
- **Fórmula por faixa:** `saldo vencido na faixa / base definida`.
- **Por que importa:** mostra a gravidade e a idade do estoque problemático.
- **O que declarar:** saldo nominal, contábil, presente ou devedor; parcela ou contrato; carteira total, elegível, vencida ou safra.

### Distribuição por idade do Informe Mensal

**Distribuição por idade**, conhecida no mercado como *aging*, é a abertura do saldo vencido por idade do atraso:

1. até 30 dias;
2. 31 a 60 dias;
3. 61 a 90 dias;
4. 91 a 120 dias;
5. 121 a 150 dias;
6. 151 a 180 dias;
7. 181 a 360 dias;
8. 361 a 720 dias;
9. 721 a 1.080 dias;
10. acima de 1.080 dias.

Uma faixa ausente não deve ser preenchida como zero sem regra explícita.

### Inadimplência Over N

- **O que significa:** saldo com atraso superior ao corte N.
- **Fórmula:** `Over N = saldo com atraso superior a N dias / base definida`.
- **Por que importa:** agrega todas as faixas depois do corte e facilita comparação temporal.
- **Limitação:** “superior a N” pode incluir ou excluir o próprio dia N; o documento deve esclarecer. Over é cumulativo e não é uma faixa isolada.

## 2. Migração, cura e renegociação

- **Taxa de migração, ou roll rate:** `saldo que migrou do estado i para o estado j / saldo inicial no estado i`. Mostra se o atraso está piorando ou melhorando.
- **Taxa de cura:** `saldo que voltou ao estado adimplente / saldo elegível em atraso no início`. Mede regularização.
- **Renegociação:** deve ser identificada separadamente. Alterar vencimento ou contrato pode produzir cura aparente sem pagamento integral.
- **Por que importa:** o mesmo Over pode esconder carteira estabilizando ou migrando rapidamente para faixas piores.

## 3. Safra e FPD

- **Safra:** grupo de créditos originados no mesmo período; *vintage* é o termo em inglês usado para essa coorte.
- **Inadimplência por safra:** `saldo em atraso da coorte / exposição da mesma coorte`.
- **Inadimplência na primeira obrigação, ou First Payment Default (FPD):** atraso ou inadimplência na primeira obrigação da coorte, segundo critério definido.
- **Fórmula de FPD:** `exposição inadimplida na primeira obrigação / exposição elegível da coorte`.
- **Por que importa:** sinaliza fraude, seleção ruim, falha de ativação ou deterioração muito precoce.
- **Limitação:** coorte, primeira obrigação, janela e critério de inadimplência precisam ser definidos. A revisão não localizou definição literal de FPD nos 95 regulamentos vigentes e 52 relatórios de classificação de risco varridos; a fórmula é convenção operacional do glossário.

## 4. Provisão e perda esperada

### Provisão ou redução ao valor recuperável

- **O que é:** ajuste contábil acumulado para refletir perda estimada conforme política e norma aplicáveis.
- **Índice:** `provisão ou redução acumulada / exposição bruta definida`.
- **Por que importa:** antecipa no patrimônio uma estimativa de perda que ainda pode não ter virado baixa ou caixa.
- **O que não é:** caixa reservado, perda necessariamente realizada ou sinônimo automático de perda esperada.
- **Termo legado:** **Provisão para Devedores Duvidosos (PDD)** pode aparecer em documentos e sistemas; confira a conta e a política usada.

### Perda esperada

- **O que é:** estimativa prospectiva de perda para modelo e horizonte definidos.
- **Forma conceitual:** `perda esperada = PD × LGD × EAD`.
- **Probability of Default (PD):** probabilidade de inadimplência.
- **Loss Given Default (LGD):** perda em caso de inadimplência.
- **Exposure at Default (EAD):** exposição no momento da inadimplência.
- **Por que importa:** separa probabilidade, severidade e exposição.
- **Limitação:** a forma multiplicativa não é fórmula universal da contabilidade de toda carteira. Matriz de migração, fluxo descontado e outros modelos podem ser usados.

## 5. Perda realizada e baixa

- **Perda realizada:** impacto econômico reconhecido conforme a política e a reconciliação contábil.
- **Baixa contábil, ou write-off:** retirada ou redução do ativo quando o critério de baixa é atendido. A cobrança pode continuar depois da baixa.
- **Por que importa:** reconcilia o que deixou de ser estimativa e virou impacto reconhecido.
- **Limitação:** queda do **patrimônio líquido (PL)** subordinado não prova baixa; despesas, amortizações e marcação também alteram o patrimônio.

## 6. Recuperação

- **Fórmula:** `caixa recuperado líquido / base de créditos em recuperação`.
- **O que declarar:** coorte, exposição de origem, custos, horizonte e desconto temporal.
- **Por que importa:** mede quanto da exposição inadimplida voltou como caixa depois da cobrança.
- **Limitação:** recuperação bruta de NPL, recuperação líquida de atraso recente e recuperação sobre preço de aquisição respondem a perguntas diferentes.

## 7. Cobertura de provisão

- **Fórmula:** `provisão acumulada / saldo vencido na base definida`.
- **Uso:** compara estoque reconhecido de provisão com uma faixa de atraso.
- **Limitação:** acima de 100% não prova conservadorismo; abaixo de 100% não prova insuficiência. Garantia, cura, recuperação, horizonte e política contábil mudam a interpretação.

## O que o Informe Mensal captura

- **Entrega:** faixas de atraso e valores contábeis agregados úteis para séries históricas.
- **Não entrega sozinho:** política contábil completa, PD, LGD, EAD, coorte de FPD, roll rate, cura, renegociação, critério de baixa ou recuperação líquida.
- **Documentos necessários:** demonstrações e notas para política contábil; regulamento para gatilhos; relatórios operacionais e de classificação de risco para safras, cobrança e premissas.

Fontes: **Instrução da Comissão de Valores Mobiliários (CVM) 489** e orientações oficiais; padrão do Informe Mensal; demonstrações, documentos primários e metodologia analítica da revisão. Verificação: **16/07/2026**.
