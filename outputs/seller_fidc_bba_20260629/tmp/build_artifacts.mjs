import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = "/Users/matheusjprates/fidc/outputs/seller_fidc_bba_20260629";
const DATA = path.join(ROOT, "data");
const OFFICE = path.join(ROOT, "office");
const PREVIEWS = path.join(ROOT, "previews");

const NAVY = "#001E62";
const ORANGE = "#EC7000";
const BLUE = "#4E73DF";
const GREEN = "#00A676";
const TEAL = "#00A3A1";
const RED = "#C00000";
const GRAY = "#6B7280";
const LIGHT = "#F5F6F8";
const MID = "#D9DEE8";
const TEXT = "#172033";
const WHITE = "#FFFFFF";

function parseCSV(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  const header = rows.shift() ?? [];
  return rows
    .filter((r) => r.some((v) => v !== ""))
    .map((r) => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""])));
}

async function loadCSV(name) {
  return parseCSV(await fs.readFile(path.join(DATA, name), "utf8"));
}

function num(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function fmtPt(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "n.d.";
  return Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPct(value) {
  if (value === null || value === undefined || value === "") return "n.d.";
  return (Number(value) * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }) + "%";
}

function colName(index0) {
  let n = index0 + 1;
  let name = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function addr(row0, col0, rowCount, colCount) {
  const start = `${colName(col0)}${row0 + 1}`;
  const end = `${colName(col0 + colCount - 1)}${row0 + rowCount}`;
  return rowCount === 1 && colCount === 1 ? start : `${start}:${end}`;
}

function sheetName(name) {
  return `'${name.replaceAll("'", "''")}'`;
}

function tableRange(sheet, startRow, startCol, headers, rows, tableName) {
  const matrix = [headers, ...rows];
  const rangeRef = addr(startRow, startCol, matrix.length, headers.length);
  sheet.getRange(rangeRef).values = matrix;
  const table = sheet.tables.add(rangeRef, true, tableName);
  table.showFilterButton = true;
  table.showBandedRows = true;
  sheet.getRange(addr(startRow, startCol, 1, headers.length)).format = {
    fill: NAVY,
    font: { color: WHITE, bold: true },
  };
  sheet.getRange(rangeRef).format.borders = { preset: "all", style: "thin", color: MID };
  sheet.getRange(rangeRef).format.wrapText = true;
  return { rangeRef, matrix };
}

function helperRange(sheet, startRow, startCol, matrix) {
  const rangeRef = addr(startRow, startCol, matrix.length, matrix[0].length);
  sheet.getRange(rangeRef).values = matrix;
  sheet.getRange(rangeRef).format = {
    fill: WHITE,
    font: { color: WHITE, size: 1 },
  };
  return rangeRef;
}

function addWorkbookTitle(sheet, title, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange("A1:J1").merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: NAVY,
    font: { color: WHITE, bold: true, size: 16 },
  };
  sheet.getRange("A2:J2").merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format = {
    fill: LIGHT,
    font: { color: GRAY, italic: true, size: 10 },
  };
}

function addRawSheet(workbook, name, rows, tableName) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const headers = Object.keys(rows[0] ?? { vazio: "" });
  const values = rows.map((r) => headers.map((h) => coerceCell(r[h])));
  tableRange(sheet, 0, 0, headers, values, tableName);
  sheet.freezePanes.freezeRows(1);
  sheet.getUsedRange().format.autofitColumns();
  return sheet;
}

function coerceCell(value) {
  if (value === "") return null;
  if (typeof value !== "string") return value;
  if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
  return value;
}

async function saveWorkbook(workbook, filename, renderSheet = "Resumo") {
  await fs.mkdir(OFFICE, { recursive: true });
  await fs.mkdir(PREVIEWS, { recursive: true });
  const preview = await workbook.render({
    sheetName: renderSheet,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(PREVIEWS, filename.replace(/\.xlsx$/, ".png")),
    new Uint8Array(await preview.arrayBuffer()),
  );
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(OFFICE, filename));
}

function setWidths(sheet, widths) {
  widths.forEach((w, i) => {
    sheet.getRange(`${colName(i)}:${colName(i)}`).format.columnWidth = w;
  });
}

