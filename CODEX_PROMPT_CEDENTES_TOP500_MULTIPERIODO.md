# Incorporar cedentes com CNAE e segmento, no Top 500 e em quatro competências

## O que já existe e o que muda

O repositório já tem a triagem de cedentes de uma competência só:
`services/industry_cedente_triage.py` (`DEFAULT_COMPETENCE = "202606"`,
`DEFAULT_CUTOFF_RANK = 437`), `scripts/build_fidc_cedente_triage.py`, os artefatos em
`data/industry_study/cedente_triage/202606/` e três abas no workbook. Os dois parâmetros já estão
isolados no topo do serviço — a extensão é natural, não é reescrita.

Três mudanças de escopo:

1. **Corte passa de 437 para 500 fundos.** É critério redondo e defensável em comitê.
2. **Quatro competências:** `202312`, `202412`, `202512`, `202606`.
3. **Enriquecimento cadastral do cedente** — CNAE, seção CNAE, UF, município, porte, capital
   social, Simples/MEI — mais duas colunas derivadas: **Natureza do cedente** e **Segmento**.

O material de referência com tudo isso pronto está em `FIDC_Top500_Cedentes_Segmento_2023_2026.xlsx`,
na raiz do repositório. Use como especificação de conteúdo e como gabarito de conferência: os
números que você produzir têm que bater com os de lá.

## Onde buscar cada dado

**Informe Mensal da CVM.** As competências antigas não estão no diretório corrente — 2023 e 2024
saem dos arquivos anuais:

```
https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/HIST/inf_mensal_fidc_2023.zip
https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/HIST/inf_mensal_fidc_2024.zip
https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202512.zip
https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_202606.zip
```

Tabela I traz até 18 identificadores de cedente por fundo — `TAB_I2A12_CPF_CNPJ_CEDENTE_1..9` para
direitos creditórios com retenção de risco e `TAB_I2B12_*` para sem retenção, cada um com o
`PR_CEDENTE_i` correspondente. Tabela IV traz o PL. O layout de colunas é o mesmo nas quatro
competências.

**Cadastro do cedente.** Duas fontes, use na ordem:

- Dados Abertos do CNPJ da Receita Federal, em massa, quando precisar resolver muitos CNPJ. O
  diretório fica em `https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/`. Os
  blocos que interessam são Empresas (razão social, capital social, porte), Estabelecimentos (CNAE
  principal, UF, município, situação cadastral, matriz/filial), Simples e a tabela de CNAEs. São
  cerca de 6,6 GB no total, latin-1, delimitador `;`.
- BrasilAPI (`https://brasilapi.com.br/api/cnpj/v1/{cnpj}`) quando o incremento for pequeno. Ela
  aguenta uma requisição a cada ~2 segundos sem estourar rate limit; acima disso devolve 429.

O recorte já resolvido dos cedentes deste universo está em `cadastro_receita.json` e
`cadastro_extra.json` no material de referência — 498 cedentes distintos, 478 resolvidos.

## Três armadilhas que você precisa tratar

**1. CNPJ fictício.** Em dez/23 e dez/24 uma parte grande do campo de cedente vem preenchida com
`00.000.000/0000-00` ou `99.999.999/9999-99` — são 674 e 457 vínculos no Top 500. É preenchimento
de fachada: o fundo declara alguma coisa sem identificar ninguém. Detecte por dígito repetido
(`len(set(digitos)) == 1 and digitos[0] in '09'`), marque como segmento **"Não informado"** e
exclua de qualquer contagem de cobertura.

O efeito é grande: sem o desconto, dez/23 aparentaria 260 fundos declarando cedente; o número real
é 188. E a narrativa inverte — com o desconto, a transparência **melhora** até 2025 e recua em 2026,
em vez de cair desde 2023.

**2. Zero à esquerda comido.** Alguns CNPJ chegam com 13 dígitos porque a CVM perdeu o zero
inicial. O preenchimento com `zfill(14)` é inequívoco e recupera o cadastro — é assim que a Cielo
(`01.027.058/0001-91`) deixa de aparecer como documento irregular.

**3. O percentual declarado não sustenta rateio.** `PR_CEDENTE_i` soma, por fundo, mediana de 50%
e média de 148%, com 45 fundos acima de 105%. **Não pondere PL por esse campo.** Para atribuir PL a
segmento, use o cedente dominante (maior percentual declarado; empate pela ordem), que fecha 100%.

## A coluna Segmento

Cinco faixas, aplicadas nesta ordem, com uma coluna **Critério** ao lado registrando qual regra
disparou em cada linha:

1. **IFs** — nome contendo QI, BMP, MAREE, MULTIPLIKE, PICPAY, LISTO, IFOOD PAGO, CREDSYSTEM,
   PARATI, TRADEMASTER, CAPITAL CONSIG, MEUCASHCARD; ou token financeiro (`SCD`, `IP`, `Banco`,
   `Sociedade de Crédito`, `Instituição de Pagamento`, `Securitizadora`, `Financeira`); ou CNAE em
   64/65/66. **Exceção obrigatória: CNAE 6462 e 6463 NÃO contam** — são holdings de instituições
   *não*-financeiras, e sem essa exceção J&F, Philco e Conasa Infraestrutura viram banco.
