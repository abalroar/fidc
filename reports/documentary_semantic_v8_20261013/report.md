# Correção semântica V8 — curadoria documental

Corte: 2026-10-13T14:20:19+00:00. Conjunto: 194 CNPJs das carteiras cadastradas e 1 classe investida adicional documentada (Multiplik, CNPJ 23.426.441/0001-55). Comparação com os dados imutáveis do commit `9ffb7cfb3e0de22de885e8c8176f862ec7edca24`.

A validação exige condições efetivas em elegibilidade e identificação positiva de originadores e devedores. Introduções sem condições, conflitos de prestadores e menções em SAC, cadastro, concentração, cobrança ou riscos ficam fora da prova desses critérios. Os oito devedores relidos e as quatro células manuais corrigidas foram incluídos na conferência final.

| Escopo | Antes: valor e fonte / denominador | Depois: valor e fonte / denominador | Pendências depois |
|---|---:|---:|---:|
| 194 CNPJs cadastrados | 7803/11053 (70,60%) | 7751/11053 (70,13%) | 3302 |
| Classe investida adicional | 36/57 (63,16%) | 35/57 (61,40%) | 22 |

O denominador inclui critérios aplicáveis e aqueles cuja aplicabilidade está em apuração. Somente a não aplicabilidade comprovada por documento sai do denominador. O numerador exige valor confirmado e fonte com identidade, data e localização. As duas medições usam a mesma regra; o denominador ficou estável por fundo.

Nas 220 células afetadas originalmente, 209 respostas foram recuperadas ou substituídas por conteúdo específico, 0 preservaram o valor após retirada de fonte irrelevante e 11 passaram a pendência qualificada. A revisão V8 acrescentou 140 células de devedor: 77 recuperadas, 6 com valor preservado e 57 pendentes. O conjunto comparado reúne 360 células distintas.

A QA leu os 195 JSONs, com 11117 critérios e 7812 células confirmadas. Foram conferidos 7588 valores primários e 16771 trechos de prova automática: zero rejeições restantes e zero fontes secundárias inválidas nos três critérios corrigidos. As 5 interpretações manuais que exigem contexto estão registradas separadamente com hash do trecho e motivo da aprovação. A conferência de OCR encontrou 68 fontes e zero usos automáticos de páginas excluídas; 2 fontes usam leitura visual dirigida identificada.

A suíte final passou com 433 testes e 33 subtests em9,06s no hash da guarda V8; o resultado está em [tests.json](tests.json). A validação dirigida de builder/guarda passou com71 testes e31 subtests antes do writer final. A auditoria mede pertinência e rastreabilidade; validade jurídica, vigência e interpretação quantitativa permanecem sujeitas às ressalvas documentais de cada célula.

Arquivos de conferência:

- [Cobertura por fundo, antes e depois](coverage_by_fund_before_after.csv): 195 linhas, com nomes completos e denominadores.
- [Todas as pendências e motivos](pending_cells_with_reasons.csv): 3324 linhas; inclui aplicabilidade ainda em apuração.
- [Manifesto dos mesmos dados conferidos](input_manifest.json): hashes de dados, código, comparação e QA.
- [Comparação detalhada das 360 células](../../data/documentary_diligence/qa/clause_validation_v8_comparison.json).
- [QA final V8](../../data/documentary_diligence/qa/clause_validation_final_v8.json).

Hash da comparação: `d1c750a8e5c52065c53cc51c908583a2baf0f8b50da5656dc23de1e88846f97e`. Guarda V8: `746b9dd73f83c6f1b21c2c7b5c00e9dc34d1c1f00a12859b65860dd36ef1330c`. Os snapshots V7 são intermediários históricos; o relatório anterior das 04:16 permanece preservado.