async function buildEmissionsWorkbook(data) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Resumo");
  addWorkbookTitle(
    sheet,
    "FIDC Sellers - histórico de emissões",
    "Base: curadoria Toma Conta filtrada para CNPJ 50.473.039/0001-02; valores em R$ mm.",
  );
  const headers = [
    "Série",
    "Classe",
    "Data emissão",
    "Volume emissão (R$ mm)",
    "PU emissão (R$)",
    "BBA principal (R$ mm)",
    "Remuneração",
    "Fonte",
  ];
  const bbaBySeries = new Map([
    ["S3", 150.5],
    ["S5", 750.0],
  ]);
  const rows = data.emissions.map((r) => [
    r.serie_curta,
    r.tipo,
    r.data_emissao_integralizacao || "não disponível",
    fmtPt(r.volume_mm, 1),
    r.pu_emissao_brl ? fmtPt(r.pu_emissao_brl, 2) : "n.d.",
    fmtPt(bbaBySeries.get(r.serie_curta) ?? 0, 1),
    r.remuneracao,
    r.fonte,
  ]);
  tableRange(sheet, 4, 0, headers, rows, "EmissoesResumo");
  setWidths(sheet, [13, 18, 16, 15, 12, 15, 28, 36, 4, 4, 4, 4, 4, 4]);

  const helperRows = [
    ["Série", "Volume emissão", "BBA principal"],
    ...data.emissions.map((r) => [
      r.serie_curta,
      num(r.volume_mm) ?? 0,
      bbaBySeries.get(r.serie_curta) ?? 0,
    ]),
  ];
  const helperRef = helperRange(sheet, 4, 10, helperRows);
  const chart = sheet.charts.add("bar", sheet.getRange(helperRef));
  chart.title = "Emissões do fundo vs posições Itaú BBA (R$ mm)";
  chart.hasLegend = true;
  chart.yAxis = { numberFormatCode: 'R$ #.##0' };
  chart.setPosition("J14", "Q32");
  if (chart.series.items[0]) chart.series.items[0].fill = NAVY;
  if (chart.series.items[1]) chart.series.items[1].fill = ORANGE;

  addRawSheet(workbook, "Dados_emissoes", data.emissions, "EmissoesRaw");
  addRawSheet(workbook, "Inventario", data.inventory, "InventarioRaw");
  addRawSheet(workbook, "Fontes", data.sources, "FontesRaw");
  await saveWorkbook(workbook, "fidc_sellers_emissoes.xlsx");
}

async function buildAmortizationWorkbook(data) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Resumo");
  addWorkbookTitle(
    sheet,
    "FIDC Sellers - cronograma de amortização",
    "Parcelas em percentual do saldo remanescente; valores em R$ mm calculados mecanicamente sobre o volume de emissão.",
  );
  const sched = data.amortization.filter((r) => r.data && r.data !== "não disponível na documentação");
  const headers = ["Data", "Série", "Parcela", "% documental", "Amortização (R$ mm)", "Saldo após (R$ mm)", "Definição", "Fonte"];
  const rows = sched.map((r) => [
    r.data,
    r.serie_curta,
    r.ordem_parcela,
    `${fmtPt(r.percentual_documental, 2)}%`,
    fmtPt(r.amortizacao_principal_mm_calculada, 1),
    fmtPt(r.saldo_apos_mm_calculado, 1),
    r.definicao_parcela,
    r.fonte,
  ]);
  tableRange(sheet, 4, 0, headers, rows, "CronogramaResumo");
  setWidths(sheet, [13, 12, 10, 13, 14, 14, 34, 34]);

  const uniqueDates = [...new Set(sched.map((r) => r.data))].sort((a, b) => {
    const [da, ma, ya] = a.split("/").map(Number);
    const [db, mb, yb] = b.split("/").map(Number);
    return new Date(ya, ma - 1, da) - new Date(yb, mb - 1, db);
  });
  const series = ["S1", "S2", "S5"];
  const pivotHeaders = ["Data", ...series];
  const pivotRows = uniqueDates.map((d) => [
    d,
    ...series.map((s) => {
      const hit = sched.find((r) => r.data === d && r.serie_curta === s);
      return hit ? num(hit.amortizacao_principal_mm_calculada) : 0;
    }),
  ]);
  const helperRef = helperRange(sheet, 4, 10, [pivotHeaders, ...pivotRows]);
  const chart = sheet.charts.add("bar", sheet.getRange(helperRef));
  chart.title = "Amortização programada por série (R$ mm)";
  chart.hasLegend = true;
  chart.yAxis = { numberFormatCode: 'R$ #.##0' };
  chart.setPosition("J16", "Q35");
  [NAVY, BLUE, ORANGE].forEach((color, i) => {
    if (chart.series.items[i]) chart.series.items[i].fill = color;
  });

  const gapRows = data.amortization
    .filter((r) => r.data === "não disponível na documentação")
    .map((r) => [r.serie_curta, r.amortizacao_programada, r.definicao_parcela, r.observacao, r.fonte]);
  tableRange(sheet, 25, 0, ["Série", "Status", "Definição", "Observação", "Fonte"], gapRows, "CronogramaLacunas");
  sheet.getRange(`A27:E${26 + gapRows.length}`).format.fill = "#FFF3E6";

  addRawSheet(workbook, "Dados_cronograma", data.amortization, "CronogramaRaw");
  addRawSheet(workbook, "Dados_emissoes", data.emissions, "EmissoesRaw");
  addRawSheet(workbook, "Fontes", data.sources, "FontesRaw");
  await saveWorkbook(workbook, "fidc_sellers_cronograma_amortizacao.xlsx");
}

