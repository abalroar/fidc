# Prompt mestre v2 — atualização do PPTX da indústria de FIDCs

Atualize o PPTX e seus arquivos auditáveis usando fontes oficiais, leitura documental integral e bases por CNPJ. Preserve `N/D` quando a fonte não permitir mensuração. Todo número apresentado deve existir em um CSV ou JSON do pacote, com competência, unidade, fonte e regra de cálculo.

## Escopo editorial do deck completo

Entregue um PPTX completo de 33 slides com esta ordem:

1. preserve os slides 1–9 do deck-base, atualizando apenas dados autorizados;
2. preserve o bloco corrente de emissões CVM/SRE equivalente aos antigos slides 24–27;
3. insira, depois desse bloco, os 13 slides nativos do estudo ANBIMA/IBBA: posição competitiva, sumário, originação, distribuição, visão por produto, destaque de FIDC, maiores operações, Top FIDCs Middle e metodologia;
4. preserve o bloco final equivalente aos antigos slides 33–39;
5. exclua os blocos equivalentes aos antigos slides 10–23 e 28–32.

Recupere o bloco ANBIMA de uma versão anterior compatível e valide a data de referência antes de reutilizá-lo. Preserve charts, tabelas, workbooks incorporados, notas e temas como objetos nativos. Se houver edição dos dados ANBIMA, refaça a apuração a partir das planilhas oficiais e registre a nova competência. Não atualize números pela aparência do slide.

## Fontes e precedência

Use, nesta ordem: regulamento vigente na competência, lido integralmente; documentos oficiais complementares FundosNet/B3/CVM; cadastro e Informe Mensal CVM; Tipo e Foco ANBIMA; ledger documental aprovado; inferência identificada e acompanhada de evidência. O regulamento define o mandato permitido. O Informe Mensal mede a carteira observada. Registre divergências entre ambos.

## Universo, competência e temporalidade

- Confirme a competência mais recente com cobertura completa.
- Use uma linha por competência e CNPJ de fundo, PL numérico e não ausente.
- Exclua FIC-FIDC do numerador e denominador.
- Exclua do saldo corrente fundos oficialmente extintos ou encerrados; ausência isolada de reporte continua como lacuna.
- Preserve ofertas encerradas no fluxo histórico, mesmo após extinção do fundo.
- Construa um ledger com `competencia_inicio`, `competencia_fim`, fonte, data do documento e decisão.
- Quando a classificação mudar, use a categoria vigente em cada competência. Se o histórico documental não estiver disponível, publique explicitamente um cenário reconstruído com taxonomia congelada.
- Mantenha cenários com e sem FIDC do Sistema Petrobras, CNPJ 09.195.235/0001-50, e TAPSO FIDC, CNPJ 26.287.464/0001-14. Recalcule numerador e denominador.

## Multicarteira Pulverizado PF/PJ

Inclua crédito direto a PF ou PJ confirmado no regulamento, como empréstimo pessoal, crédito estudantil, BNPL, crédito direto a MPMEs e outros produtos diretos documentados. CCB isoladamente não comprova produto, devedor ou pulverização. Leia definições, política de investimento, elegibilidade, concentração, anexos e originação.

Mantenha em Financeiro consignado/INSS/FGTS, veículos, imobiliário, adquirência, agenda de recebíveis, cartão ou meios de pagamento como produto principal e carteiras sem evidência suficiente. As ordens 11, Sólido, e 26, BizCapital Finpass PME, do ledger de 01/09/2026 permanecem em Financeiro até decisão documentada posterior.

Para concentração observada, reconcilie Tabelas I, II e VIII. Calcule direitos creditórios brutos como direitos creditórios líquidos mais PDD, com ajustes documentados. Use a maior posição positiva da Tabela VIII como proxy Top1. O critério vigente é Top1/DC brutos menor ou igual a 1%. Registre quantas posições foram reportadas; não exija 25 posições. Posições reportadas não equivalem ao total de devedores.

