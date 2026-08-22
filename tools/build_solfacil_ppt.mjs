import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "..");
const DATA_DIR = path.join(ROOT, "data", "solfacil");
const OUTPUT_DIR = path.join(ROOT, "outputs", "solfacil");
const OUTPUT = path.join(OUTPUT_DIR, "Solfacil_CRI_FIDC_20260822.pptx");
const SLIDE_COUNT = 16;

const COLOR = {
  orange: "#E46C0A",
  black: "#171717",
  blackPure: "#000000",
  darkGray: "#3C3C3C",
  gray: "#707070",
  midGray: "#A6A6A6",
  lightGray: "#D7D7D7",
  paleGray: "#F2F2F2",
  nearWhite: "#FAFAFA",
  white: "#FFFFFF",
};

const FONT = { title: 35, subtitle: 20, body: 16, small: 14, cover: 52 };
const LAYER_ORDER = ["Super Sênior", "Sênior", "Mezanino", "Subordinada/Júnior"];
const LAYER_COLORS = [COLOR.orange, COLOR.black, COLOR.gray, COLOR.midGray];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const nonEmpty = rows.filter((values) => values.some((value) => value !== ""));
  if (nonEmpty.length && nonEmpty[0].length) nonEmpty[0][0] = nonEmpty[0][0].replace(/^\uFEFF/, "");
  return nonEmpty;
}

