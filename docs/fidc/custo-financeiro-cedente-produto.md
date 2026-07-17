# Custo financeiro do cedente como produto

## Objetivo

Generalizar a prova de conceito criada para a CloudWalk sem alterar o motor
financeiro já validado. A solução deve permitir que um analista calcule o custo
de funding de:

1. CloudWalk, sempre como preset inicial;
2. uma carteira já cadastrada em Dados de Carteira;
3. um conjunto avulso de um ou mais CNPJs.

O spread CDI+ deve vir automaticamente da curadoria por série quando estiver
disponível. O analista pode preencher uma lacuna ou sobrescrever a curadoria na
simulação. A taxa documental continua visível para auditoria.

## Diagnóstico do fluxo anterior

O núcleo matemático já recebia uma lista de `FundingLine` e, portanto, não era
intrinsecamente CloudWalk. O acoplamento estava nos pontos de entrada e saída:

- CSV de emissões fixo em `cloudwalk_cotas_emissoes_pagamentos.csv`;
- editor de spreads montado sempre a partir desse CSV;
- CNPJs do IME e do waterfall inferidos apenas dessas linhas;
- títulos, metodologia e arquivos de exportação com nome CloudWalk;
- cache do Streamlit sem uma identidade explícita do escopo;
- override com fallback por nome de classe, sujeito a vazamento entre fundos;
- remoção de um override persistido incapaz de restaurar a curadoria.

A carteira CloudWalk usada como referência contém 11 CNPJs e 27 registros. Há
19 séries ativas remuneradas: 15 têm CDI+ documental e quatro Big Picture usam
os overrides legados do JSON. Esse conjunto permanece como teste de regressão.

## Arquitetura implementada

### Escopo

`services/financial_cost_scope.py` introduz `FinancialCostScope`, com:

- `kind`: `cloudwalk`, `portfolio` ou `cnpjs`;
- `label`: nome exibido e usado nos exports;
- `cnpjs`: cesta normalizada e deduplicada;
- `fund_names`: nomes conhecidos no preset ou na carteira;
- `emissions_path`: base fixa apenas para o preset de sistema;
- `signature`: hash estável do universo selecionado.

A CloudWalk é construída diretamente do CSV curado e não depende de uma
carteira persistida continuar disponível. Isso preserva o caso original mesmo
quando o backend de carteiras estiver vazio ou temporariamente indisponível.

### Resolução de curadoria

Para carteiras e CNPJs avulsos, a resolução reutiliza
`services/regulatory_profiles.py`. A ordem de fontes é:

1. perfil CSV dedicado e curado para o CNPJ;
2. base `all_fidcs` de triagem estruturada;
3. conhecimento regulatório heurístico em JSON, quando não existe perfil CSV.

O resultado inclui uma tabela de cobertura por fundo com:

- tipo de perfil;
- séries localizadas;
- séries ativas utilizáveis;
- spreads automáticos e pendentes;
- registros ambíguos bloqueados;
- arquivos-fonte e status operacional.

O fingerprint dos arquivos de curadoria participa da chave de cache junto com
a assinatura do escopo. Trocar a carteira ou atualizar uma fonte não reaproveita
um resultado anterior indevidamente.

### Identidade e conflitos de série

A identidade legada disponível é `CNPJ|texto da série`. Ela é suficiente para
a curadoria limpa da CloudWalk, mas perfis de triagem podem conter eventos
históricos, rerratificações ou emissões diferentes com o mesmo texto.

A regra segura da primeira versão é:

- duplicatas integralmente idênticas podem ser colapsadas;
- duas linhas diferentes com o mesmo `CNPJ|série` são tratadas como ambíguas;
- todas as linhas dessa chave são bloqueadas do cálculo;
- a cobertura mostra a quantidade bloqueada e a estimativa é identificada como
  parcial quando ainda houver outras séries calculáveis.

O sistema não escolhe a linha "mais completa" e não soma eventos conflitantes.
Para eliminar essa limitação de forma definitiva, a curadoria precisa fornecer
`series_id`, status do registro, vigência e identificador do evento documental.

### Spread documental, manual e efetivo

Cada `FundingLine` preserva separadamente:

- `curated_spread_aa`;
- `manual_spread_aa`;
- `spread_aa`, que é o valor efetivo;
- `spread_source`.

A precedência operacional é:

1. valor manual da sessão por `CNPJ|série`;
2. override persistido por `CNPJ|série`, usado para inicializar o preset;
3. CDI+ parseado da remuneração documental;
4. pendente, sem assumir spread zero.

Ao limpar a célula manual e atualizar a estimativa, o estado da sessão guarda a
remoção. A taxa efetiva volta à curadoria. Se não houver taxa curada, a série
volta a ficar pendente e sai dos totais.

Overrides por nome de classe e por CNPJ inteiro não são usados na interface do
produto, pois um mesmo fundo pode ter sênior e mezanino com spreads diferentes,
e fundos distintos frequentemente repetem nomes como "1ª série sênior".

### Motor, IME e waterfall

O motor de custo continua em `services/cloudwalk_financial_cost.py` para manter
compatibilidade com scripts e imports legados. A função pública
`funding_lines_from_frame()` permite alimentar o mesmo motor com qualquer
DataFrame curado.

