# Investigação — Dashboard de FIDCs da ANBIMA Data

Data da investigação: 2026-07-10
URL alvo: `https://data.anbima.com.br/publicacoes/fundos-de-investimento/dashboard-de-fidcs`

Objetivo: entender como o dashboard funciona por trás dos panos e avaliar a
viabilidade de replicar os mesmos dados em um pipeline Python
(pandas/numpy/matplotlib) sem depender de Power BI ou de qualquer ferramenta de BI.

> Método: análise estática do HTML e dos bundles JavaScript do site (via `curl`
> através do proxy de egresso), decodificação do token do embed, testes diretos
> `curl` contra os endpoints descobertos, tentativa de dirigir o Chromium headless
> (Playwright) e pesquisa da documentação oficial da ANBIMA Feed API. Todas as URLs,
> respostas e trechos abaixo foram observados de fato nesta investigação.

---

## TL;DR (conclusão prática)

- **O dashboard NÃO é HTML/tabela nem componente de dados próprio da ANBIMA.** É um
  relatório do **Microsoft Power BI publicado no modo "Publish to web" (anônimo)**,
  embutido via `<iframe>` apontando para `https://app.powerbi.com/view?r=...`.
- O site da ANBIMA (React SPA + CMS Strapi) só entrega **a URL do iframe**. Os dados
  numéricos ficam **dentro do relatório Power BI**, servidos pela infraestrutura da
  Microsoft (`*.analysis.windows.net`), não pela ANBIMA.
- **Não há endpoint da ANBIMA que devolva os dados brutos do dashboard em JSON/CSV**,
  e **não há botão de download** (XLS/CSV/anexo) na página — confirmado no CMS
  (`attachment: null`, `alternative_file_url: null`).
- Os dados do painel **existem em API oficial**, porém em outra porta: a **ANBIMA Feed
  API** (`api.anbima.com.br/feed/...`), que exige **cadastro + OAuth2 + contratação de
  produção** (não é o mesmo dado "aberto" do painel, mas cobre os mesmos indicadores
  a nível de fundo/classe).
- **Caminho recomendado**: usar a **ANBIMA Feed API oficial** (robusta, versionada,
  suportada) ou, gratuitamente, os **dados abertos da CVM** (Fundos.NET / dataset
  FIDC), reconstruindo os agregados. Fazer engenharia reversa do querydata do Power BI
  é tecnicamente possível porém frágil e em zona cinzenta de termos de uso.

---

## 1. Estrutura da página

### 1.1 Casca HTML
`GET https://data.anbima.com.br/publicacoes/fundos-de-investimento/dashboard-de-fidcs`
retorna **5.279 bytes** de HTML estático (`content-type: text/html`,
`server: nginx`, `last-modified: Mon, 06 Jul 2026`). É apenas o shell de uma SPA:

```html
<div id="root"></div>
<script type="module" crossorigin src="/publicacoes/assets/index-BFcPxGUG.js"></script>
```

Não há tabela, nem iframe, nem dado no HTML inicial — tudo é renderizado por
JavaScript (React + Vite). Google Tag Manager (`GTM-52MC5BB`) está presente.

### 1.2 Configuração de ambiente (`/publicacoes/env-config.js`)
Expõe os back-ends usados pelo front:

```js
window._env_ = {
  REACT_APP_BACKEND_API: "https://data-api.prd.anbima.com.br",
  REACT_STRAPI_CMS:      "https://data-strapi.prd.anbima.com.br",
  REACT_APP_PUBLIC_KEY:  "6LdQINIUAAAAAHSVujefm3ZsQnM-3gRqmug7dlFH",  // chave pública reCAPTCHA v3
  REACT_APP_SSO_API:     "https://sso.anbima.com.br/auth",
  REACT_APP_FIREBASE_PROJECT_ID: "anbima-data-web",
  ...
}
```

