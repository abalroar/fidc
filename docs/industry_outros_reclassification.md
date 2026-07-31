# Reclassificação documental do bucket `Outros`

## Por que existe

A curadoria histórica Top 20 fechou 143 CNPJs — os vinte maiores de cada Tipo
ANBIMA exibido em dezembro de 2023, dezembro de 2024, dezembro de 2025 e junho
de 2026. Ela reduziu `Outros` em R$ 56,0 bi em jun/26, mas o bucket continuou
concentrando mais de um terço do patrimônio do mercado, distribuído em uma
cauda longa que o corte por Top 20 não alcança.

Esta rodada estende a mesma metodologia à cauda: a fila passa a conter **todos**
os CNPJs exibidos como `Outros` nas quatro competências, ordenados pelo maior PL
observado, e exclui os que já possuem decisão no ledger analítico.

## Camadas

- `industry_outros_reclassification_queue.csv`: fila por CNPJ, com PL máximo,
  competências observadas, Tipo/Foco oficiais e o indicador `is_np` da CVM.
- `industry_outros_reclassification_conclusions.csv`: conclusão documental por
  CNPJ, com documentos lidos, páginas, trecho decisivo, escores por família,
  status, confiança e justificativa.
- `industry_top20_pending_curation.csv`: encerramento manual dos CNPJs que a
  revisão Top 20 deixou em aberto.
- `taxonomy_review_actions.csv` / `taxonomy_review_audit.csv`: ledger analítico
  e trilha de auditoria já existentes, alimentados por
  `apply_fidc_documentary_decisions.py`.
- Base CVM/ANBIMA: campos oficiais preservados, sem qualquer sobrescrita.

## Aquisição de documentos

Para cada CNPJ o pipeline busca no FundosNet o regulamento mais recente com
status ativo. Quando não há regulamento publicado, ou quando a leitura do
regulamento não fecha a decisão, um segundo passe baixa os documentos
complementares disponíveis — prospectos, suplementos, anexos, atas de
assembleia, comunicados, demonstrações financeiras e informes. Os arquivos ficam
em cache local, de modo que reprocessar a classificação não repete download.

Cada PDF é lido página a página com `pypdf`; quando a camada de texto é
insuficiente, a extração recai em `pdfplumber`. PDF sem texto extraível fica
registrado como limitação explícita e o CNPJ permanece `pendente`.

## Como a decisão é formada

Cada família econômica de direitos creditórios tem vocabulário próprio. Uma
ocorrência vale mais ou menos conforme a seção da página em que aparece:

- páginas que contêm definição, política de investimento, critérios de
  elegibilidade, condições de cessão, objetivo, composição da carteira,
  público-alvo ou anexo descritivo valem **o dobro**;
- páginas de fatores de risco e de cobrança de créditos inadimplidos valem
  **35%**, porque enumeram famílias sem definir o mandato;
- as demais valem 1.

Sobre os escores incide uma tabela de dominância declarada par a par, que
expressa relação econômica e não numérica. A cédula de crédito bancário é o
instrumento que formaliza o financiamento de veículo, e todo regulamento de
consignado cita receitas e entes públicos: quando a família específica ultrapassa
o limiar decisivo, ela absorve a genérica ainda que o vocabulário genérico
apareça com mais frequência. A absorção é limitada por uma tolerância, de modo
que uma família genérica muito mais presente não é apagada.

Precatórios e direitos judiciais privados são famílias distintas: requisitórios
contra entes públicos levam Foco `Poder Público`, enquanto créditos judiciais e
honorários de origem privada levam Foco `Recuperação`. Ambos compartilham a
taxonomia funcional `Judicial/Precatórios/NPL`.

## Estados

| Status | Quando é usado |
|---|---|
| `aprovado` | Uma família domina a definição do lastro, ou o mandato é multicarteira com predominância mensurável de um Tipo ANBIMA. A decisão entra no mix analítico. |
| `em_revisao` | Há líder identificado, mas a família seguinte permanece próxima, ou nenhuma família atingiu evidência suficiente na seção decisiva. Fica registrada com o motivo e não altera o mix. |
| `pendente` | Nenhum documento com camada de texto foi obtido. |
| `rejeitado` | A hipótese de classificar o CNPJ como FIDC direto está incorreta — regulamento de fundo de investimento financeiro sem mecânica de cessão, ou veículo que detém apenas cotas de outros fundos. |

