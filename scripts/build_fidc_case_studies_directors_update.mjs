import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const bundledNodeModules = path.join(
  os.homedir(),
  ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules",
);
const require = createRequire(path.join(bundledNodeModules, "package.json"));
const { FileBlob, PresentationFile } = require("@oai/artifact-tool");

const ROOT = process.cwd();
const baseTemplatePptxPath = path.join(
  ROOT,
  "data/industry_study/generated_revision/fidc_case_studies_template.pptx",
);
const templateFollowingStarterPptxPath = path.join(ROOT, "work/monocotista_ppt_build/template-starter.pptx");
const starterPptxPath = process.env.CASE_STUDIES_USE_TEMPLATE_STARTER === "1"
  ? templateFollowingStarterPptxPath
  : baseTemplatePptxPath;
const DATA = path.join(ROOT, "data/industry_study/generated_revision/directors_update/fidc_directors_update_data.json");
const GOVERNANCE_DATA = path.join(
  ROOT,
  "data/industry_study/generated_revision/directors_update/fidc_monocotista_governance_202607.json",
);
const OUTPUT = path.join(ROOT, "data/industry_study/generated_revision/fidc_case_studies.pptx");
const PREVIEW_DIR = path.join(ROOT, "work/presentation_build/rendered");

const C = {
  white: "#FFFFFF",
  black: "#161616",
  charcoal: "#2B2B2B",
  mid: "#5B5B5B",
  note: "#858585",
  pale: "#F4F4F4",
  line: "#D9D9D9",
  orange: "#B85300",
};

const F = {
  body: "Itau Display",
  black: "Itau Display Black",
  xbold: "Itau Display X-Bold",
};

function addText(slide, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = String(text ?? "");
  shape.text.style = {
    typeface: style.typeface || F.body,
    fontSize: style.fontSize || 14,
    bold: Boolean(style.bold),
    color: style.color || C.charcoal,
    alignment: style.alignment || "left",
    verticalAlignment: style.verticalAlignment || "top",
    autoFit: "shrinkText",
    wrap: style.wrap || "square",
    lineSpacing: style.lineSpacing || 1,
  };
  return shape;
}

function addHeader(slide, eyebrow, title, page) {
  slide.background.fill = C.white;
  addText(slide, eyebrow, { left: 58, top: 30, width: 760, height: 20 }, {
    typeface: F.xbold,
    fontSize: 11,
    bold: true,
    color: C.orange,
  });
  addText(slide, title, { left: 58, top: 54, width: 1080, height: 58 }, {
    typeface: F.black,
    fontSize: title.length > 88 ? 27 : 30,
    bold: true,
    color: C.black,
    verticalAlignment: "middle",
    lineSpacing: 0.98,
  });
  addText(slide, String(page).padStart(2, "0"), { left: 1170, top: 50, width: 50, height: 32 }, {
    typeface: F.xbold,
    fontSize: 15,
    bold: true,
    color: C.orange,
    alignment: "right",
    verticalAlignment: "middle",
  });
}

function addFooter(slide, text) {
  addText(slide, text, { left: 58, top: 676, width: 1162, height: 19 }, {
    fontSize: 9.5,
    color: C.note,
    verticalAlignment: "middle",
    wrap: "none",
  });
}

function addNotes(slide, sources) {
  slide.speakerNotes.textFrame.setText([
    "[Sources]",
    ...sources.map((source) => `- ${source}`),
    "[/Sources]",
  ].join("\n"));
  slide.speakerNotes.setVisible(true);
}

function addNativeTable(slide, { left, top, width, height, headers, rows, columnWidths, aligns = [], fontSize = 10.5, headerFontSize = 10.5, highlights = new Set() }) {
  const table = slide.tables.add({
    rows: rows.length + 1,
    columns: headers.length,
    left,
    top,
    width,
    height,
    columnWidths,
    values: [headers, ...rows],
  });
  table.styleOptions = {
    headerRow: false,
    totalRow: false,
    firstColumn: false,
    lastColumn: false,
    bandedRows: false,
    bandedColumns: false,
  };
  table.borders.assign({ style: "solid", color: C.line, width: 0.25 });
  table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: headers.length }).assign({
    fill: C.black,
    textStyle: {
      typeface: F.xbold,
      fontSize: headerFontSize,
      bold: true,
      color: C.white,
      verticalAlignment: "middle",
      autoFit: "shrinkText",
      wrap: "square",
    },
    margins: { top: 2, right: 5, bottom: 2, left: 5 },
    anchor: "middle",
  });
  const headerPx = 30;
  table.rows[0].height = headerPx * 0.75;
  rows.forEach((_, rowIndex) => {
    const fill = highlights.has(rowIndex) ? "#FFF1E6" : rowIndex % 2 ? C.pale : C.white;
    table.cells.block({ row: rowIndex + 1, column: 0, rowCount: 1, columnCount: headers.length }).assign({
      fill,
      textStyle: {
        typeface: F.body,
        fontSize,
        color: C.charcoal,
        verticalAlignment: "middle",
        autoFit: "shrinkText",
        wrap: "square",
      },
      margins: { top: 1.5, right: 5, bottom: 1.5, left: 5 },
      anchor: "middle",
    });
    table.rows[rowIndex + 1].height = ((height - headerPx) / rows.length) * 0.75;
  });
  aligns.forEach((alignment, columnIndex) => {
    table.cells.block({ row: 0, column: columnIndex, rowCount: 1, columnCount: 1 }).textStyle.alignment = alignment;
    table.cells.block({ row: 1, column: columnIndex, rowCount: rows.length, columnCount: 1 }).textStyle.alignment = alignment;
  });
  return table;
}