O cache do motor recebe as próprias `FundingLine`, os CNPJs do escopo e os nomes
dos fundos. Isso isola resultados entre seleções.

O IME é carregado para todos os fundos selecionados, para que a cobertura não
desapareça. Entretanto, caixa/LFT de um fundo sem nenhuma série precificada não
é abatido do custo líquido. O motivo fica registrado no snapshot.

A competência IME agora respeita `competência <= data snapshot`. Uma simulação
histórica não usa caixa de um informe futuro. O waterfall recebe todos os CNPJs
do escopo e mantém seus estados de ausência de cache.

## Experiência do analista

### Primeiro acesso

O modo selecionado é `CloudWalk (padrão)`. O cálculo original é carregado com:

- 11 fundos;
- 27 registros documentais;
- 19 séries ativas;
- 15 taxas documentais;
- quatro overrides persistidos;
- nenhuma série ativa sem CDI+.

### Carteira cadastrada

A lista vem do mesmo `PortfolioStore` usado em Dados de Carteira. A carteira
CloudWalk é escolhida como default dentro do seletor quando sua cesta coincidir
com o preset, independentemente da ordenação alfabética do store.

Falha no store não bloqueia o preset de sistema nem a seleção manual.

### CNPJs específicos

O campo aceita CNPJs mascarados ou somente com dígitos, separados por espaço,
vírgula, ponto e vírgula ou quebra de linha. O fluxo:

- valida os dígitos verificadores;
- mostra entradas inválidas em vez de ignorá-las;
- remove duplicados preservando a ordem;
- limita o escopo a 20 fundos.

### Cobertura antes dos KPIs

Antes das datas e dos resultados, a tela informa quantos fundos têm séries,
quantas séries ativas existem e quantas taxas vieram automaticamente. O detalhe
por fundo fica em um expander auditável.

Estados tratados explicitamente:

- sem perfil de séries;
- documentos encontrados, mas sem série remunerada e volume utilizável;
- série com spread pendente;
- perfil de triagem ou heurístico;
- identidade de série ambígua;
- IME ausente;
- cálculo parcial.

### Editor por série

O bloco `Taxas CDI+ por série` mostra:

- FIDC e CNPJ;
- série;
- CDI+ da curadoria;
- CDI+ manual editável;
- CDI+ efetivo;
- origem efetiva;
- status e fonte documental.

Os estados de edição são separados pela assinatura do escopo e pelo fingerprint
da curadoria. Uma taxa digitada em uma carteira não aparece em outra.

### Exportações

XLSX, PPTX, pacote CSV e metodologia recebem o nome do escopo. O preset
CloudWalk preserva os nomes de arquivo legados. Outras seleções usam um slug do
nome da carteira ou da seleção manual.

## Limites assumidos nesta versão

### Spread sozinho não cria uma linha de funding

Quando não há série, tipo, volume ou cronograma, não é possível calcular apenas
com um CDI+. A tela explica a limitação e não apresenta custo zero como se fosse
um resultado válido.

Para suportar qualquer CNPJ sem curadoria, uma fase posterior deve criar o fluxo
`Adicionar série manual`, com pelo menos:

- identificador e tipo de série;
- volume ou saldo inicial;
- data de emissão/integralização;
- CDI+;
- cronograma e convenção de amortização;
- fonte e justificativa.

### Curadoria não é criada ao vivo

Informar um CNPJ novo consulta os perfis e conhecimentos já produzidos no
repositório. O fluxo não baixa e interpreta regulamentos em tempo real. Um fundo
sem perfil entra na fila de curadoria, mas não ganha termos econômicos inventados.

### Estrutura de série ainda é textual

O bloqueio conservador evita dupla contagem, mas reduz cobertura em bases de
triagem. O próximo passo estrutural é persistir uma tabela canônica de séries
com identidade, vigência e lineage documental.

## Critérios de aceitação cobertos

- CloudWalk é o primeiro escopo e independe do store.
- A cesta CloudWalk continua com 11 CNPJs, 27 registros e 19 séries ativas.
- Carteiras cadastradas usam exatamente seus fundos.
- CNPJs manuais são validados, deduplicados e limitados.
- Curadoria dedicada prevalece sobre triagem.
- Taxa manual prevalece somente na série exata.
- O valor documental permanece auditável após override.
- Limpar o manual restaura a curadoria.
- Séries sem spread não entram silenciosamente nos totais.
- Colisões de série são bloqueadas.
- Escopo e fingerprint invalidam o cache.
- IME histórico respeita a data snapshot.
- Exportações genéricas não mantêm título CloudWalk.

## Arquivos principais

- `services/financial_cost_scope.py`: escopos, CNPJ, curadoria e conflitos;
- `services/cloudwalk_financial_cost.py`: linhas e motor financeiro compatível;
- `tabs/tab_cloudwalk_financial_cost.py`: seleção, cobertura, editor e resultados;
- `services/cloudwalk_financial_cost_exports.py`: XLSX/PPTX parametrizados;
- `tests/test_financial_cost_scope.py`: seleção, precedência, conflitos e regressão;
- `tests/test_cloudwalk_financial_cost.py`: matemática e snapshot IME as-of.