Um mandato que enumera quatro ou mais famílias concorrentes é multicarteira. Se
60% ou mais da evidência concorrente pertencer a um único Tipo ANBIMA, a
classificação fecha nesse tipo com o Foco multicarteira correspondente; caso
contrário permanece em `Outros / Multicarteira Outros`.

## Perímetro

Um regulamento de fundo de investimento financeiro pode mencionar direitos
creditórios, porque pode deter cotas de FIDC. O que ele nunca tem é a mecânica da
cessão: critérios de elegibilidade, condições de cessão, cedente, contrato de
cessão ou documentos comprobatórios. A detecção de perímetro usa exatamente essa
diferença, e não o nome do fundo.

## Resultado

A fila cobriu **2.158 CNPJs** exibidos como `Outros` nas quatro competências,
com download de regulamento e, quando ele não bastou, de documentos
complementares para 780 veículos.

| Status | CNPJs |
|---|---:|
| `aprovado` | 1.892 |
| `em_revisao` | 219 |
| `pendente` | 40 |
| `rejeitado` | 7 |

Efeito no mix analítico, comparado à fotografia oficial ANBIMA:

| Competência | PL direto | Outros oficial | Outros curado | Redução | Cobertura do PL por decisão aprovada |
|---|---:|---:|---:|---:|---:|
| dez/23 | R$ 452,3 bi | R$ 163,5 bi (36,1%) | R$ 117,7 bi (26,0%) | R$ 45,8 bi | 76,8% |
| dez/24 | R$ 651,5 bi | R$ 235,2 bi (36,1%) | R$ 162,1 bi (24,9%) | R$ 73,1 bi | 76,6% |
| dez/25 | R$ 772,1 bi | R$ 316,3 bi (41,0%) | R$ 206,4 bi (26,7%) | R$ 109,9 bi | 74,0% |
| jun/26 | R$ 821,4 bi | R$ 303,3 bi (36,9%) | R$ 175,2 bi (21,3%) | R$ 128,1 bi | 69,2% |

Os valores já descontam a correção de perímetro FIC descrita adiante: os 355
veículos que só detêm cotas saíram do PL direto e do numerador de `Outros`, de
modo que a coluna "Outros oficial" também é menor que a fotografia ANBIMA
publicada antes da correção.

O ledger analítico passou de 137 para **2.332 decisões** por CNPJ, todas com
evidência, página, justificativa, nível de confiança e trilha de auditoria.

## Correção de perímetro FIC

A curadoria documental encontrou veículos registrados como FIDC que nunca
compram um direito creditório: o ativo deles são cotas de outros FIDCs. Contados
dentro dos quatro tipos ANBIMA, esses fundos somam o mesmo patrimônio duas vezes
— uma no fundo investido, com a taxonomia dele, e outra no veículo que só detém
a cota.

O pipeline inicializa `is_fic_fidc` como **sinal nominal legado**, calculado
localmente por regex sobre a denominação social em
`scripts/build_fidc_industry_study.py`. Não foi identificada flag FIC oficial
dedicada nos layouts CVM inspecionados, nem equivalência oficial ANBIMA para
esse campo local.

A revisão quantitativa (`scripts/build_fidc_fic_perimeter_review.py`) acrescenta
overrides com dois critérios objetivos, ambos lidos do Informe Mensal
Estruturado:

1. **Nunca deteve direitos creditórios.** `VL_DICRED` igual a zero em *toda* a
   série histórica do CNPJ, não apenas nas competências de referência. Um fundo
   que comprou recebíveis em qualquer mês permanece no perímetro FIDC.
2. **Detém cotas de FIDC acima do limiar.** `VL_COTA_FIDC + VL_COTA_FIDC_NAO_PADRAO`
   representando pelo menos 50% de `VL_SOM_APLIC_ATIVO` (`FEEDER_MIN_SHARE`).

De 470 candidatos ao primeiro critério, **355 confirmaram** o segundo — mediana
de 96% das aplicações em cotas de FIDC. Os 115 restantes ficaram como
`sem_evidencia_suficiente` e continuam no perímetro FIDC.

A correção é gravada em `data/industry_study/fic_perimeter_overrides.csv` e
aplicada por `services/fic_perimeter.py` **antes de qualquer agregação**, dentro
de `scripts/build_fidc_revision_analysis.py`. Ela só liga o indicador; um fundo
já selecionado pelo sinal local permanece fora do universo FIDC direto.