### 1.3 Como a página monta o dashboard (bundles JS)
Fluxo reconstruído a partir dos chunks
`index-BFcPxGUG.js`, `index-yGXhvPWe.js` (rota `/:publicacao/:slug`),
`usePossibleAPIsService-*.js` e `StaticDashboardTemplate-*.js`:

1. A rota `/:publicacao/:slug` resolve `publicacao = fundos-de-investimento`,
   `slug = dashboard-de-fidcs`.
2. `usePossibleAPIsService` chama o Strapi `GET /api/publicacoes-api-list` e mapeia
   `site_path = "fundos-de-investimento"` → `api_path = "/api/dashboards"`,
   `type = "dashboard"`.
3. O componente busca no Strapi:
   `GET https://data-strapi.prd.anbima.com.br/api/dashboards?filters[template][slug][$eq]=dashboard-de-fidcs&locale=pt-BR&populate=template.attachment`
4. A resposta traz o campo `template.iframe` — a **URL do Power BI** — e o componente
   renderiza `<iframe src={template.iframe}>`.

### 1.4 O embed exato (achado central)
Resposta real do CMS Strapi (id 35 / template 266):

```json
{
  "template": {
    "title": "Dashboard de FIDCs (Fundos de Investimento em Direitos Creditórios)",
    "slug": "dashboard-de-fidcs",
    "iframe": "https://app.powerbi.com/view?r=eyJrIjoiM2M2NzVmOWItMzI0Yi00MTE1LWI5ZmYtZTM0ZWM4ZDUwODNlIiwidCI6Ijk3OTM3M2VkLWQxMzAtNDU4NS1iNTY5LTNjM2NlNjE0MTIyNyJ9",
    "iframe_height": 1500,
    "alternative_file_url": null,
    "attachment": { "data": null },
    "updatedAt": "2026-04-02T18:38:37.412Z"
  }
}
```

O parâmetro `r` é Base64 e decodifica para o descritor do relatório "Publish to web":

```json
{
  "k": "3c675f9b-324b-4115-b9ff-e34ec8d5083e",   // resourceKey (chave pública do relatório)
  "t": "979373ed-d130-4585-b569-3c3ce6141227"    // tenantId da ANBIMA no Power BI
}
```

- Plataforma de BI: **Microsoft Power BI** (`app.powerbi.com/view`, produto
  "Publish to web / anonymous embed").
- Não há Tableau, Looker, Metabase ou Qlik (o bundle contém apenas o SDK
  `powerbi-client` da Microsoft; buscas por `tableau`/`looker`/`qlik`/`metabase`
  não retornaram nada relevante).
- O `resourceKey` e o `tenantId` são **públicos** (qualquer visitante os recebe).

### 1.5 Existe um segundo fluxo (autenticado) — mas NÃO é usado no FIDC
O `StaticDashboardTemplate` tem dois caminhos de render:

```js
// g decide entre embed autenticado (Mr) e iframe público
const g = isFeatureFlagActive("auth_power_bi_embedded") && Q.includes(site_path);
// Q = ["boletim-de-mercado-de-capitais"]
...
g   && <Mr slug={slug} />        // embed com token via web-bff (só p/ boletim)
!g  && iframe && <iframe src={iframe} .../>   // publish-to-web (caso do FIDC)
```

Como `Q = ["boletim-de-mercado-de-capitais"]` e o FIDC tem
`site_path = "fundos-de-investimento"`, **o FIDC sempre cai no `<iframe>` público
publish-to-web**. O fluxo autenticado (`web-bff/v1/powerbi/reports/{slug}`, com token
de embed) só se aplica ao *Boletim de Mercado de Capitais*.

---

## 2. Tráfego de rede

Como o proxy de egresso deste ambiente **reseta as conexões TLS do Chromium**
(`net::ERR_CONNECTION_RESET`) embora o `curl` funcione, a captura de rede "ao vivo"
não foi possível aqui. Em compensação, o **código-fonte do próprio player Power BI**
(HTML de `app.powerbi.com/view`) revela exatamente quais chamadas o iframe faz, e cada
uma foi testada por `curl`.

