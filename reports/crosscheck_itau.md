# Cross-check Itaú/Intrag e PL da indústria — veredito de confiança

Competência mai/2026. Objetivo: garantir que os números do Itaú e o PL da indústria
são **indiscutíveis** antes da apresentação ao Presidente do Itaú BBA.

---

## VEREDITO

**Pode confiar.** Os números do Itaú estão corretos, são específicos por papel e o
de-para está completo (sem falso positivo nem omissão). O PL da indústria bate
exatamente com a fonte crua da CVM. Ressalva única: **os três números do Itaú são de
papéis diferentes e não podem ser somados** — e o deck deve rotular "Itaú (Intrag)" na
administração para não confundir.

---

## 1. O que é cada número do Itaú (mai/2026)

| Papel | PL | Entidades incluídas (CNPJ) | Nº fundos |
|---|--:|---|--:|
| **Gestor** | **R$ 21,4 bi** | Itaú Unibanco Asset Mgmt (40.430.971) 15,2 + Itaú Unibanco S.A. (60.701.190) 4,2 + **Kinea** (08.604.187) 2,0 | 31 |
| **Administrador** | **R$ 31,6 bi** | **Intrag DTVM** (62.418.140) — única administradora do grupo | 40 |
| **Custodiante** | **R$ 22,4 bi** | Itaú Unibanco S.A. (60.701.190) | 34 |

> **O R$ 31,6 bi é o Itaú como ADMINISTRADOR — 100% via Intrag DTVM** (o DTVM
> administrador do grupo). Não mistura gestão nem custódia. Como Intrag é a única
> administradora Itaú, "Itaú admin" = "Intrag". Já o número de **gestão (R$ 21,4 bi)
> inclui todos os "Itaús"**: Itaú Asset + Itaú Unibanco + Kinea.

## 2. Completude do de-para (auditoria)

Varredura de **todas** as entidades com "ITAU/ITAÚ/KINEA/INTRAG" em qualquer papel no
dataset (mai/2026):

| CNPJ | Entidade | Classificação |
|---|---|---|
| 62.418.140/0001-31 | INTRAG DTVM LTDA. | → Itaú ✅ |
| 40.430.971/0001-96 | ITAU UNIBANCO ASSET MANAGEMENT | → Itaú ✅ |
| 60.701.190/0001-04 | ITAU UNIBANCO S.A. | → Itaú ✅ |
| 08.604.187/0001-44 | KINEA INVESTIMENTOS | → Itaú ✅ |
| 51.381.462/0001-37 | **ITAÚNA CAPITAL LTDA.** | **NÃO é Itaú** — mantida separada ✅ |

- **Nenhuma entidade Itaú ficou de fora** (as 4 do grupo estão todas mapeadas).
- **Nenhum falso positivo**: Itaúna Capital (gestora independente, sem relação com o
  Itaú) é corretamente excluída — a chave do de-para é CNPJ, não texto.

## 3. Leitura de negócio (o que os números dizem)

- O Itaú é **pequeno na indústria de FIDC**: ~R$ 21–32 bi por papel, contra BTG e QI
  Tech em ~R$ 140 bi de administração. Confirma a tese "estamos fora da camada que
  cresceu". **O número baixo não é erro — é o achado.**
- Kinea (R$ 2,0 bi em FIDC) é pequena aqui porque atua mais em FII/FIP/multimercado;
  ainda assim é somada ao Itaú por ser do conglomerado (como você pediu).

## 4. Cross-check do PL da indústria (o R$ 880 bi)

Validação **independente** contra a fonte crua (soma de TAB_IV_A_VL_PL do Informe
Mensal da CVM, mai/2026, todas as classes):

| Métrica | Valor | Origem |
|---|--:|---|
| **PL bruto (CVM cru)** | **R$ 959 bi** | Soma direta do IME/CVM — **bate exatamente** com o Toma Conta |
| (−) FIC-FIDCs (fundos que investem em cotas de outros FIDCs) | − R$ 79 bi | 449 classes marcadas como FIC-FIDC |
| **PL ex-FIC (usado no deck)** | **R$ 880 bi** | Base líquida, evita dupla contagem |

> O R$ 880 bi **não é um número inventado**: é o PL bruto oficial da CVM (R$ 959 bi)
> menos os fundos que só investem em cotas de outros FIDCs (para não contar o mesmo
> real duas vezes). Se o Presidente preferir o número "cheio", é R$ 959 bi. A escolha
> por ex-FIC é conservadora e defensável.

## 5. Ajustes recomendados no deck (para blindar)

1. Rotular a barra do Itaú na administração como **"Itaú (Intrag)"**.
2. Nota de rodapé fixa: *"Itaú = Intrag (adm) + Itaú Asset + Itaú Unibanco + Kinea
   (gestão) + Itaú Unibanco (custódia); números por papel, não somáveis. Itaúna Capital
   não é Itaú."*
3. Sempre indicar se o PL é **ex-FIC (R$ 880 bi)** ou **bruto (R$ 959 bi)**.