| Competência | Fundos movidos | PL movido para o saldo FIC | Saldo FIC | PL direto |
|---|---:|---:|---:|---:|
| dez/23 | 65 | R$ 9,42 bi | R$ 23,60 → 33,02 bi | R$ 461,8 → 452,3 bi |
| dez/24 | 171 | R$ 31,44 bi | R$ 48,94 → 80,38 bi | R$ 682,9 → 651,5 bi |
| dez/25 | 292 | R$ 61,11 bi | R$ 85,90 → 147,01 bi | R$ 833,2 → 772,1 bi |
| jun/26 | 318 | R$ 59,01 bi | R$ 81,11 → 140,12 bi | R$ 880,4 → 821,4 bi |

Em jun/26, R$ 46,64 bi dos R$ 59,01 bi movidos estavam classificados como
`Outros` pela ANBIMA — a correção de perímetro sozinha responde por boa parte da
queda do bucket. Outros R$ 5,74 bi estavam sem classificação (`N/D`).

O método quantitativo dos overrides não usa nome. O perímetro completo ainda
inclui o sinal nominal legado como entrada decisiva, com proveniência registrada
separadamente na auditoria.

Cada correção também vira uma decisão `rejeitado` no ledger analítico
(`scripts/apply_fic_perimeter_to_ledger.py`, responsável
`curadoria_perimetro_fic`), com a evidência do informe e a nota explicando que o
patrimônio passou a alimentar o saldo de FIC. Rejeitar é a decisão honesta: a
hipótese de classificar o veículo como FIDC direto está incorreta, e o overlay
de taxonomia só aplica decisões aprovadas. Quando o critério foi apertado para
exigir ausência de direitos creditórios em toda a série, as rejeições que
deixaram de valer foram revertidas para a conclusão documental de cada fundo —
20 delas — e as três sem conclusão própria voltaram para `em_revisao`.

Uma única decisão manual do usuário foi substituída pela correção, e o script
avisa em voz alta quando isso acontece: **EXPERT III FIDC**
(`53073485000100`, R$ 3,52 bi), aprovado à mão. O informe de jun/26 mostra
R$ 2,997 bi de cotas de FIDC em R$ 3,520 bi aplicados (85%) e direitos
creditórios em R$ 0,00 nas quatro competências — é um FIC. Vale conferir a mão,
já que contraria uma aprovação humana.

## Detecção de FIC auditável e o portão único

`services/fic_detection.py` concentra a regra. O portão combina duas entradas
decisivas e um cross-check secundário:

1. **Sinal nominal legado** — `is_fic_fidc`, derivado localmente da denominação
   social. Ele permanece decisivo por compatibilidade com o perímetro histórico.
2. **Informe Mensal Estruturado** — `VL_DICRED` zerado em toda a série e cotas
   de FIDC acima de metade das aplicações. A entrada quantitativa lê o que o
   fundo detém e tem precedência no rótulo de proveniência quando existe
   override curado.
3. **Cross-check nominal secundário** — `name_says_fic()` usa um matcher mais
   estrito de token e forma legal. Quando as duas entradas decisivas estão
   ausentes, ele abre revisão e mantém o fundo no universo.

Em jun/26, o portão exclui 773 FICs e R$ 140,1245 bi. Desses, 451 fundos e
R$ 80,7176 bi saem exclusivamente pelo sinal nominal legado; 322 fundos e
R$ 59,4069 bi têm confirmação quantitativa curada. Outros nove casos aparecem
somente no cross-check nominal secundário e permanecem em revisão.

A revisão metodológica dos 451 casos decididos pelo sinal nominal legado exige
recalcular PL ex-FIC, mix, Top 20 e gráficos. Ela constitui projeto separado e
não integra esta correção de proveniência.

`FIC_TOKEN_PATTERN` casa "FIC" apenas como token isolado — delimitado por início
ou fim da string, espaço, hífen, barra, parêntese ou pontuação. `FICÇÃO`,
`SIFIC`, `FIC123` e `PACIFICO` não disparam, porque o caractere vizinho é
alfanumérico. Um caso alcançado somente pelo cross-check nominal secundário
**permanece no universo** e vai para revisão humana.