### 2.1 Chamadas do site ANBIMA (domínios próprios) — todas GET, públicas, sem auth

| Método | URL | Resposta |
|--------|-----|----------|
| GET | `data.anbima.com.br/publicacoes/.../dashboard-de-fidcs` | 200, HTML shell |
| GET | `data.anbima.com.br/publicacoes/env-config.js` | 200, JS config |
| GET | `data.anbima.com.br/publicacoes/assets/index-*.js` | 200, bundle SPA |
| GET | `data-strapi.prd.anbima.com.br/api/publicacoes-api-list` | 200, JSON (mapa de rotas) |
| GET | `data-strapi.prd.anbima.com.br/api/dashboards?filters[template][slug][$eq]=dashboard-de-fidcs...` | 200, JSON com a **URL do iframe** |

Nenhuma dessas devolve os **números** do painel — apenas metadados e a URL do embed.

### 2.2 Endpoint autenticado do back-end ANBIMA (não usado pelo FIDC)
`GET https://data-api.prd.anbima.com.br/web-bff/v1/powerbi/reports/{slug}`

- Sem o header `g-google-authorization` → **HTTP 401** `{"msg":"token cannot be blank"}`.
- Esse header é um **token reCAPTCHA v3** gerado no cliente (chave pública
  `REACT_APP_PUBLIC_KEY` acima), injetado por um interceptor Axios:
  ```js
  interceptors.request.use(t => getTokenRecaptcha(action, REACT_APP_PUBLIC_KEY, e)
     .then(e => (t.headers["g-google-authorization"] = e.envelop, t)))
  ```
- Retorna `{ report_id, embed_url, token, iframe_height }` (token de embed do Power BI).
- **Testado para o slug do FIDC → 401** (e, como visto em 1.5, o FIDC nem usa esse
  caminho). Ou seja: mesmo o fluxo autenticado é protegido por reCAPTCHA.

### 2.3 Chamadas do iframe Power BI (domínios de terceiros — Microsoft)
O player em `app.powerbi.com/view` executa, na ordem:

1. **Resolver cluster**:
   `GET https://api.powerbi.com/public/routing/cluster/{tenantId}`
   com headers `X-PowerBI-ResourceKey: {k}`, `ActivityId`, `RequestId`.
   → retorna `FixedClusterUri` (um host `wabi-brazil-south-*.analysis.windows.net`).
2. **Schema conceitual**: `POST {cluster}/public/reports/conceptualschema`
3. **Dados dos visuais**: `POST {cluster}/public/reports/querydata?synchronous=true`
   (header `X-PowerBI-ResourceKey`, corpo JSON com as *queries* DAX/visualContainer).
   **É aqui que os números do dashboard trafegam, em JSON.**

Constantes extraídas do HTML do player:
```
clusterUri      = 'https://api.powerbi.com'
routingUrl      = '/public/routing/cluster/'
queryDataUrl    = '/public/reports/querydata'
getConceptualSchemaUrl = '/public/reports/conceptualschema'
isAnonymousEmbed = true;  powerBIAccessToken = 'any';  reportId = 'any'
```

### 2.4 Resultado dos testes diretos (curl) contra a Microsoft
Todos com `resourceKey`, `tenantId`, `ActivityId`/`RequestId` e `Origin: app.powerbi.com`:

| Chamada | Resultado |
|---------|-----------|
| `GET api.powerbi.com/public/routing/cluster/{t}` | **403 Forbidden** |
| `GET api.powerbi.com/metadata/cluster` | **403** |
| `GET wabi-brazil-south-b-...analysis.windows.net/public/routing/cluster/{t}` | **403** |
| `POST wabi-brazil-south-b-...analysis.windows.net/public/reports/querydata?synchronous=true` | **403** |

