# Prompt para atualizar “Estudos de Caso”

Atue como analista sênior de crédito estruturado e pesquisador de FIDCs. Atualize o deck “Estudos de Caso” para uso executivo no Itaú BBA, com rastreabilidade documental, linguagem objetiva e objetos nativos do PowerPoint.

## Escopo

1. Atualize os casos Blue II/Azul, MCPO/Maqcampo, Lavoro Agro FIDC I, Lavoro Agro II FIAGRO-FIDC, a exposição a Americanas no Vinci Antecipe Plus FIDC, o SAV Nexoos FIDC e o FIDC Light.
2. Pesquise novos casos somente quando houver identificação inequívoca do veículo, CNPJ e documento primário.
3. Atualize a evolução regulatória e informacional desde maio de 2024 até a data de corte.
4. Atualize termos de compromisso, TACs, termos ANBIMA, multas e a cooperação CVM–Banco Central.
5. Atualize a metodologia de risco e retorno por subclasse ou série.
6. Recalcule a Carteira 101 por CNPJ e identifique os veículos com exatamente uma conta sênior reportada no Informe Mensal mais recente, com fallback explícito para a competência anterior.
7. Decomponha o PL ex-FIC do Tipo ANBIMA Financeiro em meios de pagamento, consignado INSS/público, FGTS, privado/CLT, consignado sem segregação, demais PF, PJ, imobiliário e multicarteira sem segregação.
8. Atualize a cronologia pública da Operação Carbono Oculto, da REAG e do Banco Master/Credcesta, preservando o estágio processual de cada alegação ou investigação.

## Pesquisa de cada caso

Confirme fundo, classe, subclasse, série e CNPJ. Leia regulamento, suplementos, anúncios de início e encerramento, documentos de oferta, atas, fatos relevantes, demonstrações financeiras, relatórios do administrador, páginas de rentabilidade e eventos externos.

Monte uma timeline com:

- constituição e primeira emissão;
- emissões posteriores, volumes, benchmarks e público-alvo;
- cotistas ou distribuição efetiva, quando publicados;
- lastro e concentração permitida;
- subordinação mínima e waterfall;
- evento de avaliação ou liquidação;
- primeiro sinal de deterioração nos documentos e no Informe Mensal;
- efeito por cota sênior, mezanino e subordinada;
- assembleias, quórum, matérias, votos, conflitos e resultado;
- situação final e lacunas documentais.

No SAV Nexoos, separe a relação societária e a posição de cotas da Americanas/Ame da causa documental da liquidação. A liquidação antecipada de outubro de 2022 antecede a divulgação da crise contábil da Americanas. Reconcilie o atraso bruto produzido pelo efeito vagão, a subordinação e a ordem de amortização Sênior → Mezanino.

No FIDC Light, trate o lastro como fluxo futuro de recebíveis de energia. Reconcilie rating, Evento de Desalavancagem, votação sobre Realavancagem, tutela cautelar, recuperação judicial, retenção em contas vinculadas e amortização acelerada. Destaque quando o campo de inadimplência da CVM permanecer em zero apesar dos sinais contratuais e jurídicos.

Para cada valor material, escreva no slide a fonte de coleta: Informe Mensal CVM, regulamento/ata no Fundos.NET-B3, demonstração financeira auditada, página do administrador, decisão CVM, termo ANBIMA, Banco Central, Judiciário ou notícia de mercado. Registre URL, data de consulta, documento e página nas notas do slide.

## Regras de dados

- Preserve valores declarados e campos brutos.
- Separe fonte oficial, documento primário, cálculo, inferência e lacuna.
- Use `N/D` quando a informação não estiver publicada.
- Separe zero reportado de ausência.
- Reconcilie fundo, classe e subclasse por competência.
- Trate inadimplência, carteira, PDD, subordinação e `PR_APURADA` com denominadores explícitos.
- Identifique retornos da CVM como “retorno reportado”.
- Calcule retorno econômico com cota e fluxos de amortização/distribuição, datas efetivas e benchmark.
- Mantenha divergências entre CVM, Fundos.NET e administrador visíveis.
- Trate “uma conta sênior reportada” como indício. A CVM não publica a identidade do titular; a confirmação de posição exclusiva exige cadastro interno ou informação do custodiante.
- Na Carteira 101, ordene os candidatos por PL publicado, mostre competência e preserve fundos sem dado exato como `N/D`.
- Na decomposição de Financeiro, use buckets mutuamente exclusivos e um ledger por CNPJ. Nome é sinal de triagem; taxonomia funcional e documento têm precedência. Preserve “sem segregação” quando a fonte pública não separar INSS, servidor público, FGTS, CLT, PF e PJ.
- Reconcilie TAPSO, PagSeguro, CloudWalk, PicPay e demais veículos da cadeia de pagamentos por CNPJ. Informe quanto está dentro e fora do Tipo ANBIMA Financeiro.

