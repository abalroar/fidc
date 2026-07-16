# Classificação ANBIMA usada na aba Indústria

## Separação de fontes

- Patrimônio líquido, competências, prestadores, cotistas e carteira vêm do
  Informe Mensal FIDC da CVM.
- Tipo e foco ANBIMA vêm do arquivo público **Fundos 175: características
  público**, disponibilizado no ANBIMA Data.
- Segmentos da Tabela II da CVM são usados apenas como *proxy* sinalizada
  quando o cadastro ANBIMA não cobre o CNPJ. Eles não substituem a
  classificação formal.
- `N/D` permanece separado de `Outros`.
- FIC-FIDC permanece fora do denominador dos quatro tipos para evitar dupla
  contagem econômica no market share.

Fonte oficial e detalhe do conjunto:

- <https://data.anbima.com.br/datasets>
- <https://data.anbima.com.br/datasets/fundos-175-caracteristicas-publico/detalhes>

## Atualização reproduzível

O portal público deve ser usado para obter manualmente o XLSX oficial. O
repositório não implementa crawler do site. Depois do download:

```bash
python scripts/build_fidc_industry_anbima_classification.py \
  --source-xlsx /caminho/para/fundos_175_caracteristicas_publico.xlsx
```

O comando materializa:

- `data/industry_study/industry_anbima_classification.csv.gz`;
- `data/industry_study/industry_anbima_classification_manifest.json`.

O manifesto registra URL, SHA-256 do anexo, data da fotografia, conflitos e
cobertura do cruzamento com dez/24, dez/25 e mai/26. Uma publicação não deve
prosseguir se surgirem rótulos fora da whitelist, conflitos não sinalizados ou
se a cobertura cair sem explicação.

Para atualização automatizada e histórico formal de mudanças de tipo/foco, o
caminho previsto é o ANBIMA Feed v2 autenticado. O XLS público de 29/12/2025 é
uma ponte cadastral estática e essa limitação deve permanecer visível no PPTX,
na interface e no XLSX exportado.

## Precedência e qualidade

1. Cadastro público ANBIMA por CNPJ de classe.
2. Cadastro público ANBIMA por CNPJ de fundo.
3. Evidência documental/manual publicada e rastreável.
4. Proxy CVM, sempre com asterisco e warning.
5. `N/D`, sem conversão silenciosa para `Outros`.

Classes do mesmo fundo são somadas antes dos cálculos. Divergências de
prestador, segmento, tipo ou foco permanecem registradas como alerta; nenhuma
linha conflitante é resolvida apenas pela ordem em que apareceu no arquivo.