async function buildWaterfallWorkbook(data) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Resumo");
  addWorkbookTitle(
    sheet,
    "FIDC Sellers - waterfall da carteira Itaú BBA",
    "Base: risco accruado fixo informado pelo Itaú BBA; S5 cascateada por cronograma documental.",
  );
  const headers = ["Data", "Tranche", "Série", "Amortização/vencimento (R$ mm)", "Saldo antes (R$ mm)", "Saldo após (R$ mm)", "Fonte", "Diligência"];
  const rows = data.waterfall.map((r) => [
    r.data,
    r.tranche,
    r.classe_serie,
    fmtPt(r.amortizacao_vencimento_mm, 1),
    fmtPt(r.saldo_bba_antes_mm, 1),
    fmtPt(r.saldo_bba_apos_mm, 1),
    r.fonte,
    r.diligencia,
  ]);
  tableRange(sheet, 4, 0, headers, rows, "WaterfallResumo");
  setWidths(sheet, [13, 23, 18, 20, 14, 14, 32, 42]);

  const helper = [
    ["Data", "Amortização/vencimento", "Saldo remanescente"],
    ...data.waterfall.map((r) => [r.data, num(r.amortizacao_vencimento_mm), num(r.saldo_bba_apos_mm)]),
  ];
  const helperRef = helperRange(sheet, 4, 10, helper);
  const chart = sheet.charts.add("bar", sheet.getRange(helperRef));
  chart.title = "Cascata de risco accruado Itaú BBA (R$ mm)";
  chart.hasLegend = true;
  chart.yAxis = { numberFormatCode: 'R$ #.##0' };
  chart.setPosition("J13", "Q32");
  if (chart.series.items[0]) chart.series.items[0].fill = ORANGE;
  if (chart.series.items[1]) chart.series.items[1].fill = NAVY;

  const recRows = data.reconciliation.map((r) => [
    r.data_encarteiramento,
    r.emissao_reconciliada,
    fmtPt(r.montante_principal_mm, 1),
    fmtPt(r.risco_accruado_mm, 1),
    r.vencimento_insumo_bba,
    r.status,
    r.diligencia,
  ]);
  tableRange(
    sheet,
    25,
    0,
    ["Encarteiramento", "Emissão", "Principal (R$ mm)", "Risco accruado (R$ mm)", "Vencimento BBA", "Status", "Diligência"],
    recRows,
    "ReconciliacaoResumo",
  );

  addRawSheet(workbook, "Dados_waterfall", data.waterfall, "WaterfallRaw");
  addRawSheet(workbook, "Reconciliacao", data.reconciliation, "ReconciliacaoRaw");
  addRawSheet(workbook, "Fontes", data.sources, "FontesRaw");
  await saveWorkbook(workbook, "fidc_sellers_waterfall_itau_bba.xlsx");
}

async function buildFundFullWaterfallWorkbook(data) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Resumo");
  addWorkbookTitle(
    sheet,
    "FIDC Sellers - waterfall do fundo inteiro",
    "Base: PL e saldos por cota do IME 03/2026; residual de PL pago no vencimento final, sem projeção de accrual futuro.",
  );
  const headers = [
    "Data",
    "Evento",
    "Série",
    "Senior (R$ mm)",
    "PL residual (R$ mm)",
    "Pagamento total (R$ mm)",
    "Saldo após (R$ mm)",
    "Status documental",
  ];
  const rows = data.fundFullWaterfall.map((r) => [
    r.data_evento,
    r.tipo_evento,
    r.serie_curta,
    fmtPt(r.pagamento_senior_mm, 1),
    fmtPt(r.pagamento_pl_residual_mm, 1),
    fmtPt(r.pagamento_total_mm, 1),
    fmtPt(r.saldo_apos_mm, 1),
    r.status_documental,
  ]);
  tableRange(sheet, 4, 0, headers, rows, "WaterfallFundoResumo");
  setWidths(sheet, [20, 30, 16, 16, 18, 20, 18, 42]);

  const helper = [
    ["Data", "Pagamento senior", "Pagamento PL residual", "Saldo após"],
    ...data.fundFullWaterfall.map((r) => [
      r.data_evento,
      num(r.pagamento_senior_mm),
      num(r.pagamento_pl_residual_mm),
      num(r.saldo_apos_mm),
    ]),
  ];
  const helperRef = helperRange(sheet, 4, 10, helper);
  const chart = sheet.charts.add("bar", sheet.getRange(helperRef));
  chart.title = "Waterfall do PL atual do fundo (R$ mm)";
  chart.hasLegend = true;
  chart.yAxis = { numberFormatCode: 'R$ #.##0' };
  chart.setPosition("J14", "Q35");
  if (chart.series.items[0]) chart.series.items[0].fill = NAVY;
  if (chart.series.items[1]) chart.series.items[1].fill = GREEN;
  if (chart.series.items[2]) chart.series.items[2].fill = GRAY;

  const positionHeaders = ["Competência", "Série econômica", "Série IME", "Saldo atual", "Vencimento-base", "Status"];
  const positionRows = data.fundPosition.map((r) => [
    r.competencia_base,
    r.serie_curta,
    r.classe_reportada_no_ime,
    fmtPt(r.saldo_atual_mm, 1),
    r.vencimento_base,
    r.status_documental,
  ]);
  tableRange(sheet, 19, 0, positionHeaders, positionRows, "PosicaoAtualFundo");

  addRawSheet(workbook, "Waterfall_fundo", data.fundFullWaterfall, "WaterfallFundoRaw");
  addRawSheet(workbook, "Posicao_atual", data.fundPosition, "PosicaoAtualRaw");
  addRawSheet(workbook, "IME_VNU", data.vnu, "VnuRaw");
  addRawSheet(workbook, "Fontes", data.sources, "FontesRaw");
  await saveWorkbook(workbook, "fidc_sellers_waterfall_fundo_atual.xlsx");
}

