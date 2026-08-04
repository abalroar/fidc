# Corrigir as colunas Originador, Cedente, Sub. mín., Preço por cota e Sacado dos slides 10–17

## Contexto

No bundle publicado (`202606_df11558dc92e6dff`, commit `569d6e4c`, PR #150), os oito slides de
Top 15 por tipo ANBIMA saem praticamente vazios nessas cinco colunas:

| Slide | Bloco | Período |
|---|---|---|
| 10 / 11 | Fomento Mercantil | jun/26 · dez/25 |
| 12 / 13 | Agro, Indústria e Comércio | jun/26 · dez/25 |
| 14 / 15 | Financeiro | jun/26 · dez/25 |
| 16 / 17 | Outros | jun/26 · dez/25 |

São 120 linhas e 72 CNPJs distintos. A taxa de `N/D` medida no PPTX entregue:

| Coluna | N/D | % |
|---|---:|---:|
| Originador | 90/120 | 75% |
| Cedente | 106/120 | 88% |
| Sub. mín. | 113/120 | 94% |
| Preço por cota | 113/120 | 94% |
| Sacado | 118/120 | 98% |

Fomento Mercantil e Outros estão em **0/15 de originador nos dois períodos** — as quatro páginas
são uma coluna inteira de `N/D`.

## Causas identificadas

Investiguei `origin/main` e o payload publicado. Valide cada uma antes de agir; se discordar de
alguma, diga e siga o seu diagnóstico.

**1. A única fonte que preenche essas colunas é a transcrição manual das fotos.**
`_apply_manual_enrichment_to_rankings` em `scripts/build_fidc_revision_artifact_payload.py` é o
único ponto que escreve em `originador`, `cedente` e `sacado` do `emission_field_audit`, e ele lê
só `data/industry_study/industry_cnpj_manual_enrichment.csv`. O campo
`fonte_enriquecimento_manual` do payload confirma: 32 das 120 linhas vieram de `IMG_8698.jpg`,
`IMG_8706.JPG`, `IMG_8707.jpg`; as outras 88 estão em `N/D`. As fotos cobriam o bloco Financeiro,
por isso ele tem 12/15 e 14/15 preenchidos e os outros três blocos têm zero. Não existe pipeline
documental alimentando essas tabelas.

**2. O CSV base já nasce vazio.** `data/industry_study/emission_field_audit.csv` tem, nas 120
linhas do bloco: originador 96% `N/D`, cedente 96%, subordinação 94%, preço 94%, sacado 100%. Em
71 dessas linhas a coluna `fonte_originador_cedente` aponta para a URL genérica
`https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciador` — endereço do gerenciador, não um
documento. É um marcador de "consultar aqui" que nunca virou extração.

**3. A curadoria flagship citada no rodapé cobre 8% do universo das tabelas.** O rodapé dos slides
afirma que as cinco colunas "usam a mesma curadoria documental flagship". A Carteira 101 tem 101
CNPJs; **6 dos 72 CNPJs desses slides estão nela**. Os outros 66 nunca passaram pela varredura. E a
varredura funciona: dentro da Carteira 101 ela atingiu cedente 92%, preço por cota 84%, mínimo
júnior 82%, sacado 37% (aba "Cobertura varredura"). O scanner
(`scripts/scan_carteira_101_documents.py` + `services/carteira_101_document_audit.py`) extrai
exatamente `originador`, `cedente`, `sacado_devedor`, `minimo_junior` e preço — só nunca foi
apontado para esses 66 CNPJs.

**4. Dado já publicado no mesmo commit não foi ligado à tabela.** A triagem de cedentes
(`data/industry_study/cedente_triage/202606/fidc_cedentes_top437_202606.csv.gz`, e a aba
"Cedentes · Top 437" do próprio workbook) cobre **68 dos 72 CNPJs**, e em 27 deles traz
`cedente_razao_social_consolidada` da Tabela I do Informe Mensal. **26 desses 27 aparecem como
`N/D` na coluna Cedente do deck.** Exemplos, todos com razão social disponível e `N/D` no slide:

- `09.195.235/0001-50` FIDC do Sistema Petrobras → PETROLEO BRASILEIRO S A
- `21.126.275/0001-46` Venda de Veículos → RENAULT DO BRASIL S.A. (+1)
- `11.230.727/0001-81` FIDC GM → GENERAL MOTORS DO BRASIL LTDA
- `52.651.831/0001-27` Hyundai → HYUNDAI MOTOR BRASIL MONTADORA
- `28.279.473/0001-99` → HONDA AUTOMOVEIS DO BRASIL LTDA
- `50.095.909/0001-49` Vita Auto → STELLANTIS AUTOMOVEIS BRASIL LTDA. (+1)
- `47.228.232/0001-65` Agro Flex → SYNGENTA PROTECAO DE CULTIVOS LTDA
- `52.610.624/0001-24` Aetos Energia → BRF ENERGIA S.A.
- `12.817.329/0001-29` Havan → HAVAN S.A
- `54.979.779/0001-68` ACR Bem → STONE INSTITUICAO DE PAGAMENTO S.A
- `63.662.224/0001-89` Santander Auto Loans → SANTANDER SOCIEDADE DE CREDITO

O workbook entregue tem as duas abas lado a lado — "Auditoria emissões" toda `N/D` e
"Cedentes · Top 437" preenchida — sem junção entre elas.

**5. Preço por cota já extraído aparece como `N/D`.** Quatro CNPJs dos slides têm preço na aba
"Preços por cota" da Carteira 101 e saem `N/D` no deck: `11.468.186/0001-24` ATLANTA
(R$ 1.000.000,00, fonte regulamento), `28.169.275/0001-72` PagSeguro I (R$ 1.000,00, regulamento),
`62.393.829/0001-59` Comerciais Medici I (R$ 1.000,00, emissão), `62.588.266/0001-54` VTK
(R$ 1.000,00, regulamento).

**6. Nada no CI reprova esse estado.** `tests/test_industry_revision_artifacts.py` só afirma que os
títulos `"Originador"`, `"Cedente"`, `"Sub. mín."`, `"Preço por cota"` e `"Sacado"` aparecem no
texto do slide — presença de cabeçalho, não de conteúdo. O guard de
`scripts/publish_fidc_revision_bundle.py` verifica contagem (180 linhas = 120 + 60), não
preenchimento. Uma tabela 100% `N/D` passa nos 1.203 testes. É por isso que a suíte ficou verde com
o deck vazio.

**7. Dois defeitos menores, de baixo risco.** O rótulo `bloco` no CSV ainda é `"slides 10–13"`,
resquício de quando eram quatro páginas — hoje são oito, slides 10 a 17; e o casamento manual usa
**raiz de 8 dígitos do CNPJ** (`raiz_cnpj_foto`), que pode colar o dado de um fundo no fundo irmão
do mesmo grupo.

## O que fazer

Encadeie as fontes que já existem no repositório e só então preencha o que faltar com documento.
Ordem de prioridade sugerida, mas decida você onde encaixa cada peça:

1. **Cedente** — junte a triagem de cedentes (Tabela I do Informe Mensal) ao
   `emission_field_audit` por CNPJ de 14 dígitos. É a fonte oficial e cobre 68 dos 72 CNPJs.
2. **Preço por cota, Sub. mín., Originador, Sacado** — traga o que a Carteira 101 já extraiu para
   os 6 CNPJs em comum, e rode o scanner documental para os 66 restantes.
3. O que sobrar sem documento continua `N/D`. Não estime, não interpole, não deduza do nome do
   fundo.

### Regras que não podem ser violadas

- **Cedente ≠ Originador.** A Tabela I traz o cedente **legal**, que em muitos casos é um veículo
  financeiro e não o originador econômico: Multiplica declara QI DTVM, Monee declara QI SCD. Preencha
  a coluna Cedente com o que a CVM diz e deixe Originador para o que o documento sustentar. Se as
  duas colunas ficarem idênticas em massa, a junção está errada.
- **Sacado não existe na CVM.** Nenhuma das 17 tabelas do Informe Mensal tem campo de sacado ou
  devedor identificado. Essa coluna só pode ser preenchida por leitura de regulamento, e ficará
  parcial mesmo depois da varredura — dentro da Carteira 101 o teto foi 37%. Não invente cobertura
  aqui, e ajuste o rodapé para dizer isso.
- **Procedência visível.** Mantenha a convenção do `*` para complemento manual e registre a fonte
  linha a linha (documento e id, não a URL do gerenciador) na aba "Auditoria emissões". Se a fonte
  não identifica o documento, o campo não está auditado.
- **Rodapé honesto.** Enquanto a curadoria flagship cobrir 8% do universo, o rodapé não pode
  afirmar que as cinco colunas vêm dela. Corrija a frase para o que for verdade depois da correção.

### Trave o regressão

Suba o contrato de "cabeçalho existe" para "cabeçalho existe **e** a coluna tem preenchimento
mínimo", por bloco e por período, com o piso calibrado no que a fonte realmente sustenta — alto
para Cedente, que tem base CVM; baixo e explícito para Sacado. O teste tem que ficar vermelho se
alguém republicar uma coluna inteira de `N/D`. Some ao guard de publicação a mesma verificação, já
que ele é quem barra o bundle.

## Delegue a Luna

Passe ao GPT Luna as tarefas fechadas e verificáveis, e guarde o seu contexto para as decisões de
junção e para o scanner documental. Sugestão de recorte:

**Para a Luna:**
- Renomear o rótulo `bloco` de `"slides 10–13"` para a faixa correta e ajustar as referências.
- Trocar o casamento por raiz de 8 dígitos por CNPJ de 14 dígitos em `_apply_manual_enrichment_to_rankings`,
  reportando qualquer linha que perca correspondência.
- Substituir a URL genérica do gerenciador, onde ela aparece como fonte, por `N/D — sem documento
  identificado`, já que ela não é evidência.
- Reescrever as três notas de rodapé dos slides e o texto do Leia-me das abas afetadas depois que os
  números finais existirem.
- Conferir formatação: percentuais, `R$`, truncamento das células e ausência de mojibake nas colunas
  novas.
- Rodar a suíte e relatar as falhas.

**Você fica com:** o desenho da junção cedente/originador, o critério de precedência entre fontes
(regulamento > emissão > assembleia > informe), a execução e a validação do scanner nos 66 CNPJs, e
a calibragem dos pisos de cobertura no teste.

## Entrega

Republique o bundle e reporte, por coluna e por bloco, a cobertura **antes e depois** em número de
linhas e em % do PL das tabelas. Diga explicitamente quantas linhas continuam `N/D` e por quê —
sem documento, sem campo na CVM, ou fora do escopo da varredura. Se a cobertura de alguma coluna
continuar baixa depois de tudo, isso é um resultado legítimo; o que não pode acontecer é o deck
afirmar uma procedência que não tem.
