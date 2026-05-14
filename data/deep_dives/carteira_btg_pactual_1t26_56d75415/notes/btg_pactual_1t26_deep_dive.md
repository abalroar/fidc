# Deep Dive BTG Pactual 1T26

## Escopo

Carteira analisada: BTG Pactual 1T26, portfolio id `56d75415a8444cf1981f0e08d9cb2e40`.

Fundos/veículos no pacote:

- Consignado Delta Receivables I FIDC, CNPJ 54.871.427/0001-94.
- MT Consignado Privado I FIDC, CNPJ 60.010.416/0001-12.
- BTG Pactual Ceres Confina FI nas Cadeias Produtivas do Agronegócio, CNPJ 62.696.791/0001-93.
- PLGN Marketplace FICFIDC, CNPJ 55.563.624/0001-09.
- V CDT 1 FIDC, CNPJ 62.552.447/0001-20.
- Classe Consignado Privado do MT Global FIDC, CNPJ 63.953.620/0001-65.

## Conclusão Principal

A única evidência nominal explícita de Meu Tudo/Parati na carteira está no MT Consignado Privado I. O regulamento e as atas desse fundo indicam Parati - Crédito, Financiamento e Investimento S.A. como Endossante e Tudo Serviços S.A. como Meu Tudo/Agente de Retenção e Cobrança, com créditos originados por empréstimo consignado via Plataforma MT.

Não foi encontrada menção exata a Banco PAN como cedente, originador, parceiro ou fonte dos créditos nos documentos locais analisados.

## Sacados e Origem

No MT Consignado, os devedores são pessoas físicas com vínculo formal de emprego, CTPS digital, categoria eSocial 101, validadas pela Dataprev. Os direitos creditórios são CCBs eletrônicas de empréstimo consignado concedido pelo Endossante por meio da Plataforma MT, com fluxo operacional ligado à consignação/arquivos Dataprev e conta vinculada.

No Consignado Delta, reaproveitado da curadoria dedicada anterior, os documentos apontam CCCBs/CCBs de empréstimos pessoais consignados, mas não identificam nominalmente originador/cedente como Meu Tudo, Parati ou Banco PAN.

No MT Global, o CNPJ correto para a classe da carteira é 63.953.620/0001-65. A classe recebeu ativos/obrigações por cisão do MT Consignado e do BTG Pactual Consignados II. Para a parcela vinda do MT Consignado, a origem documental remete a Parati/Meu Tudo/Plataforma MT. Para o BTG Consignados II, o regulamento local analisado descreve cedentes financeiros genéricos e créditos ligados a CCBs/FGTS/INSS, sem nomear Parati, Meu Tudo ou Banco PAN.

## Veículos Não Consignados ou com Lacuna

O Ceres Confina é veículo de cadeias produtivas do agronegócio, não consignado. O próprio regulamento afirma que, pela diversidade de cedentes/endossantes/devedores, não é possível precisar os processos de origem e políticas de crédito dos cedentes/endossantes.

O PLGN Marketplace é FICFIDC. Os documentos analisados indicam investimento em cotas da classe investida e ativos financeiros de liquidez, sem identificar cedentes/sacados finais no nível do FICFIDC.

O V CDT 1 identifica VR Benefícios e Serviços de Processamento S.A. como prestador de retenção/cobrança, mas não revela cedentes, sacados ou origem final dos créditos no documento local analisado.

## Artefatos

As tabelas principais adicionadas ao pacote são:

- `key_findings.csv`: resumo executivo auditável.
- `cedentes_sacados_origem.csv`: mapa de cedentes/endossantes, agentes, sacados/devedores e origem.
- `source_vehicle_trace.csv`: trilha de CNPJs e cisões, especialmente para MT Global.
- `comparison_main.csv`, `emissions.csv`, `thresholds.csv`: pacote padrão do app com IME, emissões e gatilhos monitoráveis.