2. **Agro** — nome com Rural, Agro, Fertilizante, Agrícola, Agropecuária, Usina, Açucareira,
   Defensivo, Semente, Cereais; ou CNAE da seção A, ou de defensivos, adubos e açúcar.
3. **Infra e Energia** — nome com Energia, Infraestrutura, Elétric, Saneamento, Transmissão,
   Petróleo, Combustível, Gás, Rodovia, Ferrovia, Portuári, Aeroport, Telecom; ou CNAE de
   eletricidade, saneamento, extrativa, transporte e telecom. Vem **antes** de Large de propósito:
   é o balde mais específico, e uma distribuidora de energia grande dispararia os dois.
4. **Large** — grupo grande ou multinacional identificado pelo nome, ou CNAE de montadora, ou
   capital social ≥ R$ 300 mi. O critério de capital fica explícito na coluna Critério.
5. **Potencial Middle** — resíduo.

Escritório de advocacia (CNAE 6911) sai para "Não classificado" com o motivo escrito: é cessão de
precatório ou honorário, não empresa operacional.

**Potencial Middle é resíduo, não confirmação.** Não é atestado de faturamento entre R$ 30 e
500 milhões — nenhuma fonte pública traz faturamento. Registre isso onde o dado aparecer.

A coluna **Natureza do cedente** (Operacional, Holding/participação, Fundo/securitizadora,
Instituição financeira, Escritório de advocacia, Ente público) é derivada do CNAE e serve para
filtrar veículo de empresa operacional antes da triagem. Dentro de Potencial Middle isso importa:
holding não tem faturamento próprio para avaliar.

## O que precisa existir ao final

**Dados versionados**, seguindo o padrão que você já usa em `cedente_triage/`, com uma pasta por
competência e manifesto próprio. Inclua a curva de cobertura e o log de exclusões.

**No workbook Dados da Indústria**, as abas de cedente passam a trazer competência, CNPJ do cedente
em dígitos puros e formatado, o bloco cadastral completo e as colunas Natureza e Segmento. Decida
se substitui as três abas atuais ou acrescenta — o critério é o leitor não ficar com duas versões
divergentes do mesmo fato.

**No Streamlit**, dentro da área de Indústria: a evolução do mix de segmento nas quatro
competências, a curva de cobertura do Top 500 sobre o PL da indústria, e a tabela de cedentes
filtrável por competência, segmento, natureza, UF e seção CNAE. Os downloads seguem o padrão dos
que já existem.

**No PPTX**, avalie onde cabe sem inchar o deck. Duas leituras se sustentam sozinhas: a composição
do PL do Top 500 por segmento do cedente, e a queda da cobertura de 87,5% para 72,6% enquanto a
indústria dobrava. Você decide se vira slide, se entra em slide existente, ou se fica só no
workbook — o deck já tem 37 páginas e não precisa de mais por obrigação.

## Números para conferir

O corte de 500 fundos cobre 87,5% do PL em dez/23, 81,9% em dez/24, 73,5% em dez/25 e 72,6% em
jun/26. O PL do 500º fundo sobe de R$ 138 mi para R$ 379 mi. Fundos que identificam cedente de
verdade: 188, 146, 205 e 172. Cedentes distintos nas quatro competências: 498, dos quais 478
resolvidos no cadastro.

Em jun/26, pela atribuição ao cedente dominante: IFs R$ 111,3 bi (41,2% do PL identificado), Infra
e Energia R$ 73,1 bi (27,1%), Large R$ 47,8 bi (17,7%), Agro R$ 23,8 bi (8,8%), Potencial Middle
R$ 11,5 bi (4,3%). Fundos sem cedente declarado somam R$ 454,9 bi, ou 62,7% do Top 500 — por isso
todo gráfico de mix precisa deixar o denominador visível.

Se os seus números divergirem materialmente destes, pare e reporte a divergência antes de publicar.

## Não quebrar o que está de pé

Rode a suíte antes e guarde a linha de base. Nenhum teste existente pode passar a falhar. O
`DEFAULT_CUTOFF_RANK` muda de 437 para 500 — qualquer teste ou rótulo que cite 437 precisa
acompanhar, inclusive os nomes de arquivo em `cedente_triage/202606/`.

Como a mudança altera número publicado, gere um diff antes e depois da cobertura e do mix por
segmento em jun/26, e explique cada diferença que não seja consequência direta do corte 437 → 500.

## Delegação

Você fica com: o desenho do esquema multi-competência, a decisão sobre substituir ou acrescentar
abas, onde entra no Streamlit e se entra no PPTX.

**Effort alto** — o pipeline de ingestão das quatro competências com o tratamento das três
armadilhas; e o diff de cobertura e mix antes/depois.

**Effort médio** — o enriquecimento cadastral e as duas colunas derivadas; a materialização dos
artefatos versionados; os componentes de Streamlit.

**Effort baixo, Luna e Terra** — parametrizar `DEFAULT_CUTOFF_RANK` e renomear os artefatos de 437
para 500; normalizar CNPJ para 14 dígitos com zero à esquerda em todos os ETLs; escrever os textos
de Leia-me e as notas de limitação; conferir formatação, acentuação e mojibake; rodar a suíte.
