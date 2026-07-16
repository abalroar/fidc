# Casos documentais usados no glossário

O corpus congelado contém exatamente 100 fundos. Esta página não cataloga os 100: identifica dez casos com documento primário recuperado que servem de referências cruzadas para linguagem contratual. A presença não constitui seleção de investimento, rating ou avaliação corrente.

## Casos narrativos reconciliados

| Fundo | CNPJ do fundo | Segmento oficial na competência 202605 | Documento-âncora | Uso editorial |
|---|---|---|---|---|
| FIDC do Sistema Petrobras | 09.195.235/0001-50 | Industrial | regulamento, Fundos.NET 792797 | arquitetura corporativa e política de classe |
| TAPSO FIDC RL | 26.287.464/0001-14 | Cartão de crédito | regulamento, Fundos.NET 1066031 | recebíveis e estrutura de pagamentos |
| Cloudwalk Bela FIDC | 62.393.679/0001-83 | Cartão de crédito | regulamento, Fundos.NET 1117954 | meios de pagamento como taxonomia documental |
| Itaú Crédito Privado FIDC RL | 53.286.499/0001-01 | Serviços | regulamento, Fundos.NET 579249 | limites e elegibilidade |
| Esperanza FIDC | 53.263.761/0001-00 | Financeiro — outros | regulamento, Fundos.NET 830304 | necessidade de ler a abertura “outros” com documentos |
| BTG Pactual Consignados II FIDC | 52.242.420/0001-88 | Serviços | regulamento, Fundos.NET 938243 | distinção entre segmento reportado e taxonomia funcional |
| Classe Consignado Privado do MT Global FIDC RL | 63.953.619/0001-30 | Comercial | anexo/regulamento da classe 63.953.620/0001-65, Fundos.NET 1222863 | vínculo fundo–classe e documento no CNPJ componente |
| Aetos Energia FIDC | 52.610.624/0001-24 | Serviços | regulamento, Fundos.NET 794164 | concentração e fluxos de serviços |
| FIDC PagSeguro I | 28.169.275/0001-72 | Cartão de crédito | regulamento, Fundos.NET 1149521 | papéis no arranjo de pagamento |
| Cielo FIDC | 26.286.939/0001-58 | Cartão de crédito | regulamento, Fundos.NET 1017493 | necessidade de identificar o devedor no direito concreto |

Os rótulos de uso editorial são temas de leitura, não constatações de risco. Cada afirmação contratual deve citar a página do documento; o nome do fundo, isoladamente, não prova mecanismo, devedor ou garantia.

## Como os 100 foram escolhidos

1. competência oficial congelada em 202605, conforme `competencia_snapshot`;
2. CNPJ normalizado e PL agregado no nível do fundo, somando classes componentes;
3. exclusão de PL nulo ou não positivo;
4. dois maiores de cada estrato ocupado, ou um quando só havia um;
5. até dois casos de Sem segmentação IME reservados antes do complemento;
6. vagas restantes preenchidas por PL global, com desempate por CNPJ;
7. FIC-FIDCs mantidos por materialidade e separados nas prevalências de crédito subjacente.

O algoritmo produziu 100 CNPJs únicos e cobriu os 18 estratos ocupados. Marcas e patentes não tinha população classificável na competência.

## Como os casos sustentam verbetes

- norma pode sustentar conceito normativo sem prevalência contratual;
- prática recorrente exige ao menos dois fundos economicamente independentes e documentação suficiente;
- cláusula de um único fundo é específica ou exemplo;
- cache-only não sustenta afirmação categórica;
- templates idênticos são uma família de evidência, não múltiplas práticas independentes.

## Onde está o rastro completo

Seleção, cobertura, inventário, evidências atômicas e limitações estão em `reports/glossario_100_fidcs_20260716/`. Os arquivos estruturados desta página contêm os mesmos dez fundos narrativos, com CNPJ, fonte e data de verificação.

Data de corte documental desta revisão: **16/07/2026**.