async function readCsv(name) {
  const matrix = parseCsv(await fs.readFile(path.join(DATA_DIR, name), "utf8"));
  if (!matrix.length) return [];
  const [headers, ...body] = matrix;
  return body.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function cleanText(value) {
  return String(value ?? "")
    .replace(/→/g, " para ")
    .replace(/←/g, " desde ")
    .replace(/↔/g, " e ")
    .replace(/-{1}>/g, " para ")
    .replace(/\s+/g, " ")
    .trim();
}

function shorten(value, limit = 58) {
  const text = cleanText(value);
  return text.length <= limit ? text : `${text.slice(0, Math.max(1, limit - 1)).trimEnd()}…`;
}

function numberOrNull(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (!text || text.toLowerCase() === "n/d") return null;
  const parsed = Number(text.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function formatNumber(value, digits = 0) {
  const numeric = numberOrNull(value);
  if (numeric === null) return "n/d";
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(numeric);
}

function formatMetric(row) {
  const value = numberOrNull(row?.valor);
  if (value === null) return "n/d";
  if (row.unidade === "R$ mi") return `R$ ${formatNumber(value, value >= 100 ? 0 : 1)} mi`;
  return `${formatNumber(value, Number.isInteger(value) ? 0 : 1)} ${cleanText(row.unidade)}`.trim();
}

function formatMi(value, digits = 1) {
  const numeric = numberOrNull(value);
  return numeric === null ? "n/d" : `R$ ${formatNumber(numeric, digits)} mi`;
}

function formatPct(value, digits = 1) {
  const numeric = numberOrNull(value);
  return numeric === null ? "n/d" : `${formatNumber(numeric * 100, digits)}%`;
}

function formatMonths(value) {
  const numeric = numberOrNull(value);
  return numeric === null ? "n/d" : `${formatNumber(numeric, 1)} meses`;
}

function formatCurrencyCompact(value) {
  const numeric = numberOrNull(value);
  if (numeric === null) return "n/d";
  if (Math.abs(numeric) >= 1_000_000) return `R$ ${formatNumber(numeric / 1_000_000, 1)} mi`;
  if (Math.abs(numeric) >= 1_000) return `R$ ${formatNumber(numeric / 1_000, 0)} mil`;
  return `R$ ${formatNumber(numeric, 0)}`;
}

function formatDate(value) {
  const text = String(value ?? "");
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : cleanText(text || "n/d");
}

function formatMonthLabel(value) {
  const match = /^(\d{4})-(\d{2})/.exec(String(value ?? ""));
  if (!match) return cleanText(value);
  const labels = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${labels[Number(match[2]) - 1]}/${match[1].slice(-2)}`;
}

function splitSourceIds(value) {
  return String(value ?? "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
}

function sourceIdsFromRows(rows) {
  const ids = [];
  for (const row of rows) {
    for (const sourceId of splitSourceIds(row?.fonte_id)) {
      if (!ids.includes(sourceId)) ids.push(sourceId);
    }
  }
  return ids;
}

function dateBasesFromRows(rows) {
  const values = [];
  for (const row of rows) {
    const value = String(row?.data_base ?? row?.competencia ?? "").trim();
    for (const date of value.match(/\d{4}-\d{2}-\d{2}/g) ?? []) {
      if (!values.includes(date)) values.push(date);
    }
  }
  return values.sort();
}

function footerDate(rows, sourceCatalog) {
  let dates = dateBasesFromRows(rows);
  if (!dates.length && sourceCatalog) {
    dates = sourceIdsFromRows(rows)
      .flatMap((sourceId) => String(sourceCatalog.get(sourceId)?.data_base ?? "").match(/\d{4}-\d{2}-\d{2}/g) ?? [])
      .filter((value, index, values) => values.indexOf(value) === index)
      .sort();
  }
  if (!dates.length) return "n/d";
  if (dates.length === 1) return dates[0];
  return `${dates[0]} a ${dates[dates.length - 1]}`;
}

function shortVehicle(value) {
  const aliases = {
    FIDC_I: "FIDC I",
    FIDC_II: "FIDC II",
    FIDC_III: "FIDC III",
    FIDC_IV: "FIDC IV",
    FIDC_V: "FIDC V",
    FIDC_VI: "FIDC VI",
    FIDC_VII: "FIDC VII",
    CRI_K1: "CRI K1",
    CRI_K2: "CRI K2",
    CRI_K3: "CRI K3",
    CRI_K4: "CRI K4",
    CRI_V174: "VERT 174",
    CRI_V177: "VERT 177",
  };
  return aliases[value] ?? cleanText(value);
}

function canonicalLayer(value) {
  const text = cleanText(value).toLowerCase();
  if (text.includes("super")) return "Super Sênior";
  if (text.includes("sênior") || text.includes("senior")) return "Sênior";
  if (text.includes("mezan")) return "Mezanino";
  return "Subordinada/Júnior";
}

function addText(slide, text, position, style = {}, name = undefined) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = cleanText(text);
  shape.text.style = {
    fontSize: style.fontSize ?? FONT.body,
    bold: style.bold ?? false,
    color: style.color ?? COLOR.black,
    alignment: style.alignment ?? "left",
  };
  return shape;
}

function addRect(slide, position, fill = COLOR.white, lineFill = COLOR.lightGray, lineWidth = 1, name = undefined) {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position,
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
  });
}

function addRule(slide, left, top, width, color = COLOR.lightGray, weight = 1) {
  return slide.shapes.add({
    geometry: "line",
    position: { left, top, width, height: 1 },
    fill: "none",
    line: { style: "solid", fill: color, width: weight },
  });
}

function addHeader(slide, title, section) {
  addText(
    slide,
    title,
    { left: 60, top: 54, width: 1160, height: 54 },
    { fontSize: FONT.title, bold: true, color: COLOR.black },
    `title-${section}`,
  );
  addRule(slide, 60, 119, 1160, COLOR.black, 1);
}

function footerSourceLabel(ids) {
  if (!ids.length) return "n/d";
  if (ids.length <= 2) return ids.join("; ");
  return `${ids.slice(0, 2).join("; ")} +${ids.length - 2}`;
}

function addFooter(slide, slideNumber, rows, sourceCatalog) {
  const ids = sourceIdsFromRows(rows);
  addRule(slide, 60, 666, 1160, COLOR.lightGray, 1);
  addText(
    slide,
    `Data-base: ${footerDate(rows, sourceCatalog)} | Fonte: ${footerSourceLabel(ids)}`,
    { left: 60, top: 674, width: 1050, height: 22 },
    { fontSize: FONT.small, color: COLOR.gray },
  );
  addText(
    slide,
    `${slideNumber}/${SLIDE_COUNT}`,
    { left: 1130, top: 674, width: 90, height: 22 },
    { fontSize: FONT.small, color: COLOR.gray, alignment: "right" },
  );
}

function addSpeakerSources(slide, rows, sourceCatalog, method) {
  const ids = sourceIdsFromRows(rows);
  const lines = ["[Sources]"];
  if (!ids.length) lines.push("- n/d");
  for (const id of ids) {
    const source = sourceCatalog.get(id);
    if (source) {
      const locator = [source.documento, source.url_ou_caminho, source.trecho_ou_pagina]
        .map(cleanText)
        .filter(Boolean)
        .join(" | ");
      lines.push(`- ${id} | ${locator}`);
    } else {
      lines.push(`- ${id} | fonte_id sem linha correspondente em 17_fontes.csv`);
    }
  }
  lines.push("", "[Method]", `- ${cleanText(method)}`);
  slide.speakerNotes.textFrame.setText(lines.join("\n"));
  slide.speakerNotes.setVisible(true);
}

function addNativeTable(slide, values, options = {}) {
  const safeValues = values.map((row) => row.map((value) => cleanText(value)));
  const table = slide.tables.add({
    rows: safeValues.length,
    columns: safeValues[0].length,
    left: options.left,
    top: options.top,
    width: options.width,
    height: options.height,
    values: safeValues,
    columnWidths: options.columnWidths,
  });
  table.styleOptions = { headerRow: true, bandedRows: false };
  table.borders.assign({ style: "solid", fill: COLOR.lightGray, width: 1 });
  const header = table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: safeValues[0].length });
  header.assign({
    fill: options.headerFill ?? COLOR.black,
    textStyle: { fontSize: options.headerFontSize ?? FONT.body, bold: true, color: COLOR.white },
    borders: { style: "solid", fill: options.headerFill ?? COLOR.black, width: 1 },
  });
  if (safeValues.length > 1) {
    const body = table.cells.block({ row: 1, column: 0, rowCount: safeValues.length - 1, columnCount: safeValues[0].length });
    body.assign({
      fill: COLOR.white,
      textStyle: { fontSize: options.bodyFontSize ?? FONT.body, color: COLOR.black },
      borders: { style: "solid", fill: COLOR.lightGray, width: 1 },
    });
  }
  for (let row = 0; row < safeValues.length; row += 1) {
    if (table.rows[row]) table.rows[row].height = options.rowHeight ?? options.height / safeValues.length;
    if (row > 0 && row % 2 === 0) {
      table.cells.block({ row, column: 0, rowCount: 1, columnCount: safeValues[0].length }).fill = COLOR.paleGray;
    }
  }
  return table;
}

function addChartFrame(slide, position) {
  return addRect(slide, position, COLOR.white, COLOR.lightGray, 1);
}

function addChartTitle(slide, title, position) {
  addText(slide, title, position, { fontSize: FONT.subtitle, bold: true, color: COLOR.darkGray });
}

function addFlowConnector(slide, from, to, options = {}) {
  return slide.shapes.connect(from, to, {
    kind: options.kind ?? "straight",
    fromSide: options.fromSide ?? "right",
    toSide: options.toSide ?? "left",
    line: { style: "solid", fill: options.color ?? COLOR.orange, width: options.width ?? 2 },
    head: options.head === false ? { type: "none" } : { type: "triangle", width: "sm", length: "sm" },
  });
}

function createPresentation() {
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  presentation.theme.colorScheme = {
    name: "Solfácil Crédito",
    themeColors: {
      accent1: COLOR.orange,
      accent2: COLOR.black,
      accent3: COLOR.gray,
      accent4: COLOR.midGray,
      accent5: COLOR.lightGray,
      accent6: COLOR.paleGray,
      bg1: COLOR.white,
      bg2: COLOR.paleGray,
      tx1: COLOR.black,
      tx2: COLOR.gray,
      dk1: COLOR.blackPure,
      dk2: COLOR.darkGray,
      lt1: COLOR.white,
      lt2: COLOR.paleGray,
      hlink: COLOR.orange,
      folHlink: COLOR.darkGray,
    },
  };
  return presentation;
}

function addSlide1(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  const indicators = data.painel.filter((row) => row.tipo === "indicador");
  const selected = [
    "FIDCs confirmados",
    "Operações de CRI",
    "Séries de CRI",
    "Classes/subclasses FIDC",
    "Volume nominal total",
    "Volume público registrado",
  ].map((label) => indicators.find((row) => row.indicador_ou_etapa === label)).filter(Boolean);

  addText(
    slide,
    "Solfácil: CRIs e FIDCs em uma régua única",
    { left: 60, top: 72, width: 690, height: 128 },
    { fontSize: FONT.cover, bold: true, color: COLOR.black },
    "cover-title",
  );
  addText(
    slide,
    "Estrutura, prazo, proteção, cessões e custo com rastreabilidade por fonte e competência.",
    { left: 60, top: 220, width: 600, height: 92 },
    { fontSize: 24, color: COLOR.darkGray },
  );
  addRule(slide, 60, 336, 560, COLOR.orange, 4);
  addText(slide, "Leitura para crédito estruturado", { left: 60, top: 360, width: 420, height: 34 }, { fontSize: 22, bold: true, color: COLOR.black });
  addText(
    slide,
    "O warehouse absorve originação contínua; o CRI transfere pools elegíveis para passivos por série.",
    { left: 60, top: 410, width: 530, height: 110 },
    { fontSize: 20, color: COLOR.gray },
  );

  addNativeTable(
    slide,
    [
      ["Universo", "Medida", "Data-base"],
      ...selected.map((row) => [row.indicador_ou_etapa, formatMetric(row), row.data_base]),
    ],
    {
      left: 700,
      top: 120,
      width: 520,
      height: 390,
      columnWidths: [235, 165, 120],
      bodyFontSize: 16,
      rowHeight: 55,
    },
  );
  addText(
    slide,
    "Valores públicos e privados permanecem separados nos CSVs de séries e conflitos.",
    { left: 700, top: 532, width: 520, height: 64 },
    { fontSize: FONT.body, color: COLOR.gray },
  );
  addFooter(slide, 1, selected, sourceCatalog);
  addSpeakerSources(slide, selected, sourceCatalog, "Tabela de capa lida de 00_painel.csv; nenhuma métrica foi digitada no slide.");
}

function addSlide2(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Originação entra nos FIDCs; o CRI alonga o passivo", "MAPA DO PROGRAMA");
  const mapRows = data.painel.filter((row) => row.tipo === "mapa");
  const nodePositions = [80, 360, 640, 920].map((left) => ({ left, top: 240, width: 220, height: 112 }));
  const nodes = mapRows.slice(0, 4).map((row, index) => {
    const node = addRect(slide, nodePositions[index], index === 2 ? COLOR.paleGray : COLOR.white, index === 2 ? COLOR.orange : COLOR.black, index === 2 ? 3 : 1, `flow-${index + 1}`);
    node.text = `${cleanText(row.indicador_ou_etapa)}\n${shorten(row.leitura, 68)}`;
    node.text.style = { fontSize: FONT.body, bold: index === 2, color: COLOR.black, alignment: "center" };
    return node;
  });
  for (let index = 0; index < nodes.length - 1; index += 1) addFlowConnector(slide, nodes[index], nodes[index + 1]);

  const metricRows = ["PL dos FIDCs", "Volume público registrado", "Cessões documentadas"]
    .map((label) => data.painel.find((row) => row.indicador_ou_etapa === label))
    .filter(Boolean);
  addNativeTable(
    slide,
    [
      ["Ponto de leitura", "Valor", "Interpretação"],
      ...metricRows.map((row) => [row.indicador_ou_etapa, formatMetric(row), shorten(row.leitura, 78)]),
    ],
    {
      left: 180,
      top: 430,
      width: 920,
      height: 168,
      columnWidths: [250, 190, 480],
      bodyFontSize: FONT.body,
      rowHeight: 42,
    },
  );
  const usedRows = [...mapRows.slice(0, 4), ...metricRows];
  addFooter(slide, 2, usedRows, sourceCatalog);
  addSpeakerSources(slide, usedRows, sourceCatalog, "Fluxo montado com conectores Office; textos e métricas vêm de 00_painel.csv.");
}

function addTimelineBand(slide, rows, top, label) {
  const dates = rows.map((row) => new Date(`${row.data_inicio_ou_emissao}T00:00:00Z`));
  const minDate = Math.min(...dates.map((date) => date.getTime()));
  const maxDate = Math.max(...dates.map((date) => date.getTime()));
  const left = 170;
  const width = 980;
  addText(slide, label, { left: 60, top: top - 18, width: 90, height: 36 }, { fontSize: 22, bold: true, color: COLOR.black });
  const start = addRect(slide, { left, top, width: 4, height: 4 }, COLOR.gray, COLOR.gray, 0);
  const end = addRect(slide, { left: left + width, top, width: 4, height: 4 }, COLOR.gray, COLOR.gray, 0);
  addFlowConnector(slide, start, end, { head: false, color: COLOR.gray, width: 2 });
  rows.forEach((row, index) => {
    const time = new Date(`${row.data_inicio_ou_emissao}T00:00:00Z`).getTime();
    const ratio = maxDate === minDate ? 0.5 : (time - minDate) / (maxDate - minDate);
    const x = left + ratio * width;
    const marker = slide.shapes.add({
      geometry: "ellipse",
      position: { left: x - 7, top: top - 7, width: 14, height: 14 },
      fill: index % 2 === 0 ? COLOR.orange : COLOR.black,
      line: { style: "solid", fill: COLOR.white, width: 1 },
    });
    const labelTop = top + [-130, 20, -65][index % 3];
    addText(
      slide,
      `${shortVehicle(row.veiculo_id)}\n${formatDate(row.data_inicio_ou_emissao)}`,
      { left: Math.max(60, Math.min(1120, x - 58)), top: labelTop, width: 116, height: 58 },
      { fontSize: FONT.body, bold: true, color: COLOR.darkGray, alignment: "center" },
    );
    marker.bringToFront();
  });
}

function addSlide3(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  const fidcs = data.veiculos.filter((row) => row.tipo === "FIDC" && row.data_inicio_ou_emissao !== "n/d");
  const cris = data.veiculos.filter((row) => row.tipo === "CRI" && row.data_inicio_ou_emissao !== "n/d");
  addHeader(slide, `FIDCs precedem ${formatNumber(cris.length)} operações de take-out`, "LINHA DO TEMPO");
  addTimelineBand(slide, fidcs, 265, "FIDCs");
  addTimelineBand(slide, cris, 500, "CRIs");
  addFooter(slide, 3, data.veiculos, sourceCatalog);
  addSpeakerSources(slide, data.veiculos, sourceCatalog, "Datas lidas de 01_veiculos.csv; posição horizontal calculada entre a primeira e a última data de cada faixa.");
}

function addSlide4(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "A senioridade concentra o volume emitido", "TAMANHO POR CAMADA");
  const rows = data.series.filter((row) => row.veiculo_id.startsWith("CRI_") && numberOrNull(row.montante_emitido_R$) !== null);
  const vehicles = [...new Set(rows.map((row) => row.veiculo_id))];
  const totals = new Map();
  const layerTotals = new Map(LAYER_ORDER.map((layer) => [layer, new Map()]));
  for (const vehicle of vehicles) {
    const vehicleRows = rows.filter((row) => row.veiculo_id === vehicle);
    totals.set(vehicle, vehicleRows.reduce((sum, row) => sum + numberOrNull(row.montante_emitido_R$), 0));
    for (const layer of LAYER_ORDER) {
      layerTotals.get(layer).set(
        vehicle,
        vehicleRows.filter((row) => canonicalLayer(row.camada) === layer).reduce((sum, row) => sum + numberOrNull(row.montante_emitido_R$), 0),
      );
    }
  }
  const seniorTotal = rows
    .filter((row) => ["Super Sênior", "Sênior"].includes(canonicalLayer(row.camada)))
    .reduce((sum, row) => sum + numberOrNull(row.montante_emitido_R$), 0);
  const totalIssued = rows.reduce((sum, row) => sum + numberOrNull(row.montante_emitido_R$), 0);

  addChartFrame(slide, { left: 60, top: 145, width: 790, height: 455 });
  slide.charts.add("bar", {
    position: { left: 78, top: 160, width: 754, height: 420 },
    categories: vehicles.map(shortVehicle),
    series: LAYER_ORDER.map((layer, index) => ({
      name: layer,
      values: vehicles.map((vehicle) => layerTotals.get(layer).get(vehicle) / 1_000_000),
      fill: LAYER_COLORS[index],
      line: { style: "solid", fill: LAYER_COLORS[index], width: 1 },
    })),
    barOptions: { direction: "column", grouping: "stacked", gapWidth: 38, overlap: 100 },
    hasLegend: true,
    legend: { position: "bottom", overlay: false, textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.darkGray }, line: { style: "solid", fill: COLOR.lightGray, width: 1 } },
    yAxis: {
      numberFormatCode: '0 "mi"',
      textStyle: { fontSize: FONT.body, fill: COLOR.gray },
      majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 },
    },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });

  addNativeTable(
    slide,
    [
      ["Operação / métrica", "Valor"],
      ["Sênior + super sênior", formatPct(totalIssued ? seniorTotal / totalIssued : null, 1)],
      ...vehicles.map((vehicle) => [shortVehicle(vehicle), formatMi(totals.get(vehicle) / 1_000_000, 1)]),
    ],
    { left: 880, top: 160, width: 310, height: 438, columnWidths: [170, 140], bodyFontSize: FONT.body },
  );
  addFooter(slide, 4, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Volumes somados por veiculo_id e camada a partir de 02_series.csv; valores convertidos de reais para R$ milhões.");
}

function addSlide5(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Os CRIs documentam limites de WAM e ticket do pool", "ELEGIBILIDADE");
  const rows = data.elegibilidade.filter((row) => !row.veiculo_id.startsWith("Δ"));
  const values = [
    ["Veículo", "Idade máxima", "WAM máximo", "Ticket PF", "Ticket PJ", "Carência"],
    ...rows.map((row) => [
      shortVehicle(row.veiculo_id),
      row.idade_maxima_devedor === "n/d" ? "n/d" : `${formatNumber(row.idade_maxima_devedor)} anos`,
      row.wam_max_dias === "n/d" ? "n/d" : `${formatNumber(row.wam_max_dias)} dias`,
      formatCurrencyCompact(row.ticket_max_PF_R$),
      formatCurrencyCompact(row.ticket_max_PJ_R$),
      row.carencia_max_dias === "n/d" ? "n/d" : `${formatNumber(row.carencia_max_dias)} dias`,
    ]),
  ];
  addNativeTable(slide, values, {
    left: 60,
    top: 142,
    width: 1160,
    height: 476,
    columnWidths: [160, 180, 180, 220, 220, 200],
    bodyFontSize: FONT.body,
    rowHeight: 34,
  });
  addFooter(slide, 5, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Comparação literal de idade, WAM, tickets e carência em 03_elegibilidade.csv; n/d permanece texto.");
}

function addSlide6(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "O take-out alonga o prazo até a última série", "PRAZOS NA MESMA ESCALA");
  const rows = data.prazos;
  const criRows = rows.filter((row) => row.veiculo_id.startsWith("CRI_") && numberOrNull(row.prazo_max_recebivel_meses) !== null && numberOrNull(row.prazo_do_veiculo_meses) !== null);
  const fidcRows = rows.filter((row) => row.veiculo_id.startsWith("FIDC_"));
  const maxValue = Math.max(...criRows.flatMap((row) => [numberOrNull(row.prazo_max_recebivel_meses), numberOrNull(row.prazo_do_veiculo_meses)]));
  const axisMax = Math.ceil(maxValue / 12) * 12;
  const axisStep = Math.max(12, Math.ceil(axisMax / 72) * 12);

  addChartFrame(slide, { left: 60, top: 145, width: 790, height: 460 });
  slide.charts.add("bar", {
    position: { left: 78, top: 160, width: 754, height: 425 },
    categories: criRows.map((row) => shortVehicle(row.veiculo_id)),
    series: [
      { name: "Recebível máximo", values: criRows.map((row) => numberOrNull(row.prazo_max_recebivel_meses)), fill: COLOR.midGray },
      { name: "Passivo mais longo", values: criRows.map((row) => numberOrNull(row.prazo_do_veiculo_meses)), fill: COLOR.orange },
    ],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 42 },
    hasLegend: true,
    legend: { position: "bottom", textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: {
      min: 0,
      max: axisMax,
      majorUnit: axisStep,
      title: { text: "meses", textStyle: { fontSize: FONT.body, fill: COLOR.gray } },
      textStyle: { fontSize: FONT.body, fill: COLOR.gray },
      majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 },
    },
    yAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.darkGray }, line: { style: "solid", fill: COLOR.lightGray, width: 1 } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  addNativeTable(
    slide,
    [
      ["FIDC", "Prazo do passivo"],
      ...fidcRows.map((row) => [shortVehicle(row.veiculo_id), formatMonths(row.prazo_do_veiculo_meses)]),
    ],
    { left: 880, top: 168, width: 310, height: 302, columnWidths: [135, 175], bodyFontSize: FONT.body },
  );
  addText(
    slide,
    "Os vencimentos efetivos dos FIDCs permanecem n/d; o gráfico usa apenas pares documentados.",
    { left: 880, top: 500, width: 310, height: 90 },
    { fontSize: FONT.body, color: COLOR.gray },
  );
  addFooter(slide, 6, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Gráfico inclui somente linhas com prazo máximo do recebível e prazo do veículo documentados em 05_prazos_wam.csv.");
}

function waterfallColumn(slide, rows, left, title, condition) {
  addText(slide, title, { left, top: 150, width: 450, height: 34 }, { fontSize: 24, bold: true, color: COLOR.black, alignment: "center" });
  const nodes = rows.map((row, index) => {
    const node = addRect(
      slide,
      { left: left + 55, top: 205 + index * 72, width: 340, height: 48 },
      index === rows.length - 1 ? COLOR.paleGray : COLOR.white,
      index === rows.length - 1 ? COLOR.orange : COLOR.black,
      index === rows.length - 1 ? 2 : 1,
    );
    node.text = shorten(row.degrau, 45);
    node.text.style = { fontSize: FONT.body, bold: index === 0 || index === rows.length - 1, color: COLOR.black, alignment: "center" };
    return node;
  });
  for (let index = 0; index < nodes.length - 1; index += 1) {
    addFlowConnector(slide, nodes[index], nodes[index + 1], { kind: "straight", fromSide: "bottom", toSide: "top" });
  }
  addText(slide, shorten(condition, 108), { left, top: 552, width: 450, height: 42 }, { fontSize: FONT.body, color: COLOR.gray, alignment: "center" });
}

function addSlide7(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Gatilhos mudam o caixa para sequencial", "WATERFALL");
  const proRata = data.waterfallVisual.filter((row) => row.regime === "Pró-rata condicionado");
  const sequential = data.waterfallVisual.filter((row) => row.regime === "Sequencial pós-evento");
  const criK1 = data.waterfall.find((row) => row.veiculo_id === "CRI_K1");
  waterfallColumn(slide, proRata, 90, "Pró-rata condicionado", proRata[0]?.condicao ?? "n/d");
  waterfallColumn(slide, sequential, 740, "Sequencial pós-evento", sequential[0]?.condicao ?? "n/d");
  slide.shapes.add({
    geometry: "line",
    position: { left: 640, top: 150, width: 1, height: 430 },
    fill: "none",
    line: { style: "solid", fill: COLOR.lightGray, width: 1 },
  });
  addText(
    slide,
    shorten(criK1?.gatilho_de_mudanca_para_sequencial ?? "n/d", 105),
    { left: 405, top: 607, width: 470, height: 38 },
    { fontSize: FONT.body, bold: true, color: COLOR.black, alignment: "center" },
  );
  const usedRows = [...proRata, ...sequential, ...(criK1 ? [criK1] : [])];
  addFooter(slide, 7, usedRows, sourceCatalog);
  addSpeakerSources(slide, usedRows, sourceCatalog, "Degraus lidos de 06b_waterfall_visual.csv; gatilho específico lido de 06_waterfall.csv. Conexões são conectores Office.");
}

function addSlide8(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "A subordinada pode sair antes do vencimento", "SUBORDINADA");
  const rows = data.subordinada;
  const attachments = rows.map((row) => ({ ...row, attachment: numberOrNull(row.attachment_atual_pct_carteira) })).filter((row) => row.attachment !== null);
  const selectedIds = ["FIDC_I", "FIDC_II", "FIDC_VI", "FIDC_VII", "CRI_K1", "CRI_K2"];
  const selected = selectedIds.map((id) => rows.find((row) => row.veiculo_id === id)).filter(Boolean);
  addNativeTable(
    slide,
    [
      ["Veículo", "Saque", "Quórum", "Trava"],
      ...selected.map((row) => [
        shortVehicle(row.veiculo_id),
        shorten(row.saque_permitido, 24),
        shorten(row.quorum, 24),
        shorten(row.trava_temporal, 34),
      ]),
    ],
    { left: 60, top: 155, width: 540, height: 350, columnWidths: [110, 135, 120, 175], bodyFontSize: FONT.body },
  );
  addText(
    slide,
    "Pagamento observado de principal subordinado permanece n/d nas fontes públicas.",
    { left: 60, top: 530, width: 540, height: 72 },
    { fontSize: FONT.body, color: COLOR.gray },
  );
  addChartFrame(slide, { left: 635, top: 145, width: 585, height: 460 });
  addChartTitle(slide, "Attachment atual calculado (% da carteira)", { left: 665, top: 158, width: 520, height: 30 });
  slide.charts.add("bar", {
    position: { left: 655, top: 195, width: 545, height: 390 },
    categories: attachments.map((row) => shortVehicle(row.veiculo_id)),
    series: [{ name: "Attachment (% da carteira)", values: attachments.map((row) => Number((row.attachment * 100).toFixed(1))), fill: COLOR.orange }],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 48 },
    hasLegend: false,
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fontSize: FONT.body, fill: COLOR.black, bold: true } },
    xAxis: {
      min: 0,
      textStyle: { fontSize: FONT.body, fill: COLOR.gray },
      majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 },
    },
    yAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  addFooter(slide, 8, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Tabela e attachment lidos de 07_subordinada.csv; o percentual foi calculado na camada de dados como NAV mezanino mais NAV júnior dividido pela carteira bruta.");
}

function addSlide9(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "PDD acima do atraso sinaliza efeito vagão", "PDD E ATRASO");
  const rows = data.pdd.filter((row) => numberOrNull(row.pdd_observada_pct_carteira) !== null && numberOrNull(row.saldo_90d_pct_carteira) !== null);
  const ratioRows = rows.filter((row) => numberOrNull(row.razao_pdd_sobre_90d) !== null).sort((a, b) => numberOrNull(b.razao_pdd_sobre_90d) - numberOrNull(a.razao_pdd_sobre_90d));
  const aboveOne = ratioRows.filter((row) => numberOrNull(row.razao_pdd_sobre_90d) > 1);
  addChartFrame(slide, { left: 60, top: 145, width: 830, height: 470 });
  slide.charts.add("bar", {
    position: { left: 78, top: 160, width: 795, height: 435 },
    categories: rows.map((row) => shortVehicle(row.veiculo_id)),
    series: [
      { name: "PDD (% carteira)", values: rows.map((row) => Number((numberOrNull(row.pdd_observada_pct_carteira) * 100).toFixed(1))), fill: COLOR.orange },
      { name: "Saldo acima de 90d (% carteira)", values: rows.map((row) => Number((numberOrNull(row.saldo_90d_pct_carteira) * 100).toFixed(1))), fill: COLOR.gray },
    ],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 45 },
    hasLegend: true,
    legend: { position: "bottom", textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: {
      textStyle: { fontSize: FONT.body, fill: COLOR.gray },
      majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 },
    },
    yAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  addNativeTable(
    slide,
    [
      ["Veículo", "Razão"],
      ["Razão superior a 1", formatNumber(aboveOne.length)],
      ...ratioRows.slice(0, 5).map((row) => [shortVehicle(row.veiculo_id), `${formatNumber(row.razao_pdd_sobre_90d, 1)}x`]),
    ],
    { left: 930, top: 165, width: 250, height: 430, columnWidths: [150, 100], bodyFontSize: FONT.body },
  );
  addFooter(slide, 9, data.pdd, sourceCatalog);
  addSpeakerSources(slide, data.pdd, sourceCatalog, "Percentuais e razão lidos de 08_pdd.csv; contagem superior a 1 calculada no builder.");
}

function addSlide10(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Caps contratuais limitam a concentração", "CONCENTRAÇÃO");
  const rows = data.concentracao;
  const criRows = rows.filter((row) => row.veiculo_id.startsWith("CRI_"));
  addNativeTable(
    slide,
    [
      ["CRI", "Cap contratual individual", "Cap classificatório ANBIMA", "Observado"],
      ...criRows.map((row) => [
        shortVehicle(row.veiculo_id),
        numberOrNull(row.cap_individual_pct) === null ? shorten(row.cap_individual_pct, 36) : formatPct(row.cap_individual_pct, 2),
        formatPct(row.cap_por_devedor_ANBIMA_pct, 0),
        formatPct(row.concentracao_observada_individual, 2),
      ]),
    ],
    { left: 90, top: 148, width: 1100, height: 230, columnWidths: [155, 350, 320, 275], bodyFontSize: FONT.body },
  );
  const chartRows = rows.filter((row) => numberOrNull(row.cap_individual_pct) !== null && numberOrNull(row.concentracao_observada_individual) !== null);
  addChartFrame(slide, { left: 90, top: 400, width: 1100, height: 215 });
  slide.charts.add("bar", {
    position: { left: 108, top: 412, width: 1065, height: 190 },
    categories: chartRows.map((row) => shortVehicle(row.veiculo_id)),
    series: [
      { name: "Cap individual", values: chartRows.map((row) => numberOrNull(row.cap_individual_pct)), fill: COLOR.black },
      { name: "Observado", values: chartRows.map((row) => numberOrNull(row.concentracao_observada_individual)), fill: COLOR.orange },
    ],
    barOptions: { direction: "column", grouping: "clustered", gapWidth: 52 },
    hasLegend: true,
    legend: { position: "bottom", textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    yAxis: { numberFormatCode: "0%", textStyle: { fontSize: FONT.body, fill: COLOR.gray }, majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  addFooter(slide, 10, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Caps e concentrações observadas lidos de 04_concentracao.csv; cap ANBIMA mantido em coluna distinta.");
}

function matrixState(value) {
  const text = cleanText(value).toLowerCase();
  if (text.startsWith("cedeu")) return "Cedeu";
  if (text.includes("não elegível")) return "Não elegível";
  if (text.includes("n/d")) return "Pode ceder, dados incompletos";
  return "Pode ceder";
}

function addSlide11(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  const documentedCedents = [...new Set(data.cessoes.map((row) => shortVehicle(row.fidc_cedente)))];
  addHeader(slide, `${documentedCedents.join(" e ")} têm cessões documentadas`, "MATRIZ DE CESSÃO");
  const headers = ["FIDC", "K1", "K2", "K3", "K4", "VERT 174", "VERT 177"];
  const columns = ["CRI_K1", "CRI_K2", "CRI_K3", "CRI_K4", "CRI_V174", "CRI_V177"];
  const tableValues = [headers, ...data.matriz.map((row) => [shortVehicle(row.fidc), ...columns.map((column) => matrixState(row[column]))])];
  addNativeTable(slide, tableValues, {
    left: 60,
    top: 145,
    width: 1160,
    height: 322,
    columnWidths: [125, 172, 172, 172, 172, 174, 173],
    bodyFontSize: FONT.body,
  });
  addNativeTable(
    slide,
    [
      ["Data", "Cedente", "Cessionário", "Volume"],
      ...data.cessoes.map((row) => [formatDate(row.data), shortVehicle(row.fidc_cedente), shortVehicle(row.cri_cessionario), formatMi(row.volume_R$mi, 3)]),
    ],
    { left: 200, top: 495, width: 880, height: 135, columnWidths: [180, 210, 220, 270], bodyFontSize: FONT.body, rowHeight: 27 },
  );
  const usedRows = [...data.matriz, ...data.cessoes];
  addFooter(slide, 11, usedRows, sourceCatalog);
  addSpeakerSources(slide, usedRows, sourceCatalog, "Estados resumidos de 11_matriz_fidc_cri.csv; cessões e volumes lidos de 11b_cessoes.csv.");
}

function addSlide12(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Amortizações e novas emissões movem o saldo consolidado", "CURVA DE AMORTIZAÇÃO");
  const realizedAll = data.cronograma.filter((row) => row.status === "Realizado");
  const expectedSeries = new Map();
  for (const row of data.series.filter((row) => row.veiculo_id.startsWith("CRI_"))) {
    if (!expectedSeries.has(row.veiculo_id)) expectedSeries.set(row.veiculo_id, new Set());
    expectedSeries.get(row.veiculo_id).add(row.serie);
  }
  const rowsByMonthVehicle = new Map();
  for (const row of realizedAll) {
    if (!rowsByMonthVehicle.has(row.competencia)) rowsByMonthVehicle.set(row.competencia, new Map());
    const monthGroups = rowsByMonthVehicle.get(row.competencia);
    if (!monthGroups.has(row.veiculo_id)) monthGroups.set(row.veiculo_id, []);
    monthGroups.get(row.veiculo_id).push(row);
  }
  const completeMonths = new Set([...rowsByMonthVehicle.entries()].filter(([, monthGroups]) =>
    [...monthGroups.entries()].every(([vehicle, group]) => {
      const present = new Set(group.map((row) => row.serie));
      return present.size === expectedSeries.get(vehicle)?.size && group.every((row) => numberOrNull(row.saldo_final) !== null);
    }),
  ).map(([month]) => month));
  const realized = realizedAll.filter((row) => completeMonths.has(row.competencia));
  const projected = data.cronograma.filter((row) => row.status === "Projetado");
  const monthLayer = new Map();
  for (const row of realized) {
    const month = row.competencia;
    const layer = canonicalLayer(row.camada);
    if (!monthLayer.has(month)) monthLayer.set(month, new Map());
    const bucket = monthLayer.get(month);
    bucket.set(layer, (bucket.get(layer) ?? 0) + numberOrNull(row.saldo_final));
  }
  const months = [...monthLayer.keys()].sort();
  const chartMonths = months.slice(-30);
  addChartFrame(slide, { left: 60, top: 145, width: 900, height: 470 });
  slide.charts.add("area", {
    position: { left: 78, top: 162, width: 865, height: 430 },
    categories: chartMonths.map(formatMonthLabel),
    series: LAYER_ORDER.map((layer, index) => ({
      name: layer,
      values: chartMonths.map((month) => (monthLayer.get(month).get(layer) ?? 0) / 1_000_000),
      fill: LAYER_COLORS[index],
      line: { style: "solid", fill: LAYER_COLORS[index], width: 1 },
    })),
    areaOptions: { grouping: "stacked" },
    hasLegend: true,
    legend: { position: "bottom", textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.gray }, labelOffsetPercent: 80 },
    yAxis: { numberFormatCode: '0 "mi"', textStyle: { fontSize: FONT.body, fill: COLOR.gray }, majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  addNativeTable(
    slide,
    [
      ["Status", "Linhas"],
      ["Realizado", formatNumber(realized.length)],
      ["Projetado", formatNumber(projected.length)],
      ["Meses completos no gráfico", formatNumber(chartMonths.length)],
    ],
    { left: 990, top: 170, width: 200, height: 190, columnWidths: [125, 75], bodyFontSize: FONT.body },
  );
  addText(
    slide,
    "A curva projetada completa permanece limitada: termos públicos não entregam todos os fluxos mensais por série.",
    { left: 990, top: 400, width: 200, height: 142 },
    { fontSize: FONT.body, color: COLOR.gray },
  );
  addFooter(slide, 12, data.cronograma, sourceCatalog);
  addSpeakerSources(slide, data.cronograma, sourceCatalog, "Saldos finais realizados agregados por competência e camada em 13_cronograma_pagamentos.csv; entram apenas meses em que todas as séries reportadas de cada operação fecham com saldo documentado.");
}

function rateSummary(rows) {
  const rates = [...new Set(rows.map((row) => cleanText(row.taxa_contratada)).filter((value) => value && value !== "n/d"))];
  if (!rates.length) return "n/d";
  if (rates.length <= 3) return rates.join("; ");
  return `${rates.slice(0, 3).join("; ")} +${rates.length - 3} séries`;
}

function addSlide13(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "O custo all-in ainda não é comparável", "CUSTO DE CAPTAÇÃO");
  const rows = data.custo;
  const vehicles = [...new Set(rows.filter((row) => row.veiculo_id.startsWith("CRI_")).map((row) => row.veiculo_id))];
  const publicSeries = new Set(
    data.series
      .filter((row) => row.veiculo_id.startsWith("CRI_") && row.colocacao === "pública")
      .map((row) => `${row.veiculo_id}|${row.serie}`),
  );
  const summaries = vehicles.map((vehicle) => rows.find((row) => row.veiculo_id === vehicle && row.serie === "Resumo do veículo"));
  const tableValues = [
    ["CRI", "Taxas contratadas publicadas", "All-in", "Distribuição uma vez", "Limitação"],
    ...vehicles.map((vehicle, index) => {
      const series = rows.filter((row) => publicSeries.has(`${row.veiculo_id}|${row.serie}`));
      const summary = summaries[index];
      return [
        shortVehicle(vehicle),
        shorten(rateSummary(series), 62),
        summary?.custo_all_in_bps ?? "n/d",
        numberOrNull(summary?.custo_distribuicao_uma_vez_bps) === null ? "n/d" : `${formatNumber(summary.custo_distribuicao_uma_vez_bps, 1)} bps`,
        shorten(summary?.nota_metodo ?? "n/d", 58),
      ];
    }),
  ];
  addNativeTable(slide, tableValues, {
    left: 60,
    top: 150,
    width: 1160,
    height: 350,
    columnWidths: [120, 350, 110, 190, 390],
    bodyFontSize: FONT.body,
  });
  const allInMissing = summaries.filter((row) => !row || numberOrNull(row.custo_all_in_bps) === null).length;
  addRect(slide, { left: 60, top: 535, width: 1160, height: 80 }, COLOR.black, COLOR.black, 0);
  addText(
    slide,
    `${formatNumber(allInMissing)} de ${formatNumber(vehicles.length)} operações permanecem com all-in n/d`,
    { left: 90, top: 551, width: 520, height: 38 },
    { fontSize: 24, bold: true, color: COLOR.white },
  );
  addText(
    slide,
    "Faltam curva DI datada, inflação implícita, custos recorrentes completos, hedge e preço de cessão.",
    { left: 640, top: 548, width: 540, height: 52 },
    { fontSize: FONT.body, color: COLOR.white },
  );
  addFooter(slide, 13, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Taxas e lacunas lidas de 12_custo_captacao.csv; contagem de all-in n/d calculada por resumo de veículo.");
}

function addSlide14(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Denominador e PDD mudam ao redor do take-out", "ANTES E DEPOIS");
  const rows = data.antesDepois.filter((row) => row.cri_evento === "CRI_K1" && ["FIDC_II", "FIDC_IV"].includes(row.fidc));
  const fidcs = [...new Set(rows.map((row) => row.fidc))];
  const mobs = [...new Set(rows.map((row) => Number(row.mob)))].sort((a, b) => a - b);

  addChartFrame(slide, { left: 60, top: 148, width: 550, height: 425 });
  addChartTitle(slide, "PDD / carteira", { left: 85, top: 160, width: 500, height: 30 });
  slide.charts.add("line", {
    position: { left: 78, top: 198, width: 514, height: 355 },
    categories: mobs.map((mob) => String(mob)),
    series: fidcs.map((fidc, index) => ({
      name: shortVehicle(fidc),
      values: mobs.map((mob) => numberOrNull(rows.find((row) => row.fidc === fidc && Number(row.mob) === mob)?.pdd_pct_carteira)),
      line: { style: "solid", fill: index === 0 ? COLOR.orange : COLOR.black, width: 3 },
      marker: { symbol: index === 0 ? "circle" : "diamond", size: 7 },
    })),
    hasLegend: true,
    legend: { position: "bottom", textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: { title: { text: "mês relativo à cessão", textStyle: { fontSize: FONT.body, fill: COLOR.gray } }, textStyle: { fontSize: FONT.body, fill: COLOR.gray } },
    yAxis: { numberFormatCode: "0%", textStyle: { fontSize: FONT.body, fill: COLOR.gray }, majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });

  addChartFrame(slide, { left: 650, top: 148, width: 570, height: 425 });
  addChartTitle(slide, "PL do FIDC", { left: 675, top: 160, width: 520, height: 30 });
  slide.charts.add("line", {
    position: { left: 668, top: 198, width: 534, height: 355 },
    categories: mobs.map((mob) => String(mob)),
    series: fidcs.map((fidc, index) => ({
      name: shortVehicle(fidc),
      values: mobs.map((mob) => numberOrNull(rows.find((row) => row.fidc === fidc && Number(row.mob) === mob)?.pl_R$mi)),
      line: { style: "solid", fill: index === 0 ? COLOR.orange : COLOR.black, width: 3 },
      marker: { symbol: index === 0 ? "circle" : "diamond", size: 7 },
    })),
    hasLegend: true,
    legend: { position: "bottom", textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    xAxis: { title: { text: "mês relativo à cessão", textStyle: { fontSize: FONT.body, fill: COLOR.gray } }, textStyle: { fontSize: FONT.body, fill: COLOR.gray } },
    yAxis: { numberFormatCode: '0 "mi"', textStyle: { fontSize: FONT.body, fill: COLOR.gray }, majorGridlines: { style: "solid", fill: COLOR.lightGray, width: 1 } },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  const eventRow = rows.find((row) => Number(row.mob) === 0);
  for (const left of [354, 966]) {
    slide.shapes.add({
      geometry: "line",
      position: { left, top: 205, width: 1, height: 260 },
      fill: "none",
      line: { style: "solid", fill: COLOR.orange, width: 2 },
    });
    addText(slide, "t=0", { left: left - 25, top: 176, width: 50, height: 22 }, { fontSize: FONT.small, bold: true, color: COLOR.black, alignment: "center" });
  }
  addText(slide, eventRow ? cleanText(eventRow.evento) : "evento n/d", { left: 515, top: 588, width: 250, height: 30 }, { fontSize: FONT.body, bold: true, color: COLOR.black, alignment: "center" });
  addText(
    slide,
    shorten(eventRow?.leitura ?? "n/d", 142),
    { left: 180, top: 620, width: 920, height: 30 },
    { fontSize: FONT.body, color: COLOR.gray, alignment: "center" },
  );
  addFooter(slide, 14, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Séries t−3 a t+3 lidas de 14_antes_depois.csv; nenhuma causalidade é inferida sem tape por CCB.");
}

function addSlide15(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "CRI alonga; FIDC preserva flexibilidade", "FIDC VS. CRI");
  const rows = data.fidcVsCri;
  addNativeTable(
    slide,
    [
      ["Dimensão", "Veredito", "Evidência", "O que falta"],
      ...rows.map((row) => [
        shorten(row.dimensao, 34),
        cleanText(row.vantagem_real),
        shorten(row.evidencia, 40),
        shorten(row.o_que_falta_para_confirmar, 58),
      ]),
    ],
    { left: 60, top: 148, width: 820, height: 475, columnWidths: [205, 115, 220, 280], bodyFontSize: FONT.body },
  );
  const verdicts = ["FIDC", "CRI", "neutro"];
  const counts = verdicts.map((verdict) => rows.filter((row) => row.vantagem_real.toLowerCase() === verdict.toLowerCase()).length);
  addChartFrame(slide, { left: 920, top: 180, width: 270, height: 330 });
  slide.charts.add("bar", {
    position: { left: 940, top: 205, width: 230, height: 275 },
    categories: verdicts,
    series: [{ name: "Dimensões", values: counts, fill: COLOR.orange }],
    barOptions: { direction: "column", grouping: "clustered", gapWidth: 62 },
    hasLegend: false,
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fontSize: FONT.body, fill: COLOR.black, bold: true } },
    xAxis: { textStyle: { fontSize: FONT.body, fill: COLOR.darkGray } },
    yAxis: { visible: false, majorGridlines: null },
    chartFill: COLOR.white,
    plotAreaFill: COLOR.white,
  });
  addText(
    slide,
    "Vereditos refletem apenas evidência pública; campos n/d não contam como vantagem.",
    { left: 920, top: 545, width: 270, height: 72 },
    { fontSize: FONT.body, color: COLOR.gray, alignment: "center" },
  );
  addFooter(slide, 15, rows, sourceCatalog);
  addSpeakerSources(slide, rows, sourceCatalog, "Tabela lida de 15_fidc_vs_cri.csv; contagem por veredito calculada no builder.");
}

function addSlide16(presentation, data, sourceCatalog) {
  const slide = presentation.slides.add();
  slide.background.fill = COLOR.white;
  addHeader(slide, "Lacunas abertas têm pedido definido", "PRÓXIMAS DILIGÊNCIAS");
  const missingSources = data.fontes.filter((row) => row.status_obtencao !== "obtido");
  const currentPositionRows = data.subscritores.filter((row) => row.titulares_atuais === "n/d");
  const allInRows = data.custo.filter((row) => row.serie === "Resumo do veículo" && row.custo_all_in_bps === "n/d");
  const wamRows = data.prazos.filter((row) => row.wam_observado_dias === "n/d");
  const subRows = data.subordinada.filter((row) => row.principal_subordinado_ja_pago_R$mi === "n/d");
  const projectedRows = data.cronograma.filter((row) => row.status === "Projetado");
  const gapRows = [
    ["Curva DI e inflação implícita", "Séries datadas da data-base", "B3 e ANBIMA", "Equivalência de taxas e custo all-in"],
    ["Posição corrente dos titulares", "Mapa por investidor e concentração", "Escriturador e agente fiduciário", "Risco de concentração pós-oferta"],
    ["WAM observado", "Tape por CCB com saldo e vencimento", "Gestores e custodiante", "Descasamento ativo-passivo"],
    ["Pagamentos da subordinada", "Histórico de principal por classe/série", "Administrador e securitizadora", "Attachment antes e depois"],
    ["Curvas mensais projetadas", "Anexos de amortização por série", "Securitizadoras", "Curva de morte contratual"],
    ["Custos recorrentes completos", "Fees, hedge e preço de cessão", "Cedente, coordenador e prestadores", "Comparação FIDC e CRI"],
  ];
  addNativeTable(
    slide,
    [["Lacuna", "Pedido", "Destinatário", "Efeito na análise"], ...gapRows],
    { left: 60, top: 150, width: 1160, height: 350, columnWidths: [260, 290, 285, 325], bodyFontSize: FONT.body },
  );
  const obtained = data.fontes.filter((row) => row.status_obtencao === "obtido").length;
  const conflictCount = data.conflitos.length;
  addRect(slide, { left: 60, top: 535, width: 1160, height: 84 }, COLOR.black, COLOR.black, 0);
  addText(
    slide,
    `${formatNumber(obtained)} de ${formatNumber(data.fontes.length)} fontes obtidas`,
    { left: 90, top: 556, width: 350, height: 34 },
    { fontSize: 24, bold: true, color: COLOR.white },
  );
  addText(
    slide,
    `${formatNumber(conflictCount)} conflitos registrados | ${formatNumber(missingSources.length)} fontes não localizadas`,
    { left: 470, top: 558, width: 700, height: 34 },
    { fontSize: 22, color: COLOR.white, alignment: "right" },
  );
  const usedRows = [
    ...data.fontes,
    ...currentPositionRows,
    ...allInRows,
    ...wamRows,
    ...subRows,
    ...projectedRows,
    ...data.conflitos,
  ];
  addFooter(slide, 16, usedRows, sourceCatalog);
  addSpeakerSources(slide, usedRows, sourceCatalog, "Lacunas derivadas dos campos n/d e status de obtenção nos CSVs correspondentes; pedidos e destinatários são diligências propostas.");
}

async function main() {
  const [
    painel,
    veiculos,
    series,
    elegibilidade,
    concentracao,
    prazos,
    waterfall,
    waterfallVisual,
    subordinada,
    pdd,
    subscritores,
    matriz,
    cessoes,
    custo,
    cronograma,
    antesDepois,
    fidcVsCri,
    conflitos,
    fontes,
  ] = await Promise.all([
    readCsv("00_painel.csv"),
    readCsv("01_veiculos.csv"),
    readCsv("02_series.csv"),
    readCsv("03_elegibilidade.csv"),
    readCsv("04_concentracao.csv"),
    readCsv("05_prazos_wam.csv"),
    readCsv("06_waterfall.csv"),
    readCsv("06b_waterfall_visual.csv"),
    readCsv("07_subordinada.csv"),
    readCsv("08_pdd.csv"),
    readCsv("10_subscritores.csv"),
    readCsv("11_matriz_fidc_cri.csv"),
    readCsv("11b_cessoes.csv"),
    readCsv("12_custo_captacao.csv"),
    readCsv("13_cronograma_pagamentos.csv"),
    readCsv("14_antes_depois.csv"),
    readCsv("15_fidc_vs_cri.csv"),
    readCsv("16_conflitos.csv"),
    readCsv("17_fontes.csv"),
  ]);
  const data = {
    painel,
    veiculos,
    series,
    elegibilidade,
    concentracao,
    prazos,
    waterfall,
    waterfallVisual,
    subordinada,
    pdd,
    subscritores,
    matriz,
    cessoes,
    custo,
    cronograma,
    antesDepois,
    fidcVsCri,
    conflitos,
    fontes,
  };
  const sourceCatalog = new Map(fontes.map((row) => [row.fonte_id, row]));
  const presentation = createPresentation();

  addSlide1(presentation, data, sourceCatalog);
  addSlide2(presentation, data, sourceCatalog);
  addSlide3(presentation, data, sourceCatalog);
  addSlide4(presentation, data, sourceCatalog);
  addSlide5(presentation, data, sourceCatalog);
  addSlide6(presentation, data, sourceCatalog);
  addSlide7(presentation, data, sourceCatalog);
  addSlide8(presentation, data, sourceCatalog);
  addSlide9(presentation, data, sourceCatalog);
  addSlide10(presentation, data, sourceCatalog);
  addSlide11(presentation, data, sourceCatalog);
  addSlide12(presentation, data, sourceCatalog);
  addSlide13(presentation, data, sourceCatalog);
  addSlide14(presentation, data, sourceCatalog);
  addSlide15(presentation, data, sourceCatalog);
  addSlide16(presentation, data, sourceCatalog);

  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(OUTPUT);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
