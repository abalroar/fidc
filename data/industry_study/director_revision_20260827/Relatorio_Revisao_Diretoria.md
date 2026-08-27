# Revisão da apresentação de FIDCs

**Data da revisão:** 27/08/2026. **Competência mantida:** jun/26. Valores de PL ex-FIC. A revisão usa a mesma base congelada da apresentação, sem atualização de competência.

## Entrega e aplicação

- **Industria_FIDC_Completa_Revisada_20260827.pptx:** apresentação completa. O ranking é substituído no slide 34; o slide 38 contém a versão adicional de “Saldo e Tipos” sem TAPSO/Petrobras; o slide 39 apresenta a triagem PF/PJ. Os demais slides originais, inclusive o slide 4, são preservados.
- **FIDC_Revisao_Diretoria_20260827.pptx:** somente as três lâminas de revisão, na mesma ordem, para copiar para outra apresentação. Os gráficos permanecem como objetos nativos do PowerPoint.
- **bases/:** valores por CNPJ, séries, prestadores, evidências e manifesto de hashes. As classificações oficiais e as decisões aprovadas foram preservadas.

A numeração e o conteúdo do arquivo disponível no repositório diferem das fotos: o gráfico de saldo está no slide 4; a lâmina “Riscos e Mitigantes” não foi localizada. As instruções escritas nas fotografias não foram tratadas como pedidos adicionais. Para editar essa tabela e manter as alterações feitas pelo usuário, é necessário receber o PPTX das fotos.

Esta entrega é um suplemento datado, disponibilizado no bloco “Revisão da Diretoria · 27/08/2026”. O pacote executivo original e seus anexos dinâmicos permanecem disponíveis separadamente.

## 1. Prestadores: Top 5 + Itaú + Kanastra

Foram mantidos os cinco maiores de cada função e acrescentados os dois comparadores abaixo. O quinto colocado permanece na lista. A grafia usada pelas fontes é **Kanastra**.

| Função — PL em R$ bi | Itaú | Kanastra / Limine |
|---|---:|---:|
| Administração | 27,1 | 12,8 |
| Gestão | 20,6 | 10,6 |
| Custódia | 20,4 | 19,5 |

Itaú inclui Intrag e Kinea; Kanastra inclui Limine. As funções têm universos próprios e não devem ser somadas entre si. O ranking já excluía TAPSO e Sistema Petrobras, conforme seu perímetro original. Os gráficos de independentes à direita foram preservados.

**Diagnóstico do estado anterior:** no ranking geral do PPTX do repositório, Kanastra não estava somada à linha Itaú; ela ficava fora da seleção visível. A tabela de relações societárias usada em outras análises registra sua ligação minoritária ao Itaú. Além disso, a rotina anterior substituía o último colocado por Itaú quando ele estava fora do Top 5. A nova seleção mantém o Top 5 e acrescenta os comparadores, com a composição de grupo explícita e rastreável em `prestadores_linhagem.csv`.