function shortName(row) {
  const aliases = {
    "62838025000116": "Endurance FIDC (TOP 2025 J)",
    "63546406000194": "Pine INSS III FIDC",
    "65347578000164": "ICRED INSS III FIDC",
    "44574361000117": "UPL 02 FIDC",
    "58152340000118": "Monee II FIDC",
    "65207096000184": "SumUp Smart IV (TOP 2025 C)",
    "62626887000185": "SumUp Smart IV (TOP 2025 C)",
    "63622842000103": "Desbrava Uno FIDC",
    "40919667000107": "RecargaPay I FIDC",
    "47640584000123": "Sol Agora Green ESG FIDC",
    "42085830000109": "CloudWalk Akira I FIDC",
    "54083697000130": "Pernambucanas FIDC",
    "52100879000147": "Sotreq FIDC",
    "58476088000100": "Saga FIDC (Consórcio Daltez)",
    "65873297000145": "ArcelorMittal Vértice FIDC",
    "65836995000170": "Pneucash II (Daycoval 0410)",
    "54857414000160": "Indie Merx Raiz I FIDC",
    "53270983000142": "Angá FGTS +AG FIDC",
    "57270666000187": "Mobilitas FIDC",
    "44173467000109": "MT INSS Receivables III FIDC",
  };
  if (aliases[row.cnpj]) return aliases[row.cnpj];
  return String(row.nome_cvm || row.nome_referencia)
    .replace(/FUNDO DE INVESTIMENTO EM DIREITOS CREDITÓRIOS/gi, "FIDC")
    .replace(/RESPONSABILIDADE LIMITADA/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function brlBn(value, digits = 1) {
  return `R$ ${(Number(value) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits })} bi`;
}

function brlMn(value) {
  return (Number(value) / 1e6).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function pct(value, digits = 1) {
  return `${(Number(value) * 100).toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

function competence(value) {
  return value === "2026-06" ? "jun/26" : "jul/26";
}

function metric(slide, value, label, left, width, accent = false) {
  addText(slide, value, { left, top: 126, width, height: 38 }, {
    typeface: F.black,
    fontSize: 26,
    bold: true,
    color: accent ? C.orange : C.black,
  });
  addText(slide, label, { left, top: 163, width, height: 34 }, {
    fontSize: 11.5,
    color: C.mid,
    lineSpacing: 1.02,
  });
}

function addSectionLabel(slide, text, left, top, width = 510) {
  addText(slide, text, { left, top, width, height: 18 }, {
    typeface: F.xbold,
    fontSize: 10.5,
    bold: true,
    color: C.orange,
    verticalAlignment: "middle",
  });
}

function addTimeline(slide, events) {
  const lineX = 618;
  slide.shapes.add({
    geometry: "line",
    position: { left: lineX, top: 169, width: 0, height: 372 },
    fill: "none",
    line: { style: "solid", fill: C.orange, width: 1.25 },
  });
  events.forEach((event, index) => {
    const y = 174 + index * 89;
    slide.shapes.add({
      geometry: "ellipse",
      position: { left: lineX - 5, top: y - 5, width: 10, height: 10 },
      fill: index === events.length - 1 ? C.orange : C.white,
      line: { style: "solid", fill: C.orange, width: 1.4 },
    });
    addText(slide, event[0], { left: 637, top: y - 7, width: 96, height: 19 }, {
      typeface: F.xbold,
      fontSize: 10.2,
      bold: true,
      color: index === events.length - 1 ? C.orange : C.charcoal,
      verticalAlignment: "middle",
    });
    addText(slide, event[1], { left: 747, top: y - 8, width: 448, height: 20 }, {
      typeface: F.xbold,
      fontSize: 11.3,
      bold: true,
      color: C.black,
      verticalAlignment: "middle",
    });
    addText(slide, event[2], { left: 747, top: y + 14, width: 448, height: 46 }, {
      fontSize: 9.7,
      color: C.mid,
      lineSpacing: 0.98,
    });
  });
}

function buildNexoosCase(presentation, after) {
  const { slide } = presentation.slides.insert({ after });
  addHeader(
    slide,
    "Caso 5 · SAV Nexoos / Americanas",
    "SAV Nexoos: a carteira PME deteriorou antes da crise da Americanas",
    7,
  );
  addSectionLabel(slide, "Estrutura, emissões e vínculo societário", 58, 133);
  addNativeTable(slide, {
    left: 58, top: 155, width: 510, height: 246,
    headers: ["Item", "Leitura documental"],
    rows: [
      ["Veículo", "CNPJ 38.284.301/0001-67; início em 30 mar/21; BRL Trust até mai/24 e Hemera depois"],
      ["Lastro", "CCBs e empréstimos a PMEs originados na Plataforma Nexoos; sem coobrigação do cedente"],
      ["Sênior 1 e 2", "R$ 86,2 mi e R$ 103,8 mi; CDI + 4,5% a.a.; 48 meses e 24 meses de carência"],
      ["Mezanino / Júnior", "Mezanino R$ 41,5 mi a CDI + 7,0% a.a.; Júnior sem benchmark; subordinação total mínima de 30%"],
      ["Americanas / Ame", "R$ 30,65 mi em dez/22; 56% da sênior, 2% da mezanino e 19% do PL; cadastro integral N/D"],
    ],
    columnWidths: [128, 382],
    aligns: ["left", "left"],
    fontSize: 9.1,
    headerFontSize: 9.8,
  });
  addSectionLabel(slide, "Sinais no Informe Mensal", 58, 416);
  addNativeTable(slide, {
    left: 58, top: 438, width: 510, height: 188,
    headers: ["Competência", "PL R$ mi", "Atraso / carteira", "Subordinação"],
    rows: [
      ["mar/22", "172,1", "4,3%", "49,2%"],
      ["set/22", "279,6", "10,8%", "30,1%"],
      ["out/22", "198,8", "13,9%", "30,4%"],
      ["dez/22", "159,4", "23,8%", "27,9%"],
      ["ago/23", "64,8", "119,6% bruto*", "42,3%"],
    ],
    columnWidths: [112, 98, 180, 120],
    aligns: ["center", "right", "right", "right"],
    fontSize: 9.2,
    headerFontSize: 9.5,
    highlights: new Set([3, 4]),
  });
  addSectionLabel(slide, "Cronologia do crédito e da liquidação", 610, 133, 585);
  addTimeline(slide, [
    ["mar–dez/21", "Início e incorporação do SAV Omie", "O veículo inicia com Júnior e incorpora o SAV Omiexperience FIDC em dez/21."],
    ["fev–abr/22", "Captação amplia o PL para R$ 280 mi", "Entram Mezanino e duas séries seniores; 71–72 contas são reportadas após a emissão."],
    ["24 out/22", "Cotistas aprovam liquidação por unanimidade", "Altas de juros pressionam PMEs e projeções; cessam aquisições e começa o caixa Sênior → Mezanino."],
    ["dez/22–ago/23", "Atraso e PDD consomem a proteção", "Subordinação reportada cai a 27,9%; efeito vagão leva o atraso bruto acima da carteira."],
    ["2024–jun/26", "Sênior é resgatada; sobra posição residual", "Ata posterior confirma resgate integral da Sênior. PL cai a R$ 0,7 mi; liquidação segue em curso."],
  ]);
  addFooter(slide, "* O atraso bruto inclui parcelas futuras pelo efeito vagão e pode superar a carteira. O vínculo com LASA é societário e de investimento; a ata de out/22 não atribui causalidade à crise contábil de jan/23.");
  addNotes(slide, [
    "BRL Trust — ato e suplementos, 16 mar. 2022, pp. 1–10: https://www.brltrust.com.br/wp-content/uploads/2021/04/ATOS-E-SUPLEMENTOS-_-16.03.22-VFf.pdf",
    "BRL Trust — AGE de liquidação antecipada, 24 out. 2022, pp. 1–3: https://www.brltrust.com.br/wp-content/uploads/2021/04/2022-10-24_FIDC-SAV-NEXOOS_AGE-VL.pdf",
    "Hemera — regulamento, 8 mai. 2024, pp. 35, 39–44 e 57–68: https://hemeradtvm.com.br/wp-content/uploads/2024/05/2024-05-08_FIDC-SAV-NEXOOS_REGULAMENTO-VL.pdf",
    "Hemera — AGOE, 20 jan. 2025, anexo da AGE de 25 set. 2024, p. 3; confirma resgate integral das cotas seniores: https://hemeradtvm.com.br/wp-content/uploads/2024/05/2025-01-20_FIDC-SAV-NEXOOS_AGOE-VL.pdf",
    "Ame Digital — demonstrações financeiras de 2022, nota SAV Nexoos; posição de R$ 30,65 mi e percentuais por classe: https://images.amedigital.com/site-ame/demonstrativo-financeiro/INF901032778350122022.pdf",
    "Nexoos SEP — demonstrações financeiras de 2021/2023; aquisição pela Ame Digital e etapas societárias: https://www.nexoos.com.br/demonstrativos-financeiros/",
    "Liberum Ratings — relatórios 1T22, 2T22 e 3T22; CCBs de PMEs, efeito vagão e desempenho: https://www.liberumratings.com.br/detalhes-ativo/historico-6248/",
    "CVM — Informe Mensal FIDC, CNPJ 38.284.301/0001-67; cálculo atraso/carteira e subordinação por competência: https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "Hemera/ANBIMA — informativo mensal mar. 2025, p. 1; evento de liquidação e índices sobre PL: https://hemeradtvm.com.br/wp-content/uploads/2024/05/2025-03_FIDC-SAV-NEXOOS_INFORMATIVO-MENSAL-ANBIMA.pdf",
  ]);
  return slide;
}

function buildLightCase(presentation, after) {
  const { slide } = presentation.slides.insert({ after });
  addHeader(
    slide,
    "Caso 6 · FIDC Light",
    "FIDC Light: rating e eventos jurídicos sinalizaram risco com atraso CVM zerado",
    8,
  );
  addSectionLabel(slide, "Estrutura e emissões", 58, 133);
  addNativeTable(slide, {
    left: 58, top: 155, width: 510, height: 246,
    headers: ["Item", "Leitura documental"],
    rows: [
      ["Veículo", "CNPJ 29.665.468/0001-87; início em 4 jun/18; Oliveira Trust e XP Gestão/XP Vista"],
      ["Lastro", "Fluxo futuro de contas e serviços de energia da Light Serviços; arrecadação por contas vinculadas"],
      ["Sênior 1", "R$ 1,0 bi; CDI + 1,22% a.a.; 72 meses; vencimento previsto em jun/24"],
      ["Sênior 2", "R$ 400 mi; IPCA + 5,75% a.a.; 72 meses; vencimento previsto em jun/24"],
      ["Júnior / cotistas", "R$ 35,03 mi inicial; 159–193 contas em 2023; cadastro integral N/D e exemplos públicos em EFPCs"],
    ],
    columnWidths: [128, 382],
    aligns: ["left", "left"],
    fontSize: 9.1,
    headerFontSize: 9.8,
  });
  addSectionLabel(slide, "Informe Mensal durante a crise", 58, 416);
  addNativeTable(slide, {
    left: 58, top: 438, width: 510, height: 188,
    headers: ["Competência", "PL R$ mi", "Atraso CVM", "Contas"],
    rows: [
      ["jan/23", "516,5", "0,0%", "159"],
      ["fev/23", "420,9", "0,0%", "148"],
      ["jun/23", "230,5", "0,0%", "193"],
      ["ago/23", "97,9", "0,0%", "193"],
      ["set/23", "0,9", "0,0%", "1"],
    ],
    columnWidths: [128, 116, 146, 120],
    aligns: ["center", "right", "right", "right"],
    fontSize: 9.2,
    headerFontSize: 9.5,
    highlights: new Set([0, 4]),
  });
  addSectionLabel(slide, "Cronologia dos gatilhos e da amortização", 610, 133, 585);
  addTimeline(slide, [
    ["jun/18", "R$ 1,4 bi em duas séries seniores", "Fluxo futuro de energia financia Sênior 1 e 2; Júnior inicial de R$ 35,03 mi."],
    ["3 fev/23", "Fitch corta AAAsf para BBsf", "O rebaixamento configura Desalavancagem e aciona amortização acelerada."],
    ["23 fev/23", "Seniores mantêm a aceleração", "87,31% votam contra Realavancagem; Júnior não vota. A ata não identifica os dissidentes."],
    ["abr–mai/23", "Liminar e recuperação judicial suspendem o fluxo", "Tutela interrompe retenções; pedido de RJ gera novo gatilho. Rating cai a Bsf/B-sf."],
    ["15 jun–set/23", "Retenção volta; seniores saem e Júnior absorve", "PL cai a R$ 0,9 mi e resta uma conta. Oliveira Trust registra –99,70353% acumulado na Júnior."],
  ]);
  addFooter(slide, "A disputa pública opôs o Grupo Light ao FIDC e a outros credores. Entre cotistas, houve votação não unânime; a ata não individualiza posições. O fundo foi cancelado na CVM em fev/24.");
  addNotes(slide, [
    "Oliveira Trust — página do FIDC Light, estrutura, documentos e retorno acumulado da cota subordinada: https://api-site.oliveiratrust.com.br/novo/fundos-captacao/12861",
    "Oliveira Trust — fato relevante de 3 fev. 2023, rebaixamento AAAsf(bra) → BBsf(bra), download código 1619961: https://api-site.oliveiratrust.com.br/scot/modulos/downloads/baixar.php?cod=1619961",
    "Oliveira Trust — AGE realizada em 23 fev. 2023, pp. 1–4; quórum, direitos de voto e deliberação. Documento obtido na página do administrador.",
    "Oliveira Trust/XP — fatos relevantes de 17 abr., 15 mai. e 21 jun. 2023; tutela, recuperação judicial e retomada da retenção: https://api-site.oliveiratrust.com.br/scot/modulos/downloads/baixar.php?cod=1646131 ; https://api-site.oliveiratrust.com.br/scot/modulos/downloads/baixar.php?cod=1669891 ; https://api-site.oliveiratrust.com.br/scot/modulos/downloads/baixar.php?cod=1682941",
    "Fitch Ratings — relatórios de monitoramento de 9 mai. e 31 jul. 2023, disponíveis na página do administrador; emissão, lastro de fluxo futuro e ratings Bsf/B-sf.",
    "Light S.A. — demonstrações financeiras; emissão de 1,4 milhão de cotas seniores concluída em 5 jun. 2018 e remuneração das séries: https://ri.light.com.br/",
    "CVM — Informe Mensal FIDC, CNPJ 29.665.468/0001-87; PL, cotistas, composição de cotas e atraso reportado: https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "Exemplos públicos de cotistas, sem pretensão de cadastro completo: Braslight, demonstrações de 2022; BRF Previdência, relatório de investimentos set. 2022.",
  ]);
  return slide;
}

function updateCaseOverviewSlides(presentation) {
  replaceText(
    presentation,
    "sh/7qp4be9c",
    "Blue II / Azul · MCPO / Maqcampo · Lavoro · Americanas",
    "Blue II / Azul · MCPO / Maqcampo · Lavoro · Americanas · SAV Nexoos · FIDC Light",
  );
  const summary = presentation.slides.items[1];
  replaceText(
    presentation,
    "sh/9072xkry",
    "Quatro casos com canais distintos de materialização da perda",
    "Seis casos com canais distintos de materialização da perda",
  );
  setTable(summary.tables.items[0], [
    ["Caso", "Ativo / lastro", "Primeiro sinal documentado", "Transmissão econômica", "Lição para os dados"],
    ["Blue II / Azul", "Debêntures da Azul", "Waivers e disputa sobre amortização", "Perda atravessa Júnior, Mezaninos e Sênior", "Inadimplência aparece tarde"],
    ["MCPO + Lavoro", "Recebíveis do agronegócio", "Subordinação, aging, resolução e downgrade", "Liquidação, waivers e dissidência", "Atas antecedem o colapso do PL"],
    ["Americanas / Vinci", "Debênture LAMEA6/LAMEAA6", "Queda de preço após inconsistências contábeis", "Marcação diária na cota única", "Preço antecede atraso"],
    ["SAV Nexoos + Light", "CCBs de PMEs / fluxo futuro de energia", "Atraso PME / rebaixamento e gatilho", "Caixa prioriza seniores; subordinadas ficam com o residual", "Estrutura e rating podem liderar o Informe"],
  ]);
  addNotes(summary, [
    "Síntese dos seis estudos de caso. Fontes completas, documentos e cálculos estão nas notas das lâminas individuais.",
    "CVM — Informe Mensal FIDC: https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "Fundos.NET/B3, páginas dos administradores, demonstrações financeiras, atas, fatos relevantes e relatórios de rating identificados por veículo/CNPJ.",
  ]);

  const transversalIndex = presentation.slides.items.length === 22 ? 8 : 6;
  const transversal = presentation.slides.items[transversalIndex];
  setTable(transversal.tables.items[0], [
    ["Camada", "Sinal capturado", "Exemplo", "Limite analítico", "Fonte"],
    ["Regulamento / suplemento", "Lastro, benchmark, subordinação, gatilhos e waterfall", "Blue II concentra em Azul; Nexoos financia PMEs; Light usa fluxo futuro", "Versões e apêndices mudam; exige controle por data", "Fundos.NET / administrador"],
    ["Ata / fato relevante", "Waiver, falta de quórum, conflito, votação e medida aprovada", "Nexoos liquida por unanimidade; seniores do Light mantêm aceleração", "Pode ser publicado após o evento econômico", "Fundos.NET / administrador"],
    ["Informe Mensal CVM", "PL, carteira, aging, PDD, subordinação e retorno reportado", "Nexoos chega a 119,6% bruto; Light mantém atraso zero durante os gatilhos", "Perímetros podem divergir; zero e ausência exigem separação", "Dados Abertos CVM"],
    ["Administrador / DF", "Cota, amortização, ativo nominal, cotista divulgado e opinião do auditor", "Ame identifica posição no Nexoos; Oliveira Trust mostra –99,70% na Júnior do Light", "Cadastro completo e histórico em lote variam", "Administrador / DF auditada"],
    ["Evento externo", "RJ, RE, Chapter 11, rating e mercado", "Azul, Agrovenci/Lavoro, Americanas e Light", "Exige leitura de garantias, coobrigação e servicing", "Judiciário, agência e companhia"],
  ]);
  addNotes(transversal, [
    "Leitura transversal construída a partir das fontes primárias indicadas nas lâminas de cada caso.",
    "CVM — Informe Mensal FIDC: https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "Regulamentos, suplementos, atas, fatos relevantes, relatórios de rating e demonstrações financeiras são tratados por versão e CNPJ.",
  ]);
}

function carteira101Rows(data) {
  return data.carteira_101.one_senior_account_funds.map((row, index) => [
    `${index + 1}`,
    shortName(row),
    brlMn(row.pl_publicado_brl),
    competence(row.competencia_cvm),
    "Sim*",
  ]);
}

function buildCarteira101(presentation, after, data) {
  const { slide } = presentation.slides.insert({ after });
  const summary = data.carteira_101.summary;
  const funds = data.carteira_101.one_senior_account_funds;
  addHeader(slide, "Carteira 101 · cotas seniores", "A CVM sinaliza 19 fundos com uma única conta sênior reportada", 8);
  metric(slide, "19 fundos", "uma conta sênior na Tabela X.1.1", 58, 240, true);
  metric(slide, brlBn(summary.one_senior_account_pl_brl, 2), "PL publicado desses veículos", 342, 245);
  metric(slide, pct(summary.pl_coverage, 1), "do PL conhecido da carteira com dado CVM", 630, 280);
  metric(slide, "23 fundos", "sem dado exato; mantidos como N/D", 950, 270);
  const rows = carteira101Rows(data);
  addNativeTable(slide, {
    left: 58, top: 211, width: 568, height: 425,
    headers: ["#", "Fundo / classe", "PL R$ mi", "Comp.", "1 conta"],
    rows: rows.slice(0, 10),
    columnWidths: [28, 336, 82, 60, 62],
    aligns: ["center", "left", "right", "center", "center"],
    fontSize: 9.6,
    headerFontSize: 9.5,
  });
  addNativeTable(slide, {
    left: 652, top: 211, width: 568, height: 425,
    headers: ["#", "Fundo / classe", "PL R$ mi", "Comp.", "1 conta"],
    rows: rows.slice(10),
    columnWidths: [28, 336, 82, 60, 62],
    aligns: ["center", "left", "right", "center", "center"],
    fontSize: 9.6,
    headerFontSize: 9.5,
  });
  addFooter(slide, "* Uma conta sênior é indício compatível com posição exclusiva da carteira interna; a CVM não publica a identidade do titular. CNPJ é a chave de reconciliação.");
  addNotes(slide, [
    "CVM — Informe Mensal FIDC, Tabelas IV e X.1.1, competências jul/2026 e jun/2026: https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    "Arquivo de cálculo: directors_update/carteira_101_cotistas_senior_202607.csv. Método: soma de contas seniores por tipo de investidor e CNPJ; jul/26 com fallback jun/26.",
  ]);
  return slide;
}

function updateCarteira101Existing(presentation, data, slideOverride = null) {
  const slide = slideOverride || presentation.slides.items[7];
  const tables = slide.tables.items;
  if (tables.length !== 2) throw new Error(`Slide 8 deveria conter duas tabelas; contém ${tables.length}.`);
  const headers = ["#", "Fundo / classe", "PL R$ mi", "Comp.", "1 conta"];
  const rows = carteira101Rows(data);
  setTable(tables[0], [headers, ...rows.slice(0, 10)]);
  setTable(tables[1], [headers, ...rows.slice(10)]);
}

function replaceSlideText(slide, oldText, newText) {
  const shape = slide.shapes.items.find((item) => String(item.text ?? "") === oldText);
  if (!shape) throw new Error(`Texto herdado não encontrado no slide duplicado: ${oldText}`);
  shape.text = newText;
}

function formatGovernanceTable(table, riskRows, alertRows) {
  [174, 112, 106, 66, 110].forEach((width, index) => {
    table.columns.get(index).width = width;
  });
  table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: 5 }).assign({
    textStyle: {
      typeface: F.xbold,
      fontSize: 8.4,
      bold: true,
      color: C.white,
      alignment: "left",
      verticalAlignment: "middle",
      autoFit: "shrinkText",
      wrap: "square",
    },
    margins: { top: 1.5, right: 3, bottom: 1.5, left: 3 },
  });
  for (let rowIndex = 1; rowIndex <= 10; rowIndex += 1) {
    let fill = rowIndex % 2 === 0 ? C.pale : C.white;
    if (riskRows.has(rowIndex - 1)) fill = "#FFF1E6";
    if (alertRows.has(rowIndex - 1)) fill = "#ECECEC";
    table.cells.block({ row: rowIndex, column: 0, rowCount: 1, columnCount: 5 }).assign({
      fill,
      textStyle: {
        typeface: F.body,
        fontSize: 8.05,
        color: C.charcoal,
        alignment: "left",
        verticalAlignment: "middle",
        autoFit: "shrinkText",
        wrap: "square",
      },
      margins: { top: 1, right: 3, bottom: 1, left: 3 },
    });
    table.rows[rowIndex].height = 35.5 * 0.75;
  }
  table.cells.block({ row: 1, column: 3, rowCount: 10, columnCount: 1 }).textStyle.alignment = "center";
}

function buildMonocotistaGovernance(presentation, governance, slideOverride = null) {
  const source = slideOverride || presentation.slides.items[9];
  if (!source || source.tables.items.length !== 2) {
    throw new Error("Slide 10 deveria conter duas tabelas nativas para ser duplicado.");
  }
  const slide = slideOverride || source.duplicate();
  if (!slideOverride) slide.moveTo(10);

  replaceSlideText(slide, "Carteira 101 · cotas seniores", "Carteira 101 · governança de cotistas");
  replaceSlideText(slide, "A CVM sinaliza 19 fundos com uma única conta sênior reportada", "Quatro fundos têm uma posição sênior; três dão maioria de votos à subordinada");
  replaceSlideText(slide, "19 fundos", "4 / 20");
  replaceSlideText(slide, "uma conta sênior na Tabela X.1.1", "uma posição sênior reportada em jul/26");
  replaceSlideText(slide, "R$ 7,45 bi", "3 / 20");
  replaceSlideText(slide, "PL publicado desses veículos", "Mez + Jr acima de 50% dos votos");
  replaceSlideText(slide, "99,0%", "0 / 20");
  replaceSlideText(slide, "do PL conhecido da carteira com dado CVM", "beneficiário final identificado publicamente");
  replaceSlideText(slide, "23 fundos", "3 alertas");
  replaceSlideText(slide, "sem dado exato; mantidos como N/D", "iFood, Pine e VTK exigem reconciliação");
  replaceSlideText(
    slide,
    "* Uma conta sênior é indício compatível com posição exclusiva da carteira interna; a CVM não publica a identidade do titular. CNPJ é a chave de reconciliação.",
    "Posições = contas por série no Informe Mensal; podem repetir o investidor. QC = 1 cota/1 voto; FP = posição financeira. % por beneficiário exige registro do escriturador/B3.",
  );

  const headers = ["FIDC / CNPJ", "Sênior", "Mez + Jr", "Voto sub.", "Conclusão documental"];
  const rows = governance.fundos.map((row) => [
    `${row.nome}\n${row.cnpj}`,
    row.senior,
    row.subordinada,
    row.voto_sub,
    row.conclusao,
  ]);
  const leftTable = slide.tables.items[0];
  const inheritedRightTable = slide.tables.items[1];
  setTable(leftTable, [headers, ...rows.slice(0, 10)]);
  slide.tables.deleteById(inheritedRightTable.id);
  const rightTable = addNativeTable(slide, {
    left: 652,
    top: 211,
    width: 568,
    height: 425,
    headers,
    rows: rows.slice(10),
    columnWidths: [174, 112, 106, 66, 110],
    aligns: ["left", "left", "left", "center", "left"],
    fontSize: 8.05,
    headerFontSize: 8.4,
  });
  formatGovernanceTable(leftTable, new Set([8, 9]), new Set([]));
  formatGovernanceTable(rightTable, new Set([2]), new Set([0, 1, 9]));

  const fundDocumentIds = governance.fundos
    .flatMap((row) => row.documentos)
    .map((item) => item.replace("Fundos.NET ", ""));
  addNotes(slide, [
    "CVM — Informe Mensal FIDC, Tabelas X.1.1 e X.2, competência 31 jul. 2026: https://dados.cvm.gov.br/dataset/fidc-doc-inf_mensal",
    `Fundos.NET/B3 — regulamentos, atas, anúncios de encerramento e demonstrações financeiras: documentos ${fundDocumentIds.join(", ")}; consulta por ID em https://fnet.bmfbovespa.com.br/fnet/publico/visualizarDocumento`,
    `Corpus documental: ${governance.metodologia.corpus}`,
    `Método de posições: ${governance.metodologia.posicao}`,
    `Método de PL: ${governance.metodologia.pl}`,
    `Método de voto: ${governance.metodologia.voto}`,
    "Correções cadastrais validadas: Angá FGTS II 53.577.135/0001-80; Cartão de Compra Supplier II 50.988.212/0001-05.",
  ]);
  return slide;
}

function buildFinanceiro(presentation, after, data) {
  const { slide } = presentation.slides.insert({ after });
  const summary = data.financeiro.summary;
  const decomposition = data.financeiro.decomposition;
  addHeader(slide, "Indústria · Financeiro", "R$ 323,9 bi: pagamentos lideram; R$ 79,0 bi seguem sem segregação suficiente", 9);
  metric(slide, brlBn(summary.financeiro_pl_brl, 1), "PL ex-FIC · Tipo ANBIMA Financeiro", 58, 275, true);
  metric(slide, brlBn(summary.payment_chain_pl_brl, 1), "meios de pagamento e cartões", 354, 270);
  metric(slide, brlBn(summary.consignado_total_pl_brl, 1), "consignado total, inclusive proxy", 650, 270);
  metric(slide, "1.103", "CNPJs no perímetro", 950, 270);
  const rows = decomposition.map((row) => [
    row.bucket_financeiro
      .replace(" / cartoes", " e cartões")
      .replace("Consignado sem segregacao publica", "Consignado sem segregação pública")
      .replace("Demais credito PF", "Demais crédito PF")
      .replace("Credito PJ", "Crédito PJ")
      .replace("Imobiliario", "Imobiliário")
      .replace("Outros / multicarteira sem segregacao PF-PJ", "Outros / multicarteira sem PF-PJ"),
    brlBn(row.pl_brl, 1).replace("R$ ", ""),
    pct(row.share, 1),
    String(row.fundos),
    row.ordem <= 5 ? "nome + taxonomia funcional" : "taxonomia funcional / residual",
  ]);
  addNativeTable(slide, {
    left: 58, top: 211, width: 1162, height: 392,
    headers: ["Segmento analítico", "PL", "% Financeiro", "Fundos", "Regra predominante"],
    rows,
    columnWidths: [385, 130, 130, 95, 422],
    aligns: ["left", "right", "right", "right", "left"],
    fontSize: 10.5,
    headerFontSize: 10.5,
    highlights: new Set([0]),
  });
  addText(slide, "TAPSO", { left: 58, top: 620, width: 90, height: 24 }, { typeface: F.xbold, fontSize: 13, bold: true, color: C.orange });
  addText(slide, `${brlBn(summary.tapso_pl_brl, 1)} está dentro de Financeiro. A curadoria documental de adquirência soma R$ 94,9 bi dentro do bloco; R$ 4,3 bi estão classificados em outros tipos ANBIMA.`, { left: 148, top: 618, width: 1072, height: 35 }, { fontSize: 11.5, color: C.charcoal });
  addFooter(slide, "Perímetro: PL ex-FIC de jun/26; buckets mutuamente exclusivos. Nome é sinal de triagem. Ausência de segregação permanece explícita.");
  addNotes(slide, [
    "CVM/ANBIMA — base de PL ex-FIC e taxonomia aplicada no artefato setorial, competência jun/2026.",
    "Arquivos de cálculo: directors_update/financeiro_decomposition_202606.csv e financeiro_decomposition_fund_ledger_202606.csv.",
    "Curadoria documental de adquirência: directors_update/financeiro_acquiring_document_ledger_202606.csv.",
  ]);
  return slide;
}

function buildCarbono(presentation, after) {
  const { slide } = presentation.slides.insert({ after });
  addHeader(slide, "Supervisão · Operação Carbono Oculto", "A operação expôs fundos de poucos cotistas e uma supervisão fragmentada por veículo", 10);
  const rows = [
    ["jun/25", "CVM informa ter encaminhado um caso ao MPF antes da operação", "Um caso de PLD/FTP identificado em supervisão", "A divulgação pública não identifica o veículo nem permite medir a cobertura total"],
    ["28 ago/25", "Operação Carbono Oculto é deflagrada", "Investigação descreve fintechs e fundos em camadas para ocultar recursos; FIP Camaçari aparece ligado a entidades REAG", "Atribuições permanecem como alegações/investigações até decisão definitiva"],
    ["22 set/25", "SSR/CVM pede dados de 13 fundos nominalmente listados", "2 FIPs/FIMs e 10 FIIs; abertura de apurações em SSR, SSE e SIN", "A atuação direcionada registrada publicamente ocorre após a operação"],
    ["fev/26", "CVM apresenta escala da REAG até nov/25", "R$ 373,95 bi, 499 fundos e 5.049 investidores administrados/geridos", "Escala por prestador dificultava leitura consolidada de vínculos e alertas"],
    ["2026", "GT Master revisa 314 processos; 87 fundos ligados à Carbono Oculto", "33% de abstenção de auditoria versus 4% na indústria; 65 ofícios de alerta e 14 termos de acusação", "A própria CVM recomenda painel por regulado, vínculos e gatilhos de auditoria"],
  ];
  addNativeTable(slide, {
    left: 58, top: 143, width: 1162, height: 470,
    headers: ["Data", "Fato público", "Uso de fundos / resposta", "O que permaneceu fora do radar público"],
    rows,
    columnWidths: [92, 300, 386, 384],
    aligns: ["center", "left", "left", "left"],
    fontSize: 10.4,
    headerFontSize: 10.5,
  });
  addText(slide, "Leitura executiva", { left: 58, top: 626, width: 150, height: 22 }, { typeface: F.xbold, fontSize: 12.5, bold: true, color: C.orange });
  addText(slide, "O registro público mostra ação anterior em um caso e apuração direcionada após a operação. O ponto crítico foi consolidar relações entre fundos, cotistas, prestadores e partes ligadas.", { left: 210, top: 624, width: 1010, height: 35 }, { fontSize: 11.5, color: C.charcoal });
  addFooter(slide, "Data de corte: 20 ago. 2026 | fatos de investigação descritos como alegações ou apurações, sem antecipação de condenação.");
  addNotes(slide, [
    "CVM — resposta ao Congresso sobre Carbono Oculto: https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor=3068110&filename=Tramitacao-REQ+370%2F2025+CSPCCO",
    "CVM — apresentação à CAE, 24 fev. 2026: https://www.gov.br/cvm/pt-br/assuntos/noticias/anexos/2026/20260224-apresentacao-ppt-cae-cvm.pdf",
    "CVM — recomendações do GT Master: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/comite-de-riscos-da-cvm-analisa-recomendacoes-do-gt-master/",
    "ANTT — nota técnica com descrição da investigação e FIP Camaçari: https://www.gov.br/antt/pt-br/assuntos/rodovias/novos-projetos-em-rodovias/bndes-cn2-centro-oeste-norte/arquivos-para-download/comissao-de-outorga/nota-tecnica-antt-ndeg10395-2025-coed2-2025-sucon-dir-antt/@@download/file",
  ]);
  return slide;
}

function buildMaster(presentation, after) {
  const { slide } = presentation.slides.insert({ after });
  addHeader(slide, "Supervisão · Banco Master", "Credcesta era carteira de crédito; fundos aparecem na circulação e na avaliação dos ativos", 11);
  const stages = [
    ["1", "Originação", "Credcesta, PIX, cartão e outros créditos de varejo"],
    ["2", "Venda ao BRB", "Compras de carteiras desde 1 jul. 2024"],
    ["3", "Substituições", "R$ 10,8 bi substituídos dentro de R$ 30,4 bi adquiridos"],
    ["4", "Fundos e ativos", "CVM apura ofertas, documentos, reavaliações e partes relacionadas"],
  ];
  stages.forEach((stage, index) => {
    const left = 58 + index * 292;
    addText(slide, stage[0], { left, top: 132, width: 34, height: 34 }, { typeface: F.black, fontSize: 24, bold: true, color: C.orange });
    addText(slide, stage[1], { left: left + 40, top: 132, width: 225, height: 22 }, { typeface: F.xbold, fontSize: 13, bold: true, color: C.black });
    addText(slide, stage[2], { left: left + 40, top: 155, width: 225, height: 46 }, { fontSize: 10.5, color: C.mid });
    if (index < stages.length - 1) addText(slide, "→", { left: left + 264, top: 142, width: 24, height: 24 }, { typeface: F.xbold, fontSize: 20, bold: true, color: C.note, alignment: "center" });
  });
  const rows = [
    ["1 jul/24–mar/25", "BRB compra carteiras originadas pelo Master", "Planilhas obtidas por LAI e reportagem apontam R$ 30,4 bi em compras", "Fonte jornalística; validar documentos transacionais e processos"],
    ["mar/25", "BRB identifica parcela descrita como fraudulenta", "Compras e substituições continuaram, segundo a apuração publicada", "A validade de cada crédito não é observável no Informe Mensal público"],
    ["2025–26", "CVM abre e consolida processos ligados a Master, REAG e entidades conexas", "Investigações sobre notas, CRIs, FIDCs, ofertas, avaliação e documentos de suporte", "Processos possuem estágios distintos; investigação não equivale a condenação"],
    ["2026", "GT Master identifica padrões de risco", "Ativos reavaliados sem base razoável, documentos falsos/inadequados e possível manipulação", "O desenho de supervisão anterior não consolidava adequadamente regulados e vínculos"],
  ];
  addNativeTable(slide, {
    left: 58, top: 225, width: 1162, height: 375,
    headers: ["Data", "Fato", "Evidência pública", "Limite de conclusão"],
    rows,
    columnWidths: [140, 300, 376, 346],
    aligns: ["center", "left", "left", "left"],
    fontSize: 10.4,
    headerFontSize: 10.5,
  });
  addText(slide, "Credcesta", { left: 58, top: 617, width: 100, height: 22 }, { typeface: F.xbold, fontSize: 12.5, bold: true, color: C.orange });
  addText(slide, "Nome de produto de crédito consignado/cartão. O dado público de FIDC não identifica devedor individual nem comprova existência, validade ou adimplência de cada contrato.", { left: 160, top: 614, width: 1060, height: 38 }, { fontSize: 11.5, color: C.charcoal });
  addFooter(slide, "Data de corte: 20 ago. 2026 | valores e cronologia preservam a fonte; conclusões sancionadoras dependem dos processos.");
  addNotes(slide, [
    "CVM — processos relativos a Grupo Master, REAG e entidades conexas: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/informacoes-relativas-a-grupo-master-reag-e-outras-entidades-conexas",
    "CVM — recomendações do GT Master: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/comite-de-riscos-da-cvm-analisa-recomendacoes-do-gt-master/",
    "Metrópoles — planilhas do BRB obtidas por LAI, 6 abr. 2026: https://www.metropoles.com/colunas/demetrio-vecchioli/brb-comprou-r-304-bilhoes-em-ativos-do-banco-master-veja-planilhas",
  ]);
  return slide;
}

function setTable(table, values) {
  values.forEach((row, rowIndex) => row.forEach((value, columnIndex) => table.cells.set(rowIndex, columnIndex, String(value))));
}

function replaceText(presentation, id, oldText, newText) {
  presentation.resolve(id).text.replace(oldText, newText);
}

function setPageAndCutoff(presentation) {
  presentation.slides.items.forEach((slide, index) => {
    if (index >= 1 && slide.shapes.items[2]) {
      slide.shapes.items[2].text = String(index + 1).padStart(2, "0");
    }
    slide.shapes.items.forEach((shape) => {
      const value = String(shape.text ?? "");
      if (!value) return;
      if (value.includes("19 ago. 2026")) shape.text.replace("19 ago. 2026", "20 ago. 2026");
      if (value.includes("19 ago/26")) shape.text.replace("19 ago/26", "20 ago/26");
    });
  });
}

function updateRegulatorySlides(presentation) {
  const baseByLength = new Map([[16, 7], [20, 11], [22, 13]]);
  const base = baseByLength.get(presentation.slides.items.length);
  if (base === undefined) throw new Error(`Quantidade inesperada de slides para capítulo regulatório: ${presentation.slides.items.length}.`);
  const regulatory = presentation.slides.items.slice(base, base + 7);
  replaceText(presentation, "sh/ts7md4r2", "19 de agosto de 2026", "20 de agosto de 2026");
  replaceText(presentation, "sh/18byd4zy", "De mai/24 a ago/26, as chaves melhoraram e os dados de crédito continuam parciais", "De mai/24 a ago/26, a identidade melhorou; lastro, devedor e retorno seguem parciais");
  setTable(regulatory[0].tables.items[0], [
    ["Data", "Mudança", "Preocupação", "Implementação", "Efeito observado até ago/26", "Fonte"],
    ["Mai/24", "Novo Informe Mensal", "Erros de série, subclasse e continuidade", "Seleção prévia de campos e reporte de séries extintas", "Melhora de identidade; aging, PDD e retorno continuam autorreportados", "CVM · 8 mai/24"],
    ["Jan/25", "Dados Abertos por classe/subclasse", "Cadastro e série histórica fragmentados", "Arquivos cadastrais e bases adaptadas à RCVM 175", "Chaves mais utilizáveis; ponte histórica ainda necessária", "CVM · 30 jan/25"],
    ["Abr/25", "Orientação CVM–ANBIMA", "Desenquadramento e reporte pouco uniformes", "Administrador comunica evento e padroniza tratamento no Informe", "Governança melhora; resultado por fundo não é publicado", "CVM / ANBIMA"],
    ["2025–26", "IDs e validações de arquivo", "Chaves inválidas, precisão e reprocessamento", "Identificadores e validações adicionais no leiaute", "Menos erro formal; conteúdo econômico ainda depende do prestador", "CVM · portal"],
    ["Abr/26", "ACT CVM–BCB", "Visão incompleta do endividamento e do risco", "Intercâmbio e qualificação do reporte ao SCR, inclusive securitizadoras", "Ganho supervisório; dados protegidos não chegam à base pública", "CVM / BCB"],
    ["Mai–jul/26", "Plano emergencial", "Supervisão isolada e validação limitada de lastro", "22 medidas, painel de vínculos, seleção por risco e amostra de lastro", "Desenho substantivo; execução e impacto ainda não demonstrados", "CVM / STF"],
    ["Ago/26", "Tabela VIII", "Distribuição de valores pouco estruturada", "Arquivo público com sequencial e valor desde 2025", "Nova granularidade de valor; sem identificador público do devedor", "CVM · Dados Abertos"],
  ]);

  replaceText(presentation, "sh/ofq5svm5", "Teste de efetividade", "Posições públicas e efetividade");
  replaceText(presentation, "sh/1cfmhgne", "As chaves avançaram; risco de crédito e retorno continuam com lacunas", "CVM e ANBIMA reconhecem ganhos de padronização e limites operacionais dos reportes");
  setTable(regulatory[1].tables.items[0], [
    ["Tema", "Posição pública da CVM", "Posição pública da ANBIMA", "O que foi implementado", "Leitura de efetividade", "Fonte"],
    ["Identidade", "Padronizar fundo, classe, subclasse e série", "Apoio à adaptação e orientação conjunta", "Novo Informe, cadastros e IDs", "Efetivo para chaves recentes", "CVM / ANBIMA"],
    ["Conteúdo", "Ampliar dados abertos e informação de crédito", "Apoia transparência; pede formatos redesenhados e reporte separado quando há reprocessamento", "Novos arquivos e Tabela VIII", "Parcial: devedor e garantias seguem incompletos", "CVM · consulta / ANBIMA"],
    ["Operação", "Validação e cumprimento de prazos", "Relata falhas recorrentes no CVMWeb no 10º dia útil e pede 20º dia para balancete", "Ajustes de leiaute e orientação", "Ponto operacional ainda aberto", "ANBIMA · consulta"],
    ["PDD e lastro", "Amostra de lastro, SCR e supervisão por risco", "Termos exigem revisão de PDD, preço, lastro, controles e auditoria", "Plano emergencial e compromissos", "Em implantação; resultado por fundo sem painel", "CVM / ANBIMA"],
    ["Retorno", "Maior precisão e identificação de subclasse", "Defende informação acurada e acessível", "Leiaute mais preciso", "Parcial: amortização e denominador exigem reconstrução", "CVM / ANBIMA"],
    ["Integração", "Acordos com ANBIMA e BCB", "Compartilhamento evita duplicidade de supervisão", "Canais formais e SCR ampliado", "Efetivo como infraestrutura; impacto não mensurado publicamente", "Acordos oficiais"],
  ]);

  setTable(regulatory[2].tables.items[0], [
    ["Origem", "Escopo e metas", "Prazo", "Fonte"],
    ["Aprovado em 26 mai/26 após cautelar do STF na ADI 7.791; homologado em 3 jul/26", "22 medidas, quatro eixos, cerca de R$ 560 mi adicionais e meta de reduzir 20% do estoque processual", "31 dez. 2026 para metas imediatas; contratações tecnológicas podem superar 12 meses", "Plano CVM e STF"],
  ]);
  regulatory[2].tables.items[1].cells.set(0, 3, "Verificação pública em 20 ago/26");

  setTable(regulatory[3].tables.items[0], [
    ["Instrumento", "Base", "O que faz", "Prazo e checagem", "Pagamento / multa", "Se houver descumprimento"],
    ["Termo de Compromisso CVM", "Lei 6.385/76, art. 11, §§5º–8º; RCVM 45/21", "Suspende ou evita o PAS; sem confissão; exige cessar, corrigir e eventualmente indenizar", "Prazo no termo; superintendência competente monitora; arquivamento após comprovação", "Obrigação pecuniária não é multa sancionadora", "PAS inicia ou retoma; título executivo pode ser cobrado"],
    ["TAC", "Lei 7.347/85, art. 5º, §6º", "Ajusta conduta às exigências legais; título executivo extrajudicial", "Prazo, prova e fiscalização são definidos no instrumento", "Pode prever reparação e multa cominatória", "Órgão legitimado pode executar judicialmente"],
    ["Termo ANBIMA", "Códigos privados de autorregulação e adesão da instituição", "Suspende o procedimento; arquivamento após obrigações e evidências; sem confissão", "Cronograma pode incluir manuais, atas, treinamento e auditoria; ANBIMA verifica", "Contribuição educacional não é multa pública", "Procedimento prossegue e aplicam-se regras dos códigos"],
  ]);

  setTable(regulatory[4].tables.items[0], [
    ["Instituição / data", "Preocupação registrada", "Compromissos", "Prazo / verificação", "Pagamento / fonte"],
    ["BRL Trust · 15 jul/24", "Metodologia de PDD e possível transferência de riqueza", "Revisão de método e controles, treinamento, correção e auditoria", "Obrigações precisam ser cumpridas e comprovadas para arquivamento", "Termo ANBIMA"],
    ["Singulare · 17 jul/25", "Falhas na verificação de lastro", "Revisão de procedimentos e manuais, treinamento e auditoria independente", "ANBIMA recebe evidências previstas no termo", "R$ 300 mil · contribuição educacional"],
    ["Vórtx · 13 nov/25", "PDD sem evidência mensal e divergências de preço", "Manuais, três meses de atas, auditoria, reprecificação e correção de sistema", "Parte das obrigações em até 240 dias; comprovação à ANBIMA", "R$ 1,109 mi · contribuição educacional"],
    ["Acordo CVM–ANBIMA · 1S25", "Sobreposição e dispersão de supervisão", "Compartilhamento de informações e aproveitamento do monitoramento autorregulatório", "CVM pode usar evidências da ANBIMA; competências públicas permanecem", "Cinco termos divulgados pela ANBIMA"],
    ["Nomes adicionais pesquisados", "Oliveira Trust, BEM, REAG, Intrag e denominações aproximadas", "Resultados preservados por CNPJ, instrumento e tema; ausência de termo específico não vira conclusão", "Revalidar nome societário, data, obrigação e status de cumprimento", "CVM / ANBIMA · corte 20 ago/26"],
  ]);

  setTable(regulatory[6].tables.items[0], [
    ["Data", "Ato / desdobramento", "Conteúdo", "Efeito e limite observado", "Fonte"],
    ["25 abr/14", "Convênio anterior", "Estrutura inicial de intercâmbio de informações entre BCB e CVM", "Base jurídica e operacional prévia ao novo acordo", "CVM / BCB"],
    ["set/25–13 abr/26", "Negociação e assinatura do ACT", "Uniformiza, qualifica e amplia o compartilhamento; inclui securitizadoras e informações de operações de crédito", "Melhora visão de devedor, endividamento e risco para os supervisores", "Notícia e ACT"],
    ["Desde 2012 / 2026", "FIDCs no SCR e ampliação de uso", "FIDCs já reportavam ao SCR; acordo reforça reporte, consulta e intercâmbio", "Continuidade relevante; novidade está na integração e abrangência", "CVM / BCB"],
    ["Ago/26", "Leitura de implementação", "Plano emergencial prevê processar dados do ACT, cruzar bases e testar lastro", "Benefício é supervisório; o ACT não promete abertura pública de devedores", "CVM · corte 20 ago/26"],
  ]);
  regulatory[5].tables.items[0].cells.set(4, 3, "Processos e notícias em curso foram preservados como pesquisa. Até 20 ago/26, não foi localizada decisão CVM que transforme os achados dos termos ANBIMA de 2024/25 em condenação sancionadora equivalente");
  regulatory[5].tables.items[0].cells.set(4, 4, "CVM, ANBIMA e notícias · corte 20 ago/26");

  const sourcesBySlide = new Map([
    [base, [
      "CVM — novo Informe Mensal, 8 mai. 2024: https://www.gov.br/cvm/pt-br/assuntos/noticias/2024/nova-versao-do-informe-mensal-para-fidc-disponivel-no-sistema-fundos.net",
      "CVM — Dados Abertos de fundos, 30 jan. 2025: https://www.gov.br/cvm/pt-br/assuntos/noticias/2025/portal-dados-abertos-cvm-traz-novidades-nas-informacoes-sobre-fundos-de-investimento",
      "CVM — novidades dos Dados Abertos, Tabela VIII em 13 ago. 2026: https://dados.cvm.gov.br/pages/novidades",
      "CVM/BCB — ACT, 13 abr. 2026: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/cvm-e-banco-central-fortalecem-cooperacao-para-o-aprimoramento-das-informacoes-de-credito-no-pais/",
    ]],
    [base + 1, [
      "ANBIMA — manifestação na consulta pública CVM SDM 07/25: https://conteudo.cvm.gov.br/cvm_institucional/export/sites/cvm/audiencias_publicas/ap_sdm/anexos/2025/sdm0725__ANBIMA.PDF",
      "CVM — plano emergencial: https://www.gov.br/cvm/pt-br/assuntos/noticias/anexos/2026/20260527-plano-emergencial-de-reestruturacao-da-atividade-fiscalizatoria-da-cvm.pdf",
    ]],
    [base + 2, [
      "CVM — plano emergencial, 27 mai. 2026: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/cvm-encaminha-ao-ministerio-da-fazenda-sua-proposta-de-plano-emergencial-de-reestruturacao-da-atividade-fiscalizatoria",
      "CVM — homologação pelo STF, 3 jul. 2026: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/plano-emergencial-de-reestruturacao-da-cvm-e-homologado-pelo-stf-e-reforca-condicoes-para-atuacao-da-autarquia",
    ]],
    [base + 3, [
      "CVM — FAQ de Termo de Compromisso: https://www.gov.br/cvm/pt-br/assuntos/processos/termos-de-compromisso",
      "Lei 6.385/1976: https://www.planalto.gov.br/ccivil_03/leis/l6385compilada.htm",
      "Lei 7.347/1985: https://www.planalto.gov.br/ccivil_03/leis/l7347compilada.htm",
    ]],
    [base + 4, [
      "ANBIMA — Singulare, 17 jul. 2025: https://www.anbima.com.br/pt_br/noticias/confira-os-termos-de-compromisso-firmados-com-instituicoes-que-seguem-os-codigos-anbima-8A2AB2AE97EC651A01981922CDCC3732-00.htm",
      "ANBIMA — BRL Trust, 15 jul. 2024: https://www.anbima.com.br/data/files/73/B4/6B/BF/1604C910CF6A83C9F82BA2A8/TC_-_BRL_Trust_Distribuidora_de_Titulos_e_Valores_Mobiliarios_S_A__-_15_07_2024_-_AGRT_pdf",
      "ANBIMA — Vórtx, 13 nov. 2025: https://www.anbima.com.br/data/files/9C/95/5D/34/9E23C910342903C9BA2BA2A8/TC%20_AGRT0042025_Vorx%20DTVM%20Ltda.pdf",
      "ANBIMA — termos no acordo CVM-ANBIMA, 1S25: https://www.anbima.com.br/pt_br/noticias/anbima-firma-termos-de-compromisso-com-cinco-instituicoes-no-1-semestre-dentro-do-acordo-de-cooperacao-com-a-cvm.htm",
    ]],
    [base + 6, [
      "CVM/BCB — ACT, 13 abr. 2026: https://www.gov.br/cvm/pt-br/assuntos/noticias/2026/cvm-e-banco-central-fortalecem-cooperacao-para-o-aprimoramento-das-informacoes-de-credito-no-pais/",
      "CVM — Informativo do Colegiado sobre o ACT: https://conteudo.cvm.gov.br/cvm_institucional/export/sites/cvm/publicacao/informativos_colegiado/anexos/2026/Informativo01_RC03022026.pdf",
    ]],
  ]);
  const originals = presentation.slides.items;
  for (const [zeroIndex, sources] of sourcesBySlide) addNotes(originals[zeroIndex], sources);
}

function updateAgendaSlide(presentation) {
  replaceText(
    presentation,
    "sh/kv2h4rqp",
    "Deck publicado em Dados da Indústria > Exportações com o rótulo “Estudos de Caso”. O prompt de atualização fica disponível no mesmo bloco.",
    "Arquivo atualizado no artefato usado por Dados da Indústria > Exportações, com o rótulo “Estudos de Caso”. Publicação externa depende de commit, merge e deploy.",
  );
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  const data = JSON.parse(await fs.readFile(DATA, "utf8"));
  const governance = JSON.parse(await fs.readFile(GOVERNANCE_DATA, "utf8"));
  const presentation = await PresentationFile.importPptx(await FileBlob.load(starterPptxPath));
  const originals = [...presentation.slides.items];
  if (![16, 20, 22, 23].includes(originals.length)) throw new Error(`Deck-base deveria ter 16, 20, 22 ou 23 slides; contém ${originals.length}.`);
  if (originals.length === 23) {
    updateCarteira101Existing(presentation, data, originals[9]);
    buildMonocotistaGovernance(presentation, governance, originals[10]);
  } else {
    updateRegulatorySlides(presentation);
    updateAgendaSlide(presentation);
    updateCaseOverviewSlides(presentation);
    if (originals.length === 16) {
      let caseAfter = originals[5];
      caseAfter = buildNexoosCase(presentation, caseAfter);
      buildLightCase(presentation, caseAfter);
      let after = originals[6];
      after = buildCarteira101(presentation, after, data);
      after = buildFinanceiro(presentation, after, data);
      after = buildCarbono(presentation, after);
      buildMaster(presentation, after);
    } else if (originals.length === 20) {
      let caseAfter = originals[5];
      caseAfter = buildNexoosCase(presentation, caseAfter);
      buildLightCase(presentation, caseAfter);
      updateCarteira101Existing(presentation, data, originals[7]);
    }
    buildMonocotistaGovernance(presentation, governance);
  }
  setPageAndCutoff(presentation);

  if (presentation.slides.items.length !== 23) throw new Error(`Deck deveria ter 23 slides; gerou ${presentation.slides.items.length}.`);
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(PREVIEW_DIR, `${stem}.png`), await presentation.export({ slide, format: "png", scale: 1.5 }));
    await fs.writeFile(path.join(PREVIEW_DIR, `${stem}.layout.json`), await (await slide.export({ format: "layout" })).text());
  }
  await writeBlob(path.join(PREVIEW_DIR, "montage.webp"), await presentation.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(OUTPUT);
  console.log(JSON.stringify({ output: OUTPUT, slides: presentation.slides.items.length, previews: PREVIEW_DIR }));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