Ou seja: fora de um contexto de navegador real, a Microsoft **rejeita (403)** as
chamadas de dados do Power BI publish-to-web. Num navegador legítimo elas funcionam
(o painel renderiza publicamente para qualquer um), mas replicá-las por HTTP puro
exige reproduzir fielmente o protocolo anti-abuso (headers de telemetria, sequência
resolveCluster→conceptualschema→querydata, possivelmente fingerprint), que **não é
documentado**.

---

## 3. Autenticação e acesso

- **Dashboard (o painel visível)**: **público e anônimo**. Não exige login. O acesso é
  garantido pelo modo "Publish to web" do Power BI; a chave está embutida na página.
- **Back-end `data-api` da ANBIMA**: protegido por **reCAPTCHA v3** (`g-google-authorization`),
  mas irrelevante para o FIDC (que usa o iframe público).
- **ANBIMA Feed API oficial** (`api.anbima.com.br/feed/...`): exige
  **cadastro no portal de developers + OAuth2 (client_credentials)**:
  ```
  POST https://api.anbima.com.br/oauth/access-token
  Authorization: Basic base64(client_id:client_secret)
  { "grant_type": "client_credentials" }
  ```
  O cadastro/registro é gratuito, mas o **acesso ao ambiente de Produção requer
  solicitação** (`anbimafeed@anbima.com.br`); a documentação de overview não publica
  preços nem separa explicitamente pacotes gratuitos de pagos. É o ponto a confirmar
  diretamente com a ANBIMA para uso pleno.
- **Exportação XLS/CSV na página do dashboard**: **não existe**. No CMS,
  `attachment.data = null` e `alternative_file_url = null`; o componente só renderiza o
  botão "Baixar arquivo completo" quando há `attachment`, o que não é o caso do FIDC.

---

## 4. Frequência e mecanismo de atualização

- O HTML/CMS do dashboard **não expõe carimbo "atualizado em"** para os dados; o campo
  `display_date` do template é `null`. O `updatedAt` do registro Strapi
  (`2026-04-02`) refere-se à **edição do card/publicação**, não aos dados.
- Como os dados vivem dentro do relatório Power BI, a cadência real é a do **refresh do
  dataset Power BI da ANBIMA** (não observável de fora).
- A comunicação institucional da ANBIMA descreve o ANBIMA Data com atualização
  **diária** para fundos; não encontramos confirmação pública de atualização *horária*
  específica para o painel de FIDCs. Os indicadores de estoque (PL, contas, classes)
  têm natureza **mensal** (competência regulatória CVM), então o "refresh" mais
  frequente reflete recomposição de agregados, não granularidade intradiária.
- Conclusão: a atualização é **automatizada via pipeline da ANBIMA** (não há indício de
  carga manual de arquivos fixos), mas a **granularidade dos dados é mensal/por
  competência**.

---

## 5. Estrutura dos dados

### 5.1 Dentro do dashboard (Power BI) — indicadores citados publicamente
Confirmados no `content` do CMS e no anúncio oficial da ANBIMA:
- Patrimônio Líquido (PL)
- Quantidade de **classes e contas por segmento de investidor**
- **Volume captado** nas ofertas
- **PL dos FIDCs com restrição de investimento** e responsabilidade limitada
- **Foco de atuação** dos fundos
- **Número de administradores e gestores**

Esses valores só existem, hoje, como **agregados renderizados no visual Power BI**
(JSON do `querydata`), não como arquivo baixável nem endpoint JSON da ANBIMA.

### 5.2 ANBIMA Feed API — Fundos Estruturados (mesma família de dado, nível fundo/classe)
Base: `https://api.anbima.com.br/feed/fundos/v1`

| Endpoint | Uso |
|----------|-----|
| `GET /fundos-estruturados?classe-anbima=FIDC&page=&size=` | lista de FIDCs (paginação, `size` máx 300) |
| `GET /fundos-estruturados/{CNPJ}` | dados cadastrais, prestadores, taxas |
| `GET /fundos-estruturados/{CNPJ}/serie-historica?data-inicio=&data-fim=` | série histórica (máx 5 anos) |