A separação solicitada é compatível com a parceria operacional e participação minoritária descritas pelo [Itaú, abril/2025](https://www.itau.com.br/media/dam/m/36e80c6030c3408c/original/010425-intrag-volta-ao-negocio-de-fidcs-de-recebiveis-em-parceria-com-a-kanastra.pdf). A incorporação de Limine ao grupo Kanastra consta do [comunicado da Kanastra](https://pt.linkedin.com/posts/kanastra_kanastra-compra-limine-dtvm-para-avan%C3%A7ar-activity-7181046721483816960-aUAG). Isso não altera a classificação societária das demais tabelas.

## 2. Versão de saldo sem TAPSO e Sistema Petrobras

CNPJs excluídos do numerador e do denominador em todos os períodos apresentados:

- Sistema Petrobras — **09.195.235/0001-50**: R$ 61,3 bi em jun/26.
- TAPSO — **26.287.464/0001-14**: R$ 41,5 bi em jun/26.

A retirada soma **R$ 102,8 bi**. O PL cai de **R$ 821,4 bi** para **R$ 718,6 bi**.

| Categoria herdada da apresentação | Original — R$ bi | Sem os dois — R$ bi | Participação sem os dois |
|---|---:|---:|---:|
| Fomento Mercantil | 88,4 | 88,4 | 12,3% |
| Agro, Indústria e Comércio | 203,9 | 142,6 | 19,8% |
| Financeiro | 323,9 | 282,4 | 39,3% |
| Precatórios / ações | 81,8 | 81,8 | 11,4% |
| Multicedente / multisacado | 86,5 | 86,5 | 12,0% |
| Recuperação / NP | 35,2 | 35,2 | 4,9% |
| N/D | 1,6 | 1,6 | 0,2% |

A coorte de ofertas efetivamente utilizada nos gráficos de emissões não contém nenhum dos dois CNPJs. Por isso, os gráficos inferiores mantêm seus valores; essa conclusão se limita à coorte usada pelo material. As quatro datas do saldo e suas participações foram recalculadas. A precisão integral está nos CSVs; a soma dos números arredondados pode diferir do total.

O rótulo “Precatórios / ações” soma R$ 81,8 bi na base publicada. Ele deriva do foco curado “Poder Público”; não foi revalidado fundo a fundo como exclusivamente judicial nesta rodada.

## 3. Crédito pulverizado PF/PJ: resultado da investigação

**O total de crédito pulverizado PF/PJ permanece N/D.** A base permite construir uma fila de candidatos por classificação atual; ela não comprova a concentração por devedor nem a parcela efetiva PF/PJ das carteiras.

| Recorte da classificação atual | Fundos | PL dos fundos — R$ bi | % do PL total |
|---|---:|---:|---:|
| PF pessoal / estudantil / BNPL (triagem) | 137 | 39,1 | 4,8% |
| PJ / PF-PJ (triagem) | 91 | 14,6 | 1,8% |
| Fomento Mercantil | 591 | 88,4 | 10,8% |
| Multicedente / multisacado | 351 | 86,5 | 10,5% |

Os candidatos PF e PJ somam **R$ 53,7 bi**, equivalentes a **6,5%** do PL ex-FIC. Esse valor é uma **triagem não exaustiva, com conflitos documentais conhecidos**. Não é estimativa validada, piso ou teto do mercado pulverizado. O valor de R$ 88 bi destacado na fotografia não foi adotado como dado de PF/PJ.

### Definição aplicada na triagem

O recorte PF usa os rótulos existentes de crédito pessoal, estudantil e BNPL dentro de Financeiro. O recorte PJ/PF-PJ usa a taxonomia funcional “Crédito PJ” remanescente. Foram separados previamente meios de pagamento/cartão, consignado/FGTS, veículos e imobiliário. Esses produtos também podem ter devedores pulverizados; a exclusão serve apenas para examinar o recorte sugerido pela tabela da foto. Nenhum nome de fundo foi usado para inferir PF/PJ ou pulverização.

“Fomento Mercantil” descreve uma atividade/originação. “Multicedente/multisacado” descreve uma estrutura. PF/PJ descreve a natureza do devedor. Essas dimensões podem coexistir. Adicionar uma sétima fatia de PF/PJ ao gráfico atual exige reclassificar os fundos elegíveis e retirar o mesmo PL da categoria de origem, com uma regra de precedência explícita.

### Lacuna no grupo multicedente/multisacado

Do total desse grupo, R$ 68,5 bi vêm do foco “Multicarteira Outros”. Outros R$ 18,0 bi correspondem à decisão aprovada para PAN AUTO. Portanto, a legenda da apresentação não equivale à comprovação de múltiplos cedentes e devedores em todos os fundos. A decisão aprovada de PAN AUTO foi mantida; a taxonomia funcional antiga de veículos não foi usada para tratá-lo como crédito pulverizado confirmado.

### Regulamentos consultados nesta rodada

Foi feita extração de texto de 4 regulamentos (528 páginas no total), seguida de leitura focal das cláusulas indicadas abaixo. As referências usam a paginação do arquivo PDF; a página com o limite de concentração foi também conferida visualmente. Isso não representa nova revisão manual de todos os fundos. O PL desses quatro candidatos soma R$ 11,3 bi.

- **MERCADO CRÉDITO FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS RESPONSABILIDADE LIMITADA — CNPJ 33254370000104**. PL: R$ 3,0 bi. Admite devedores CCB PF e PJ; PPV tem Mercado Pago como devedor. Rótulo PJ do ledger não identifica composição efetiva. [Regulamento, páginas 9;94](https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1128340).

- **MERCADO CRÉDITO II BRASIL FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS DE RESPONSABILIDADE LIMITADA — CNPJ 41970012000126**. PL: R$ 1,8 bi. Define consumidores e comerciantes PF/PJ; contém CCB e PPV. Não alocar todo o PL a PJ pulverizado. [Regulamento, páginas 21;51](https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1077334).

- **MERCADO CRÉDITO I BRASIL FIDC SEGMENTO FINANCEIRO DE RESPONSABILIDADE LIMITADA — CNPJ 37511828000114**. PL: R$ 0,8 bi. Consumidores PF e comerciantes; Anexo VII item (u) limita a 0,5% os direitos adquiridos relacionados a um único devedor. Limite contratual não prova composição observada. [Regulamento, páginas 20;50;143](https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1200490).

- **FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS MONEE I DE RESPONSABILIDADE LIMITADA — CNPJ 42922136000107**. PL: R$ 5,8 bi. Regulamento 1159092 descreve recebíveis de arranjos de pagamento, devidos por credenciadoras ou subcredenciadoras. Revalidar a associação do rótulo BNPL antes de fechar o volume. [Regulamento, páginas 30;31;32;33](https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1159092).

A classificação vigente contém 1585 CNPJs com ação aprovada entre 3474 fundos ex-FIC em jun/26, cobrindo 72,3% do PL. Esse indicador mede a aplicação do histórico de curadoria; não prova que todos os documentos foram relidos nesta rodada. Os demais registros conservam a origem oficial, proxy ou indisponível indicada por linha.

### O que falta para fechar a abertura

1. Definir o universo desejado: incluir ou separar consignado, financiamento de veículos, imobiliário e arranjos de pagamento; manter PF/PJ misto como categoria quando não houver segregação.
2. Fixar o critério de pulverização — por exemplo, limites de concentração por devedor, top devedores e quantidade de devedores — e distinguir limite contratual de concentração efetivamente observada.
3. Obter composição PF/PJ e concentração da carteira na competência analisada. Os arquivos públicos CVM já disponíveis no projeto não trazem a distribuição completa de sacados. Os campos PF/PJ de cotistas descrevem investidores e não podem substituir a natureza dos devedores. Ver [dataset CVM](https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal) e [especificação do informe](https://cvmweb.cvm.gov.br/SWB/Sistemas/SCW/PadroesXML/PadraoXMLMensalFIDC576.asp).
4. Validar os candidatos e os fundos atualmente em multicarteira, registrando evidência, data, PF/PJ/misto e concentração. A revisão focal identifica prioridades; a base por CNPJ permite continuar sem repetir a extração.

Para o slide de riscos da fotografia, a célula de mercado de “Crédito Pulverizado PF e PJ” deve permanecer **N/D**, ou ser apresentada explicitamente como triagem, até esse fechamento. Os valores de Fomento Mercantil e Multicedente/multisacado podem manter o recorte publicado com as ressalvas acima.

## Rastreabilidade e verificação

Os números financeiros desta nota e dos slides derivam dos CSVs em `bases/`. `manifest.json` registra os hashes dos insumos e saídas; `verificacao_documental_focal.csv` registra URL, hash, páginas, conclusão e lacunas dos regulamentos. Nenhuma nova decisão foi gravada no ledger aprovado. A exportação usa gráficos nativos e inclui notas de fonte. Assim como o arquivo original, os PPTX não contêm planilhas Excel incorporadas; os dados acompanham a entrega em CSV. A interação “Editar dados” no PowerPoint desktop não foi testada.

Os resultados dos testes, da inspeção de objetos Office e da preservação dos slides originais acompanham a entrega em `qa/`. O código foi mantido em uma worktree separada, sem alterar o checkout de trabalho existente. Os downloads desta revisão são validados pelo manifesto próprio, sem substituir o bundle canônico.