Cada linha recebe `is_fic`, `fic_detection_method`, `fic_detection_evidence` e
`fic_exclusion_reason`, e a auditoria completa fica em
`industry_fic_detection_audit.csv`.

`exclude_fics_from_fidc_universe()` é o portão único, e `split_fidc_universe()`
devolve os dois lados. Os dois são necessários: o elegível alimenta tudo que é
analítico, o excluído alimenta o saldo de FIC. Apagar as linhas excluídas
zeraria justamente o saldo que a exclusão existe para construir.
`assert_universe_excludes_fics()` roda sobre os produtos derivados e falha em
voz alta se um FIC reaparecer num ranking ou no mix.

## Cross-check da taxonomia

`services/taxonomy_crosscheck.py` procura contradições internas nas decisões
aprovadas e **não reescreve nada**: cada achado traz evidência, motivo e ação
sugerida. Duas armadilhas moldaram as regras. A primeira foi escrever a tabela
Tabela II × N1 com rótulos inventados em vez do vocabulário real de
`FUNCTIONAL_TAXONOMY` — isso produziu 686 falsos achados, entre eles todos os
609 "Ações judiciais / Judicial-Precatórios-NPL", que estão corretos. A segunda
foi casar as regras contra o rótulo de família entre colchetes e a linha
"Escores documentais" das notas: são a saída do próprio classificador, e casar
contra elas é confirmar a classificação com ela mesma. `_documentary_text()`
remove as duas antes de qualquer busca.

## Três fontes de evidência, em ordem de força

1. **Classificação ANBIMA declarada no regulamento.** Regulamentos adaptados à
   Resolução CVM 175 costumam trazer, no anexo da classe, o Tipo e o Foco de
   atuação que o próprio gestor atribuiu — a mesma taxonomia que a curadoria
   preenche, escrita por quem responde por ela. Quando existe, prevalece sobre
   qualquer inferência por vocabulário e fecha a decisão com confiança alta.
2. **Definição do lastro, política de investimento e critérios de
   elegibilidade**, pontuados por família econômica com os pesos descritos
   acima.
3. **Segmento da Tabela II declarado no informe mensal estruturado.** É o único
   documento que fala da carteira efetivamente detida, e não do mandato
   permitido. Usado para desempatar famílias em disputa (concentração ≥ 60%) ou
   para fechar sozinho um caso sem documento legível (concentração ≥ 90%).

## Contextos negativos

Duas construções aparecem literalmente em quase todo regulamento e não são
evidência de nada:

- as **obrigações do administrador e do gestor** da Resolução CVM 175, que
  citam precatórios federais em uma hipótese condicional (`no caso de classe
  destinada ao público em geral que adquira precatórios federais...`);
- a **definição de Contrato de Cobrança** e os procedimentos de cobrança, que
  citam direitos de crédito inadimplidos em qualquer fundo, performado ou não.

Uma ocorrência dentro de uma janela de 320 caracteres dessas expressões é
descartada. A calibração inicial desta rodada aprovou dezenas de fundos como
`Poder Público` ou `Recuperação` com base nesses trechos; a inspeção manual dos
vinte maiores de cada foco expôs o padrão e o filtro foi introduzido antes de
qualquer publicação.

## Continuidade

O pipeline nunca reinicia o trabalho. A fila exclui todo CNPJ que já tenha
decisão no ledger, e `apply_fidc_documentary_decisions.py` preserva aprovações
existentes: sobrescrever uma aprovação exige `--allow-override` acompanhado de
`--override-reason`, que fica gravado nas notas e na auditoria.

## Republicação do bundle pendente

O bundle Office publicado em `data/industry_study/generated_revision/` registra
os hashes SHA-256 do ledger e da auditoria de taxonomia no momento da
publicação, e a aplicação falha fechada quando a curadoria muda depois disso.
Como esta rodada alterou o ledger, o bundle publicado ficou defasado e
`test_industry_exports_are_valid_office_files` acusa
`curadoria ou auditoria de Outros mudou após a publicação; regenere o bundle`.

A regeneração não pôde ser executada nesta sessão porque o renderizador
`scripts/build_fidc_revision_artifacts.mjs` depende de `@oai/artifact-tool`, que
não está presente no runtime Node deste ambiente. Em um ambiente com o runtime
disponível, basta:

