# Estudo FIDC - nascimentos CVM e ofertas 2024FY-2026YTD

Data de corte: 2026-06-09.

## Metodo

- Nascimento CVM estrito: menor data conhecida entre constituicao, inicio e registro >= 2024-01-01.
- Registro desde 2024: data de registro CVM >= 2024-01-01; pode incluir recadastro/adaptacao de veiculo antigo.
- Volume de ofertas: conjunto CVM Ofertas Publicas de Distribuicao, tabelas `oferta_resolucao_160.csv` e `oferta_distribuicao.csv`.
- Volume encerrado conservador: apenas `Oferta Encerrada` na RCVM 160 e linhas do rito ordinario com data de encerramento.
- Volume registrado valido/ou aberto: exclui `Registro Caducado`, `Oferta Revogada` e `Oferta Suspensa`, mas inclui registros concedidos ainda nao encerrados.
- Setor nao foi inferido por nome. A fila de classificacao preserva campos CVM de lastro/ativos para leitura posterior de regulamentos e documentos da oferta.

## Totais de ofertas

| Periodo | Linhas | Linhas validas/abertas | Linhas encerradas | Volume registrado valido/aberto | Volume encerrado conservador | Emissores unicos |
|---|---:|---:|---:|---:|---:|---:|
| 2024FY | 1,458 | 1,318 | 1,291 | R$ 113.815.301.163,28 | R$ 112.458.301.168,76 | 845 |
| 2025FY | 1,717 | 1,657 | 1,440 | R$ 130.926.790.183,77 | R$ 121.609.523.691,56 | 943 |
| 2026YTD | 690 | 686 | 122 | R$ 58.215.585.287,32 | R$ 25.734.039.585,59 | 466 |

## Ofertas por nascimento CVM do emissor

| Periodo | Emissor nasceu desde 2024 | Linhas | Volume registrado valido/aberto | Volume encerrado conservador | Emissores unicos |
|---|---:|---:|---:|---:|---:|
| 2024FY | nao | 890 | R$ 58.676.126.162,63 | R$ 58.093.426.168,11 | 448 |
| 2024FY | sim | 568 | R$ 55.139.175.000,65 | R$ 54.364.875.000,65 | 397 |
| 2025FY | nao | 644 | R$ 33.173.201.901,01 | R$ 31.400.935.657,12 | 301 |
| 2025FY | sim | 1,073 | R$ 97.753.588.282,76 | R$ 90.208.588.034,44 | 642 |
| 2026YTD | nao | 243 | R$ 14.628.943.948,78 | R$ 4.494.592.099,65 | 141 |
| 2026YTD | sim | 447 | R$ 43.586.641.338,54 | R$ 21.239.447.485,94 | 325 |

## Entidades CVM

| Tipo | Total | Nascidas desde 2024 | Registradas desde 2024 | Provavel recadastro/adaptacao |
|---|---:|---:|---:|---:|
| classe_rcvm175 | 5,026 | 2,936 | 4,740 | 1,804 |
| fundo_legado_cad_fi | 1,802 | 0 | 1 | 1 |
| fundo_rcvm175 | 7,378 | 2,977 | 3,243 | 266 |

## Arquivos gerados

- `fidc_cvm_entities_all.csv`: universo CVM FIDC de fundos/classes.
- `fidc_cvm_born_since_2024.csv`: entidades com nascimento estrito desde 2024.
- `fidc_cvm_registrations_since_2024.csv`: entidades registradas desde 2024, incluindo possiveis recadastros/adaptacoes.
- `fidc_public_offers_2024_2026ytd.csv`: ofertas publicas de cotas de FIDC/FIAGRO-FIDC no periodo.
- `fidc_offer_classification_queue.csv`: fila para classificacao setorial por leitura documental.
- `summary.json`: metricas agregadas e auditoria de fontes.