Mostre quantidade de fundos, PL integral dos fundos selecionados, participação no PL ex-FIC e posições reportadas. Exposição efetiva PF/PJ, divisão PF/PJ e total de devedores ficam `N/D` até uma base oficial fechar essas métricas.

## Recuperação, precatórios e multicedente

Aplique o overlay documental aprovado ao Tipo/Foco ANBIMA e mantenha os campos oficiais em colunas separadas:

- Precatórios / ações: Tipo Outros + Foco Poder Público.
- Multicedente / multisacado: Tipo Outros + Foco Multicarteira Outros ou Multicedente/Multissacado.
- Recuperação / NP: Tipo Outros + Foco Recuperação.
- N/D: linha que não fecha em outra categoria.

Registre documento, página, trecho de evidência, confiança e responsável. Fundos novos exigem leitura do regulamento. Fundos com mudança de classificação exigem intervalo temporal ou decisão explícita de retroaplicação.

## Novas emissões por setor

Use ofertas públicas primárias de cotas de FIDC encerradas, deduplicadas pela chave oficial. Faça o match pelo CNPJ do fundo e depois pelo CNPJ da classe; sem match fica N/D. Use o mesmo ledger efetivo do saldo. Exclua FIC-FIDC dos setores e mostre seu volume na reconciliação. Se 2023 precisar ser escalado ao total ANBIMA, publique o fator. Investigue emissores N/D materialmente relevantes e documente buscas frustradas.

Entregue um CSV por oferta com data, CNPJ, nome, valor observado, fator, valor apurado, categoria, tipo de match, FIC e fonte; e um CSV agregado cujas participações fechem 100% do volume ex-FIC.

## Prestadores e identidade visual

Em administração, gestão e custódia, preserve o Top 5 verdadeiro e acrescente Itaú e Kanastra quando estiverem fora dele. Itaú agrega apenas entidades documentadas do conglomerado no papel analisado, como Intrag e Kinea quando aplicável. Kanastra agrega Limine conforme a curadoria. Não some papéis diferentes e publique a linhagem por entidade.

Use a mesma cor para a mesma casa em todos os gráficos: Itaú `FF5500`; Kanastra `7030A0`; QI Tech `2456D6`; BTG `1D4080`; Oliveira Trust `7A1F3D`; Bradesco `73787D`; Daycoval `BEC2C5`; Genial `6EC5E9`; Tercon `8D9399`; CBSF/REAG `73C6A1`; Finaxis `5B6065`; BRL Trust `454A4F`; Hemera `30353A`. Uma casa nova recebe cor distinta, legível e estável, registrada no mapa de paleta.

## Textos metodológicos mínimos

- `* PF/PJ = PL de fundos com crédito direto PF/PJ confirmado em regulamento e Top1 mensal <=1% dos DC brutos; 24 CNPJs; Sólido e BizCapital mantidos em Financeiro. Exposição efetiva e total de devedores: N/D.`
- `* Outros = Poder Público para Precatórios/ações; Multicarteira Outros ou Multicedente/Multissacado para Multicedente/multissacado; Recuperação para Recuperação/NP, após overlay documental aprovado.`
- `* Emissões = ofertas CVM/SRE encerradas, match por CNPJ de fundo e depois classe, FIC fora, não localizado=N/D; 2023 escalado ao total ANBIMA.`
- Informe se a série usa vigência documental ou taxonomia congelada.

## Controles e entregáveis

Valide CNPJs como texto de 14 dígitos; reconcilie PL bruto, ex-FIC e cenários; confirme categorias e participações; preserve N/D; mantenha PF/PJ retirado exclusivamente de Financeiro; confirme Sólido e BizCapital em Financeiro; use a mesma lista efetiva nas emissões; gere hashes SHA-256; renderize todos os slides; inspecione OOXML, charts, tabelas, notas e overflow.

Entregue: PPTX completo de 33 slides; PPTX das lâminas alteradas; CSVs de decisões PF/PJ, incluídos, categorias, emissões, exclusões e prestadores; relatório; metodologia; manifesto; ZIP; commit, push, merge; e validação dos downloads anônimos do site contra o manifesto.
