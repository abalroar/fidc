# Curadoria documental de FIDCs

Atualize o deep dive de crédito consumido por Dados de Carteira → Documentos. Use o schema documental v2 e o processo descrito em `docs/documentary_diligence.md`.

Carteira selecionada para inspeção: [NOME_OU_ID_DA_CARTEIRA_EXISTENTE]
ID: <portfolio_id>
Competência solicitada: [PERIODO_OU_COMPETENCIA]

## Escopo

O processo global deduplica os CNPJs de todas as carteiras existentes em `portfolios.json`. A carteira selecionada define a inspeção visual e a ordem das colunas. Preserve a composição de todas as carteiras e o trabalho alheio. Use checkout isolado quando houver mudanças concorrentes.

Para manutenção dirigida, os comandos individuais aceitam `--only-cnpj`; declare o escopo executado. Quando a solicitação abranger todas as carteiras, execute a atualização global. Não transforme uma restrição operacional da interface em restrição de aquisição.

## Aquisição e identidade

1. Confirme CNPJ, fundo, classe e subclasse. Nomes semelhantes não demonstram identidade.
2. Catalogue Fundos.NET sem restringir o tipo de fundo: FIDC, FIC e FIAGRO podem ter registros em categorias diferentes.
3. Reutilize arquivos íntegros, URLs e hashes. Obtenha regulamentos, versões, anexos, apêndices, suplementos, atas, fatos relevantes, DFs, ratings e verificação de lastro.
4. Pesquise fontes primárias do administrador, gestor, agência e verificador quando o documento referido estiver ausente do Fundos.NET. Registre a busca efetivamente realizada, resultado, bloqueio e rota ainda não executada.
5. Siga classes investidas somente com vínculo documental e CNPJ exato. Política de investimento, vínculo nominal e posição efetiva recebem estados distintos. Nunca estime pesos não declarados.

## Leitura e critérios

Use `services/documentary_criteria_catalog.py` como catálogo comum, preservando perguntas anteriores e critérios específicos. Extraia números, bases, camadas, prazos, frequência, cura, reincidência e consequências. Inclua elegibilidade, concentração, alocação, reservas, subordinação, waterfall, PDD, garantias, servicing, hedge, taxas, quóruns, emissões, eventos e alterações.

Cada resposta precisa de documento, versão/data e cláusula ou página. Campo XML deve apontar ao caminho do campo, sem inventar página. Separe trecho primário, parecer anterior rastreável e leitura dirigida registrada. Trecho recuperado por palavra-chave precisa responder à pergunta; definição, remissão e matéria de assembleia não demonstram limite ou cobrança.

Mantenha as versões anteriores no histórico. Se a versão atual não confirmar a resposta, suspenda a afirmação antiga. Regulamento geral, anexo, apêndice e ato de alteração exigem escopo e prevalência explícitos. Data de arquivo não comprova início de vigência. Exponha conflitos com seu efeito, sem decidir por suposição.

## Ausência e competência

Use estados tipificados com motivo individual: documento não obtido, inacessível, texto não recuperado, cláusula não localizada, anexo referido ausente, conflito ou extração pendente. Não use N/D genérico, traço ou instruções de interface como resposta. Não aplicabilidade exige fundamento documental; aplicabilidade em apuração fica no denominador.

Resolva a posição comum da cesta completa. Preserve exclusões e fonte temporal. Cruze limites somente com numerador, denominador, unidade, camada e vigência compatíveis. PL zero permanece zero; dado ausente permanece ausente. Posição mensal não demonstra conformidade diária, cura ou reincidência. Disponibilidades não equivalem automaticamente à reserva contratual.

## Execução e recursos

Execute o wrapper serial `scripts/refresh_all_documentary_diligence.py --resume`. Use piso de disco, orçamento de download, limites por arquivo, timeout e retomada. Um arquivo por vez; reaproveite o corpus e não carregue histórias financeiras extensas ao abrir Documentos. Consulte `--help` para limites e etapas.

Publique critérios e metadados portáveis; mantenha PDFs, textos, XMLs e caminhos pessoais fora do Git. O acervo local sustenta retomada; o inventário público conserva fonte, hash, versão, resultado e motivo.

## Aceite

- Meça respostas com valor e fonte ÷ critérios aplicáveis por fundo, antes/depois no mesmo denominador. Declare a limitação da reconstrução histórica.
- Liste cada célula pendente com seu motivo. Preserve perguntas sem resposta e diferencie revisão automática e leitura dirigida.
- Mantenha fundos em colunas estáveis. Consolide somente regras comuns comprovadas e conserve as fontes individuais.
- Valide cesta ampla, fundo individual e FIC; competência, fontes inline, CSV/JSON e PPTX efetivamente servidos.
- Execute testes relevantes e o relatório `scripts/report_documentary_diligence.py` depois de encerrar aquisição e construção. Confirme consistência dos insumos.
- Relate implementação local, commit/PR e publicação separadamente. Concluir o código não confirma funcionamento no ambiente público.
