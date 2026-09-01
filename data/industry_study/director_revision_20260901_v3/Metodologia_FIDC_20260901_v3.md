# Metodologia da revisão de 01/09/2026 · v3

## Decisão PF/PJ

O ledger preserva 26 fundos avaliados. Entram 24; Sólido e BizCapital Finpass PME permanecem em Financeiro por decisão do usuário. A leitura integral dos regulamentos confirma produto de crédito direto PF/PJ nos incluídos. A proxy mensal usa a maior posição positiva da Tabela VIII dividida pelos direitos creditórios brutos reconciliados. O corte é Top1 igual ou inferior a 1%. Não há requisito mínimo de 25 linhas positivas: o material registra 578 posições entre 24 fundos, sendo 5 fundos com 25, 18 com 24 e 1 com 21.

O valor mostrado é o PL integral dos fundos selecionados. A exposição efetiva PF/PJ, a divisão PF versus PJ e o total de devedores permanecem N/D.

## Estoque

O cenário principal exclui TAPSO e Sistema Petrobras do numerador e do denominador em todas as competências. A lista de 24 CNPJs de jun/26 é retroaplicada ao histórico e retirada de Financeiro. Essa é uma taxonomia congelada, não uma reconstrução da classificação vigente em cada data.

## Recuperação, precatórios e multicedente

O Tipo/Foco ANBIMA recebe primeiro o overlay documental aprovado por CNPJ. A regra de exibição é:

- Outros + Poder Público: Precatórios / ações;
- Outros + Multicarteira Outros ou Multicedente/Multissacado: Multicedente / multisacado;
- Outros + Recuperação: Recuperação / NP;
- demais casos sem fechamento: N/D.

## Emissões

A base usa ofertas públicas primárias de cotas de FIDC encerradas, da CVM/SRE. O emissor é cruzado primeiro pelo CNPJ do fundo e depois pelo CNPJ da classe contra o mapa congelado de jun/26. Emissores ausentes desse mapa ficam em N/D. FIC-FIDC fica fora das oito categorias. O volume de 2023 é escalado ao total encerrado ANBIMA, mantendo o mix observado da coorte CVM. Fundos extintos continuam no fluxo histórico; sem classificação recuperável, ficam em N/D.

Os CSVs por oferta, categoria e CNPJ são a fonte numérica dos slides.

## Estrutura editorial e compatibilidade Office

O deck final contém 29 slides. Em relação à v2, saem os slides 23, 24, 26 e 33. Os slides 17 e 19 permanecem e usam quatro charts nativos recriados a partir das séries ANBIMA já auditadas. O reempacotamento substitui relações OOXML de charts que acionavam a reparação do PowerPoint.

Títulos principais e cabeçalhos editoriais usam caixa mista. Rodapés de fonte e metodologia ficam alinhados à esquerda. Linhas cinza isoladas são removidas quando a separação já está definida por espaço, alinhamento ou mudança de bloco. Os antigos chips laranja dos slides 14 e 25 são eliminados; título e explicação de cada bloco metodológico passam a ocupar uma única caixa de texto.

A validação exige renderização integral, teste de overflow, inspeção estrutural e abertura direta dos dois PPTX no Microsoft PowerPoint sem aviso de reparação.

## Paleta dos prestadores

Cada participante usa cor estável em administração, gestão e custódia. Itaú usa `FF5500`, Kanastra `7030A0`, QI Tech `2456D6`, BTG `1D4080`, Oliveira Trust `7A1F3D`, Bradesco `73787D`, Daycoval `BEC2C5`, Genial `6EC5E9`, Tercon `8D9399`, CBSF/REAG `73C6A1`, Finaxis `5B6065`, BRL Trust `454A4F` e Hemera `30353A`.