async function buildValidationWorkbook(data) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Resumo");
  addWorkbookTitle(
    sheet,
    "FIDC Sellers - validação de juros e amortização",
    "Conciliação entre documentos de emissão, curadoria e informes mensais estruturados.",
  );
  const headers = ["Evento", "Data", "Séries", "Status", "Divergência", "Fonte"];
  const rows = data.payment.map((r) => [
    r.evento,
    r.data_documental,
    r.series_afetadas,
    r.status_validacao,
    r.divergencia,
    r.fonte,
  ]);
  tableRange(sheet, 4, 0, headers, rows, "ValidacaoResumo");
  setWidths(sheet, [34, 16, 20, 36, 44, 32]);

  const vnu = data.vnu.filter((r) => ["1", "2", "5"].includes(String(r.indice_lista)));
  const months = [...new Set(vnu.map((r) => r.competencia))].sort((a, b) => {
    const [ma, ya] = a.split("/").map(Number);
    const [mb, yb] = b.split("/").map(Number);
    return new Date(ya, ma - 1, 1) - new Date(yb, mb - 1, 1);
  });
  const idxs = [
    ["Série 1 / índice 1", 1],
    ["Série 2 / índice 2", 2],
    ["Série 5 / índice 5", 5],
  ];
  const helperHeaders = ["Competência", ...idxs.map((x) => x[0])];
  const helperRows = months.map((m) => [
    m,
    ...idxs.map(([, idx]) => {
      const hit = vnu.find((r) => r.competencia === m && Number(r.indice_lista) === idx);
      return hit ? num(hit.vnu_brl) : null;
    }),
  ]);
  const helperRef = helperRange(sheet, 4, 8, [helperHeaders, ...helperRows]);
  const chart = sheet.charts.add("line", sheet.getRange(helperRef));
  chart.title = "VNU reportado nos informes mensais (R$)";
  chart.hasLegend = true;
  chart.yAxis = { numberFormatCode: 'R$ #.##0' };
  chart.setPosition("H19", "O37");
  [NAVY, BLUE, ORANGE].forEach((color, i) => {
    if (chart.series.items[i]) chart.series.items[i].line = { style: "solid", fill: color, width: 2 };
  });

  addRawSheet(workbook, "Dados_validacao", data.payment, "ValidacaoRaw");
  addRawSheet(workbook, "IME_VNU", data.vnu, "VnuRaw");
  addRawSheet(workbook, "Fontes", data.sources, "FontesRaw");
  await saveWorkbook(workbook, "fidc_sellers_validacao_pagamentos.xlsx");
}

function addText(slide, text, left, top, width, height, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left, top, width, height },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: style.fontSize ?? 16,
    bold: style.bold ?? false,
    color: style.color ?? TEXT,
  };
  return shape;
}

function addBand(slide, title, kicker = "FIDC Sellers | Itaú BBA") {
  slide.background.fill = "#F7F8FA";
  slide.shapes.add({
    geometry: "rect",
    position: { left: 0, top: 0, width: 1280, height: 60 },
    fill: NAVY,
    line: { style: "solid", fill: NAVY, width: 0 },
  });
  addText(slide, kicker, 54, 18, 320, 20, { fontSize: 11, bold: true, color: WHITE });
  addText(slide, title, 54, 76, 820, 44, { fontSize: 26, bold: true, color: NAVY });
  slide.shapes.add({
    geometry: "rect",
    position: { left: 54, top: 125, width: 90, height: 5 },
    fill: ORANGE,
    line: { style: "solid", fill: ORANGE, width: 0 },
  });
}