Campos relevantes (amostra):
- Cadastro: `cnpj_fundo`, `razao_social`, `classe_anbima`, `tipo_anbima`,
  `categoria_anbima`, `composicao_fundo`, `foco_atuacao`, `tributacao_alvo`.
- Classes/séries: `codigo_anbima`, `nome_fantasia`, `tipo_classe_cota`,
  `situacao_atual` (A/E), `data_encerramento`.
- Prestadores: administrador, gestor, custodiante, controlador, auditor
  (`nome`, `cnpj`, `principal`).
- Série histórica: `data_referencia`, `patrimonio_liquido`, `valor_cota`,
  `captacao`, `resgate`, `numero_cotistas`.
- Preços/secundário: `GET /feed/precos-indices/v1/fidc/mercado-secundario`.

Cobertura vs. dashboard: a Feed API entrega **PL, captação, resgate, nº de cotistas,
foco de atuação, administradores/gestores por CNPJ**, permitindo **reconstruir**
quase todos os agregados do painel (o "segmento de investidor" e "restrição de
investimento/responsabilidade limitada" dependem de campos de classe/RCVM 175
disponíveis na v2 da API).

### 5.3 Dados abertos gratuitos (CVM / Fundos.NET) — já mapeados neste repositório
- `https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal` (Informe Mensal FIDC, ZIPs mensais).
- Fundos.NET (Informe Mensal Estruturado, XML por documento) — pipeline já existente
  em `fundonet_fidc_pipeline.py` e documentado em `INVESTIGACAO.md`.
Estes cobrem PL, carteira, passivos, cotistas por classe/competência a nível de fundo,
permitindo agregação própria (o mesmo insumo que a ANBIMA consome).

---

## 6. Viabilidade de extração

**É possível replicar os dados sem Power BI? Sim — mas não copiando o painel, e sim
reconstruindo os agregados a partir da fonte de dados por fundo.**

| Via | Formato | Auth | O que dá | Robustez |
|-----|---------|------|----------|----------|
| **ANBIMA Feed API** (`api.anbima.com.br/feed`) | JSON, paginado (≤300/pág) | OAuth2 + cadastro + liberação de produção | PL, captação, resgate, cotistas, cadastro, prestadores, foco, preços secundário — por CNPJ | **Alta** (oficial, versionada) |
| **Dados abertos CVM / Fundos.NET** | CSV/ZIP e XML | Nenhuma (grátis) | Informe Mensal FIDC completo por competência/fundo | **Alta** (oficial, grátis), exige agregação própria |
| **querydata do Power BI** (embed público) | JSON DAX | resourceKey público + protocolo não documentado | os agregados exatos já calculados no painel | **Baixa** (403 fora de navegador; frágil; ToS-cinza) |
| **Scraping do DOM / screenshot** | — | — | só o visual | **Muito baixa** |

Detalhes:
- **Preso dentro do visual**: os *números já consolidados* do painel (ex.: "PL por
  segmento de investidor" exatamente como plotado). Só saem via `querydata` (protegido,
  ver §2.4) ou refazendo o cálculo a partir dos dados-fonte.
- **API pública do Power BI Embedded**: a que existe é a de *publish-to-web anônimo*
  (`/public/reports/querydata` com `X-PowerBI-ResourceKey`). Não é documentada para
  consumo programático, retornou **403** em todos os testes diretos deste ambiente, e
  raspá-la depende de emular um navegador — **instável e sujeita a bloqueio/violação de
  termos de uso da Microsoft/ANBIMA**.
- **Rate-limit/paginação**: na Feed API, paginação explícita (`page`/`size`, máx 300;
  série histórica máx 5 anos). No Power BI público não há limites documentados (é
  justamente o que o desaconselha).
