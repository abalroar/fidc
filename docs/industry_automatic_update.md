# Atualização da indústria de FIDCs

`scripts/update_fidc_industry.py --apply` verifica os arquivos oficiais da CVM,
reconstrói as tabelas e publica o pacote Excel/PPT/HTML após a validação. A
verificação isolada usa `--check-only` e mantém a base publicada intacta.

O inventário inclui todos os ZIPs mensais e anuais disponíveis de Informe
Mensal, cadastro de fundos/classes, histórico de prestadores e ofertas públicas.
Os arquivos incluem todos os veículos reportantes. A publicação ANBIMA de
renda fixa e seu anexo também participam da detecção de mudanças. HTTP
condicional evita downloads repetidos; SHA-256 identifica retificações mesmo
quando a competência continua igual. A primeira consulta verifica os bytes
integrais. Um ZIP inválido preserva o cache anterior.

Os comparativos correntes seguem `ComparisonCut`: último mês com status
`completa` em `industry_competence_status.csv`. Para agosto de 2026, o intervalo
é janeiro a agosto, comparado com janeiro a agosto dos anos anteriores. O
calendário avança automaticamente, inclusive na mudança de ano e em fevereiro.
A competência preliminar permanece separada. Datas de documentos, snapshots
cadastrais ANBIMA e decisões históricas de classificação são preservadas. Se a
ANBIMA publicar depois da CVM, o estudo CVM avança e a comparação ANBIMA mantém
a janela da sua própria fonte, identificada no manifest e na apresentação.

O processo mantém um lock local, o estado em `.cache/industry-refresh/state.json`
e backups das versões substituídas de fontes. A automação reutiliza esse estado
e os caches do checkout principal em cada worktree, evitando reiniciar a
detecção de fontes a cada execução. A reconstrução ocorre em um
diretório privado. Os dados publicados são promovidos após a validação integral
do pacote, e o conjunto anterior permanece recuperável. Uma falha conserva o
staging para diagnóstico. Alterações concorrentes na base publicada impedem
a promoção. As fontes só recebem o status de publicadas após o sucesso.

O workbook de estilo vem do Excel canônico já validado e é congelado por hash;
o processo dispensa um arquivo específico da pasta Downloads. Os campos sem
evidência continuam `N/D`, e zeros reportados pela CVM continuam zero. Novos
fundos recebem lacunas documentais explícitas. Conflitos de perímetro ou de
curadoria interrompem a publicação para revisão.

A automação do Codex acompanha este chat diariamente às 09h, no fuso
America/Sao_Paulo. Quando houver mudança validada, ela executa a atualização,
testa os fluxos de exportação e publica os arquivos pertinentes no GitHub. Sem
mudança relevante, permanece silenciosa. Essa execução local requer o
computador ligado e o aplicativo Codex aberto. O fluxo verifica também uma sessão nova de
https://tomaconta-fidcs.streamlit.app/ e seus downloads após a publicação.

Para reproduzir com diretórios próprios, estão disponíveis `--data-dir`,
`--raw-dir`, `--offers-dir`, `--cadastro-dir`, `--state` e `--input-workbook`.
Os caches brutos e os backups permanecem fora do Git. O commit da publicação
inclui os dados materializados, manifests, artefatos Office e código que os
consome.