function addFoot(slide, source) {
  addText(slide, source, 54, 690, 980, 18, { fontSize: 8, color: GRAY });
  addText(slide, "Confidencial", 1160, 690, 80, 18, { fontSize: 8, color: GRAY });
}

function addPptTable(slide, left, top, width, height, headers, rows, widths = null) {
  const table = slide.tables.add({
    rows: rows.length + 1,
    columns: headers.length,
    left,
    top,
    width,
    height,
    values: [headers, ...rows],
  });
  table.styleOptions = { headerRow: true, bandedRows: true };
  table.borders.assign({ style: "solid", fill: "#D7DCE5", width: 0.75 });
  for (let c = 0; c < headers.length; c++) {
    const cell = table.getCell(0, c);
    cell.fill = NAVY;
    cell.text.style = { fontSize: 9, bold: true, color: WHITE };
    if (widths?.[c]) table.columns.get(c).width = widths[c];
  }
  for (let r = 1; r <= rows.length; r++) {
    for (let c = 0; c < headers.length; c++) {
      const cell = table.getCell(r, c);
      cell.text.style = { fontSize: 8.2, color: TEXT };
      cell.fill = r % 2 === 0 ? WHITE : "#FAFBFC";
    }
  }
  return table;
}

function addCallout(slide, left, top, width, height, title, body, fill = "#FFF3E6") {
  slide.shapes.add({
    geometry: "rect",
    position: { left, top, width, height },
    fill,
    line: { style: "solid", fill: ORANGE, width: 1.2 },
  });
  addText(slide, title, left + 16, top + 12, width - 32, 20, { fontSize: 11, bold: true, color: NAVY });
  addText(slide, body, left + 16, top + 38, width - 32, height - 48, { fontSize: 10, color: TEXT });
}

