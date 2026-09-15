# Brief para o Codex — output orientado a insight (aba Indústria / Toma Conta FIDCs)

> Cole isto no início da tarefa do Codex. Objetivo: parar de entregar **infraestrutura
> vazia** e passar a entregar **achado de negócio pronto para um slide do Comitê**.
> Contexto: há uma apresentação de FIDCs para o Presidente do Itaú BBA em 15 dias.

## Regra de ouro

**Nenhuma tarefa está "pronta" enquanto não produzir uma linha material com um achado que
um diretor do BBA usaria.** Pipeline que roda mas devolve `sem_uso` / `0 linhas` **não é
entrega** — é andaime. Se um ledger/atlas/auditoria nasce vazio, a tarefa é **preenchê-lo
com dados reais** ou **não criá-lo**.

## O que mudar no comportamento

1. **Lidere pela resposta, não pelo processo.**
   - ❌ "40/40 artefatos presentes, 13 módulos ok, py_compile passou, git diff --check ok."
   - ✅ "Oliveira Trust passou de R$ 20→76 bi em gestão e virou a maior; QI Tech domina
        administração com R$ 139 bi. Itaú administra R$ 32 bi (4–5x atrás)."
   - Métricas de processo (compile, diff, contagem de artefato) vão **no rodapé**, em 1 linha.

2. **Materialize dado, não estrutura.** Antes de criar mais um domínio de ledger/auditoria,
   pergunte: "isto vai nascer com linhas reais?" Se a resposta for não, priorize **popular o
   que já existe vazio** (cedentes/sacados, delta mensal, lacunas do snapshot).

3. **Toda entrega responde a uma das perguntas do Presidente:**
   - Quem **cresceu / caiu** (gestor, administrador, custodiante) e por quê?
   - Quem são os **cedentes e sacados relevantes** (nome, setor, materialidade)?
   - O que explica **QI Tech e BTG** ganharem, e a **Oliveira Trust** liderar?
   - O que os **regulamentos** dizem (subordinação, gatilhos, benchmark, última emissão)?
   Se a tarefa não move nenhuma dessas, **questione a prioridade antes de codar.**

4. **Definição de "done" = insight apresentável.** Um número + um "e daí?" (implicação para
   o BBA). Ex.: "Mercado Pago é o maior sacado (R$ 5,7 bi) → crédito colado a pagamentos."

5. **Foco na camada mais fraca primeiro.** Hoje o gargalo é **cedente/sacado** (só ~142
   partes nomeadas). Adensar as leituras de regulamento dos **Top 50–100 fundos por PL**
   vale mais que qualquer novo módulo de meta-pipeline.

## Formato de report ao usuário (obrigatório)

```
ACHADO (1–3 bullets de negócio, com número e implicação)
DADO NOVO MATERIAL: X linhas em <arquivo> (não "infra pronta, 0 linhas")
LIMITAÇÃO/RISCO: o que ainda está ralo ou incerto
— rodapé: compile/diff/testes/commit em 1 linha
```

## Anti-padrões a evitar (observados)

- Criar ledger/atlas/auditoria que reporta `N domínios sem_uso`. **Vazio não conta.**
- Encerrar rodada com "não commitei porque não pediram" sem dizer **qual insight saiu**.
- Somar entidades sem de-para de conglomerado (Itaú Asset ≠ Itaú Unibanco ≠ Kinea devem
  somar; **Itaúna ≠ Itaú**). Use `services/conglomerados.py`.
- Reportar cobertura de artefato como se fosse resultado de negócio.

## Prioridades imediatas (ordem)

1. Adensar **cedentes/sacados** nomeados dos Top 100 fundos (materialidade + setor + evidência).
2. **Delta mensal** de gestor/administrador/custodiante com narrativa de "quem entrou/saiu".
3. **Regulamentos** dos Top 25: subordinação mínima, gatilhos, benchmark, última emissão.
4. Só então: mais meta-pipeline, se houver linha material para preencher.
