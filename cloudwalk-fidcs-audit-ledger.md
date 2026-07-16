# CloudWalk FIDCs - ledger de auditoria

## Escopo

Revisão dos slides anexos contra o deep dive local `data/deep_dives/carteira_cloudwalk_7681d350`, regulamentos/termos de emissão armazenados em `data/raw` e extrações regulatórias locais.

## Achados materiais

1. **A.I.**: o deep dive original trazia a emissão inicial de 14/10/2024 (Sr R$1.680,0 mm; Mez R$260,0 mm). A versão mais recente do regulamento `993693` indica Sr R$2.245,6 mm e Mez R$347,5 mm, além de Jr R$90,0 mm. O slide antigo acertava a direção do lote adicional, mas usava Sub/Jr de R$108 mm sem fonte localizada.

2. **PI**: o termo `883040` sustenta a oferta pública de R$3.141,6 mm (Sr + Mez). O mesmo pacote indica Jr privado de R$97,2 mm. Portanto, o slide deve separar oferta pública de stack completo; R$108 mm de Sub/Jr não foi suportado na fonte localizada.

3. **Bela**: os termos de emissão sustentam R$4,2 bi em set/25 e R$5,5 bi em fev/26 para oferta pública Sr + Mez. A cota subordinada/junior deve ser apresentada como alvo/derivação por subordinação, salvo fonte de emissão privada específica.

4. **Big Picture I-IV**: volumes foram localizados, mas os spreads CDI+ não foram encontrados nos PDFs baixados pelo deep dive. Foram mantidos como inputs manuais do usuário: CDI+1,20%, CDI+1,50%, CDI+1,90% e CDI+3,00%.

5. **FIDCs antigos**: Kick Ass II / Multibancos I exige distinção entre volume/status histórico e última rerratificação econômica; deep dive aponta CDI+1,37%. Akira II tem cronograma explícito de amortização, não dedução linear.

## Fontes principais citadas no deck

- A.I.: `data/raw/57609282000146/993693_regulamento_regulamento_993693_2025-09-04.pdf`
- PI: `data/raw/60356171000180/883040_regulamento_regulamento_883040_2025-04-11.pdf` e `993687_regulamento_regulamento_993687_2025-09-04.pdf`
- Bela: `data/raw/62393679000183/993253_emissao_emissao_993253_2025-09-16.pdf`, `1117954_regulamento_regulamento_1117954_2026-02-19.pdf` e `1166893_emissao_emissao_1166893_2026-04-20.pdf`
- Big Picture: regulamentos `1072697`, `1072783`, `1072799`, `1072746`
- Akira II: `data/raw/44124617000194/851798_regulamento_regulamento_851798_2025-02-28.pdf`

## Observação de uso

O PPTX é propositalmente executivo. Para discussão com Comitê, usar o ledger para justificar a origem dos ajustes e o deck para conduzir a narrativa.