## Regulação e fiscalização

Para cada mudança regulatória, informe data, preocupação original, implementação concreta, fonte oficial, efeito observado e lacuna remanescente. Classifique a efetividade como efetiva, parcial, em implantação ou sem evidência pública suficiente, com justificativa factual.

Para Termo de Compromisso CVM, TAC e termo ANBIMA, explique base jurídica, efeito processual, prazo, prova de cumprimento, fiscalização e consequência do descumprimento. Use “multa” somente quando houver processo, acusado, conduta, decisão e valor confirmados. Separe pagamentos consensuais e contribuições educacionais.

No acordo CVM–BCB, detalhe objeto, ampliação do SCR, entidades reportantes, uso supervisório, sigilo, cronograma e novidades posteriores. Informe quando o resultado existir apenas em ambiente protegido ou não tiver painel público.

Na Operação Carbono Oculto, informe datas, fundos e tipos de fundos citados, prestadores, uso alegado das estruturas, providências da CVM antes e depois da operação e recomendações posteriores. Separe operação policial, investigação administrativa, termo de acusação, processo sancionador e condenação.

No Banco Master, trate Credcesta como produto/carteira de crédito. Separe originação, venda de carteira, substituições, circulação por fundos e avaliação dos ativos. Informe a fonte de cada valor e explique que o Informe Mensal público não comprova a existência ou a validade de contratos individuais.

## Estrutura do deck

Mantenha uma lâmina por caso e capítulos separados para:

1. síntese executiva;
2. casos em timeline;
3. leitura transversal das evidências;
4. Carteira 101: uma conta sênior reportada;
5. decomposição do Tipo ANBIMA Financeiro;
6. Operação Carbono Oculto e REAG;
7. Banco Master e Credcesta;
8. evolução regulatória, posições públicas e teste de efetividade;
9. plano emergencial da CVM;
10. instrumentos jurídicos e termos por prestador;
11. sanções e multas confirmadas;
12. cooperação CVM–BCB;
13. risco e retorno;
14. agenda analítica.

## Padrão visual e Office

- Fundo branco, texto preto, tons de cinza e laranja Itaú `#EC7000` somente para hierarquia e timelines.
- Fontes Itaú Display, Itaú Display Black e Itaú Display X-Bold.
- Títulos em caixa normal; evite caixa alta integral.
- Use tabelas nativas do Office. Proíba tabelas simuladas por caixas de texto.
- Use shapes somente para timelines, setas e elementos funcionais.
- Evite cards, chips, painéis coloridos, sombras e linhas cinza decorativas.
- Aplique hierarquia por tamanho, peso e família tipográfica: título, cabeçalho, primeira coluna e corpo.
- Mantenha todas as tabelas, textos e formas editáveis no PowerPoint.
- Inclua fontes nas notas de cada slide em bloco `[Sources]`.

## Linguagem

Escreva em português, com frases curtas, diretas e factuais. Evite slogans, surpresa, exagero, contraposições retóricas e conclusões sem evidência. Use magnitude, data, competência e fonte perto de cada conclusão.

## QA e publicação

Renderize todos os slides, inspecione cada página, execute teste de overflow e conte tabelas nativas no OOXML. Verifique fontes, cortes, sobreposições, placeholders, notas e links. Publique o PPTX em `Dados da Indústria > Exportações` com o rótulo `Estudos de Caso`. Exiba este prompt no expander `Prompt usado para atualizar este artefato`. Teste o download em sessão anônima após o deploy.