```
python3 scripts/publish_fidc_revision_bundle.py \
    --input-workbook <workbook-base.xlsx> --skip-download
```

O ledger em si está íntegro: `assert_taxonomy_review_ledger_matches_audit`
reproduz as 2.332 decisões a partir da trilha de auditoria.

## Normalização de espaços em branco

A trilha de auditoria é reexecutada pela normalização do próprio módulo, que
colapsa sequências de espaços. Uma decisão gravada com espaço duplo na evidência
deixa de ser reproduzível por sua própria trilha sem que nada da decisão tenha
mudado. `apply_fidc_documentary_decisions.py` passou a normalizar os campos na
gravação, e `normalize_taxonomy_ledger_whitespace.py` reescreveu as 555 decisões
já gravadas que tinham essa característica — apenas espaços mudaram, e cada
reescrita ficou registrada na auditoria.

## Limitações

A conclusão descreve o mandato permitido pelo documento. A materialidade efetiva
de cada família depende da carteira observada em cada competência. A denominação
social não determina a taxonomia analítica de Tipo e Foco. No perímetro FIC, o
sinal nominal legado continua decisivo e é identificado como tal na auditoria.

## Fila de taxonomia no Streamlit

A seção **Fila de Taxonomia** do app (`tabs/tab_taxonomy_queue.py`) permite
aprovar, editar, manter em revisão ou rejeitar a classificação de qualquer CNPJ
com conclusão documental.

O painel lê `industry_outros_reclassification_conclusions.csv`,
`industry_top20_pending_curation.csv` e o ledger diretamente do disco — **não**
depende do bundle Office publicado. Essa separação é deliberada: o bundle falha
fechado sempre que o ledger muda, que é justamente o que curar faz, de modo que
uma fila alimentada pelo bundle se trancaria após a primeira decisão.

Por padrão a fila mostra apenas o que ainda pede decisão (`em_revisao` e
`pendente`), ordenado pelo maior PL. O botão *Incluir já decididos* reabre
qualquer fundo aprovado ou rejeitado para edição, e a busca aceita nome, CNPJ
com ou sem máscara.

Os cinco campos são listas fechadas encadeadas: o Foco depende do Tipo, o N2
depende do N1, e a Tabela II usa o vocabulário da CVM. Um teste percorre as
2.162 linhas da fila e confirma que os valores pré-preenchidos sempre produzem
uma ação que `validate_taxonomy_review_action` aceita — o formulário não oferece
combinação que o ledger recuse.

A gravação passa por `commit_taxonomy_review_action`, com a mesma trilha de
auditoria de qualquer outra decisão, e o responsável fica registrado como
`curadoria_manual_streamlit`.

### Fila aberta, sem token para quem revisa

Ler a fila e gravar uma decisão não toca em credencial nenhuma: a fila é montada
a partir de CSV em disco e a decisão é escrita em CSV, sob `flock`, que serializa
revisores simultâneos no mesmo servidor. Quem abre o link revisa — sem login,
sem token, sem secret.

O único ponto que exige credencial é **publicar no GitHub**, porque o GitHub não
aceita push anônimo. Essa credencial fica no servidor, uma vez, e o visitante
nunca a vê nem a fornece. Duas formas:

- **App rodando numa máquina com o clone já autenticado** (`streamlit run app.py`,
  exposto na rede local ou por túnel): funciona sem nenhuma configuração
  adicional, porque o push usa a credencial git que já está ali.
- **Servidor público** (Streamlit Community Cloud e afins): exige exatamente um
  secret no servidor — uma deploy key com escopo de escrita neste repositório.
  Continua sem token para o visitante.

Sem credencial alguma o app ainda revisa e grava, mas só no disco de onde ele
roda; num host efêmero as decisões se perdem no restart.

#### Credencial por secret

Numa máquina corporativa o caminho da credencial ambiente costuma não existir:
sem credential helper, sem chaveiro, sem SSH na porta 22, sem direito de
instalar nada. O secret resolve isso porque só depende de HTTPS na 443, que é o
que o proxy da empresa deixa passar de qualquer jeito.

`resolve_push_credential()` lê `github_token` de `st.secrets` e monta
`https://x-access-token:<token>@github.com/<owner>/<repo>.git`. A URL é passada
como argumento de um único `git push`: não entra em `.git/config`, não vira
remote, não sobrevive ao comando. E `redact()` cobre toda mensagem devolvida
pelo publisher, porque o git ecoa a URL do remoto em vários erros — sem isso um
push recusado imprimiria o token na tela de quem estiver usando o painel.

