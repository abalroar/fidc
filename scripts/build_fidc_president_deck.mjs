import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Monthly use: point --data to the refreshed deck_content.json and --output
// to the versioned PPTX path. The published v2 deck remains the visual base.

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index < 0) return fallback;
  if (!process.argv[index + 1] || process.argv[index + 1].startsWith("--")) {
    throw new Error(`Missing value for ${name}`);
  }
  return process.argv[index + 1];
}

async function loadArtifactTool() {
  try {
    return await import("@oai/artifact-tool");
  } catch (error) {
    const fallback = path.join(
      os.homedir(),
      ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules",
      "@oai/artifact-tool/dist/artifact_tool.mjs",
    );
    try {
      return await import(pathToFileURL(fallback).href);
    } catch {
      throw new Error(`Unable to load @oai/artifact-tool: ${error.message}`);
    }
  }
}

const DATA_PATH = path.resolve(argValue(
  "--data",
  path.join(REPO_ROOT, "outputs/fidc_presidente_bba_20260711_v2/deck_content.json"),
));
const TEMPLATE_PATH = path.resolve(argValue(
  "--template",
  path.join(REPO_ROOT, "outputs/fidc_presidente_bba_20260711_v2/FIDC_Industria_Executivo_Definitivo_20260711_v2.pptx"),
));
const starterPptxPath = TEMPLATE_PATH;
const FINAL = path.resolve(argValue(
  "--output",
  path.join(REPO_ROOT, "outputs/fidc_presidente_bba_latest/FIDC_Industria_Executivo_Definitivo.pptx"),
));
const ROOT = path.resolve(argValue(
  "--work-dir",
  path.join(REPO_ROOT, ".cache/fidc-president-deck"),
));
const PREVIEW = path.join(ROOT, "final-preview");
const LAYOUT = path.join(ROOT, "final-layout");

const { FileBlob, PresentationFile } = await loadArtifactTool();

const content = JSON.parse(await fs.readFile(DATA_PATH, "utf8"));
const metrics = content.metrics;

const URLS = {
  cvmMonthly: "https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
  cvmOffers: "https://dados.cvm.gov.br/dataset/oferta-distrib",
  cvmCadastro: "https://dados.cvm.gov.br/dataset/fi-cad",
  anbimaClassification: "https://www.anbima.com.br/data/files/85/40/8F/2D/79E386106416A38678A80AC2/Diretrizes_e_deliberacoes_do_Codigo_de_Administracao_de_Recursos_de_terceiros.pdf",
  anbima2023: "https://www.anbima.com.br/pt_br/noticias/ofertas-no-mercado-de-capitais-chegam-a-r-463-7-bilhoes-em-2023.htm",
  anbima2024: "https://www.anbima.com.br/data/files/56/66/80/A5/DAE849109036A849B82BA2A8/Coletiva_MercadodeCapitais_2024_apresentacao.pdf",
  anbima2025: "https://www.anbima.com.br/pt_br/imprensa/ofertas-no-mercado-de-capitais-atingem-r-838-8-bilhoes-e-batem-recorde-em-2025.htm",
  fundosNet: "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
  bela: "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1117954",
  pi: "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=993687",
  akira: "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=851798",
  tapso: "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=726965",
  pagseguro: "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1149521",
  dataFile: DATA_PATH,
};

const COLORS = {
  orange: "#EC7000",
  orangeLight: "#F4B183",
  black: "#111111",
  teal: "#008A82",
  blue: "#326A96",
  gray: "#A4A09B",
  lightGray: "#D9D7D4",
  green: "#218C5B",
  red: "#B42318",
  white: "#FFFFFF",
};

const p = await PresentationFile.importPptx(
  await FileBlob.load(starterPptxPath),
);
const CHART_SLOTS = p.slides.items.map((s) =>
  s.charts.items.map((chart) => ({ id: chart.id, frame: chart.toSnapshot().frame })),
);

function slide(n) {
  return p.slides.items[n - 1];
}

function put(s, index, value) {
  const shape = s.shapes.items[index];
  if (!shape?.text?.set) {
    throw new Error(`Missing editable text at slide ${p.slides.items.indexOf(s) + 1}, shape ${index}`);
  }
  shape.text.set(String(value ?? ""));
}

function monthLabel(competence) {
  const months = [
    "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
  ];
  const [year, month] = competence.split("-").map(Number);
  return `${months[month - 1]} ${year}`;
}

function common(n, title, source, kicker = `INDÚSTRIA FIDC | ${monthLabel(metrics.current_month)}`) {
  const s = slide(n);
  const shapes = s.shapes.items;
  put(s, 1, kicker);
  put(s, 2, title);
  put(s, 3, String(n).padStart(2, "0"));
  put(s, shapes.length - 2, source);
  put(s, shapes.length - 1, `Itaú BBA | ${String(n).padStart(2, "0")}`);
  return s;
}

function setNotes(s, title, method, sources, caveat = "") {
  const lines = [
    title,
    `Método: ${method}`,
    caveat ? `Limite: ${caveat}` : "",
    "Fontes:",
    ...sources,
  ].filter(Boolean);
  s.speakerNotes.textFrame.setText(lines.join("\n"));
  s.speakerNotes.setVisible(true);
}