- **Necessidade de associação ANBIMA**: para a **Feed API de produção**, sim há um
  gate de cadastro/solicitação (e possível contratação — a confirmar com
  `anbimafeed@anbima.com.br`). Para **CVM/Fundos.NET**, não há gate algum.

---

## 7. Conclusão e recomendação

**O que dá para puxar hoje para um pipeline Python (pandas/numpy/matplotlib) sem Power BI:**
- **Tudo o que o painel mostra pode ser reconstruído** — não a partir do painel, mas
  das fontes por-fundo. Duas rotas sustentáveis:
  1. **ANBIMA Feed API oficial** — melhor fidelidade à taxonomia ANBIMA (classe_anbima,
     foco_atuacao, segmento de investidor RCVM 175, prestadores). **Recomendada** se o
     uso justifica o cadastro/contratação. Requer OAuth2 e liberação de produção.
  2. **Dados abertos CVM / Fundos.NET** — **gratuito e sem autenticação**, já com
     pipeline neste repo (`fundonet_fidc_pipeline.py`). Entrega o insumo mensal por
     fundo; os agregados do painel (PL total, por segmento, captação, nº de
     administradores/gestores) são obtidos por `groupby` próprio.

**O que exige acesso pago/associado:** o acesso **pleno de produção** à ANBIMA Feed API
(cadastro + solicitação; condições comerciais a confirmar com a ANBIMA). O painel em si
é gratuito, mas não expõe os dados de forma consumível.

**O que exigiria engenharia reversa do embed (desaconselhado):** puxar os JSON do
`querydata` do Power BI publish-to-web. Funciona no navegador, mas é **frágil**
(403 em acesso direto, protocolo não documentado, sujeito a quebra e a violação de
termos), e **desnecessário**, já que as mesmas grandezas estão disponíveis por vias
oficiais.

**Caminho mais robusto e sustentável (recomendação final):**
> Construir o pipeline sobre **dados por-fundo oficiais** — priorizar a **ANBIMA Feed
> API** para aderência à classificação ANBIMA (ou os **dados abertos da CVM** como base
> gratuita imediata) — e **reproduzir os gráficos em matplotlib** a partir desses
> agregados. **Não** depender do iframe do Power BI nem do endpoint `querydata`.

---

### Anexo — URLs e artefatos de referência
- Página: `https://data.anbima.com.br/publicacoes/fundos-de-investimento/dashboard-de-fidcs`
- Config: `https://data.anbima.com.br/publicacoes/env-config.js`
- CMS do card: `https://data-strapi.prd.anbima.com.br/api/dashboards?filters[template][slug][$eq]=dashboard-de-fidcs&locale=pt-BR&populate=template.attachment`
- Mapa de rotas: `https://data-strapi.prd.anbima.com.br/api/publicacoes-api-list`
- Embed Power BI: `https://app.powerbi.com/view?r=eyJrIjoiM2M2NzVmOWItMzI0Yi00MTE1LWI5ZmYtZTM0ZWM4ZDUwODNlIiwidCI6Ijk3OTM3M2VkLWQxMzAtNDU4NS1iNTY5LTNjM2NlNjE0MTIyNyJ9`
  (`resourceKey=3c675f9b-324b-4115-b9ff-e34ec8d5083e`, `tenantId=979373ed-d130-4585-b569-3c3ce6141227`)
- Endpoint autenticado (só boletim): `https://data-api.prd.anbima.com.br/web-bff/v1/powerbi/reports/{slug}`
- ANBIMA Feed — Fundos Estruturados: `https://api.anbima.com.br/feed/fundos/v1/fundos-estruturados`
- ANBIMA Feed — OAuth2: `https://api.anbima.com.br/oauth/access-token`
- Docs oficiais: `https://developers.anbima.com.br/en/documentacao/fundos/apis-de-fundos/fundos-estruturados/`
- Dados abertos CVM: `https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal`