**É o mesmo token do cadastro de carteiras.** `services/portfolio_store.py` já
lê `github_token` e `github_repo` do mesmo `st.secrets` para gravar
`portfolios.json`, e pede exatamente a mesma permissão — a diferença é só o
caminho: carteiras vão pela API de conteúdo do GitHub, o ledger vai por `git
push`. As chaves de repositório e branch do publisher começam por `github_repo`
e `github_branch` justamente para reaproveitar as entradas que já existem, sem
duplicar configuração.

Passo a passo:

1. **Token.** Se o cadastro de carteiras já grava no GitHub, o token existente
   serve e não há nada a gerar — pule para o passo 3. Para criar um novo: GitHub
   → Settings → Developer settings → Personal access tokens → Fine-grained
   tokens → Generate new token. Repository access: **Only select repositories →
   `abalroar/fidc`**. Repository permissions: **Contents: Read and write**. Nada
   além disso. Se o repositório pertence a uma organização com SSO, autorize o
   token para ela na lista de tokens, senão o push volta 403.
2. **Rodando local:** copie `.streamlit/secrets.toml.example` para
   `.streamlit/secrets.toml`, cole o token em `github_token` e reinicie o app.
   O `.gitignore` já ignora `secrets.toml`; confirme com
   `git check-ignore -v .streamlit/secrets.toml` antes de colar.
3. **No Streamlit Community Cloud:** Manage app → Settings → Secrets. Se
   `github_token` e `github_repo` já estão lá ao lado de
   `github_portfolios_path`, não mexa em nada — o ledger passa a usá-los
   sozinho. Se só `github_token` estiver definido, o repositório é descoberto
   pelo remoto do clone.
4. **Conferir:** o painel imprime `Token dos secrets em uso. Publicando em
   owner/repo.` logo abaixo dos controles de publicação. Sem essa linha, o
   token não foi lido e o push está tentando a credencial do clone.
5. **Atrás de proxy corporativo**, se o push travar sem resposta:
   `git config --global http.proxy http://usuario:senha@proxy.empresa:8080`.

Um host que publica a partir de um commit deixa o HEAD destacado, e nesse estado
`git push <remoto> HEAD` falha porque HEAD não resolve para branch nenhuma.
`_push_target()` cobre o caso: sem branch checada, o destino vem de
`github_branch` (padrão `main`) e o refspec é explícito.

Revogar é o botão de emergência: apagar o token no GitHub derruba de uma vez o
push do ledger e a gravação de carteiras, sem mexer no código nem no
repositório.

Abrir a fila troca autenticação por atribuição, e a atribuição é a parte que
vale preservar. O painel pede **Quem está revisando** — assinatura, não login,
sem verificação — e `reviewer_responsible()` grava o nome em `responsavel` como
`curadoria_manual_streamlit:<nome>`. Em branco, a decisão fica honestamente
registrada como anônima, nunca atribuída a quem não a tomou. A trilha de
auditoria é o que torna a alegação conferível.

O trabalho já concluído fica protegido por um único caminho de destruição, e ele
é guardado: reabrir um fundo **aprovado** exige motivo explícito, que lidera as
notas da decisão — o mesmo `--override-reason` que os scripts em lote cobram.
Sem motivo, a decisão anterior é preservada e nada é gravado.

### Publicação no repositório

As decisões tomadas no painel gravam nos dois CSV do ledger. Enquanto não forem
commitadas, existem apenas no clone onde o app roda — a próxima sessão, aqui ou
no Codex, partiria do estado anterior.

O painel resolve isso: mostra quantos arquivos do ledger têm decisões não
publicadas, oferece **Publicar no repositório** (commit e push) e um alternador
para publicar automaticamente a cada decisão. `services/ledger_publisher.py`
prepara **apenas** os dois arquivos do ledger, nunca a árvore inteira, de modo
que trabalho em andamento em outros arquivos não é arrastado junto. Um push
recusado é tentado uma segunda vez após rebase no remoto, que é o que acontece
quando o mesmo ledger avançou em outra máquina; se ainda assim falhar, o commit
local permanece e o motivo é exibido.