function fmt1(value) {
  return Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function pct(value, digits = 1) {
  return `${(100 * Number(value)).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

function pp(value, digits = 1) {
  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} p.p.`;
}

function brlBi(value, digits = 1) {
  return `R$ ${Number(value / 1e9).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} bi`;
}

function rank(value) {
  return value == null || Number.isNaN(Number(value)) ? "—" : `#${Math.round(Number(value))}`;
}

function deltaRank(value) {
  if (value == null || Number.isNaN(Number(value))) return "novo";
  const number = Number(value);
  return number > 0 ? `+${Math.round(number)}` : `${Math.round(number)}`;
}

function shortName(name) {
  const map = new Map([
    ["QI TECH + SINGULARE", "QI + Singulare"],
    ["OLIVEIRA TRUST", "Oliveira Trust"],
    ["BANCO DAYCOVAL S.A", "Daycoval"],
    ["GRUPO BRADESCO/BEM", "Bradesco / BEM"],
    ["ITAU/INTRAG", "Itaú / Intrag"],
    ["REAG/CBSF", "REAG"],
    ["GRUPO BB", "BB"],
    ["GRUPO GENIAL", "Genial"],
    ["SOLIS INVESTIMENTOS S A", "Solis"],
    ["SOLIS INVESTIMENTOS LTDA", "Solis"],
    ["TERCON INVESTIMENTOS S.A", "Tercon"],
    ["BRL TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A", "BRL Trust"],
    ["BRL TRUST INVESTIMENTOS LTDA", "BRL Trust Inv."],
    ["VORTX DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Vórtx"],
    ["VERT DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Vert"],
    ["VERT GESTORA DE RECURSOS FINANCEIROS LTDA", "Vert Gestão"],
    ["BEM DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "BEM"],
    ["HEMERA DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Hemera"],
    ["ID CORRETORA DE TITULOS E VALORES MOBILIARIOS S.A", "ID"],
    ["PLANNER CORRETORA DE VALORES S.A", "Planner"],
    ["LIMINE TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Limine"],
    ["ECO GESTAO DE ATIVOS LTDA", "ECO Gestão"],
    ["ANGA ADMINISTRACAO DE RECURSOS LTDA", "Ângá"],
    ["ARTESANAL INVESTIMENTOS LTDA", "Artesanal"],
    ["BANVOX DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Banvox"],
    ["MAF DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A", "MAF"],
    ["SEFER INVESTIMENTOS DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Sefer"],
    ["FINAXIS CORRETORA DE TITULOS E VALORES MOBILIARIOS S.A", "Finaxis"],
    ["TRUSTEE DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA", "Trustee"],
    ["CATALISE INVESTIMENTOS LTDA", "Catalise"],
    ["OURO PRETO GESTAO DE RECURSOS S.A", "Ouro Preto"],
    ["REDWOOD ADMINISTRACAO DE RECURSOS LTDA", "Redwood"],
  ]);
  const direct = map.get(name);
  if (direct) return direct;
  const cleaned = String(name ?? "").replace(/\s+/g, " ").trim();
  return cleaned.length > 26 ? `${cleaned.slice(0, 24)}…` : cleaned;
}

function singleSeries(name, values, fill, valuesFormatCode = "0.0") {
  return { name, values, fill, valuesFormatCode };
}

function replaceBarChart(s, index, config) {
  const slideIndex = p.slides.items.indexOf(s);
  const slot = CHART_SLOTS[slideIndex]?.[index];
  if (!slot) throw new Error(`Missing chart slot ${index} on slide ${slideIndex + 1}`);
  const direction = config.direction ?? "bar";
  const hasLegend = config.hasLegend ?? config.series.length > 1;
  s.charts.deleteById(slot.id);
  return s.charts.add("bar", {
    position: slot.frame,
    categories: config.categories,
    series: config.series,
    hasLegend,
    legend: {
      position: config.legendPosition ?? "bottom",
      overlay: false,
      textStyle: { fill: COLORS.gray, fontSize: config.legendFontSize ?? 10 },
    },
    barOptions: {
      direction,
      grouping: config.grouping ?? "clustered",
      gapWidth: config.gapWidth ?? 45,
      overlap: config.overlap ?? 0,
    },
    dataLabels: config.dataLabels ?? {
      showValue: true,
      position: direction === "column" ? "outEnd" : "outEnd",
      textStyle: { fill: COLORS.black, fontSize: config.labelFontSize ?? 10, bold: true },
    },
    xAxis: config.xAxis ?? (direction === "column"
      ? {
          textStyle: { fill: COLORS.gray, fontSize: 10 },
          line: { style: "solid", fill: COLORS.lightGray, width: 1 },
          majorGridlines: null,
        }
      : {
          min: config.min,
          max: config.max,
          textStyle: { fill: COLORS.gray, fontSize: 9 },
          line: { style: "solid", fill: COLORS.lightGray, width: 1 },
          majorGridlines: { style: "solid", fill: "#ECEAE8", width: 1 },
        }),
    yAxis: config.yAxis ?? (direction === "column"
      ? {
          min: config.min,
          max: config.max,
          textStyle: { fill: COLORS.gray, fontSize: 9 },
          line: { style: "solid", fill: COLORS.lightGray, width: 1 },
          majorGridlines: { style: "solid", fill: "#ECEAE8", width: 1 },
        }
      : {
          textStyle: { fill: COLORS.black, fontSize: 10 },
          line: { style: "solid", fill: COLORS.lightGray, width: 1 },
          majorGridlines: null,
        }),
    chartFill: "none",
    plotAreaFill: "none",
    titlePlacement: "none",
  });
}

function byRole(role) {
  return content.current_role_rankings.filter((row) => row.role === role);
}

function participant(rows, name, nameField = "participant") {
  const row = rows.find((entry) => entry[nameField] === name);
  if (!row) throw new Error(`Missing participant ${name} in ${nameField}`);
  return row;
}

function fillTwoColumnEvidence(s, header, rows, secondHeader, callout) {
  const slots = [[6, 7], [9, 10], [12, 13], [15, 16], [19, 20], [22, 23]];
  put(s, 5, header);
  put(s, 18, secondHeader);
  rows.slice(0, 6).forEach((row, index) => {
    put(s, slots[index][0], row[0]);
    put(s, slots[index][1], row[1]);
  });
  put(s, 25, callout);
}

function fillCurrentRoleSlide(n, role, title, color, countCallout) {
  const rows = byRole(role);
  const plRows = [...rows].sort((a, b) => a.rank_pl - b.rank_pl).slice(0, 8);
  const chartRows = [...plRows].reverse();
  const s = common(
    n,
    title,
    "Fonte: CVM Informe Mensal + cadastro atual; universo bruto de mai/2026.",
  );
  replaceBarChart(s, 0, {
    categories: chartRows.map((row) => shortName(row.participant)),
    series: [{
      ...singleSeries("PL (R$ bi)", chartRows.map((row) => row.pl_bi), color, "0.0"),
      points: chartRows.map((row, idx) => ({
        idx,
        fill: row.participant === "ITAU/INTRAG" ? COLORS.teal : color,
      })),
    }],
    direction: "bar",
    hasLegend: false,
    min: 0,
    max: Math.ceil(Math.max(...plRows.map((row) => row.pl_bi)) * 1.25 / 10) * 10,
    gapWidth: 42,
    labelFontSize: 9,
  });
  const countRows = [...rows].sort((a, b) => a.rank_fundos - b.rank_fundos).slice(0, 6);
  const evidence = countRows.map((row) => [
    `${rank(row.rank_fundos)}  ${shortName(row.participant)}`,
    `${Math.round(row.funds_current).toLocaleString("pt-BR")} | ${fmt1(row.share_pct)}%`,
  ]);
  fillTwoColumnEvidence(
    s,
    "TABELA | FUNDOS | SHARE DO PL",
    evidence,
    "CONTINUAÇÃO DO RANKING",
    countCallout,
  );
  setNotes(
    s,
    `Posição atual de ${role}`,
    "Barras ordenadas por PL decrescente; tabela ordenada por número de fundos decrescente. Consolidação por grupo econômico.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.dataFile],
    role === "administrador"
      ? "Administração é observada diretamente no informe mensal."
      : "Foto atual ligada ao cadastro vigente; não implica que o mesmo papel valha para datas históricas.",
  );
}

function fillTypeRankSlide(n, category, title, selectedNames, callout) {
  const rows = content.administrator_type_rank_delta.filter(
    (row) => row.classe_analitica === category,
  );
  const top2025 = rows
    .filter((row) => row.rank_2025 != null)
    .sort((a, b) => a.rank_2025 - b.rank_2025)
    .slice(0, 7);
  const chartRows = [...top2025].reverse();
  const s = common(
    n,
    title,
    "Fonte: CVM Informe Mensal; PL ex-FIC positivo; administração observada.",
  );
  replaceBarChart(s, 0, {
    categories: chartRows.map((row) => shortName(row.participant)),
    series: [{
      ...singleSeries("Share no tipo em 2025", chartRows.map((row) => 100 * row.share_2025), COLORS.orange, '0.0"%"'),
      points: chartRows.map((row, idx) => ({
        idx,
        fill: row.participant === "ITAU/INTRAG" ? COLORS.teal : COLORS.orange,
      })),
    }],
    direction: "bar",
    hasLegend: false,
    min: 0,
    max: Math.ceil(Math.max(...top2025.map((row) => 100 * row.share_2025)) * 1.25 / 5) * 5,
    gapWidth: 42,
    labelFontSize: 9,
  });
  const evidence = selectedNames.map((name) => {
    const row = participant(rows, name);
    const rankPath = [row.rank_2023, row.rank_2024, row.rank_2025]
      .map((value) => value == null ? "—" : Math.round(Number(value)))
      .join("→");
    return [
      shortName(name),
      `${rankPath} | ${deltaRank(row.delta_posicoes_2023_2025)}`,
    ];
  });
  fillTwoColumnEvidence(
    s,
    "TABELA | RANK 23→24→25 | Δ",
    evidence,
    "MOVIMENTOS RELEVANTES",
    callout,
  );
  setNotes(
    s,
    `Ranking de administradores no tipo ${category}`,
    "Ranking por PL dentro da macroclasse analítica em dez/2023, dez/2024 e dez/2025; FIC-FIDC e PL não positivo excluídos.",
    [URLS.cvmMonthly, URLS.anbimaClassification, URLS.bela, URLS.pi, URLS.akira, URLS.pagseguro, URLS.dataFile],
    "Deltas por tipo são publicados apenas para administração, o papel diretamente observado em cada informe mensal.",
  );
}

function offerRows(role) {
  return content.offer_role_annual
    .filter((row) => row.ano === 2025 && row.role === role)
    .map((row) => ({ ...row, participant: row[role] }))
    .sort((a, b) => a.rank - b.rank);
}

function fillOfferRoleSlide(n, role, title, color, callout) {
  const rows = offerRows(role);
  const top = rows.slice(0, 8);
  const chartRows = [...top].reverse();
  const s = common(
    n,
    title,
    "Fonte: CVM RCVM 160; primárias FIDC encerradas em 2025; teto registrado.",
  );
  replaceBarChart(s, 0, {
    categories: chartRows.map((row) => shortName(row.participant)),
    series: [{
      ...singleSeries("Share do teto registrado", chartRows.map((row) => 100 * row.share), color, '0.0"%"'),
      points: chartRows.map((row, idx) => ({
        idx,
        fill: row.participant === "ITAU/INTRAG" ? COLORS.teal : color,
      })),
    }],
    direction: "bar",
    hasLegend: false,
    min: 0,
    max: Math.ceil(Math.max(...top.map((row) => 100 * row.share)) * 1.25 / 5) * 5,
    gapWidth: 42,
    labelFontSize: 9,
  });
  const topFour = rows.slice(0, 4).map((row) => [
    `${rank(row.rank)}  ${shortName(row.participant)}`,
    `${fmt1(100 * row.share)} | ${fmt1(row.volume_registrado_brl / 1e9)} | ${row.ofertas}`,
  ]);
  const itau = participant(rows, "ITAU/INTRAG");
  const evidence = [
    ...topFour,
    [`${rank(itau.rank)}  Itaú / Intrag`, `${fmt1(100 * itau.share)} | ${fmt1(itau.volume_registrado_brl / 1e9)} | ${itau.ofertas}`],
    ["Universo 2025", `${metrics.cvm_closed_registered_2025_offers.toLocaleString("pt-BR")} | ${fmt1(metrics.cvm_closed_registered_2025_brl / 1e9)}`],
  ];
  fillTwoColumnEvidence(
    s,
    "TABELA | % | R$ BI | REQ.",
    evidence,
    "ITAÚ E UNIVERSO",
    callout,
  );
  setNotes(
    s,
    `Share de ofertas por ${role}`,
    "Cotas de FIDC, ofertas primárias, rito automático RCVM 160, status Oferta Encerrada, ano do encerramento 2025. Share calculado sobre Valor Total Registrado.",
    [URLS.cvmOffers, URLS.dataFile],
    "Valor Total Registrado é teto/montante máximo do requerimento e não colocação efetiva. Campos de papel cobrem 100% do volume de 2025.",
  );
}

// 01 | Cover
{
  const s = slide(1);
  put(s, 1, "ITAÚ BBA | INVESTMENT SERVICES");
  put(s, 2, "FIDCs: onde o mercado cresceu, quem ganhou e como o Itaú reage");
  put(s, 3, "Estoque, tipos, prestadores, ofertas e limites de evidência em uma leitura executiva reproduzível");
  put(s, 5, `CVM universo integral | Competência ${metrics.current_month} | ANBIMA 2023–2025 | RCVM 160`);
  put(s, 6, "11 JUL 2026");
  setNotes(
    s,
    "Abertura executiva",
    "Deck reconstruído a partir do universo mensal CVM, publicações ANBIMA e ofertas RCVM 160.",
    [URLS.cvmMonthly, URLS.cvmOffers, URLS.anbimaClassification, URLS.dataFile],
    "O deck de Clodo Couto foi usado como referência de conteúdo; os números foram reprocessados.",
  );
}

// 02 | Executive answer
{
  const s = common(
    2,
    "Escala fiduciária e gestão especializada definem a disputa",
    "Fontes: CVM Informe Mensal, Cadastro e Ofertas; ANBIMA 2023–2025.",
  );
  put(s, 5, pct(metrics.itau_admin_share));
  put(s, 6, `share da Intrag no PL administrado em ${metrics.current_month}`);
  put(s, 7, pp(metrics.itau_admin_delta_pp));
  put(s, 8, `ganho em 12 meses; ranking ${rank(metrics.itau_admin_previous_rank)} → ${rank(metrics.itau_admin_rank)}`);
  put(s, 9, pct(metrics.offer_2025_admin_custodian_same_volume_share));
  put(s, 10, "do teto registrado com administrador = custodiante em 2025");
  put(s, 12, "TRÊS FATOS QUE DEFINEM A RESPOSTA");
  put(s, 13, "PL");
  put(s, 14, `${brlBi(metrics.ex_fic_pl_brl)} ex-FIC; +${pct(metrics.pl_growth_2024)} em 2024 e +${pct(metrics.pl_growth_2025)} em 2025.`);
  put(s, 16, "OFERTA");
  put(s, 17, `ANBIMA publicou ${brlBi(90.8e9)} em 2025; QI teve 21,8% do teto CVM em administração.`);
  put(s, 19, "GATE");
  put(s, 20, `Gestão/custódia atuais cobrem ${pct(metrics.manager_current_pl_coverage)} / ${pct(metrics.custodian_current_pl_coverage)} do PL; histórico fica abaixo do gate.`);
  put(s, 21, "Tese: industrializar administração e custódia sem tratar gestão como commodity; o mercado mostra papéis fiduciários agrupados e gestão competitivamente distinta.");
  setNotes(
    s,
    "Síntese executiva",
    "Estoque atual, crescimento anual, captação ANBIMA e estrutura de ofertas CVM apresentados com denominadores separados.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.anbima2025, URLS.dataFile],
  );
}

// 03 | Denominators
{
  const classifiedPl = metrics.ex_fic_pl_brl * metrics.classification_share;
  const s = common(
    3,
    "Dois denominadores: estoque competitivo e composição por tipo",
    "Fonte: CVM Informe Mensal; competência mai/2026.",
  );
  replaceBarChart(s, 0, {
    categories: ["PL classificado", "Ex-FIC | PL > 0", "CVM bruto"],
    series: [singleSeries("PL (R$ bi)", [classifiedPl / 1e9, metrics.ex_fic_pl_bi, metrics.gross_pl_bi], COLORS.orange, "0")],
    direction: "bar",
    hasLegend: false,
    min: 0,
    max: 1050,
    gapWidth: 55,
    labelFontSize: 11,
  });
  put(s, 5, "QUAL DENOMINADOR RESPONDE A CADA PERGUNTA");
  put(s, 7, `Prestadores: PL bruto de ${brlBi(metrics.gross_pl_brl)} e ${metrics.current_universe_funds.toLocaleString("pt-BR")} fundos/classes.`);
  put(s, 9, `Crescimento e tipo: ${brlBi(metrics.ex_fic_pl_brl)} ex-FIC, PL positivo; 3.605 veículos e 3.600 fundos.`);
  put(s, 11, `Classe oficial atribuída a ${pct(metrics.classification_share)} do PL; ${pct(metrics.payment_unknown_share)} é meios de pagamento indeterminado.`);
  put(s, 13, "ANBIMA e CVM medem fluxos de oferta; market share usa o estoque CVM.");
  setNotes(
    s,
    "Reconciliação dos denominadores",
    "PL bruto para papéis competitivos; PL ex-FIC positivo para crescimento e composição; classe oficial somente onde a regra é reproduzível.",
    [URLS.cvmMonthly, URLS.dataFile],
    `O PL ex-FIC líquido incluindo valores não positivos é ${brlBi(metrics.ex_fic_reported_net_pl_brl)}; a diferença para o universo PL>0 é imaterial e permanece documentada.`,
  );
}

// 04 | Taxonomy
{
  const s = common(
    4,
    "ANBIMA classifica pela origem; cartão não é uma quinta classe",
    "Fonte: ANBIMA, Diretriz de Classificação do FIDC nº 09.",
  );
  put(s, 5, "CLASSE ANBIMA");
  put(s, 6, "ORIGEM / LÓGICA");
  put(s, 7, "FOCOS");
  put(s, 8, "NÃO CONFUNDIR COM");
  const rows = [
    ["FOMENTO MERCANTIL", "Recebíveis pulverizados cedidos para antecipar recursos", "Factoring; duplicatas; notas; cheques", "Nem todo multicedente é Fomento"],
    ["FINANCEIRO", "Crédito originado por instituições financeiras", "Imobiliário; consignado; pessoal; veículos", "A origem do crédito define a classe"],
    ["AGRO, INDÚSTRIA E COMÉRCIO", "Recebíveis do setor real e crédito corporativo", "Infra; comerciais; corporativo; agro", "Cartão exige classe explícita no regulamento"],
    ["OUTROS", "Recuperação, poder público e carteiras residuais", "NPL; poder público; multicarteira outros", "Multicedente/multissacado é estrutura"],
  ];
  const starts = [9, 14, 19, 24];
  rows.forEach((row, i) => row.forEach((value, j) => put(s, starts[i] + j, value)));
  setNotes(
    s,
    "Classes oficiais ANBIMA",
    "Paráfrase executiva da Diretriz ANBIMA nº 09; quatro classes oficiais e respectivos focos.",
    [URLS.anbimaClassification],
    "Meios de pagamento descreve o lastro econômico, não substitui a classe declarada no regulamento.",
  );
}

// 05 | Card audit
{
  const s = common(
    5,
    "Cartão não determina a classe; TAPSO impede extrapolar",
    "Fontes: regulamentos Fundos.NET e CVM mai/2026; links completos nas notas.",
  );
  put(s, 5, "FUNDO");
  put(s, 6, "PL / SHARE");
  put(s, 7, "CLASSE");
  const auditRows = content.card_sample_audit.map((row) => [
    row.fundo,
    row.pl_atual_brl > 0 ? `${fmt1(row.pl_atual_brl / 1e9)} / ${pct(row.share_pl_segmento_cartao)}` : "—",
    row.status === "EXPLÍCITA"
      ? `${row.classe_declarada.startsWith("Agro") ? "AIC" : "Outros"} | explícita`
      : "Indeterminada",
  ]);
  const rows = [
    ...auditRows,
    ["Amostra", pct(metrics.card_sample_pl_share), "dirigida"],
    ["Regra", "doc.", "sem inferir"],
    ["Publicação", "TAPSO", "fora"],
  ];
  const starts = [8, 12, 16, 20, 24, 28, 32, 36];
  rows.forEach((row, i) => row.forEach((value, j) => put(s, starts[i] + j, value)));
  put(s, 41, pct(metrics.card_sample_pl_share));
  put(s, 42, "do PL de cartões nos cinco documentos");
  put(s, 43, pct(metrics.card_explicit_sample_pl_share));
  put(s, 44, "do PL do segmento com classe explícita");
  put(s, 45, pct(metrics.card_unresolved_sample_pl_share));
  put(s, 46, "do PL do segmento concentrado no TAPSO");
  put(s, 48, "BELA, PI e Akira II são AIC; PagSeguro é Outros; TAPSO fica fora até evidência explícita.");
  setNotes(
    s,
    "Auditoria da classificação de recebíveis de cartão",
    "Leitura dos regulamentos indicados pelo usuário e ponderação pelo PL do segmento Cartão de crédito no snapshot CVM de mai/2026.",
    [URLS.bela, URLS.pi, URLS.akira, URLS.tapso, URLS.pagseguro, URLS.cvmMonthly, URLS.dataFile],
    "PI e Akira II não têm PL positivo na foto atual; a amostra documental cobre 60,4% do PL, mas apenas 17,6% tem classe explícita em fundos com PL atual.",
  );
}

// 06 | PL growth
{
  const s = common(
    6,
    "PL cresceu 28,6% a.a. até 2023; 2024 acelerou para 47,9%",
    "Fonte: CVM Informe Mensal; PL ex-FIC positivo em cada dezembro.",
  );
  const annual = content.annual_pl.filter((row) => row.competencia.endsWith("-12"));
  replaceBarChart(s, 0, {
    categories: annual.map((row) => row.rotulo),
    series: [singleSeries("PL ex-FIC (R$ bi)", annual.map((row) => row.pl_ex_fic_bi), COLORS.orange, "0")],
    direction: "column",
    hasLegend: false,
    min: 0,
    max: 950,
    gapWidth: 36,
    labelFontSize: 10,
  });
  put(s, 5, "CRESCIMENTO DO ESTOQUE");
  put(s, 7, `2018–2023: CAGR de ${pct(metrics.pl_cagr_2018_2023)}.`);
  put(s, 9, `2024: ${pct(metrics.pl_growth_2024)} sobre 2023.`);
  put(s, 11, `2025: ${pct(metrics.pl_growth_2025)} sobre 2024.`);
  put(s, 13, "PL combina retorno e fluxos. Captação ANBIMA: R$ 38,7 bi (2023), R$ 81,4 bi (2024), R$ 90,8 bi (2025).");
  setNotes(
    s,
    "Crescimento anual do PL",
    "Fechamentos de dezembro de 2018 a 2025; FIC-FIDC e PL não positivo excluídos. CAGR 2018-2023 = (PL2023/PL2018)^(1/5)-1.",
    [URLS.cvmMonthly, URLS.anbima2023, URLS.anbima2024, URLS.anbima2025, URLS.dataFile],
    "Variação de estoque não pode ser decomposta publicamente entre retorno e emissão nova. Os volumes ANBIMA são contraponto, não ponte de reconciliação.",
  );
}

// 07 | 100% mix
{
  const s = common(
    7,
    "Financeiro ultrapassou AIC em 2026; 18,4% fica fora das classes",
    "Fonte: CVM Informe Mensal; mapeamento analítico para classes ANBIMA.",
  );
  const annual = content.annual_pl;
  const classOrder = [
    "Financeiro",
    "Agro, Indústria e Comércio",
    "Outros",
    "Fomento Mercantil",
    "Meios de pagamento | classe não determinada",
    "Sem evidência suficiente",
  ];
  const names = ["Financeiro", "AIC", "Outros", "Fomento", "Pagamentos indet.", "Sem evidência"];
  const fills = [COLORS.orange, COLORS.black, COLORS.teal, COLORS.orangeLight, COLORS.blue, COLORS.gray];
  const series = classOrder.map((category, idx) => {
    const values = annual.map((year) => {
      const row = content.anbima_mix.find(
        (item) => item.competencia === year.competencia && item.classe_anbima_macro === category,
      );
      return row?.share_pct ?? 0;
    });
    return {
      name: names[idx],
      values,
      fill: fills[idx],
      valuesFormatCode: '0.0"%"',
      dataLabelOverrides: values.map((value, point) => ({
        idx: point,
        text: value >= 5 ? `${value.toFixed(0)}%` : "",
        showValue: value >= 5,
        position: "center",
        textStyle: { fill: idx >= 3 ? COLORS.black : COLORS.white, fontSize: 8, bold: true },
      })),
    };
  });
  replaceBarChart(s, 0, {
    categories: annual.map((row) => row.rotulo.replace(" YTD", "\nmai")),
    series,
    direction: "column",
    grouping: "stacked",
    overlap: 100,
    gapWidth: 30,
    hasLegend: true,
    legendPosition: "bottom",
    legendFontSize: 8,
    dataLabels: { showValue: true, position: "center", textStyle: { fill: COLORS.white, fontSize: 8, bold: true } },
    yAxis: {
      min: 0,
      max: 100,
      majorUnit: 20,
      numberFormatCode: '0"%"',
      textStyle: { fill: COLORS.gray, fontSize: 8 },
      line: { style: "solid", fill: COLORS.lightGray, width: 1 },
      majorGridlines: { style: "solid", fill: "#ECEAE8", width: 1 },
    },
  });
  const mix = (period, category) => content.anbima_mix.find(
    (row) => row.competencia === period && row.classe_anbima_macro === category,
  );
  put(s, 5, "LEITURA 2023 → MAI/26");
  put(s, 6, "Agro, Ind. e Comércio"); put(s, 7, `${rank(mix("2023-12", "Agro, Indústria e Comércio").rank_pl)} → ${rank(mix(metrics.current_month, "Agro, Indústria e Comércio").rank_pl)}`);
  put(s, 9, "Financeiro"); put(s, 10, `${rank(mix("2023-12", "Financeiro").rank_pl)} → ${rank(mix(metrics.current_month, "Financeiro").rank_pl)}`);
  put(s, 12, "Pagamentos indet."); put(s, 13, `${fmt1(mix("2023-12", "Meios de pagamento | classe não determinada").share_pct)}% → ${fmt1(mix(metrics.current_month, "Meios de pagamento | classe não determinada").share_pct)}%`);
  put(s, 15, "Sem evidência"); put(s, 16, `${fmt1(mix(metrics.current_month, "Sem evidência suficiente").share_pct)}% atual`);
  put(s, 19, `As quatro classes cobrem ${pct(metrics.classification_share)} do PL atual; pagamentos indeterminados (${pct(metrics.payment_unknown_share)}) ficam separados.`);
  put(s, 20, "A faixa não classificada é parte do resultado, não uma categoria residual rebatizada como Outros.");
  setNotes(
    s,
    "Composição anual do PL ex-FIC",
    "100% do PL ex-FIC positivo por competência; classe analítica baseada no recebível dominante, com overrides apenas quando o regulamento declara a classe.",
    [URLS.cvmMonthly, URLS.anbimaClassification, URLS.bela, URLS.pi, URLS.akira, URLS.pagseguro, URLS.dataFile],
  );
}

// 08–10 | Current roles
fillCurrentRoleSlide(
  8,
  "administrador",
  "BTG lidera PL administrado; QI lidera número de fundos",
  COLORS.orange,
  `Itaú / Intrag: ${rank(metrics.itau_admin_rank)} por PL, ${brlBi(metrics.itau_admin_pl_brl)} e ${pct(metrics.itau_admin_share)} de share.`,
);
fillCurrentRoleSlide(
  9,
  "gestor",
  "Oliveira lidera PL gerido; Tercon lidera número de fundos",
  COLORS.orange,
  "Gestão é mais fragmentada: o líder tem 7,9% do PL, enquanto a cauda reúne gestoras especializadas com muitos fundos.",
);
fillCurrentRoleSlide(
  10,
  "custodiante",
  "BTG lidera PL custodiado; QI lidera número de fundos",
  COLORS.blue,
  "Oliveira é #3 em PL custodiado; Daycoval é #2 em quantidade. Itaú aparece fora do top 8 por PL.",
);

// 11–13 | Type ranks
fillTypeRankSlide(
  11,
  "Agro, Indústria e Comércio",
  "AIC: QI retoma #1; Itaú avança dez posições para #6",
  ["QI TECH + SINGULARE", "GRUPO BB", "BTG PACTUAL", "OLIVEIRA TRUST", "ITAU/INTRAG", "HEMERA DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS LTDA"],
  "Em 2025, QI tem 24,2% do PL AIC; Itaú chega a 5,2%. Cartões sem classe explícita ficam fora deste ranking.",
);
fillTypeRankSlide(
  12,
  "Financeiro",
  "Financeiro: QI sobe nove posições; Itaú estreia em #9",
  ["REAG/CBSF", "BANCO DAYCOVAL S.A", "QI TECH + SINGULARE", "OLIVEIRA TRUST", "BRL TRUST DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A", "ITAU/INTRAG"],
  "REAG mantém #1; Daycoval fica #2. QI sai de #12 para #3 e o Itaú aparece em 2025 com 2,8% do PL do tipo.",
);
fillTypeRankSlide(
  13,
  "Outros",
  "Outros: BTG mantém #1; REAG sobe onze posições",
  ["BTG PACTUAL", "QI TECH + SINGULARE", "GRUPO GENIAL", "MAF DISTRIBUIDORA DE TITULOS E VALORES MOBILIARIOS S.A", "REAG/CBSF", "OLIVEIRA TRUST"],
  "Fomento representa menos de 0,1% no mapeamento dominante: QI é #1 e Planner #2 em 2025, sem base material para conclusão comercial.",
);

// 14 | Annual offers
{
  const s = common(
    14,
    "Captação chegou a R$ 90,8 bi; teto CVM foi R$ 116,3 bi",
    "Fontes: ANBIMA 2023–2025 e CVM RCVM 160; valores não equivalentes.",
  );
  const anbima = content.public_issuance.sort((a, b) => a.ano - b.ano);
  const cvm = content.offer_annual.sort((a, b) => a.ano - b.ano);
  replaceBarChart(s, 0, {
    categories: anbima.map((row) => String(row.ano)),
    series: [
      singleSeries("ANBIMA | captação publicada", anbima.map((row) => row.volume_publicado_brl / 1e9), COLORS.orange, "0.0"),
      singleSeries("CVM | teto registrado", cvm.map((row) => row.volume_registrado_bi), COLORS.black, "0.0"),
    ],
    direction: "column",
    grouping: "clustered",
    hasLegend: true,
    min: 0,
    max: 135,
    gapWidth: 50,
    labelFontSize: 9,
  });
  put(s, 5, "DUAS MEDIDAS, DOIS USOS");
  put(s, 7, "ANBIMA publica captação anual: R$ 38,7 bi (2023), R$ 81,4 bi (2024) e R$ 90,8 bi (2025).");
  put(s, 9, "CVM soma Valor Total Registrado: R$ 26,2 bi, R$ 95,4 bi e R$ 116,3 bi; não é valor efetivamente colocado.");
  put(s, 11, "2023 é transição da RCVM 160 e fica parcial na base automática. 2024 tem 918 operações ANBIMA; 2025, mais de mil.");
  put(s, 13, "Revisões: 2023 = R$ 43,7 bi; 2024 comparável ≈ R$ 82,9 bi.");
  setNotes(
    s,
    "Captação anual e teto registrado",
    "ANBIMA: volume anual publicado em cada vintage. CVM: soma do Valor Total Registrado de ofertas primárias de cotas de FIDC, rito automático RCVM 160, encerradas no ano.",
    [URLS.anbima2023, URLS.anbima2024, URLS.anbima2025, URLS.cvmOffers, URLS.dataFile],
    "As séries têm conceitos diferentes e não devem ser reconciliadas por subtração. O ano de 2023 da CVM é parcial/transicional.",
  );
}

// 15–17 | Offer roles
fillOfferRoleSlide(
  15,
  "administrador",
  "Ofertas 2025: QI lidera administração com 21,8% do teto",
  COLORS.orange,
  "QI combina 431 requerimentos e R$ 25,3 bi registrados; Daycoval, Oliveira e BTG completam o top 4.",
);
fillOfferRoleSlide(
  16,
  "gestor",
  "Ofertas 2025: gestão é fragmentada; líder tem só 6,4%",
  COLORS.orange,
  "ECO e Oliveira estão praticamente empatadas; o top 10 não reproduz a liderança fiduciária de QI, Daycoval e BTG.",
);
fillOfferRoleSlide(
  17,
  "custodiante",
  "Ofertas 2025: QI lidera custódia com 20,1% do teto",
  COLORS.blue,
  "O ranking de custódia se aproxima do de administração: QI, Daycoval, Oliveira e BTG ocupam as quatro primeiras posições.",
);

// 18 | Monostructure
{
  const managerTop10 = offerRows("gestor").slice(0, 10).reduce((sum, row) => sum + row.share, 0);
  const s = common(
    18,
    "Administração e custódia vêm juntas; gestão segue outra dinâmica",
    "Fonte: CVM RCVM 160; ofertas primárias de FIDC encerradas em 2025.",
  );
  put(s, 5, "ADMINISTRAÇÃO + CUSTÓDIA");
  put(s, 6, pct(metrics.offer_2025_admin_custodian_same_volume_share));
  put(s, 7, "do teto registrado");
  put(s, 9, "92,5% dos requerimentos têm o mesmo grupo nos dois papéis.");
  put(s, 11, "QI, Daycoval, Oliveira e BTG lideram os dois rankings.");
  put(s, 13, "Fato: os serviços fiduciários aparecem majoritariamente empacotados.");
  put(s, 15, "TODOS OS TRÊS PAPÉIS");
  put(s, 16, pct(metrics.offer_2025_all_same_volume_share));
  put(s, 17, "do teto registrado");
  put(s, 19, `${pct(metrics.offer_2025_all_same_offer_share)} dos requerimentos.`);
  put(s, 21, "Oliveira: R$ 7,4 bi; BTG: R$ 4,5 bi; Itaú: R$ 1,6 bi em combinações monoestruturadas.");
  put(s, 23, "Fato: monoestrutura completa existe, mas não é a regra do mercado.");
  put(s, 25, "GESTÃO");
  put(s, 26, "6,4%");
  put(s, 27, "share do líder");
  put(s, 29, `Os dez maiores somam ${pct(managerTop10)} do teto registrado.`);
  put(s, 31, "ECO lidera; Oliveira, Vert, Ângá, Solis e Artesanal vêm em seguida.");
  put(s, 33, "Conclusão: gestão é um mercado mais fragmentado e não deve ser confundida com administração/custódia.");
  setNotes(
    s,
    "Teste de monoestrutura",
    "Comparação de nomes consolidados de administrador, gestor e custodiante em cada requerimento encerrado de 2025; ponderação por Valor Total Registrado e por contagem.",
    [URLS.cvmOffers, URLS.dataFile],
    "A igualdade de nomes/grupos indica coincidência de papéis declarados, não economics, controle societário do fundo ou prestação de todos os serviços operacionais.",
  );
}

// 19 | Historical coverage
{
  const s = common(
    19,
    "Foto atual é quase censitária; histórico chega no máximo a 42%",
    "Fontes: CVM Cadastro histórico, cadastro atual e ofertas datadas.",
  );
  replaceBarChart(s, 0, {
    categories: ["Gestão", "Custódia"],
    series: [
      singleSeries("Cadastro atual | mai/26", [100 * metrics.manager_current_pl_coverage, 100 * metrics.custodian_current_pl_coverage], COLORS.orange, '0.0"%"'),
      singleSeries("Histórico ativo | dez/25", [100 * metrics.manager_2025_high_pl_coverage, 100 * metrics.custodian_2025_high_pl_coverage], COLORS.black, '0.0"%"'),
      singleSeries("Teto incl. ofertas datadas", [100 * metrics.manager_2025_pl_coverage, 100 * metrics.custodian_2025_pl_coverage], COLORS.teal, '0.0"%"'),
    ],
    direction: "column",
    grouping: "clustered",
    hasLegend: true,
    min: 0,
    max: 110,
    gapWidth: 45,
    labelFontSize: 9,
  });
  put(s, 5, "POR QUE FOTO SIM, DELTA NÃO");
  put(s, 7, `Mai/26: gestão ${pct(metrics.manager_current_pl_coverage)} e custódia ${pct(metrics.custodian_current_pl_coverage)} do PL.`);
  put(s, 9, `Dez/25: cadastro histórico ativo cobre só ${pct(metrics.manager_2025_high_pl_coverage)} / ${pct(metrics.custodian_2025_high_pl_coverage)}.`);
  put(s, 11, `Incluindo ofertas anteriores sem fim de vigência, o teto sobe apenas a ${pct(metrics.manager_2025_pl_coverage)} / ${pct(metrics.custodian_2025_pl_coverage)}.`);
  put(s, 13, "Gate = 80% do PL: ranking atual publicado; deltas históricos excluídos.");
  setNotes(
    s,
    "Cobertura histórica dos papéis",
    "PL do universo mensal ligado a cadastro histórico ativo na data; camada adicional aceita a última oferta pública registrada até a data como evidência datada, sem presumir vigência posterior.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.dataFile],
    "A camada com ofertas é limite superior, pois uma oferta anterior não prova que o prestador permaneceu até o fechamento do ano.",
  );
}

// 20 | Competitor models
{
  const admin = byRole("administrador");
  const manager = byRole("gestor");
  const custodian = byRole("custodiante");
  const qiAdmin = participant(admin, "QI TECH + SINGULARE");
  const btgAdmin = participant(admin, "BTG PACTUAL");
  const btgAdminHistory = participant(content.administrator_current, "BTG PACTUAL");
  const olAdmin = participant(admin, "OLIVEIRA TRUST");
  const olManager = participant(manager, "OLIVEIRA TRUST");
  const olCustody = participant(custodian, "OLIVEIRA TRUST");
  const qiOffer = participant(offerRows("administrador"), "QI TECH + SINGULARE");
  const btgOffer = participant(offerRows("administrador"), "BTG PACTUAL");
  const olOffer = participant(offerRows("administrador"), "OLIVEIRA TRUST");
  const s = common(
    20,
    "QI vende escala; BTG domina estoque; Oliveira integra os três papéis",
    "Fontes: CVM Informe Mensal, Cadastro e RCVM 160; mai/26 e 2025.",
  );
  put(s, 5, "QI TECH + SINGULARE");
  put(s, 6, Math.round(qiAdmin.funds_current));
  put(s, 7, "fundos administrados");
  put(s, 9, `${pct(qiOffer.share)} do teto registrado em administração; ${qiOffer.ofertas} requerimentos.`);
  put(s, 11, `${brlBi(qiOffer.volume_registrado_brl)} registrados; liderança também em custódia.`);
  put(s, 13, "Leitura factual: maior escala por quantidade e maior produção fiduciária em 2025.");
  put(s, 15, "BTG PACTUAL");
  put(s, 16, brlBi(btgAdmin.pl_brl_current));
  put(s, 17, "sob administração FIDC");
  put(s, 19, `#1 em PL administrado e custodiado; ${pp(btgAdminHistory.delta_share_pp)} em administração.`);
  put(s, 21, `${pct(btgOffer.share)} do teto 2025; ${brlBi(4.547932e9)} com BTG nos três papéis.`);
  put(s, 23, "Leitura factual: liderança de estoque e capacidade de monoestrutura relevante.");
  put(s, 25, "OLIVEIRA TRUST");
  put(s, 26, brlBi(olCustody.pl_brl_current));
  put(s, 27, "sob custódia FIDC");
  put(s, 29, `Administração ${brlBi(olAdmin.pl_brl_current)} | gestão ${brlBi(olManager.pl_brl_current)}.`);
  put(s, 31, `${brlBi(olOffer.volume_registrado_brl)} em administração; ${brlBi(7.4189e9)} nos três papéis.`);
  put(s, 33, "Leitura factual: integração de papéis e presença forte em mandatos de maior volume.");
  setNotes(
    s,
    "Modelos competitivos observados",
    "Comparação de PL, número de fundos, teto registrado, requerimentos e coincidência dos três papéis.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.dataFile],
    "Os rótulos de modelo são inferências executivas dos indicadores observados, não informação contratual ou de receita.",
  );
}

// 21 | Cotistas
{
  const s = common(
    21,
    "58% dos FIDCs têm até 5 cotistas; eles concentram 48% do PL",
    "Fonte: CVM Informe Mensal; universo ex-FIC integral de mai/2026.",
  );
  const hist = content.cotista_histogram.filter((row) => row.bucket !== "Sem cotista positivo");
  replaceBarChart(s, 0, {
    categories: hist.map((row) => row.bucket),
    series: [{
      ...singleSeries("# de FIDCs", hist.map((row) => row.fundos), COLORS.orange, "0"),
      points: [{ idx: 5, fill: COLORS.black }],
    }],
    direction: "column",
    hasLegend: false,
    min: 0,
    max: 1100,
    gapWidth: 40,
    labelFontSize: 10,
  });
  put(s, 5, "CENSO DO INFORME MENSAL");
  put(s, 6, metrics.cotista_funds.toLocaleString("pt-BR"));
  put(s, 7, "fundos ex-FIC com PL positivo");
  put(s, 8, fmt1(metrics.cotistas_median));
  put(s, 9, "cotistas na mediana");
  put(s, 10, pct(metrics.cotista_positive_pl_share));
  put(s, 11, "do PL tem contagem positiva");
  put(s, 12, "Contas reportadas por fundo/classe, não CPF/CNPJ único. A base não revela beneficiário final nem valor investido por categoria.");
  setNotes(
    s,
    "Distribuição da quantidade de cotistas",
    "Histograma de todos os fundos ex-FIC com PL positivo no snapshot de mai/2026.",
    [URLS.cvmMonthly, URLS.dataFile],
    "A contagem não identifica bancos, pessoas físicas ou gestoras individualmente e não traz valor por tipo de investidor.",
  );
}

// 22 | Document funnel
{
  const s = common(
    22,
    "Foram curados 823 fundos; cedente aceito cobre só 2,6% do PL",
    "Fonte: universo CVM mai/2026 e documentos públicos CVM/Fundos.NET.",
  );
  put(s, 5, "ETAPA");
  put(s, 6, "FUNDOS ATUAIS");
  put(s, 7, "COBERTURA DO PL");
  const rows = [
    ["01  Universo CVM atual", "4.219", "100,0%"],
    ["02  Documentos públicos locais", "729", "20,1%"],
    ["03  Texto pronto para busca", "729", "20,1%"],
    ["04  Candidatos de participantes", "267", "7,4%"],
    ["05  Cedente aceito", "107", "2,6%"],
    ["06  Encerramento validado", "153", "3,8%"],
    ["07  Seleção documental", "—", "não aleatória"],
    ["08  Uso publicável", "—", "escopo / método"],
  ];
  const starts = [8, 12, 16, 20, 24, 28, 32, 36];
  rows.forEach((row, i) => row.forEach((value, j) => put(s, starts[i] + j, value)));
  put(s, 41, "823");
  put(s, 42, "fundos distintos no corpus total");
  put(s, 43, "729");
  put(s, 44, "fundos atuais com texto pesquisável");
  put(s, 45, "2,6%");
  put(s, 46, "do PL atual com cedente aceito");
  put(s, 48, "Conclusão: o trabalho documental é profundo, mas dirigido; não sustenta ranking industrial de cedentes, sacados ou investidores nominais.");
  setNotes(
    s,
    "Funil da curadoria documental",
    "Match por CNPJ entre universo mensal CVM, corpus local, texto pesquisável, candidatos extraídos e evidência aceita.",
    [URLS.cvmMonthly, URLS.fundosNet, URLS.dataFile],
    "O corpus cobre 20,1% do PL e não é amostra aleatória; nomes nominais permanecem fora do corpo executivo.",
  );
}

// 23 | Publication gate
{
  const s = common(
    23,
    "Cada conclusão passa por cobertura, definição e comparabilidade",
    "Fontes: CVM, ANBIMA e ledger metodológico local.",
    "METODOLOGIA E FONTES",
  );
  put(s, 5, "CAMADA");
  put(s, 6, "COBERTURA / DEFINIÇÃO");
  put(s, 7, "USO");
  const rows = [
    ["PL e classes", `100% ex-FIC; ${pct(metrics.classification_share)} em classe oficial`, "PUBLICAR"],
    ["Administração", "100% do PL; papel mensal observado", "PUBLICAR DELTA"],
    ["Gestão e custódia", `foto ${pct(metrics.manager_current_pl_coverage)} / ${pct(metrics.custodian_current_pl_coverage)}; história <80%`, "FOTO ATUAL"],
    ["Ofertas", "ANBIMA = captação; CVM = teto registrado", "PUBLICAR RÓTULO"],
    ["Cotistas", `${metrics.cotista_funds.toLocaleString("pt-BR")} fundos; conta ≠ identidade`, "HISTOGRAMA"],
    ["Nomes e secundário", "corpus dirigido; sem beneficiário/trade-level", "EXCLUIR"],
  ];
  const starts = [8, 12, 16, 20, 24, 28];
  rows.forEach((row, i) => row.forEach((value, j) => put(s, starts[i] + j, value)));
  put(s, 32, "REGRA DE PUBLICAÇÃO");
  put(s, 33, "Sem inferência de classe por palavra-chave, delta histórico abaixo de 80%, colocação efetiva derivada de teto ou ranking nominal de corpus não censitário.");
  setNotes(
    s,
    "Gate de publicação",
    "Classificação de cada evidência por cobertura, definição, temporalidade e comparabilidade.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.anbimaClassification, URLS.dataFile],
  );
}

// 24 | Commercial response
{
  const s = common(
    24,
    "Fechar o gap de escala sem tratar gestão como serviço fiduciário",
    "Recomendação derivada do estoque, ranking por papel e ofertas RCVM 160.",
  );
  put(s, 5, "01");
  put(s, 6, "Atacar Financeiro");
  put(s, 7, "Financeiro virou o maior tipo em mai/26: priorizar originadores de consignado, pessoal, veículos e crédito financeiro.");
  put(s, 9, "02");
  put(s, 10, "Industrializar o fiduciário");
  put(s, 11, "Administração e custódia coincidem em 91,8% do teto 2025: onboarding, documentos, SLA e dados devem funcionar como uma oferta integrada.");
  put(s, 13, "03");
  put(s, 14, "Orquestrar gestão");
  put(s, 15, "O maior gestor tem 7,9% do estoque e 6,4% das ofertas: construir ecossistema de gestoras, sem exigir monoestrutura em todo mandato.");
  put(s, 17, "04");
  put(s, 18, "Separar escala e alto tíquete");
  put(s, 19, "QI prova cadência; Oliveira prova integração em volumes maiores. Operar esteira padronizada e célula sênior sob a mesma governança.");
  put(s, 22, "A vantagem potencial do Itaú é relacionamento + balanço + confiança; a lacuna observada é converter isso em cadência fiduciária e distribuição.");
  setNotes(
    s,
    "Resposta comercial",
    "Ações ligadas às diferenças observadas entre composição do PL, administração, custódia, gestão e produção de ofertas.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.dataFile],
  );
}

// 25 | Decisions
{
  const s = common(
    25,
    "A decisão é onde pôr balanço, fábrica e responsabilidade",
    "Ambição calculada sobre o PL bruto CVM de mai/2026; proposta para discussão.",
  );
  put(s, 5, "5,0%");
  put(s, 6, "ambição inicial de share administrado");
  put(s, 7, brlBi(metrics.itau_admin_pl_gap_to_5pct_brl));
  put(s, 8, `PL incremental versus ${pct(metrics.itau_admin_share)} atual`);
  put(s, 9, "2 + 1");
  put(s, 10, "duas esteiras operacionais + dono único de P&L");
  put(s, 11, "DECISÕES PEDIDAS");
  put(s, 13, "Aprovar meta de 5,0% e bolsões prioritários: Financeiro e AIC com relacionamento atacadista.");
  put(s, 15, "Nomear dono do P&L FIDC entre BBA, Intrag, custódia, asset, distribuição e tecnologia.");
  put(s, 17, "Operar esteira de escala para cauda longa e célula integrada para mandatos de alto tíquete.");
  put(s, 19, "Medir gestão como mercado parceiro e separado; não presumir monoestrutura como condição de entrada.");
  put(s, 21, "Resultado: cinco casos em 90 dias + painel mensal com gate.");
  setNotes(
    s,
    "Decisões executivas",
    "Gap para 5,0% calculado sobre PL bruto CVM; desenho operacional derivado dos padrões competitivos observados.",
    [URLS.cvmMonthly, URLS.cvmOffers, URLS.dataFile],
  );
}

// 26 | Monthly refresh
{
  const s = common(
    26,
    "O estudo se atualiza mensalmente com seis gates automáticos",
    "Rotina reproduzível: inputs datados, outputs versionados e testes antes da publicação.",
    "MODELO OPERACIONAL MENSAL",
  );
  put(s, 5, "GATE");
  put(s, 6, "ROTINA / CONTROLE");
  put(s, 7, "SAÍDA");
  const rows = [
    ["1. Fechamento", "competência completa; reapresentações consolidadas", "BASE FECHADA"],
    ["2. Escopo", "PL bruto, ex-FIC, PL positivo e fundos sem mistura", "DENOMINADORES"],
    ["3. Classificação", "macroclasse + overrides documentais + desconhecidos", "MIX 100%"],
    ["4. Competição", "admin delta; gestão/custódia foto; ofertas por conceito", "RANKINGS"],
    ["5. Evidência", "coverage cadastral/documental e exclusões automáticas", "CONFIANÇA"],
    ["6. Publicação", "PPT executivo + arquivos CSV/JSON versionados", "DECISÃO"],
  ];
  const starts = [8, 12, 16, 20, 24, 28];
  rows.forEach((row, i) => row.forEach((value, j) => put(s, starts[i] + j, value)));
  put(s, 32, "REGRA DE PUBLICAÇÃO");
  put(s, 33, "Zero competência parcial; fonte e vintage por métrica; histórico só após 80% do PL; validação visual e de overflow antes da entrega.");
  setNotes(
    s,
    "Modelo mensal",
    "build_fidc_president_deck_dataset.py fecha os dados; build_fidc_president_deck.mjs regenera o PPT e os artefatos de QA.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.dataFile],
  );
}

// 27 | Sources
{
  const s = common(
    27,
    "Cada número tem denominador, janela, fonte e status de publicação",
    "URLs completas nas notas e em source_ledger.csv.",
    "METODOLOGIA E FONTES",
  );
  put(s, 5, "MÉTRICA");
  put(s, 6, "NÚMEROS E ESCOPO");
  put(s, 7, "STATUS");
  const rows = [
    ["Estoque", `CVM mai/26 | bruto ${brlBi(metrics.gross_pl_brl)} | ex-FIC ${brlBi(metrics.ex_fic_pl_brl)}`, "DIRETO"],
    ["Classes", `ANBIMA nº 09 | ${pct(metrics.classification_share)} do PL em classe oficial`, "MAPEADO"],
    ["Prestadores", "admin mensal; gestor/custodiante atuais; história com gate", "DIRETO / GATE"],
    ["Ofertas", "ANBIMA captação | CVM teto RCVM 160 encerrado", "DOIS CONCEITOS"],
    ["Cotistas", `${metrics.cotista_funds.toLocaleString("pt-BR")} fundos ex-FIC | contas por fundo/classe`, "SEM IDENTIDADE"],
    ["Nomes / secundário", "corpus dirigido | sem negócio a negócio B3", "EXCLUÍDO"],
  ];
  const starts = [8, 12, 16, 20, 24, 28];
  rows.forEach((row, i) => row.forEach((value, j) => put(s, starts[i] + j, value)));
  put(s, 32, "PRINCÍPIO");
  put(s, 33, "Nenhum número do material de referência foi aceito sem reprodução; divergências de vintage e escopo permanecem visíveis.");
  setNotes(
    s,
    "Fontes exatas",
    "Ledger de fonte por métrica, arquivos locais versionados e links primários em cada slide.",
    [URLS.cvmMonthly, URLS.cvmCadastro, URLS.cvmOffers, URLS.anbimaClassification, URLS.anbima2023, URLS.anbima2024, URLS.anbima2025, URLS.fundosNet, URLS.dataFile],
  );
}

await fs.mkdir(path.dirname(FINAL), { recursive: true });
await fs.mkdir(PREVIEW, { recursive: true });
await fs.mkdir(LAYOUT, { recursive: true });

for (let index = 0; index < p.slides.items.length; index += 1) {
  const current = p.slides.items[index];
  const stem = `slide-${String(index + 1).padStart(2, "0")}`;
  const png = await p.export({ slide: current, format: "png", scale: 1.5 });
  await fs.writeFile(path.join(PREVIEW, `${stem}.png`), new Uint8Array(await png.arrayBuffer()));
  const layout = await current.export({ format: "layout" });
  await fs.writeFile(path.join(LAYOUT, `${stem}.layout.json`), await layout.text());
}

const montage = await p.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(path.join(ROOT, "final-montage.webp"), new Uint8Array(await montage.arrayBuffer()));

const inspect = await p.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes",
  maxChars: 2000000,
});
await fs.writeFile(path.join(ROOT, "final-inspect.ndjson"), inspect.ndjson || "", "utf8");

const pptx = await PresentationFile.exportPptx(p);
await pptx.save(FINAL);
console.log(JSON.stringify({ final: FINAL, slides: p.slides.items.length, preview: PREVIEW, layout: LAYOUT }, null, 2));