async function buildDeck(data) {
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

  {
    const slide = presentation.slides.add();
    slide.background.fill = "#F7F8FA";
    slide.shapes.add({
      geometry: "rect",
      position: { left: 0, top: 0, width: 1280, height: 720 },
      fill: "#F7F8FA",
      line: { style: "solid", fill: "#F7F8FA", width: 0 },
    });
    slide.shapes.add({
      geometry: "rect",
      position: { left: 0, top: 0, width: 1280, height: 72 },
      fill: NAVY,
      line: { style: "solid", fill: NAVY, width: 0 },
    });
    addText(slide, "FIDC Sellers", 70, 150, 520, 54, { fontSize: 42, bold: true, color: NAVY });
    addText(slide, "Material de crédito | dados estruturais e fluxo de cotas", 70, 220, 700, 34, {
      fontSize: 18,
      color: TEXT,
    });
    addText(slide, "CNPJ 50.473.039/0001-02 | foco exclusivo no fundo Seller FIDC", 70, 260, 720, 26, {
      fontSize: 13,
      color: GRAY,
    });
    const kpis = [
      ["Documentos inventariados", "44"],
      ["PDFs locais", "21"],
      ["Emissões/séries curadas", "6"],
      ["Risco BBA accruado", "R$ 912,5 mm"],
    ];
    kpis.forEach((k, i) => {
      const x = 70 + i * 285;
      slide.shapes.add({
        geometry: "rect",
        position: { left: x, top: 400, width: 238, height: 110 },
        fill: WHITE,
        line: { style: "solid", fill: "#D7DCE5", width: 1 },
      });
      addText(slide, k[1], x + 18, 425, 200, 34, { fontSize: 24, bold: true, color: i === 3 ? ORANGE : NAVY });
      addText(slide, k[0], x + 18, 468, 190, 30, { fontSize: 11, color: GRAY });
    });
    addFoot(slide, "Fonte: curadoria Toma Conta, documentos CVM locais e insumo fixo Itaú BBA.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Cobertura documental e curadoria utilizada");
    slide.charts.add("bar", {
      position: { left: 70, top: 170, width: 430, height: 250 },
      categories: ["PDF local", "Sem PDF local"],
      series: [{ name: "Documentos", values: [21, 23], fill: NAVY, points: [{ idx: 0, fill: ORANGE }] }],
      hasLegend: false,
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fontSize: 11, fill: TEXT, bold: true } },
      yAxis: { majorGridlines: { style: "solid", fill: "#E7EAF0", width: 1 } },
    });
    addPptTable(
      slide,
      560,
      160,
      650,
      220,
      ["Base", "Cobertura"],
      [
        ["Inventário regulatório", "44 documentos para o CNPJ; 21 PDFs locais; 1.047 páginas locais."],
        ["Curadoria Toma Conta", "Emissões, cronogramas, critérios e evidências já consolidados foram reaproveitados."],
        ["Informes mensais", "IME 02/2025 a 03/2026 usado para VNU, quantidade de cotas e validação de eventos."],
      ],
      [180, 470],
    );
    addCallout(
      slide,
      70,
      470,
      1140,
      92,
      "Limite da base local",
      "Informes trimestrais, ratings e demonstrações financeiras aparecem no inventário, mas sem PDF local. Para as séries 3 e 4 de 2023, a ata remete a suplemento específico que não está disponível nos PDFs baixados.",
    );
    addFoot(slide, "Fonte: document_inventory.csv, document_coverage.csv, regulatory_knowledge/50473039000102.json.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Histórico de emissões");
    const categories = data.emissions.map((r) => r.serie_curta);
    const volume = data.emissions.map((r) => num(r.volume_mm) ?? 0);
    const bba = data.emissions.map((r) => (r.serie_curta === "S3" ? 150.5 : r.serie_curta === "S5" ? 750.0 : 0));
    slide.charts.add("bar", {
      position: { left: 70, top: 160, width: 560, height: 310 },
      categories,
      series: [
        { name: "Volume emissão", values: volume, fill: NAVY },
        { name: "Itaú BBA encarteirado", values: bba, fill: ORANGE },
      ],
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fontSize: 10, fill: TEXT } },
      yAxis: { numberFormatCode: 'R$ #.##0', majorGridlines: { style: "solid", fill: "#E7EAF0", width: 1 } },
    });
    addPptTable(
      slide,
      670,
      150,
      540,
      370,
      ["Série", "Emissão", "Volume", "Remuneração"],
      data.emissions.map((r) => [
        r.serie_curta,
        r.data_emissao_integralizacao || "n.d.",
        `R$ ${fmtPt(r.volume_mm)} mm`,
        String(r.remuneracao).replace("Não identificada nos PDFs baixados", "n.d."),
      ]),
      [70, 90, 100, 280],
    );
    addFoot(slide, "Fonte: emissions_clean.csv; 467929, 558803/559856, 909546/912093/912172/932137.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Cronograma de amortização");
    const sched = data.amortization.filter((r) => r.data && r.data !== "não disponível na documentação");
    const dates = [...new Set(sched.map((r) => r.data))];
    const series = ["S1", "S2", "S5"];
    slide.charts.add("bar", {
      position: { left: 70, top: 160, width: 760, height: 310 },
      categories: dates,
      series: series.map((s, i) => ({
        name: s,
        values: dates.map((d) => {
          const hit = sched.find((r) => r.data === d && r.serie_curta === s);
          return hit ? num(hit.amortizacao_principal_mm_calculada) : 0;
        }),
        fill: [NAVY, BLUE, ORANGE][i],
      })),
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fontSize: 10, fill: TEXT } },
      yAxis: { numberFormatCode: 'R$ #.##0', majorGridlines: { style: "solid", fill: "#E7EAF0", width: 1 } },
    });
    addCallout(
      slide,
      875,
      172,
      330,
      170,
      "Natureza das parcelas",
      "S1, S2 e S5 têm amortização programada por percentual do saldo de principal remanescente. S3/S4 não têm cronograma local disponível; subordinada júnior é residual/condicionada.",
      "#FFFFFF",
    );
    addPptTable(
      slide,
      70,
      510,
      1135,
      100,
      ["Série", "Status do cronograma", "Fonte"],
      [
        ["S1/S2", "Programado, em percentuais do saldo remanescente.", "467929 pp.115-120"],
        ["S3/S4", "Não disponível na documentação local; ata remete a suplemento não baixado.", "558803 pp.4-5; 559856 pp.1-2"],
        ["S5", "Programado de 15/12/2027 a 15/05/2028.", "912093 pp.3-5"],
      ],
      [100, 650, 385],
    );
    addFoot(slide, "Fonte: amortization_schedule.csv.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Reconcilição das posições Itaú BBA");
    addPptTable(
      slide,
      70,
      155,
      1140,
      205,
      ["Data", "Risco", "Emissão", "Participação", "Status"],
      data.reconciliation.map((r) => [
        r.data_encarteiramento,
        `R$ ${fmtPt(r.risco_accruado_mm)} mm`,
        r.emissao_reconciliada,
        fmtPct(r.participacao_bba_sobre_emissao),
        r.status,
      ]),
      [120, 130, 230, 130, 530],
    );
    addCallout(
      slide,
      70,
      410,
      540,
      115,
      "Tranche 23/11/2023",
      "Reconciliada à Sênior 3ª série por data e volume; o vencimento 15/09/2026 é do insumo BBA e não foi confirmado nos PDFs locais.",
    );
    addCallout(
      slide,
      670,
      410,
      540,
      115,
      "Tranche 26/05/2025",
      "Reconciliada à Sênior 5ª série. Documento 912093 traz amortização final em 15/05/2028, divergente do vencimento BBA 26/05/2028.",
    );
    addFoot(slide, "Fonte: bba_reconciliation.csv; insumo fixo Itaú BBA; documentos 558803/559856 e 912093.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Waterfall da carteira Itaú BBA por risco accruado");
    slide.charts.add("bar", {
      position: { left: 70, top: 155, width: 760, height: 350 },
      categories: data.waterfall.map((r) => r.data),
      series: [
        {
          name: "Amortização/vencimento",
          values: data.waterfall.map((r) => num(r.amortizacao_vencimento_mm)),
          fill: ORANGE,
        },
        {
          name: "Saldo remanescente",
          values: data.waterfall.map((r) => num(r.saldo_bba_apos_mm)),
          fill: NAVY,
        },
      ],
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fontSize: 9, fill: TEXT } },
      yAxis: { numberFormatCode: 'R$ #.##0', majorGridlines: { style: "solid", fill: "#E7EAF0", width: 1 } },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fontSize: 9, fill: TEXT } },
    });
    addPptTable(
      slide,
      870,
      155,
      335,
      350,
      ["Data", "Amort.", "Saldo após"],
      data.waterfall.map((r) => [r.data, `R$ ${fmtPt(r.amortizacao_vencimento_mm)} mm`, `R$ ${fmtPt(r.saldo_bba_apos_mm)} mm`]),
      [82, 126, 126],
    );
    addCallout(
      slide,
      70,
      540,
      1135,
      70,
      "Base da cascata",
      "A cascata usa risco accruado: R$ 150,5 mm na tranche 2023 e R$ 762,0 mm na tranche 2025. A Sênior 5ª série foi amortizada pelos percentuais documentais, com saldo final documental em 15/05/2028.",
      "#FFFFFF",
    );
    addFoot(slide, "Fonte: bba_waterfall.csv; 912093 pp.3-5; insumo fixo Itaú BBA.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Waterfall do fundo inteiro pela posição atual");
    slide.charts.add("bar", {
      position: { left: 70, top: 150, width: 740, height: 345 },
      categories: data.fundFullWaterfall.map((r) => r.data_evento),
      series: [
        {
          name: "Pagamento senior",
          values: data.fundFullWaterfall.map((r) => num(r.pagamento_senior_mm)),
          fill: NAVY,
        },
        {
          name: "Pagamento PL residual",
          values: data.fundFullWaterfall.map((r) => num(r.pagamento_pl_residual_mm)),
          fill: GREEN,
        },
        {
          name: "Saldo após",
          values: data.fundFullWaterfall.map((r) => num(r.saldo_apos_mm)),
          fill: GRAY,
        },
      ],
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fontSize: 9, fill: TEXT } },
      yAxis: { numberFormatCode: 'R$ #.##0', majorGridlines: { style: "solid", fill: "#E7EAF0", width: 1 } },
    });
    addPptTable(
      slide,
      850,
      150,
      360,
      345,
      ["Data", "Série", "Pgto.", "Saldo"],
      data.fundFullWaterfall.map((r) => [
        r.data_evento,
        r.serie_curta,
        `R$ ${fmtPt(r.pagamento_total_mm)} mm`,
        `R$ ${fmtPt(r.saldo_apos_mm)} mm`,
      ]),
      [98, 82, 92, 88],
    );
    const plRow = data.fundPosition.find((r) => r.serie_curta === "PL residual");
    addCallout(
      slide,
      70,
      530,
      1140,
      78,
      "Leitura da data final",
      `Na última data documental da S5, 15/05/2028, sobra o PL residual de R$ ${fmtPt(plRow?.saldo_atual_mm)} mm; por premissa, esse valor é pago como residual/subordinada júnior na própria data final. A S4 tem apenas mês de vencimento disponível externamente, sem dia confirmado nos PDFs locais.`,
      "#FFFFFF",
    );
    addFoot(slide, "Fonte: fund_full_waterfall.csv; IME 1162826 competência 03/2026; 467929; 912093; MercadoLibre Form 10-Q 1T26.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Validação de juros e amortizações realizadas");
    const statusCounts = data.payment.reduce((acc, r) => {
      const key = r.status_validacao.startsWith("Consistente")
        ? "Consistente"
        : r.status_validacao.startsWith("Não vencido")
          ? "Não vencido"
          : "Parcial";
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    slide.charts.add("doughnut", {
      position: { left: 70, top: 165, width: 335, height: 250 },
      categories: Object.keys(statusCounts),
      series: [{ name: "Eventos", values: Object.values(statusCounts), points: [{ idx: 0, fill: GREEN }, { idx: 1, fill: BLUE }, { idx: 2, fill: ORANGE }] }],
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fontSize: 9, fill: TEXT } },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fontSize: 9, fill: TEXT } },
    });
    addPptTable(
      slide,
      450,
      155,
      760,
      370,
      ["Evento", "Data", "Status", "Divergência"],
      data.payment.map((r) => [r.evento, r.data_documental, r.status_validacao, r.divergencia]),
      [210, 100, 240, 210],
    );
    addCallout(
      slide,
      70,
      520,
      335,
      80,
      "Leitura da validação",
      "O valor exato de caixa não está disponível nos campos oficiais do IME; a consistência foi validada por VNU e cronograma documental.",
      "#FFFFFF",
    );
    addFoot(slide, "Fonte: payment_validation.csv; IME 02/2025-03/2026; documentos de emissão.");
  }

  {
    const slide = presentation.slides.add();
    addBand(slide, "Diligências abertas e pontos para comitê");
    addPptTable(
      slide,
      70,
      155,
      1140,
      360,
      ["Tema", "Ponto", "Impacto no material"],
      [
        ["Séries 3/4 2023", "Suplemento/calendário específico não disponível nos PDFs locais.", "Vencimento BBA 15/09/2026 mantido como insumo fixo, com confirmação documental pendente."],
        ["Série 5 2025", "Vencimento BBA 26/05/2028 diverge da amortização final documentada em 15/05/2028.", "Waterfall usa cronograma documental e sinaliza a divergência."],
        ["Pagamentos realizados", "Campos CAPTA_RESGA_AMORTI do IME vieram zerados.", "Valores exatos de caixa marcados como não disponíveis; validação por VNU e cronograma."],
        ["Relatórios sem PDF local", "Informes trimestrais, ratings e DFs constam no inventário sem arquivo local.", "Não usados para números estruturais sem validação documental adicional."],
      ],
      [180, 570, 390],
    );
    addText(slide, "Entregáveis gerados", 70, 555, 220, 22, { fontSize: 14, bold: true, color: NAVY });
    addText(
      slide,
      "5 Excels editáveis por tema + deck PowerPoint com gráficos nativos; waterfall BBA em laranja e waterfall do fundo inteiro com PL residual.",
      70,
      585,
      900,
      26,
      { fontSize: 12, color: TEXT },
    );
    addFoot(slide, "Fonte: metadata.json e arquivos de suporte gerados.");
  }

  await fs.mkdir(OFFICE, { recursive: true });
  await fs.mkdir(PREVIEWS, { recursive: true });
  for (const [index, slide] of presentation.slides.items.entries()) {
    const png = await presentation.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(path.join(PREVIEWS, `deck_slide_${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(PREVIEWS, `deck_slide_${String(index + 1).padStart(2, "0")}.layout.json`), await layout.text());
  }
  const montage = await presentation.export({ format: "webp", montage: true, scale: 1 });
  await fs.writeFile(path.join(PREVIEWS, "fidc_sellers_itau_bba_credit_material_montage.webp"), new Uint8Array(await montage.arrayBuffer()));
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(path.join(OFFICE, "fidc_sellers_itau_bba_credit_material.pptx"));
}

async function main() {
  await fs.mkdir(OFFICE, { recursive: true });
  await fs.mkdir(PREVIEWS, { recursive: true });
  const data = {
    emissions: await loadCSV("emissions_clean.csv"),
    amortization: await loadCSV("amortization_schedule.csv"),
    waterfall: await loadCSV("bba_waterfall.csv"),
    fundPosition: await loadCSV("fund_current_position.csv"),
    fundFullWaterfall: await loadCSV("fund_full_waterfall.csv"),
    reconciliation: await loadCSV("bba_reconciliation.csv"),
    payment: await loadCSV("payment_validation.csv"),
    vnu: await loadCSV("ime_series_vnu.csv"),
    inventory: await loadCSV("document_inventory.csv"),
    coverage: await loadCSV("document_coverage.csv"),
    sources: await loadCSV("sources.csv"),
  };
  await buildEmissionsWorkbook(data);
  await buildAmortizationWorkbook(data);
  await buildWaterfallWorkbook(data);
  await buildFundFullWaterfallWorkbook(data);
  await buildValidationWorkbook(data);
  await buildDeck(data);
  await fs.writeFile(path.join(ROOT, "office_manifest.json"), JSON.stringify({
    files: [
      "office/fidc_sellers_emissoes.xlsx",
      "office/fidc_sellers_cronograma_amortizacao.xlsx",
      "office/fidc_sellers_waterfall_itau_bba.xlsx",
      "office/fidc_sellers_waterfall_fundo_atual.xlsx",
      "office/fidc_sellers_validacao_pagamentos.xlsx",
      "office/fidc_sellers_itau_bba_credit_material.pptx",
    ],
    previews: "previews/",
    generatedAt: new Date().toISOString(),
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
