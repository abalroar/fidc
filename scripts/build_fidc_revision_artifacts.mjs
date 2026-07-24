#!/usr/bin/env node
/*
 * Gera os artefatos finais da revisão da indústria de FIDCs.
 *
 * O PPTX e o XLSX são produzidos com @oai/artifact-tool. A camada visual
 * consome `artifact_payload.json`, cuja origem é o pipeline analítico em
 * `services/industry_revision_analysis.py`.
 */

import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import zlib from "node:zlib";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), "..");
const localNodeModules = path.join(ROOT, "node_modules");
const bundledNodeModules = path.join(
  os.homedir(),
  ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules",
);
const NODE_MODULES =
  process.env.CODEX_NODE_MODULES ||
  (existsSync(path.join(localNodeModules, "@oai/artifact-tool/package.json"))
    ? localNodeModules
    : bundledNodeModules);
const require = createRequire(path.join(NODE_MODULES, "package.json"));
const {
  FileBlob,
  Presentation,
  PresentationFile,
  SpreadsheetFile,
} = require("@oai/artifact-tool");

const INPUT_WORKBOOK =
  process.env.FIDC_INPUT_WORKBOOK ||
  "/Users/matheusjprates/Downloads/Industria_FIDC_Dados_202607.xlsx";
const REVISION_DIR = path.resolve(
  process.env.FIDC_REVISION_DIR ||
    path.join(ROOT, "data/industry_study/generated_revision"),
);
const PAYLOAD_PATH = path.resolve(
  process.env.FIDC_PAYLOAD_PATH || path.join(REVISION_DIR, "artifact_payload.json"),
);
const OUTPUT_DIR = path.resolve(
  process.env.FIDC_OUTPUT_DIR || path.join(ROOT, "outputs"),
);
const QA_DIR = path.resolve(
  process.env.FIDC_QA_DIR || path.join(OUTPUT_DIR, "qa"),
);
const OUTPUT_PPTX = path.resolve(
  process.env.FIDC_OUTPUT_PPTX ||
    path.join(OUTPUT_DIR, "Industria_FIDC_Executivo_202607_revisado.pptx"),
);
const OUTPUT_XLSX = path.resolve(
  process.env.FIDC_OUTPUT_XLSX ||
    path.join(OUTPUT_DIR, "Industria_FIDC_Dados_202607_revisado.xlsx"),
);
const FLOW_BUILDER_NAME = "build_provider_flow_explorer.mjs";
const FLOW_BUILDER_PATH = [
  process.env.FIDC_PROVIDER_FLOW_BUILDER,
  path.join(path.dirname(__filename), FLOW_BUILDER_NAME),
  path.join(ROOT, "scripts", FLOW_BUILDER_NAME),
].find((candidate) => candidate && existsSync(candidate));
const FLOW_ASSET_DIR = path.resolve(
  process.env.FIDC_PROVIDER_FLOW_ASSET_DIR ||
    path.join(OUTPUT_DIR, "provider_flow_assets"),
);
const OUTPUT_HTML = path.resolve(
  process.env.FIDC_OUTPUT_HTML ||
    path.join(OUTPUT_DIR, "provider_flows_explorer.html"),
);
const SKIP_QA = process.env.FIDC_SKIP_QA === "1";
const EXPORT_MANIFEST_PATH = path.resolve(
  process.env.FIDC_EXPORT_MANIFEST ||
    path.join(REVISION_DIR, "industry_export_bundle.json"),
);
const RENDERER_VERSION = "industry_revision_artifacts_v17";
const EXPECTED_SLIDES = 57;

const C = {
  orange: "#EC7000",
  black: "#151515",
  charcoal: "#30353A",
  mid: "#73787D",
  note: "#8D9399",
  line: "#D7DADD",
  light: "#E7E9EB",
  pale: "#F5F6F7",
  white: "#FFFFFF",
};

const PROVIDER_COLORS = {
  genial: "#6EC5E9",
  "qi tech": "#2456D6",
  "btg pactual": "#1D4080",
  "oliveira trust": "#7A1F3D",
  "banco do brasil": "#D6A800",
  itau: "#FF5500",
  cbfs: "#73C6A1",
  cbsf: "#73C6A1",
  reag: "#73C6A1",
};
const PROVIDER_GRAY_SCALE = [
  "#30353A",
  "#454A4F",
  "#5B6065",
  "#73787D",
  "#8D9399",
  "#A7ACB0",
  "#BEC2C5",
];

function normalizeProviderName(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function providerColor(value) {
  const key = normalizeProviderName(value);
  if (key === "outros identificados") return C.line;
  if (key === "prestador nao informado" || key === "nao informado") return C.pale;
  const matched = Object.entries(PROVIDER_COLORS).find(([token]) => key.includes(token));
  if (matched) return matched[1];
  let hash = 0;
  for (const character of key) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return PROVIDER_GRAY_SCALE[hash % PROVIDER_GRAY_SCALE.length];
}

const SLIDE = { width: 1280, height: 720 };
const FRAME = { left: 60, right: 60, top: 132, bottom: 654 };
const FULL_WIDTH = SLIDE.width - FRAME.left - FRAME.right;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function num(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function pct(value, digits = 1) {
  return `${(num(value) * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

function bn(value, digits = 1) {
  return `R$ ${(num(value) / 1e9).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} bi`;
}

function mm(value, digits = 0) {
  return `R$ ${(num(value) / 1e6).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} mi`;
}

function integer(value) {
  return Math.round(num(value)).toLocaleString("pt-BR");
}

const MONTHS_LONG_PT = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];
const MONTHS_SHORT_PT = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

function parseIsoDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

function parseCompetence(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})$/);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]) };
}

function dateLongPt(value) {
  const parsed = parseIsoDate(value);
  if (!parsed) return String(value || "n/d");
  return `${parsed.day} de ${MONTHS_LONG_PT[parsed.month - 1]} de ${parsed.year}`;
}

function dateShortPt(value) {
  const parsed = parseIsoDate(value);
  if (!parsed) return String(value || "n/d");
  return `${parsed.day}/${MONTHS_SHORT_PT[parsed.month - 1]}/${String(parsed.year).slice(-2)}`;
}

function competenceShortPt(value) {
  const parsed = parseCompetence(value);
  if (!parsed) return String(value || "n/d");
  const month = MONTHS_SHORT_PT[parsed.month - 1];
  return `${month[0].toUpperCase()}${month.slice(1)}/${String(parsed.year).slice(-2)}`;
}

function competenceEndLongPt(value) {
  const parsed = parseCompetence(value);
  if (!parsed) return String(value || "n/d");
  const day = new Date(Date.UTC(parsed.year, parsed.month, 0)).getUTCDate();
  return `${day} de ${MONTHS_LONG_PT[parsed.month - 1]} de ${parsed.year}`;
}

function truncateWords(value, maxChars) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxChars) return text;
  const sliced = text.slice(0, maxChars + 1);
  const cut = sliced.lastIndexOf(" ");
  return `${sliced.slice(0, cut > maxChars * 0.6 ? cut : maxChars).trim()}…`;
}

function providerShort(value) {
  return String(value || "")
    .replace(/SOCIEDADE AN[ÔO]NIMA/gi, "")
    .replace(/SERVI[CÇ]OS FINANCEIROS/gi, "")
    .replace(/CORRETORA DE T[IÍ]TULOS E VALORES MOBILI[AÁ]RIOS/gi, "")
    .replace(/DISTRIBUIDORA DE T[IÍ]TULOS E VALORES MOBILI[AÁ]RIOS/gi, "")
    .replace(/\bS\/?A\b|\bDTVM\b|\bLTDA\.?\b/gi, "")
    .replace(/\s+/g, " ")
    .replace(/[.,\- ]+$/g, "")
    .trim();
}

function focusShort(type, focus) {
  const typeMap = {
    "Agro, Indústria e Comércio": "Agro",
    "Fomento Mercantil": "Fomento",
    Financeiro: "Financeiro",
    Outros: "Outros",
  };
  const focusMap = {
    "Multicarteira Outros": "Multicarteira",
    "Recebíveis Comerciais": "Recebíveis comerciais",
    "Crédito Pessoal": "Crédito pessoal",
    "Multicarteira Financeiro": "Multicarteira",
    "Poder Público": "Poder público",
    "Crédito Corporativo": "Crédito corporativo",
  };
  return `${typeMap[type] || type}\n${focusMap[focus] || focus}`;
}

function addText(slide, text, position, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name: options.name,
    position: {
      left: position.left,
      top: position.top,
      width: position.width,
      height: position.height,
    },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = String(text ?? "");
  shape.text.style = {
    typeface: "Arial",
    fontSize: options.fontSize ?? 16,
    bold: options.bold ?? false,
    color: options.color ?? C.charcoal,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "top",
    autoFit: options.autoFit ?? "shrinkText",
    wrap: options.wrap ?? "square",
    lineSpacing: options.lineSpacing ?? 1,
    insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function addRect(slide, position, fill, options = {}) {
  return slide.shapes.add({
    geometry: options.geometry || "rect",
    name: options.name,
    position: {
      left: position.left,
      top: position.top,
      width: position.width,
      height: position.height,
    },
    fill,
    line: {
      style: "solid",
      fill: options.lineFill ?? "none",
      width: options.lineWidth ?? 0,
    },
  });
}

function addRule(slide, left, top, width, color = C.line, thickness = 1) {
  addRect(slide, { left, top, width, height: thickness }, color);
}

let automaticPageNumber = 1;

function addHeader(slide, eyebrow, title, source, _page) {
  automaticPageNumber += 1;
  slide.background.fill = C.white;
  addText(
    slide,
    eyebrow.toUpperCase().replace(/\bFIDCS\b/g, "FIDCs"),
    { left: 60, top: 27, width: 1160, height: 20 },
    { fontSize: 12, bold: true, color: C.orange },
  );
  const titleFont = title.length > 105 ? 24 : title.length > 85 ? 26 : 28;
  addText(
    slide,
    title,
    { left: 60, top: 53, width: 1160, height: 49 },
    { fontSize: titleFont, bold: true, color: C.black, verticalAlignment: "middle" },
  );
  addRule(slide, 60, 110, 1160, C.line, 1);
  addRule(slide, 60, 667, 1160, C.line, 1);
  addText(
    slide,
    source,
    { left: 60, top: 674, width: 1050, height: 18 },
    {
      fontSize: 10.5,
      color: C.note,
      verticalAlignment: "middle",
      insets: { top: 0, right: 0, bottom: 0, left: 5 },
    },
  );
  addText(
    slide,
    String(automaticPageNumber),
    { left: 1170, top: 673, width: 50, height: 18 },
    { fontSize: 10.5, color: C.note, alignment: "right", verticalAlignment: "middle" },
  );
}

function addSectionLabel(slide, text, position) {
  addText(slide, text, position, {
    fontSize: 15,
    bold: true,
    color: C.charcoal,
    verticalAlignment: "middle",
  });
  addRule(slide, position.left, position.top + position.height + 4, position.width, C.line, 1);
}

function addMetric(slide, value, label, position, accent = false) {
  addText(slide, value, { ...position, height: 40 }, {
    fontSize: 30,
    bold: true,
    color: accent ? C.orange : C.black,
  });
  addText(
    slide,
    label,
    { left: position.left, top: position.top + 44, width: position.width, height: position.height - 44 },
    { fontSize: 14, color: C.mid, lineSpacing: 1.05 },
  );
}

function addEditorialTable(slide, options) {
  const {
    left,
    top,
    width,
    height,
    headers,
    rows,
    columnWidths,
    aligns = [],
    fontSize = 12,
    headerFontSize = 11.5,
    rowHighlights = new Set(),
    rowHeight,
  } = options;
  const headerHeight = 34;
  const bodyHeight = height - headerHeight;
  const computedRowHeight = rowHeight || bodyHeight / Math.max(rows.length, 1);
  addRect(slide, { left, top, width, height: headerHeight }, C.black);
  let x = left;
  headers.forEach((header, index) => {
    const w = columnWidths[index];
    addText(slide, header, { left: x + 6, top: top + 3, width: w - 12, height: headerHeight - 6 }, {
      fontSize: headerFontSize,
      bold: true,
      color: C.white,
      alignment: aligns[index] || "left",
      verticalAlignment: "middle",
    });
    x += w;
  });
  rows.forEach((row, rowIndex) => {
    const y = top + headerHeight + rowIndex * computedRowHeight;
    const fill = rowHighlights.has(rowIndex)
      ? "#FFF1E6"
      : rowIndex % 2 === 1
        ? C.pale
        : C.white;
    addRect(slide, { left, top: y, width, height: computedRowHeight }, fill);
    addRule(slide, left, y + computedRowHeight - 1, width, C.line, 0.75);
    let cellX = left;
    row.forEach((cell, colIndex) => {
      const w = columnWidths[colIndex];
      addText(
        slide,
        cell,
        { left: cellX + 6, top: y + 3, width: w - 12, height: computedRowHeight - 6 },
        {
          fontSize,
          bold: rowHighlights.has(rowIndex) && colIndex <= 1,
          color: rowHighlights.has(rowIndex) && colIndex <= 1 ? C.orange : C.charcoal,
          alignment: aligns[colIndex] || "left",
          verticalAlignment: "middle",
          lineSpacing: 0.95,
        },
      );
      cellX += w;
    });
  });
}

function addNativeEditorialTable(slide, options) {
  const {
    left,
    top,
    width,
    height,
    headers,
    rows,
    columnWidths,
    aligns = [],
    fontSize = 9,
    headerFontSize = 8.5,
    rowHighlights = new Set(),
  } = options;
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
  const header = table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: headers.length });
  header.assign({
    fill: C.black,
    textStyle: {
      typeface: "Arial",
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
  table.rows[0].height = 22;
  rows.forEach((row, rowIndex) => {
    const fill = rowHighlights.has(rowIndex)
      ? "#FFF1E6"
      : rowIndex % 2 === 1
        ? C.pale
        : C.white;
    const range = table.cells.block({
      row: rowIndex + 1,
      column: 0,
      rowCount: 1,
      columnCount: headers.length,
    });
    range.assign({
      fill,
      textStyle: {
        typeface: "Arial",
        fontSize,
        color: C.charcoal,
        verticalAlignment: "middle",
        autoFit: "shrinkText",
        wrap: "square",
      },
      margins: { top: 1.5, right: 5, bottom: 1.5, left: 5 },
      anchor: "middle",
    });
    table.rows[rowIndex + 1].height = (height - 22) / Math.max(rows.length, 1);
  });
  aligns.forEach((alignment, columnIndex) => {
    const body = table.cells.block({
      row: 1,
      column: columnIndex,
      rowCount: rows.length,
      columnCount: 1,
    });
    body.textStyle.alignment = alignment;
    table.cells.block({ row: 0, column: columnIndex, rowCount: 1, columnCount: 1 }).textStyle.alignment = alignment;
  });
  return table;
}

function addFlatList(slide, items, position, options = {}) {
  const rowHeight = position.height / Math.max(items.length, 1);
  items.forEach((item, index) => {
    const y = position.top + index * rowHeight;
    if (index > 0) addRule(slide, position.left, y, position.width, C.line, 0.75);
    addText(
      slide,
      item.label,
      { left: position.left, top: y + 6, width: position.width * 0.53, height: rowHeight - 12 },
      { fontSize: options.fontSize || 14, bold: true, color: item.accent ? C.orange : C.charcoal, verticalAlignment: "middle" },
    );
    addText(
      slide,
      item.value,
      { left: position.left + position.width * 0.56, top: y + 6, width: position.width * 0.44, height: rowHeight - 12 },
      { fontSize: options.fontSize || 14, color: C.black, alignment: "right", verticalAlignment: "middle" },
    );
  });
}

function chartAxis(fontSize = 12, numberFormatCode) {
  return {
    visible: true,
    numberFormatCode,
    textStyle: { fill: C.note, fontSize },
    line: { style: "solid", fill: C.line, width: 1 },
    majorGridlines: { style: "solid", fill: C.light, width: 1 },
    minorGridlines: null,
  };
}

function addLegend(slide, entries, position, columns = 4) {
  const rows = Math.ceil(entries.length / columns);
  const cellW = position.width / columns;
  const cellH = position.height / rows;
  entries.forEach((entry, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    const x = position.left + col * cellW;
    const y = position.top + row * cellH;
    addRect(slide, { left: x, top: y + 5, width: 10, height: 10 }, entry.color, {
      lineFill: entry.line || "none",
      lineWidth: entry.line ? 1 : 0,
    });
    addText(
      slide,
      truncateWords(entry.label, 34),
      { left: x + 16, top: y, width: cellW - 20, height: cellH },
      { fontSize: 10.5, color: C.mid, verticalAlignment: "middle" },
    );
  });
}

function chartBase(position) {
  return {
    position,
    chartFill: "none",
    chartLine: { style: "solid", fill: "none", width: 0 },
    plotAreaFill: "none",
    plotAreaLine: { style: "solid", fill: "none", width: 0 },
  };
}

function addStraightLineChart(slide, options) {
  const categories = options.categories || [];
  const position = options.position;
  const labelIndices = options.labelIndices || categories.map((_, index) => index);
  const labelBand = options.labelBand ?? 18;
  const chartHeight = position.height - labelBand;
  const series = (options.series || []).map((item) => {
    const cleanValues = [];
    const xValues = [];
    (item.values || []).forEach((value, index) => {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) return;
      xValues.push(index);
      cleanValues.push(Number(value));
    });
    return {
      ...item,
      values: cleanValues,
      xValues,
      marker: { symbol: "none" },
    };
  });
  const chart = slide.charts.add("scatter", {
    ...chartBase({ ...position, height: chartHeight }),
    series,
    scatterOptions: { style: "line", varyColors: false },
    hasLegend: false,
    xAxis: {
      visible: false,
      tickLabelPosition: "none",
      min: 0,
      max: Math.max(1, categories.length - 1),
      majorGridlines: null,
      minorGridlines: null,
    },
    yAxis: options.yAxis,
  });
  const plotLeft = position.left + 52;
  const plotWidth = position.width - 72;
  labelIndices.forEach((index) => {
    const left =
      plotLeft +
      (categories.length <= 1 ? 0 : (index / (categories.length - 1)) * plotWidth) -
      28;
    addText(
      slide,
      categories[index],
      { left, top: position.top + chartHeight - 1, width: 56, height: labelBand + 2 },
      { fontSize: options.labelFontSize ?? 10, color: C.mid, alignment: "center" },
    );
  });
  return chart;
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function generateProviderFlowAssets() {
  if (!FLOW_BUILDER_PATH) {
    throw new Error(`Gerador dos fluxos não localizado: ${FLOW_BUILDER_NAME}`);
  }
  await fs.mkdir(FLOW_ASSET_DIR, { recursive: true });
  await fs.mkdir(path.dirname(OUTPUT_HTML), { recursive: true });
  const generated = spawnSync(
    process.execPath,
    [
      FLOW_BUILDER_PATH,
      "--payload",
      PAYLOAD_PATH,
      "--output-dir",
      FLOW_ASSET_DIR,
      "--html",
      OUTPUT_HTML,
    ],
    {
      encoding: "utf8",
      env: { ...process.env, CODEX_NODE_MODULES: NODE_MODULES },
      maxBuffer: 10 * 1024 * 1024,
    },
  );
  if (generated.error || generated.status !== 0) {
    throw new Error(
      `Falha ao gerar os fluxos navegáveis: ${generated.error?.message || generated.stderr || generated.stdout}`,
    );
  }
  const paths = {
    adminPng: path.join(FLOW_ASSET_DIR, "provider_flow_admin.png"),
    adminSvg: path.join(FLOW_ASSET_DIR, "provider_flow_admin.svg"),
    gestorPng: path.join(FLOW_ASSET_DIR, "provider_flow_gestor.png"),
    gestorSvg: path.join(FLOW_ASSET_DIR, "provider_flow_gestor.svg"),
    custodiantePng: path.join(FLOW_ASSET_DIR, "provider_flow_custodiante.png"),
    custodianteSvg: path.join(FLOW_ASSET_DIR, "provider_flow_custodiante.svg"),
    reagPng: path.join(FLOW_ASSET_DIR, "provider_flow_reag.png"),
    reagSvg: path.join(FLOW_ASSET_DIR, "provider_flow_reag.svg"),
    html: OUTPUT_HTML,
  };
  const entries = await Promise.all(
    Object.entries(paths).map(async ([key, filePath]) => {
      const stat = await fs.stat(filePath);
      if (!stat.isFile() || stat.size === 0) {
        throw new Error(`Artefato de fluxo vazio ou inválido: ${filePath}`);
      }
      return [key, filePath];
    }),
  );
  const verifiedPaths = Object.fromEntries(entries);
  const [adminPngBytes, gestorPngBytes, custodiantePngBytes, reagPngBytes] = await Promise.all([
    fs.readFile(verifiedPaths.adminPng),
    fs.readFile(verifiedPaths.gestorPng),
    fs.readFile(verifiedPaths.custodiantePng),
    fs.readFile(verifiedPaths.reagPng),
  ]);
  return {
    ...verifiedPaths,
    adminPngBytes: new Uint8Array(adminPngBytes),
    gestorPngBytes: new Uint8Array(gestorPngBytes),
    custodiantePngBytes: new Uint8Array(custodiantePngBytes),
    reagPngBytes: new Uint8Array(reagPngBytes),
    adminPngDataUrl: `data:image/png;base64,${adminPngBytes.toString("base64")}`,
    gestorPngDataUrl: `data:image/png;base64,${gestorPngBytes.toString("base64")}`,
    custodiantePngDataUrl: `data:image/png;base64,${custodiantePngBytes.toString("base64")}`,
    reagPngDataUrl: `data:image/png;base64,${reagPngBytes.toString("base64")}`,
  };
}

async function sha256File(filePath) {
  return createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

async function writeExportBundleManifest(payload, payloadRaw) {
  const payloadSha256 = createHash("sha256").update(payloadRaw).digest("hex");
  const rendererSha256 = await sha256File(__filename);
  const [pptxSha256, xlsxSha256, htmlSha256, pptxStat, xlsxStat, htmlStat] = await Promise.all([
    sha256File(OUTPUT_PPTX),
    sha256File(OUTPUT_XLSX),
    sha256File(OUTPUT_HTML),
    fs.stat(OUTPUT_PPTX),
    fs.stat(OUTPUT_XLSX),
    fs.stat(OUTPUT_HTML),
  ]);
  const manifest = {
    schema_version: "fidc_revision_export_bundle_v2",
    bundle_id: `${String(payload.latest_complete || "unknown").replace(/-/g, "")}_${payloadSha256.slice(0, 16)}`,
    payload_schema: payload.schema_version,
    latest_complete: payload.latest_complete,
    offers_as_of: payload.offers_as_of || null,
    source_signature: payloadSha256,
    payload_sha256: payloadSha256,
    renderer_version: RENDERER_VERSION,
    renderer_sha256: rendererSha256,
    generated_at: new Date().toISOString(),
    pptx: {
      filename: path.basename(OUTPUT_PPTX),
      sha256: pptxSha256,
      bytes: pptxStat.size,
      slides: EXPECTED_SLIDES,
    },
    xlsx: {
      filename: path.basename(OUTPUT_XLSX),
      sha256: xlsxSha256,
      bytes: xlsxStat.size,
    },
    html: {
      name: path.basename(OUTPUT_HTML),
      sha256: htmlSha256,
      bytes: htmlStat.size,
    },
    checks: {
      slides: EXPECTED_SLIDES,
      top20_fidcs: payload.top20_fidcs.length,
      top20_outros: payload.top20_outros.length,
      profiles: payload.profiles.length,
      market_share_combinations: new Set(
        payload.market_share.map(
          (row) => `${row.papel}|${row.tipo_anbima}|${row.foco_anbima}`,
        ),
      ).size,
    },
  };
  await fs.mkdir(path.dirname(EXPORT_MANIFEST_PATH), { recursive: true });
  const temporary = `${EXPORT_MANIFEST_PATH}.tmp-${process.pid}`;
  await fs.writeFile(temporary, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await fs.rename(temporary, EXPORT_MANIFEST_PATH);
}

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
    row.push(field);
    rows.push(row);
  }
  return rows;
}

async function readCsv(filePath) {
  const raw = await fs.readFile(filePath);
  const bytes = filePath.endsWith(".gz") ? zlib.gunzipSync(raw) : raw;
  const matrix = parseCsv(bytes.toString("utf8"));
  const headers = matrix.shift() || [];
  return { headers, rows: matrix };
}

function csvRowsAsObjects(csv) {
  return csv.rows.map((row) =>
    Object.fromEntries(csv.headers.map((header, index) => [header, row[index] ?? ""])),
  );
}

function asCell(value, header = "") {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value);
  if (/cnpj|documento|source|status|motivo|regra|nome|denominacao|competencia|foco|tipo|papel|grupo|modelo|evidencia|warning/i.test(header)) {
    return text;
  }
  if (/^(true|false)$/i.test(text)) return text.toLowerCase() === "true";
  const numeric = Number(text);
  return Number.isFinite(numeric) ? numeric : text;
}

function roleLabel(role) {
  return {
    administrador: "administração",
    gestor: "gestão",
    custodiante: "custódia",
  }[role] || role;
}

function marketChartData(payload, role, focusRows) {
  const fixed = payload.market_share_top10_fixed
    .filter((row) => row.papel === role)
    .sort((a, b) => num(a.rank_top10_geral) - num(b.rank_top10_geral))
    .map((row) => row.participante);
  const buckets = [...fixed, "Outros identificados", "Prestador não informado"];
  const categories = [];
  const blocked = [];
  let negativePl = 0;
  let negativeFunds = 0;
  const valuesByBucket = Object.fromEntries(buckets.map((bucket) => [bucket, []]));

  focusRows.forEach((focus) => {
    const scoped = payload.market_share.filter(
      (row) =>
        row.papel === role &&
        row.tipo_anbima === focus.tipo_anbima &&
        row.foco_anbima === focus.foco_anbima,
    );
    const status = scoped[0]?.publication_status || "";
    const isBlocked = String(status).startsWith("bloqueado");
    blocked.push(isBlocked);
    categories.push(
      `${focusShort(focus.tipo_anbima, focus.foco_anbima)}${isBlocked ? "*" : ""}`,
    );
    negativePl += Math.abs(num(scoped[0]?.pl_negativo_brl));
    negativeFunds += num(scoped[0]?.fundos_pl_negativo);
    const positive = buckets.map((bucket) => {
      const row = scoped.find((item) => item.participante_bucket === bucket);
      return isBlocked ? 0 : Math.max(0, num(row?.share_subtipo));
    });
    const total = positive.reduce((sum, value) => sum + value, 0);
    if (total > 0 && Math.abs(total - 1) > 1e-6) {
      throw new Error(
        `Market share não fecha 100%: ${role} · ${focus.tipo_anbima} · ${focus.foco_anbima} = ${total}`,
      );
    }
    buckets.forEach((bucket, index) => {
      valuesByBucket[bucket].push(total ? positive[index] : 0);
    });
  });
  const series = buckets.map((bucket) => ({
    name: providerShort(bucket),
    values: valuesByBucket[bucket].map((value) => value > 0 ? value : null),
    valuesFormatCode: "0.0%",
    fill: providerColor(bucket),
  }));
  return {
    categories,
    series,
    blocked,
    negativePl,
    negativeFunds,
    legend: buckets.map((bucket) => ({
      label: providerShort(bucket),
      color: providerColor(bucket),
      line: bucket === "Prestador não informado" ? C.line : undefined,
    })),
  };
}

function addMarketShareSlide(presentation, payload, role, focusRows, page, appendix = false) {
  const slide = presentation.slides.add();
  const data = marketChartData(payload, role, focusRows);
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  const scope = (payload.market_share_scope_summary || []).find((row) => row.papel === role) || {};
  const coverage = pct(scope.cobertura_classificacao_14_focos_pl, 1);
  const outside = pct(1 - num(scope.cobertura_classificacao_14_focos_pl), 1);
  const source = `Fonte: CVM/ANBIMA, ${stockShortLower}. Subtipo = Tipo+Foco ANBIMA (cadastro dez/25, evidência e proxy determinístico da Tabela II). PL ex-FIC sem Sistema Petrobras/TAPSO; cobertura ${coverage}, fora ${outside}.`;
  const titles = {
    administrador: appendix
      ? "Administração por subtipo: universo completo dos 14 focos"
      : "Bradesco e BTG lideram Recebíveis Comerciais após as exclusões",
    gestor: appendix
      ? "Gestão por subtipo: universo completo dos 14 focos"
      : "BTG lidera Crédito Pessoal; Top 10 soma 52% em Recebíveis Comerciais",
    custodiante: appendix
      ? "Custódia por subtipo: universo completo dos 14 focos"
      : "BTG e Oliveira Trust somam 54% de Crédito Pessoal",
  };
  addHeader(slide, appendix ? "APÊNDICE · MARKET SHARE" : `MARKET SHARE · ${roleLabel(role)}`, titles[role], source, page);
  const nativeSeries = data.series.map((series) => ({
    ...series,
    dataLabelOverrides: series.values.map((rawValue, idx) => {
      const value = num(rawValue);
      if (value <= 0) return { idx, showValue: false };
      return {
        idx,
        showValue: true,
        position: "center",
        text: value < 0.0005 ? "<0,1%" : undefined,
        textStyle: {
          fill: C.white,
          fontSize: 13.333333,
          bold: false,
        },
      };
    }),
  }));
  slide.charts.add("bar", {
    ...chartBase({ left: 64, top: 145, width: 1150, height: 455 }),
    categories: data.categories,
    series: nativeSeries,
    barOptions: {
      direction: "column",
      grouping: "percentStacked",
      gapWidth: appendix ? 32 : 48,
      overlap: 100,
    },
    hasLegend: true,
    legend: {
      position: "bottom",
      overlay: false,
      textStyle: { fill: C.mid, fontSize: appendix ? 8.5 : 9.5 },
    },
    xAxis: {
      visible: true,
      textStyle: { fill: C.mid, fontSize: appendix ? 9.5 : 11.5 },
      line: { style: "solid", fill: C.line, width: 1 },
      majorGridlines: null,
      minorGridlines: null,
    },
    yAxis: {
      ...chartAxis(10, "0%"),
      min: 0,
      max: 1,
      majorUnit: 0.25,
    },
    dataLabels: {
      showValue: true,
      position: "center",
      fill: "none",
      line: { style: "solid", fill: "none", width: 0 },
      textStyle: { fill: C.white, fontSize: 13.333333, bold: false },
    },
  });
  if (!appendix) {
    const omitted = payload.material_focus_omitted;
    addText(
      slide,
      `Corpo principal: 6 focos, ${pct(1 - num(omitted.share), 1)} do PL classificado. Fora do gráfico: ${omitted.focuses} focos e ${bn(omitted.pl, 1)}.`,
      { left: 72, top: 638, width: 1130, height: 20 },
      { fontSize: 10.5, color: C.note, alignment: "right" },
    );
  } else {
    const note = `Crédito Corporativo mantém 61 fundos; Coral FIDC (-R$ 20,9 mi; gestor/custodiante N/D) fica no QA e fora da normalização. No universo da função: ${integer(data.negativeFunds)} PLs negativos (${mm(data.negativePl, 1)}).`;
    addText(
      slide,
      "Proxy CVM quando ANBIMA e documentos não classificam: maior campo da Tabela II. Regras e cobertura no workbook.",
      { left: 72, top: 607, width: 1130, height: 24 },
      { fontSize: 9.3, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
    addText(slide, note, { left: 72, top: 635, width: 1130, height: 22 }, {
      fontSize: 9.5,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });
  }
  return slide;
}

function providerHistoricalRows(payload, role, limit = 6) {
  const all = (payload.provider_historical_ranking || []).filter((row) => row.papel === role);
  const latestAll = all
    .filter((row) => row.competencia === payload.latest_complete && row.participante !== "Não informado")
    .sort((a, b) => num(a.rank_periodo) - num(b.rank_periodo));
  const selected = latestAll.slice(0, limit);
  const itau = latestAll.find((row) => normalizeProviderName(row.participante) === "itau");
  if (itau && !selected.some((row) => row.participante === itau.participante)) selected.push(itau);
  const latest = selected.sort((a, b) => num(a.rank_periodo) - num(b.rank_periodo));
  const lookup = new Map(
    all.map((row) => [`${row.competencia}|${row.participante}`, row]),
  );
  return latest.map((current) => ({
    participante: current.participante,
    current,
    before2024: lookup.get(`2024-12|${current.participante}`),
    before2025: lookup.get(`2025-12|${current.participante}`),
  }));
}

function providerRankPlCell(row) {
  if (!row) return "—";
  return `${integer(row.rank_periodo)} · ${(num(row.pl_brl) / 1e9).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}`;
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function btgBankCohortContext(payload) {
  const metrics = payload.conclusion_metrics || {};
  const attribution = payload.provider_leadership_attribution?.btg
    || providerAttributionFallback(payload).btg
    || {};
  const scenarios = payload.btg_provider_ex_controlled_scenario || [];
  const managementScenario = scenarios.find((row) => row.papel === "gestor") || {};
  const providerCurrent = (payload.provider_historical_ranking || []).find(
    (row) => row.competencia === payload.latest_complete
      && row.papel === "gestor"
      && normalizeProviderName(row.participante) === "btg pactual",
  ) || {};
  const currentDetail = (payload.bank_fidc_detail || []).filter((row) => {
    const group = row.bank_group || row.grupo_bancario;
    return row.competencia === payload.latest_complete
      && ["BTG", "BTG Pactual"].includes(String(group || ""));
  });
  const observedDetail = currentDetail.filter(
    (row) => Boolean(row.observado) && num(row.pl_brl) > 0,
  );
  const listedRootsFromDetail = new Set(
    currentDetail.map((row) => String(row.cnpj_root8 || "").trim()).filter(Boolean),
  ).size;
  const observedFundsFromDetail = new Set(
    observedDetail.map((row) => String(row.cnpj_fundo || "").trim()).filter(Boolean),
  ).size;
  const cohortPlFromDetail = observedDetail.reduce((sum, row) => sum + num(row.pl_brl), 0);
  const managedPl = firstFiniteNumber(
    managementScenario.btg_pl_brl,
    attribution.managed_pl_brl,
    providerCurrent.pl_brl,
  );
  const managementExcludedFunds = firstFiniteNumber(
    managementScenario.fidcs_coorte_bancaria_excluidos,
    managementScenario.fidcs_controlados_excluidos,
    metrics.btg_bank_cohort_combo_funds,
    metrics.btg_controlados_df_excluidos_fundos,
  );
  const managementExcludedPl = firstFiniteNumber(
    managementScenario.pl_coorte_bancaria_excluido_brl,
    managementScenario.pl_controlado_excluido_brl,
    metrics.btg_bank_cohort_combo_pl_brl,
    attribution.bank_cohort_pl_brl,
    attribution.confirmed_controlled_pl_brl,
  );
  return {
    listedRoots: firstFiniteNumber(
      metrics.btg_bank_cohort_listed_roots,
      listedRootsFromDetail,
      metrics.btg_controlados_df_excluidos_fundos,
    ),
    observedFunds: firstFiniteNumber(
      metrics.btg_bank_cohort_observed_funds,
      observedFundsFromDetail,
      metrics.btg_controlados_df_excluidos_fundos,
    ),
    cohortPl: firstFiniteNumber(
      metrics.btg_bank_cohort_pl_brl,
      cohortPlFromDetail,
      attribution.bank_cohort_pl_brl,
      metrics.btg_controlados_df_excluidos_pl_brl,
      attribution.confirmed_controlled_pl_brl,
    ),
    comboFunds: firstFiniteNumber(
      metrics.btg_bank_cohort_combo_funds,
      metrics.btg_controlados_df_excluidos_fundos,
    ),
    comboPl: firstFiniteNumber(
      metrics.btg_bank_cohort_combo_pl_brl,
      attribution.bank_cohort_pl_brl,
      metrics.btg_controlados_df_excluidos_pl_brl,
      attribution.confirmed_controlled_pl_brl,
    ),
    managedPl,
    managementExcludedFunds,
    managementExcludedPl,
    residualManagedPl: firstFiniteNumber(
      managementScenario.btg_pl_ex_controlados_brl,
      attribution.residual_ex_bank_cohort_pl_brl,
      attribution.residual_unproven_pl_brl,
      Math.max(0, managedPl - managementExcludedPl),
    ),
    currentManagementRank: firstFiniteNumber(
      managementScenario.btg_rank,
      providerCurrent.rank_periodo,
      1,
    ),
    residualManagementRank: firstFiniteNumber(
      managementScenario.btg_rank_ex_controlados,
      attribution.rank_ex_bank_cohort,
      attribution.rank_without_confirmed,
      2,
    ),
  };
}

function addProviderHistoricalRankingSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const stockShort = competenceShortPt(payload.latest_complete);
  const btgScenario = new Map(
    (payload.btg_provider_ex_controlled_scenario || []).map((row) => [row.papel, row]),
  );
  const managementScenario = btgScenario.get("gestor") || {};
  const managementExcludedFunds = firstFiniteNumber(
    managementScenario.fidcs_coorte_bancaria_excluidos,
    managementScenario.fidcs_controlados_excluidos,
  );
  const managementExcludedPl = firstFiniteNumber(
    managementScenario.pl_coorte_bancaria_excluido_brl,
    managementScenario.pl_controlado_excluido_brl,
  );
  addHeader(
    slide,
    "PRESTADORES · EVOLUÇÃO DO RANKING",
    `BTG fica em #2 na administração e custódia; na gestão, o cenário sem a coorte bancária muda a posição de #${integer(managementScenario.btg_rank)} para #${integer(managementScenario.btg_rank_ex_controlados)}`,
    `Fonte: CVM e FIDCs.xlsx, aba BTG. PL ex-FIC; Sistema Petrobras e TAPSO excluídos. Na gestão, o cenário retira ${integer(managementExcludedFunds)} FIDCs e ${bn(managementExcludedPl, 1)}; o recorte não atribui controle societário.`,
    page,
  );
  const bands = [
    { role: "administrador", label: "ADMINISTRAÇÃO", top: 126 },
    { role: "gestor", label: "GESTÃO", top: 305 },
    { role: "custodiante", label: "CUSTÓDIA", top: 484 },
  ];
  bands.forEach(({ role, label, top }) => {
    const rows = providerHistoricalRows(payload, role, 6);
    const chartRows = [...rows].reverse();
    addText(slide, label, { left: 60, top, width: 690, height: 20 }, {
      fontSize: 12.5,
      bold: true,
      color: C.charcoal,
      verticalAlignment: "middle",
    });
    addText(slide, "POSIÇÃO · PL (R$ BI) · BTG SEM COORTE NA ÚLTIMA COLUNA", { left: 405, top, width: 345, height: 20 }, {
      fontSize: 9.5,
      bold: true,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });
    addNativeEditorialTable(slide, {
      left: 60,
      top: top + 23,
      width: 690,
      height: 145,
      headers: ["Participante", "Dez/24", "Dez/25", stockShort],
      rows: rows.map((row) => {
        const currentCell = providerRankPlCell(row.current);
        const scenario = btgScenario.get(role);
        const latestCell = normalizeProviderName(row.participante) === "btg pactual" && scenario
          ? `${currentCell}\ns/ coorte ${integer(scenario.btg_rank_ex_controlados)} · ${(num(scenario.btg_pl_ex_controlados_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`
          : currentCell;
        return [
          providerShort(row.participante),
          providerRankPlCell(row.before2024),
          providerRankPlCell(row.before2025),
          latestCell,
        ];
      }),
      columnWidths: [300, 125, 125, 140],
      aligns: ["left", "right", "right", "right"],
      fontSize: 8.1,
      headerFontSize: 8.1,
      rowHighlights: new Set(rows.map((row, idx) => normalizeProviderName(row.participante) === "itau" ? idx : -1).filter((idx) => idx >= 0)),
    });
    addText(slide, `PL ${stockShort.toUpperCase()} · R$ BI`, { left: 785, top, width: 435, height: 20 }, {
      fontSize: 10,
      bold: true,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 785, top: top + 23, width: 435, height: 145 }),
      categories: chartRows.map((row) => providerShort(row.participante)),
      series: [
        {
          name: `PL ${stockShort.toLowerCase()}`,
          values: chartRows.map((row) => num(row.current?.pl_brl) / 1e9),
          valuesFormatCode: "0.0",
          fill: C.charcoal,
          points: chartRows.map((row, idx) => ({ idx, fill: providerColor(row.participante) })),
        },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 28 },
      hasLegend: false,
      xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
      yAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 8.3 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      dataLabels: {
        showValue: true,
        position: "inEnd",
        fill: "none",
        line: { style: "solid", fill: "none", width: 0 },
        textStyle: { fill: C.white, fontSize: 10, bold: false },
      },
    });
  });
  return slide;
}

function independentProviderRows(payload, role, limit = 6) {
  const all = (payload.provider_independent_ranking || []).filter(
    (row) => row.papel === role,
  );
  const participant = (row) => row.participante || row.grupo_normalizado || row.grupo || "";
  const independentRank = (row) =>
    num(row.rank_independente || row.rank_independent || row.posicao_independentes, 9999);
  const latest = all
    .filter((row) => row.competencia === payload.latest_complete)
    .sort((a, b) => independentRank(a) - independentRank(b))
    .slice(0, limit);
  const lookup = new Map(
    all.map((row) => [`${row.competencia}|${participant(row)}`, row]),
  );
  return latest.map((current) => ({
    participante: participant(current),
    current,
    before2024: lookup.get(`2024-12|${participant(current)}`),
    before2025: lookup.get(`2025-12|${participant(current)}`),
  }));
}

function independentRankPlCell(row) {
  if (!row) return "—";
  const rankIndependent = num(
    row.rank_independente || row.rank_independent || row.posicao_independentes,
  );
  const rankGeneral = num(row.rank_geral || row.rank_periodo || row.posicao_geral);
  const ranks = rankGeneral
    ? `${integer(rankIndependent)}/${integer(rankGeneral)}`
    : integer(rankIndependent);
  return `${ranks} · ${(num(row.pl_brl) / 1e9).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}`;
}

function addIndependentProviderRankingSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const stockShort = competenceShortPt(payload.latest_complete);
  const currentAdmin = independentProviderRows(payload, "administrador", 6)[0];
  const currentCustody = independentProviderRows(payload, "custodiante", 6)[0];
  addHeader(
    slide,
    "PRESTADORES INDEPENDENTES · EVOLUÇÃO",
    `QI lidera administração e custódia entre independentes, com ${bn(currentAdmin?.current?.pl_brl, 1)} e ${bn(currentCustody?.current?.pl_brl, 1)}`,
    "Fonte: CVM, PL ex-FIC. Sistema Petrobras e TAPSO excluídos. Posição = ranking entre independentes / ranking geral; Singulare consolidada em QI Tech; Kanastra alocada ao Itaú pela regra de afiliação explicitada no workbook.",
    page,
  );
  const bands = [
    { role: "administrador", label: "ADMINISTRAÇÃO", top: 126 },
    { role: "gestor", label: "GESTÃO", top: 305 },
    { role: "custodiante", label: "CUSTÓDIA", top: 484 },
  ];
  bands.forEach(({ role, label, top }) => {
    const rows = independentProviderRows(payload, role, 6);
    const chartRows = [...rows].reverse();
    addText(slide, label, { left: 60, top, width: 690, height: 20 }, {
      fontSize: 12.5,
      bold: true,
      color: C.charcoal,
      verticalAlignment: "middle",
    });
    addText(slide, "POS. INDEP./GERAL · PL (R$ BI)", { left: 430, top, width: 320, height: 20 }, {
      fontSize: 9.3,
      bold: true,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });
    addNativeEditorialTable(slide, {
      left: 60,
      top: top + 23,
      width: 690,
      height: 145,
      headers: ["Participante", "Dez/24", "Dez/25", stockShort],
      rows: rows.map((row) => [
        providerShort(row.participante),
        independentRankPlCell(row.before2024),
        independentRankPlCell(row.before2025),
        independentRankPlCell(row.current),
      ]),
      columnWidths: [300, 125, 125, 140],
      aligns: ["left", "right", "right", "right"],
      fontSize: 8.1,
      headerFontSize: 8.1,
    });
    addText(slide, `PL ${stockShort.toUpperCase()} · R$ BI`, { left: 785, top, width: 435, height: 20 }, {
      fontSize: 10,
      bold: true,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 785, top: top + 23, width: 435, height: 145 }),
      categories: chartRows.map((row) => providerShort(row.participante)),
      series: [{
        name: `PL ${stockShort.toLowerCase()}`,
        values: chartRows.map((row) => num(row.current?.pl_brl) / 1e9),
        valuesFormatCode: "0.0",
        fill: C.charcoal,
        points: chartRows.map((row, idx) => ({ idx, fill: providerColor(row.participante) })),
      }],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 28 },
      hasLegend: false,
      xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
      yAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 8.3 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      dataLabels: {
        showValue: true,
        position: "inEnd",
        fill: "none",
        line: { style: "solid", fill: "none", width: 0 },
        textStyle: { fill: C.white, fontSize: 10, bold: false },
      },
    });
  });
  return slide;
}

function bankGroupColor(group) {
  const normalized = normalizeProviderName(group);
  if (normalized.includes("itau")) return providerColor("Itaú");
  if (normalized.includes("btg")) return providerColor("BTG Pactual");
  if (normalized.includes("banco do brasil") || normalized === "bb") return providerColor("Banco do Brasil");
  if (normalized.includes("bradesco")) return "#454A4F";
  if (normalized.includes("santander")) return "#8D9399";
  return C.mid;
}

function addBankFidcEvolutionSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const stockShort = competenceShortPt(payload.latest_complete);
  const stockShortLower = stockShort.toLowerCase();
  const rows = payload.bank_fidc_evolution || [];
  const periods = ["2023-12", "2024-12", "2025-12", payload.latest_complete];
  const groups = ["BTG Pactual", "Itaú", "Santander", "Bradesco", "Banco do Brasil"];
  const lookup = new Map(
    rows.map((row) => [`${row.competencia}|${row.grupo_bancario || row.grupo}`, row]),
  );
  const value = (period, group) => {
    const row = lookup.get(`${period}|${group}`);
    if (!row || row.observado === false || row.observed === false) return null;
    return num(row.pl_bruto_brl ?? row.pl_brl) / 1e9;
  };
  const latestRows = groups.map((group) => lookup.get(`${payload.latest_complete}|${group}`)).filter(Boolean);
  const latestTotal = latestRows.reduce((sum, row) => sum + num(row.pl_bruto_brl ?? row.pl_brl), 0);
  const btg = lookup.get(`${payload.latest_complete}|BTG Pactual`);
  const btgConsignadosDec25 = (payload.bank_fidc_detail || []).find(
    (row) => row.competencia === "2025-12"
      && row.grupo_bancario === "BTG Pactual"
      && String(row.cnpj_root8 || "") === "50906397",
  ) || {};
  const btgTop5 = (payload.bank_fidc_detail || [])
    .filter((row) => row.competencia === payload.latest_complete && row.grupo_bancario === "BTG Pactual" && row.observado !== false)
    .sort((a, b) => num(b.pl_brl) - num(a.pl_brl))
    .slice(0, 5);
  addHeader(
    slide,
    "FIDCs DOS CINCO BANCOS · COORTE ATUAL",
    `BTG soma ${bn(btg?.pl_bruto_brl ?? btg?.pl_brl, 1)} em ${stockShortLower}; Consignados I adiciona ${bn(btgConsignadosDec25.pl_brl, 1)} ao PL de dez/25*`,
    "Fonte: CVM, Fundos.NET, FIDCs.xlsx e conglomerados prudenciais BCB consultados em jul/26. Coorte fixa das raízes hoje listadas; PL bruto. O histórico não recupera fundos que saíram do conglomerado atual.",
    page,
  );
  addSectionLabel(slide, "PL BRUTO DA COORTE FIXA · R$ BI", { left: 60, top: 145, width: 720, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 60, top: 185, width: 720, height: 385 }),
    categories: periods.map((period) => `${competenceShortPt(period)}${period === "2025-12" ? "*" : ""}`),
    series: groups.map((group) => ({
      name: group,
      values: periods.map((period) => value(period, group)),
      valuesFormatCode: "0.0",
      fill: bankGroupColor(group),
    })),
    barOptions: { direction: "column", grouping: "stacked", gapWidth: 45, overlap: 100 },
    hasLegend: true,
    legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 9.5 } },
    xAxis: {
      visible: true,
      textStyle: { fill: C.mid, fontSize: 11 },
      line: { style: "solid", fill: C.line, width: 1 },
      majorGridlines: null,
    },
    yAxis: { ...chartAxis(9.5, "0"), min: 0 },
    dataLabels: { showValue: false },
  });
  addSectionLabel(slide, `BTG · CINCO MAIORES EM ${stockShort.toUpperCase()}`, { left: 825, top: 145, width: 395, height: 24 });
  addNativeEditorialTable(slide, {
    left: 825,
    top: 185,
    width: 395,
    height: 290,
    headers: ["Banco", "FIDC", "PL · R$ mi"],
    rows: btgTop5.map((row) => [
      "BTG",
      row.nome_curto || truncateWords(row.denominacao, 35),
      (num(row.pl_brl) / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 0 }),
    ]),
    columnWidths: [55, 245, 95],
    aligns: ["left", "left", "right"],
    fontSize: 9.2,
    headerFontSize: 8.8,
    rowHighlights: new Set([0]),
  });
  const totalByPeriod = periods.map((period) => groups.reduce((sum, group) => sum + (value(period, group) || 0), 0));
  addText(slide, `${totalByPeriod.at(-1).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} bi`, { left: 845, top: 500, width: 355, height: 40 }, {
    fontSize: 28,
    bold: true,
    color: C.orange,
  });
  addText(
    slide,
    `PL bruto da coorte dos cinco bancos em ${competenceShortPt(payload.latest_complete).toLowerCase()}. * Dez/25 usa ${bn(btgConsignadosDec25.pl_brl, 1)} do IME v2 Fundos.NET 1100733, confirmado pela DF auditada 1150673; o XML traz competência interna divergente e o parser havia lido zero.`,
    { left: 845, top: 548, width: 355, height: 86 },
    { fontSize: 11.4, color: C.mid },
  );
  return slide;
}

function addAcquiringReclassificationSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const rows = payload.acquiring_reclassified_mix || [];
  const beforePeriod = "2023-12";
  const afterPeriod = payload.latest_complete;
  const afterShort = competenceShortPt(afterPeriod);
  const afterShortLower = afterShort.toLowerCase();
  const before = rows.filter((row) => row.competencia === beforePeriod);
  const after = rows.filter((row) => row.competencia === afterPeriod);
  const category = (row) => row.categoria_analitica || row.segmento_reclassificado || row.segmento;
  const beforeMap = Object.fromEntries(before.map((row) => [category(row), row]));
  const afterMap = Object.fromEntries(after.map((row) => [category(row), row]));
  const categories = [...after]
    .sort((a, b) => num(b.pl_brl ?? b.pl) - num(a.pl_brl ?? a.pl))
    .map(category);
  const acquiring = afterMap["Adquirência"] || {};
  const curatedCount = integer(acquiring.fundos_adquirencia_curados);
  const observedCount = num(acquiring.fundos_adquirencia_observados);
  const missingCount = Math.max(0, num(acquiring.fundos_adquirencia_curados) - observedCount);
  const auditSummary = payload.card_taxonomy_summary || {};
  const shareValue = (row) => num(row?.share_pl ?? row?.share);
  const plValue = (row) => num(row?.pl_brl ?? row?.pl);
  addHeader(
    slide,
    "TAXONOMIA CVM · RECLASSIFICAÇÃO DE ADQUIRÊNCIA",
    `Os ${curatedCount} CNPJs selecionados formam Adquirência; ${bn(plValue(acquiring), 1)} e ${pct(shareValue(acquiring), 1)} do PL ex-FIC em ${afterShortLower}`,
    "Fonte: CVM, Informe Mensal e regulamentos no FundosNet. Curadoria em 21/jul/26; a categoria CVM original permanece preservada.",
    page,
  );
  addSectionLabel(slide, `PL EX-FIC · R$ BI · DEZ/23 → ${afterShort.toUpperCase()}`, { left: 60, top: 150, width: 550, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 60, top: 185, width: 550, height: 400 }),
    categories,
    series: [
      {
        name: "Dez/23",
        values: categories.map((name) => plValue(beforeMap[name]) / 1e9),
        valuesFormatCode: "0.0",
        fill: C.mid,
      },
      {
        name: competenceShortPt(afterPeriod),
        values: categories.map((name) => plValue(afterMap[name]) / 1e9),
        valuesFormatCode: "0.0",
        fill: C.orange,
      },
    ],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 35 },
    hasLegend: false,
    xAxis: { ...chartAxis(9.5, "0"), min: 0 },
    yAxis: {
      visible: true,
      textStyle: { fill: C.mid, fontSize: 9.6 },
      line: { style: "solid", fill: C.line, width: 1 },
      majorGridlines: null,
    },
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.7, bold: true } },
  });
  addSectionLabel(slide, `% DO PL EX-FIC · DEZ/23 → ${afterShort.toUpperCase()}`, { left: 670, top: 150, width: 550, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 670, top: 185, width: 550, height: 400 }),
    categories,
    series: [
      {
        name: "Dez/23",
        values: categories.map((name) => shareValue(beforeMap[name])),
        valuesFormatCode: "0.0%",
        fill: C.mid,
      },
      {
        name: competenceShortPt(afterPeriod),
        values: categories.map((name) => shareValue(afterMap[name])),
        valuesFormatCode: "0.0%",
        fill: C.orange,
      },
    ],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 35 },
    hasLegend: false,
    xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
    yAxis: {
      visible: true,
      textStyle: { fill: C.mid, fontSize: 9.6 },
      line: { style: "solid", fill: C.line, width: 1 },
      majorGridlines: null,
    },
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.7, bold: true } },
  });
  addLegend(slide, [
    { label: "Dez/23", color: C.mid },
    { label: competenceShortPt(afterPeriod), color: C.orange },
  ], { left: 930, top: 126, width: 290, height: 22 }, 2);
  addText(
    slide,
    `Bucket Cartão: ${integer(auditSummary.fundos_incluidos_adquirencia)} incluídos, ${integer(auditSummary.fundos_fora_adquirencia)} fora e ${integer(auditSummary.fundos_pendentes_curadoria)} pendentes. Em ${afterShortLower}, ${integer(observedCount)} dos ${curatedCount} CNPJs selecionados têm reporte ativo; ${integer(missingCount)} não reportam.`,
    { left: 60, top: 625, width: 1160, height: 30 },
    { fontSize: 10.7, color: C.note, alignment: "right", verticalAlignment: "middle" },
  );
  return slide;
}

function providerAttributionFallback(payload) {
  const ranking = payload.provider_historical_ranking || [];
  const current = (role, provider) => ranking.find(
    (row) => row.competencia === payload.latest_complete
      && row.papel === role
      && normalizeProviderName(row.participante) === normalizeProviderName(provider),
  );
  return {
    btg: {
      managed_pl_brl: num(current("gestor", "BTG Pactual")?.pl_brl),
      bank_cohort_pl_brl: 28_641_000_000,
      residual_ex_bank_cohort_pl_brl: Math.max(0, num(current("gestor", "BTG Pactual")?.pl_brl) - 28_641_000_000),
      bradesco_managed_pl_brl: num(current("gestor", "Bradesco")?.pl_brl),
      bank_cohort_share: num(current("gestor", "BTG Pactual")?.pl_brl)
        ? 28_641_000_000 / num(current("gestor", "BTG Pactual")?.pl_brl)
        : 0,
      rank_ex_bank_cohort: 2,
    },
    qi: {
      admin_group_pl_2024_brl: 87_040_000_000,
      legacy_singulare_pl_2024_brl: 83_490_000_000,
      original_qi_pl_2024_brl: 3_550_000_000,
      legacy_share_2024: 0.959,
    },
  };
}

function addProviderAttributionSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const stockShort = competenceShortPt(payload.latest_complete);
  const attribution = payload.provider_leadership_attribution || providerAttributionFallback(payload);
  const qi = attribution.qi || {};
  const btg = attribution.btg || {};
  const bankCohort = btgBankCohortContext(payload);
  const qiTotal = num(qi.admin_group_pl_2024_brl)
    || num(qi.legacy_singulare_pl_2024_brl) + num(qi.original_qi_pl_2024_brl);
  const managed = firstFiniteNumber(bankCohort.managedPl, btg.managed_pl_brl);
  const cohortManaged = firstFiniteNumber(
    bankCohort.managementExcludedPl,
    btg.bank_cohort_pl_brl,
    btg.confirmed_controlled_pl_brl,
  );
  const residual = firstFiniteNumber(
    bankCohort.residualManagedPl,
    btg.residual_ex_bank_cohort_pl_brl,
    btg.residual_unproven_pl_brl,
    Math.max(0, managed - cohortManaged),
  );
  const bradesco = num(btg.bradesco_managed_pl_brl);
  addHeader(
    slide,
    "PRESTADORES · LIDERANÇA EXPLICADA",
    `Singulare sustenta a escala da QI; sem a coorte bancária, o BTG fica em #${integer(bankCohort.residualManagementRank)} na gestão`,
    "Fontes: CVM; BCB, alterações societárias nov/24–nov/25; FIDCs.xlsx, aba BTG. PL ex-FIC, sem Sistema Petrobras/TAPSO.",
    page,
  );

  addSectionLabel(slide, "QI TECH · ADMINISTRAÇÃO EM DEZ/24", { left: 60, top: 145, width: 535, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 60, top: 190, width: 535, height: 230 }),
    categories: ["Singulare legado", "QI DTVM original"],
    series: [
      {
        name: "PL administrado",
        values: [
          num(qi.legacy_singulare_pl_2024_brl) / 1e9,
          num(qi.original_qi_pl_2024_brl) / 1e9,
        ],
        valuesFormatCode: "0.0",
        fill: providerColor("QI Tech"),
        points: [
          { idx: 0, fill: providerColor("QI Tech") },
          { idx: 1, fill: providerColor("QI Tech") },
        ],
      },
    ],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 45 },
    hasLegend: false,
    xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
    yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
    dataLabels: { showValue: true, position: "outEnd", fill: "none", line: { style: "solid", fill: "none", width: 0 }, textStyle: { fill: C.black, fontSize: 10, bold: false } },
  });
  addMetric(
    slide,
    pct(num(qi.legacy_share_2024) || (qiTotal ? num(qi.legacy_singulare_pl_2024_brl) / qiTotal : 0), 1),
    "do PL administrado do grupo em dez/24 estava no CNPJ legado da Singulare. O controle mudou em nov/24; em nov/25, esse CNPJ incorporou a QI DTVM e passou a QI Corretora.",
    { left: 80, top: 450, width: 495, height: 130 },
    true,
  );

  addSectionLabel(slide, `BTG PACTUAL · GESTÃO EM ${stockShort.toUpperCase()}`, { left: 665, top: 145, width: 555, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 665, top: 190, width: 555, height: 230 }),
    categories: ["BTG Pactual", "Bradesco", "BTG sem coorte bancária"],
    series: [
      {
        name: "PL gerido",
        values: [managed / 1e9, bradesco / 1e9, residual / 1e9],
        valuesFormatCode: "0.0",
        fill: providerColor("BTG Pactual"),
        points: [
          { idx: 0, fill: providerColor("BTG Pactual") },
          { idx: 1, fill: providerColor("Bradesco") },
          { idx: 2, fill: providerColor("BTG Pactual") },
        ],
      },
    ],
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 40 },
    hasLegend: false,
    xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
    yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
    dataLabels: { showValue: true, position: "inEnd", fill: "none", line: { style: "solid", fill: "none", width: 0 }, textStyle: { fill: C.white, fontSize: 10, bold: false } },
  });
  addMetric(
    slide,
    bn(cohortManaged, 1),
    `${pct(managed ? cohortManaged / managed : 0, 1)} do PL gerido pelo BTG está nos ${integer(bankCohort.managementExcludedFunds)} FIDCs da coorte com o BTG como gestor. A exclusão leva o banco de #${integer(bankCohort.currentManagementRank)} a #${integer(bankCohort.residualManagementRank)}.`,
    { left: 685, top: 450, width: 515, height: 118 },
    true,
  );
  addText(
    slide,
    `A aba BTG de FIDCs.xlsx lista ${integer(bankCohort.listedRoots)} raízes; ${integer(bankCohort.observedFunds)} tinham PL observado em ${stockShort.toLowerCase()}, somando ${bn(bankCohort.cohortPl, 1)}. A lista define o recorte analítico; controle societário exige evidência documental específica.`,
    { left: 685, top: 575, width: 515, height: 64 },
    { fontSize: 10.6, color: C.mid, lineSpacing: 1.01 },
  );
  return slide;
}

function fallbackReagFlow() {
  return {
    summary: {
      funds_origin: 131,
      pl_origin_brl: 66.327e9,
      continuing_funds: 115,
      continuing_pl_current_brl: 52.889e9,
      migrated_pl_current_brl: 10.233e9,
      migrated_share_current: 0.1935,
    },
    links: [
      { destino_grupo: "CBSF ainda declarada", fundos: 70, pl_current_brl: 42.656e9, pl_flow_brl: 41.924e9 },
      { destino_grupo: "Master Corretora", fundos: 8, pl_current_brl: 6.451e9, pl_flow_brl: 6.35e9 },
      { destino_grupo: "Planner", fundos: 31, pl_current_brl: 3.651e9, pl_flow_brl: 3.55e9 },
      { destino_grupo: "Outros migrados", fundos: 6, pl_current_brl: 0.131e9, pl_flow_brl: 0.333e9 },
      { destino_grupo: "Saída / sem reporte", fundos: 16, pl_current_brl: 0, pl_flow_brl: 14.17e9 },
    ],
  };
}

function addProviderFlowSnapshot(slide, pngBytes, alt) {
  if (!pngBytes?.byteLength) {
    throw new Error(`Imagem do fluxo ausente: ${alt}`);
  }
  slide.images.add({
    blob: pngBytes,
    contentType: "image/png",
    alt,
    fit: "contain",
    position: { left: 60, top: 118, width: 1160, height: 540 },
  });
}

function addFrozenDelinquencyHistorySlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const start = "2023-12";
  const end = String(payload.latest_complete || "");
  const endShort = competenceShortPt(end);
  const endShortLower = endShort.toLowerCase();
  const rows = (payload.delinquency_frozen_cohort_history || []).filter(
    (row) => String(row.competencia) >= start && String(row.competencia) <= end,
  );
  const latestRows = rows
    .filter((row) => String(row.competencia) === end)
    .sort((a, b) => num(b.pl_coorte_referencia_brl) - num(a.pl_coorte_referencia_brl));
  const categories = [...new Set(rows.map((row) => String(row.competencia)))].sort();
  const bySubtype = new Map();
  rows.forEach((row) => {
    const key = String(row.tipo_recebivel_tabela_ii || "N/D");
    if (!bySubtype.has(key)) bySubtype.set(key, new Map());
    bySubtype.get(key).set(String(row.competencia), row);
  });
  const aggregate = new Map(
    (payload.qa_series || [])
      .filter((row) => String(row.competencia) >= start && String(row.competencia) <= end)
      .map((row) => [String(row.competencia), row]),
  );
  const latestAggregate = aggregate.get(end) || {};
  const palette = [
    C.black,
    C.charcoal,
    "#454A4F",
    "#5B6065",
    C.mid,
    C.note,
    "#A7ACB0",
    "#BEC2C5",
    "#676C71",
    "#92979C",
  ];
  addHeader(
    slide,
    "INADIMPLÊNCIA · COORTE ATUAL POR RECEBÍVEL",
    `Financeiro encerra ${endShortLower} em ${pct(latestRows.find((row) => row.tipo_recebivel_tabela_ii === "Financeiro")?.inadimplencia_sobre_carteira, 1)}; a coorte fixa soma ${bn(latestRows.reduce((sum, row) => sum + num(row.pl_coorte_referencia_brl), 0), 1)}`,
    `Fonte: CVM, Informe Mensal. CNPJs monotipo em ${endShortLower} aplicados ao histórico; laranja = mercado ajustado. Há viés de sobrevivência.`,
    page,
  );
  addSectionLabel(slide, `% DA CARTEIRA · DEZ/23 → ${endShort.toUpperCase()}`, { left: 60, top: 137, width: 780, height: 24 });
  addStraightLineChart(slide, {
    position: { left: 60, top: 172, width: 780, height: 385 },
    categories: categories.map((competence) => {
      const [year, month] = competence.split("-");
      return `${month}/${year.slice(2)}`;
    }),
    series: [
      ...latestRows.map((latest, index) => ({
        name: latest.tipo_recebivel_tabela_ii,
        values: categories.map((competence) => bySubtype.get(latest.tipo_recebivel_tabela_ii)?.get(competence)?.inadimplencia_sobre_carteira ?? null),
        valuesFormatCode: "0.0%",
        line: { style: "solid", fill: palette[index % palette.length], width: index < 3 ? 2 : 1.35 },
      })),
      {
        name: "Consolidado ajustado",
        values: categories.map((competence) => aggregate.get(competence)?.inadimplencia_ajustada_pct ?? null),
        valuesFormatCode: "0.0%",
        line: { style: "solid", fill: C.orange, width: 3.2 },
      },
    ],
    yAxis: { ...chartAxis(9, "0%"), min: 0, max: 0.3, majorUnit: 0.05 },
    labelIndices: categories.map((_, index) => index).filter((index) => index % 4 === 0 || index === categories.length - 1),
    labelFontSize: 8.2,
  });
  addSectionLabel(slide, `FOTOGRAFIA · ${competenceShortPt(end).toUpperCase()}`, { left: 865, top: 137, width: 355, height: 24 });
  addNativeEditorialTable(slide, {
    left: 865,
    top: 172,
    width: 355,
    height: 385,
    headers: ["Tipo Tabela II", "Fundos", "PL bi", "Inad./cart."],
    rows: latestRows.map((row) => [
      row.tipo_recebivel_tabela_ii,
      integer(row.fundos_coorte),
      (num(row.pl_coorte_referencia_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
      pct(row.inadimplencia_sobre_carteira, 1),
    ]),
    columnWidths: [150, 55, 65, 85],
    aligns: ["left", "right", "right", "right"],
    fontSize: 7.6,
    headerFontSize: 7.3,
    rowHighlights: new Set(latestRows.map((row, index) => row.tipo_recebivel_tabela_ii === "Financeiro" ? index : -1).filter((index) => index >= 0)),
  });
  addLegend(
    slide,
    [
      ...latestRows.map((row, index) => ({ label: row.tipo_recebivel_tabela_ii, color: palette[index % palette.length] })),
      { label: "Consolidado ajustado", color: C.orange },
    ],
    { left: 60, top: 570, width: 1160, height: 52 },
    6,
  );
  addText(
    slide,
    `Coorte: ${integer(latestRows.reduce((sum, row) => sum + num(row.fundos_coorte), 0))} fundos e ${bn(latestRows.reduce((sum, row) => sum + num(row.pl_coorte_referencia_brl), 0), 1)}; consolidado ajustado ${pct(latestAggregate.inadimplencia_ajustada_pct, 1)}. Factoring e Imobiliário têm base pequena.`,
    { left: 60, top: 632, width: 1160, height: 28 },
    { fontSize: 9.8, color: C.note, alignment: "right", verticalAlignment: "middle" },
  );
  return slide;
}

function addReagMigrationSlide(presentation, payload, page, pngBytes) {
  const slide = presentation.slides.add();
  const fallback = fallbackReagFlow();
  const summary = payload.reag_admin_summary || payload.reag_admin_migration?.summary || fallback.summary;
  const destinationCompetence = summary.competencia_destino || payload.latest_complete;
  const destinationShort = competenceShortPt(destinationCompetence);
  const destinationShortLower = destinationShort.toLowerCase();
  const masterPlannerCurrent = (payload.reag_admin_links || [])
    .filter((row) => ["banco master", "planner"].some((name) => normalizeProviderName(row.destino_grupo).includes(name)))
    .reduce((total, row) => total + num(row.pl_current_brl ?? row.pl_2026_05_brl), 0);
  const migratedShare = num(summary.migrated_share_current) || (
    num(summary.continuing_pl_current_brl)
      ? num(summary.migrated_pl_current_brl) / num(summary.continuing_pl_current_brl)
      : 0
  );
  addHeader(
    slide,
    "CBSF / REAG · DESTINO DOS FUNDOS",
    `Master e Planner receberam ${bn(masterPlannerCurrent, 1)}; ${pct(migratedShare, 0)} do PL continuante migrou`,
    `Fontes: CVM, Informe Mensal; BCB, Ato 1.375, liquidação em 15/01/26. Coorte do CNPJ 34.829.992/0001-86 em dez/25; destino em ${destinationShortLower}. PL ex-FIC, sem Petrobras/TAPSO.`,
    page,
  );
  addProviderFlowSnapshot(
    slide,
    pngBytes,
    `Fluxo da coorte CBSF / REAG entre dezembro de 2025 e ${destinationShortLower}`,
  );
  return slide;
}

function addProviderTransitionSlide(presentation, payload, page, pngBytes, role = "administrador") {
  const slide = presentation.slides.add();
  const stockShort = competenceShortPt(payload.latest_complete);
  const stockShortLower = stockShort.toLowerCase();
  const roleLabel = {
    administrador: "ADMINISTRAÇÃO",
    gestor: "GESTÃO",
    custodiante: "CUSTÓDIA",
  }[role] || String(role).toUpperCase();
  if (role !== "administrador") {
    const coverage = (payload.provider_history_cvm_coverage || []).find(
      (row) => row.papel === role && String(row.data_referencia || "").includes("→"),
    ) || {};
    addHeader(
      slide,
      `PRESTADORES · MIGRAÇÃO EM ${roleLabel}`,
      `${integer(coverage.fundos_mudaram_grupo)} ${Math.round(num(coverage.fundos_mudaram_grupo)) === 1 ? "FIDC" : "FIDCs"} e ${bn(coverage.pl_mudou_grupo_mai26_brl, 2)} mudaram de grupo na amostra observável`,
      `Fonte: CVM, cad_fi_hist.zip, recurso histórico identificado como ICVM 555. Coorte atual de mai/26; dez/24 → mai/26; largura = PL mai/26. Cobertura comparável: ${pct(coverage.cobertura_pl_resolvida, 2)} do PL. Amostra sem extrapolação para a indústria.`,
      page,
    );
    addProviderFlowSnapshot(
      slide,
      pngBytes,
      `Fluxos observados de ${roleLabel.toLowerCase()} entre dezembro de 2024 e maio de 2026 na amostra ICVM 555`,
    );
    return slide;
  }
  const summary = payload.provider_transition_summary;
  const requiredSummaryFields = [
    "changed_funds",
    "comparable_pl_brl",
    "changed_comparable_pl_brl",
    "coverage_pl",
  ];
  if (
    !summary
    || requiredSummaryFields.some(
      (field) => summary[field] === null
        || summary[field] === undefined
        || !Number.isFinite(Number(summary[field])),
    )
  ) {
    throw new Error("provider_transition_summary ausente ou incompleto");
  }
  const changedShare = num(summary.changed_share) || (
    num(summary.comparable_pl_brl)
      ? num(summary.changed_comparable_pl_brl) / num(summary.comparable_pl_brl)
      : 0
  );
  addHeader(
    slide,
    "PRESTADORES · MIGRAÇÃO EM ADMINISTRAÇÃO",
    `${integer(summary.changed_funds)} FIDCs trocaram de administrador; ${pct(changedShare, 1)} do estoque comparável mudou de mãos`,
    `Fonte: CVM, Informe Mensal. Fundos existentes em ${stockShortLower}, com administrador observado em dez/24 e ${stockShortLower}; largura = PL ${stockShortLower}. Cobertura: ${pct(summary.coverage_pl, 1)} do PL da coorte. Ex-FIC e sem Sistema Petrobras/TAPSO.`,
    page,
  );
  addProviderFlowSnapshot(
    slide,
    pngBytes,
    `Fluxos observados de administradores entre dezembro de 2024 e ${stockShortLower}`,
  );
  return slide;
}

function fallbackExecutiveConclusions(payload) {
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  const metrics = payload.conclusion_metrics || {};
  const bankCohort = btgBankCohortContext(payload);
  const currentOfferYtd = (payload.closed_offers_annual || []).find((row) => num(row.year) === 2026) || {};
  const comparableOffers = payload.closed_offers_jan_june || payload.closed_offers_jan_may || [];
  const currentOffer = comparableOffers.find((row) => num(row.year) === 2026) || {};
  const priorOffer = comparableOffers.find((row) => num(row.year) === 2025) || {};
  const offer2024 = comparableOffers.find((row) => num(row.year) === 2024) || {};
  const currentConcentration = Object.fromEntries(
    (payload.provider_concentration_history || [])
      .filter((row) => row.competencia === payload.latest_complete)
      .map((row) => [row.papel, row]),
  );
  const provider = (role, name) => (payload.provider_historical_ranking || []).find(
    (row) => row.competencia === payload.latest_complete
      && row.papel === role
      && normalizeProviderName(row.participante) === normalizeProviderName(name),
  ) || {};
  const qiAdmin = provider("administrador", "QI Tech");
  const qiCustodian = provider("custodiante", "QI Tech");
  const otManager = provider("gestor", "Oliveira Trust");
  const reag = payload.reag_admin_summary || {};
  const cloudwalk = (payload.closed_offer_originators_2026 || []).find(
    (row) => normalizeProviderName(row.originator_group).includes("cloudwalk"),
  ) || {};
  const offerGrowth = num(priorOffer.registered_volume_brl)
    ? num(currentOffer.registered_volume_brl) / num(priorOffer.registered_volume_brl) - 1
    : 0;
  const offerGrowth2024 = num(offer2024.registered_volume_brl)
    ? num(currentOffer.registered_volume_brl) / num(offer2024.registered_volume_brl) - 1
    : 0;
  return [
    {
      order: 1,
      title: "Distribuição após a RCVM 175 continua institucional",
      bullets: [
        `Ticket médio de ${mm(currentOfferYtd.mean_registered_ticket_brl, 1)} e mediano de ${mm(currentOfferYtd.median_registered_ticket_brl, 1)} em jan–jun/26.`,
        `PF respondeu por ${pct(currentOfferYtd.natural_person_placed_volume_share, 1)} do volume colocado; ${pct(metrics.holder_ge_200m_share_fundos_ate_10_contas, 0)} dos fundos com PL ≥ R$ 200 mi têm até dez contas.`,
      ],
    },
    {
      order: 2,
      title: "Prestação de serviços é verticalizada",
      bullets: [
        `Administração e custódia ficam no mesmo conglomerado em ${pct(metrics.admin_custodia_juntas_share_pl, 1)} do PL bruto, em ${integer(metrics.admin_custodia_juntas_fundos)} fundos.`,
        `Monoestruturas reúnem ${pct(metrics.monoestrutura_share_pl, 1)} do PL.`,
      ],
    },
    {
      order: 3,
      title: "Independentes precisam de escala",
      bullets: [
        `QI Tech lidera administração (${bn(qiAdmin.pl_brl, 1)}) e custódia (${bn(qiCustodian.pl_brl, 1)}); Oliveira Trust é a maior gestora independente (${bn(otManager.pl_brl, 1)}; 3ª geral).`,
        `Na coorte CBSF/Reag, ${pct(reag.migrated_share_current, 1)} do PL continuante migrou de administrador.`,
      ],
    },
    {
      order: 4,
      title: "Migração de administrador foi baixa",
      bullets: [
        `${integer(metrics.admin_transition_2024_2025_changed_funds)} FIDCs trocaram de administrador entre dez/24 e dez/25: ${bn(metrics.admin_transition_2024_2025_changed_pl_brl, 1)}, ou ${pct(metrics.admin_transition_2024_2025_changed_share_pl, 1)} do PL comparável.`,
        `Oliveira Trust → Bradesco somou ${bn(metrics.admin_transition_2024_2025_cielo_pl_brl, 1)} em dois FIDCs Cielo.`,
      ],
    },
    {
      order: 5,
      title: "Gestão é a função menos concentrada",
      bullets: [
        `O Top 10 reúne ${pct(currentConcentration.gestor?.top10_share, 1)} do PL ex-FIC em gestão, ante ${pct(currentConcentration.administrador?.top10_share, 1)} na administração e ${pct(currentConcentration.custodiante?.top10_share, 1)} na custódia.`,
        "O recorte exclui Sistema Petrobras e TAPSO.",
      ],
    },
    {
      order: 6,
      title: "Coorte bancária do BTG concentra o combo completo",
      bullets: [
        `FIDCs.xlsx lista ${integer(bankCohort.listedRoots)} raízes do BTG; ${integer(bankCohort.observedFunds)} tinham PL observado em ${stockShortLower}, somando ${bn(bankCohort.cohortPl, 1)}.`,
        `Dentro da coorte, ${integer(bankCohort.comboFunds)} FIDCs e ${bn(bankCohort.comboPl, 1)} concentram administração, gestão e custódia no BTG.`,
      ],
    },
    {
      order: 7,
      title: "Ofertas encerradas em 2026",
      bullets: [
        `${integer(currentOfferYtd.closed_offers)} ofertas encerradas somaram ${bn(currentOfferYtd.registered_volume_brl, 1)} em jan–jun/26; alta de ${pct(offerGrowth, 0)} sobre 2025 e ${pct(offerGrowth2024, 0)} sobre 2024.`,
        `Ofertas nomináveis da CloudWalk somaram ${bn(cloudwalk.registered_volume_brl, 1)}.`,
      ],
    },
  ];
}

function executiveConclusions(payload) {
  const rows = payload.executive_conclusions;
  if (!Array.isArray(rows) || rows.length !== 7) return fallbackExecutiveConclusions(payload);
  const normalized = rows.map((row, index) => ({
    order: Math.round(num(row?.order, index + 1)),
    title: String(row?.title || "").trim(),
    bullets: Array.isArray(row?.bullets)
      ? row.bullets.map((bullet) => String(bullet || "").trim())
      : [],
  }));
  const valid = normalized.every(
    (row) => row.order >= 1
      && row.order <= 7
      && row.title
      && row.bullets.length === 2
      && row.bullets.every(Boolean),
  ) && new Set(normalized.map((row) => row.order)).size === 7;
  return valid
    ? normalized.sort((a, b) => a.order - b.order)
    : fallbackExecutiveConclusions(payload);
}

function executiveConclusionNotes(payload, fallback) {
  const notes = Array.isArray(payload.executive_conclusion_notes)
    ? payload.executive_conclusion_notes.map((note) => String(note || "").trim()).filter(Boolean)
    : [];
  return notes.length ? notes.join(" · ") : fallback;
}

function addConclusionsSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const conclusions = executiveConclusions(payload);
  const currentOffer = (payload.closed_offers_annual || []).find((row) => num(row.year) === 2026) || {};
  const metrics = payload.conclusion_metrics || {};
  const footer = [
    "Fontes: CVM, ANBIMA, BCB e FIDCs.xlsx.",
    `PF: proxy com ${pct(currentOffer.placed_quantity_registered_volume_coverage, 1)} de cobertura; contas não equivalem a investidores únicos.`,
    "Verticalização inclui FIC-FIDC; Top 10 ex-Petrobras/TAPSO.",
    `BTG: ${integer(metrics.btg_bank_cohort_observed_funds)}/${integer(metrics.btg_bank_cohort_listed_roots)} raízes observadas; ofertas até 30/jun/26.`,
  ].join(" ");
  addHeader(
    slide,
    "PRINCIPAIS CONCLUSÕES",
    "Distribuição, prestadores, migração e ofertas",
    footer,
    page,
  );
  conclusions.forEach((item, index) => {
    const column = index % 2;
    const row = Math.floor(index / 2);
    const left = column === 0 ? 60 : 660;
    const top = 132 + row * 128;
    const order = String(item.order).padStart(2, "0");
    addText(slide, `${order} · ${item.title.toUpperCase()}`, { left, top, width: 540, height: 20 }, {
      fontSize: 10.5,
      bold: true,
      color: C.orange,
    });
    addText(slide, item.bullets.map((bullet) => `• ${bullet}`).join("\n"), { left, top: top + 25, width: 540, height: 86 }, {
      fontSize: 11.4,
      color: C.charcoal,
      lineSpacing: 1.02,
    });
    addRule(slide, left, top + 117, 540, C.line, 0.7);
  });
  return slide;
}

function buildPresentation(payload, flowAssets) {
  automaticPageNumber = 1;
  const presentation = Presentation.create({ slideSize: SLIDE });
  const latestCompetence = String(payload.latest_complete || "");
  const stockShort = competenceShortPt(latestCompetence);
  const stockShortLower = stockShort.toLowerCase();
  const stockLong = competenceEndLongPt(latestCompetence);
  const stockPreliminary = payload.stock_preliminary_status || {};
  const stockPreliminaryDisclosure = stockPreliminary.competencia
    ? `Estoque mantido em ${stockShortLower}: ${competenceShortPt(stockPreliminary.competencia).toLowerCase()} tinha ${integer(stockPreliminary.n_veiculos)} veículos e ${pct(stockPreliminary.pl_ratio_vs_previous, 1)} do PL de ${stockShortLower} na carga de ${dateShortPt(stockPreliminary.generated_at_utc)}.`
    : "";
  const offersAsOf = String(payload.offers_as_of || "");
  const offersSourceAsOf = String(payload.offers_source_as_of || offersAsOf);
  const offersShort = dateShortPt(offersAsOf);
  const offersLong = dateLongPt(offersAsOf);
  const offersSourceShort = dateShortPt(offersSourceAsOf);
  const offersDate = parseIsoDate(offersAsOf);
  const latestHistory = payload.pl_history.at(-1) || {};
  const latestBase = payload.investor_base_history.at(-1) || {};
  const annualOffers = payload.closed_offers_annual || payload.offers_ytd || [];
  const currentOfferYear = Math.max(...annualOffers.map((row) => num(row.year)));
  const firstOfferYear = Math.min(...annualOffers.map((row) => num(row.year)));
  presentation.theme.colorScheme = {
    name: "Itau BBA FIDC Editorial",
    themeColors: {
      accent1: C.orange,
      accent2: C.black,
      accent3: C.charcoal,
      accent4: C.mid,
      accent5: C.note,
      accent6: C.line,
      bg1: C.white,
      bg2: C.pale,
      tx1: C.black,
      tx2: C.charcoal,
      dk1: C.black,
      dk2: C.charcoal,
      lt1: C.white,
      lt2: C.light,
      hlink: C.orange,
      folHlink: C.mid,
    },
  };

  // 1. Capa
  {
    const slide = presentation.slides.add();
    slide.background.fill = C.black;
    addRect(slide, { left: 60, top: 105, width: 88, height: 5 }, C.orange);
    addText(slide, "INDÚSTRIA DE FIDCs", { left: 60, top: 148, width: 900, height: 86 }, {
      fontSize: 48,
      bold: true,
      color: C.white,
      verticalAlignment: "middle",
    });
    addText(
      slide,
      "Escala, qualidade do dado, prestadores e fundos que explicam a concentração",
      { left: 60, top: 252, width: 1010, height: 70 },
      { fontSize: 24, color: C.light, lineSpacing: 1.05 },
    );
    addRule(slide, 60, 530, 1160, "#4B4F53", 1);
    addText(slide, `Dados de PL: ${stockLong}`, { left: 60, top: 555, width: 500, height: 28 }, {
      fontSize: 16,
      color: C.white,
    });
    addText(slide, `Ofertas encerradas até ${offersLong}`, { left: 60, top: 589, width: 520, height: 28 }, {
      fontSize: 16,
      color: C.light,
    });
    addText(slide, `Itaú BBA · ${offersDate ? `${MONTHS_LONG_PT[offersDate.month - 1][0].toUpperCase()}${MONTHS_LONG_PT[offersDate.month - 1].slice(1)} de ${offersDate.year}` : offersAsOf}`, { left: 60, top: 657, width: 500, height: 22 }, {
      fontSize: 12,
      bold: true,
      color: C.orange,
    });
  }

  // 2. Grandes números
  {
    const slide = presentation.slides.add();
    addHeader(
      slide,
      "GRANDES NÚMEROS",
      `${bn(latestHistory.pl_ex_fic, 0)} ex-FIC; a concentração aparece em fundos, prestadores e ajustes de qualidade`,
      `Fonte: CVM, ANBIMA e FundosNet; ${stockShortLower}, salvo ofertas até ${offersShort}.`,
      2,
    );
    const qa = payload.qa_latest;
    const mono = payload.service_model.find((row) => row.modelo_prestacao === "Monoestrutura");
    const summary = [
      {
        value: bn(latestHistory.pl_ex_fic, 0),
        claim: `PL ex-FIC em ${stockShortLower}`,
        detail: `${(num(latestHistory.pl_ex_fic) / num(payload.pl_history[0]?.pl_ex_fic)).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}× ${payload.pl_history[0]?.year}; FIC-FIDC: ${bn(latestHistory.pl_fic_componente, 1)}.`,
      },
      {
        value: "59%",
        claim: "dos fundos acima de R$ 200 mi têm até 10 contas",
        detail: "60,7% do PL no recorte de R$ 733,9 bi.",
      },
      {
        value: integer(qa.casos_inad_supera_carteira),
        claim: "veículos com inadimplência acima da carteira",
        detail: `Cap: ${bn(qa.excesso_removido_brl, 1)}; Top 10: ${pct(qa.excesso_top10_share, 1)}.`,
      },
      {
        value: pct(mono?.share_pl, 1),
        claim: "do PL em monoestruturas",
        detail: "Administração, gestão e custódia no mesmo conglomerado.",
      },
    ];
    summary.forEach((item, index) => {
      const y = 145 + index * 122;
      addText(slide, item.value, { left: 68, top: y, width: 185, height: 52 }, {
        fontSize: 34,
        bold: true,
        color: index === 0 ? C.orange : C.black,
        verticalAlignment: "middle",
      });
      addText(slide, item.claim, { left: 270, top: y + 2, width: 880, height: 30 }, {
        fontSize: 19,
        bold: true,
        color: C.charcoal,
      });
      addText(slide, item.detail, { left: 270, top: y + 42, width: 880, height: 44 }, {
        fontSize: 15,
        color: C.mid,
      });
      if (index < summary.length - 1) addRule(slide, 68, y + 104, 1084, C.line, 0.75);
    });
  }

  // 3. Evolução do PL
  {
    const slide = presentation.slides.add();
    const history = payload.pl_history;
    const cagrPeriods = payload.pl_total_cagr_periods || [];
    addHeader(
      slide,
      "ESCALA DA INDÚSTRIA",
      `O PL ex-FIC chegou a ${bn(latestHistory.pl_ex_fic, 0)}; FIC-FIDC adiciona ${bn(latestHistory.pl_fic_componente, 0)}`,
      `Fonte: CVM, Informe Mensal de FIDC. PL bruto = PL ex-FIC + PL de FIC-FIDC; ${stockShortLower}.`,
      3,
    );
    const categories = history.map((row) =>
      String(row.competencia) === latestCompetence ? stockShort : String(row.year),
    );
    const totalMax = Math.max(...history.map((row) => num(row.pl_total) / 1e9));
    const axisMax = Math.ceil(totalMax / 100) * 100 + 100;
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 150, width: 830, height: 465 }),
      categories,
      series: [
        {
          name: "PL ex-FIC",
          values: history.map((row) => num(row.pl_ex_fic) / 1e9),
          fill: C.orange,
        },
        {
          name: "FIC-FIDC",
          values: history.map((row) => num(row.pl_fic_componente) / 1e9),
          fill: C.line,
          dataLabelOverrides: history.map((row, idx) => ({
            idx,
            text: `${Math.round(num(row.pl_total) / 1e9).toLocaleString("pt-BR")}`,
            position: "outEnd",
            showValue: false,
            textStyle: {
              fill: [0, 9, 10, 11].includes(idx) ? C.black : C.note,
              fontSize: 9.5,
              bold: [0, 9, 10, 11].includes(idx),
            },
          })),
        },
      ],
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 55, overlap: 100 },
      hasLegend: true,
      legend: {
        position: "bottom",
        overlay: false,
        textStyle: { fill: C.mid, fontSize: 12 },
      },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 11.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: {
        ...chartAxis(11, "0"),
        min: 0,
        max: axisMax,
        majorUnit: 200,
      },
    });
    const plotLeft = 103;
    const plotTop = 158;
    const plotWidth = 756;
    const plotHeight = 395;
    history.forEach((row, index) => {
      const total = num(row.pl_total) / 1e9;
      const relevant = [0, 9, 10, 11].includes(index);
      addText(
        slide,
        Math.round(total).toLocaleString("pt-BR"),
        {
          left: plotLeft + (index + 0.5) * (plotWidth / history.length) - 24,
          top: clamp(plotTop + plotHeight - (total / axisMax) * plotHeight - 20, plotTop - 2, plotTop + plotHeight - 22),
          width: 48,
          height: 16,
        },
        {
          fontSize: 9.5,
          bold: relevant,
          color: relevant ? C.black : C.note,
          alignment: "center",
        },
      );
    });
    cagrPeriods.forEach((period) => {
      const endYear = num(period.end_year);
      const endIndex = history.findIndex((row) => num(row.year) === endYear);
      if (endIndex < 0) return;
      const total = num(history[endIndex]?.pl_total) / 1e9;
      const center = plotLeft + (endIndex + 0.5) * (plotWidth / history.length);
      const ruleTop = clamp(
        plotTop + plotHeight - (total / axisMax) * plotHeight - 42,
        plotTop + 32,
        plotTop + plotHeight - 82,
      );
      addRule(slide, center - 24, ruleTop, 48, C.orange, 1.5);
      addText(
        slide,
        pct(period.cagr, 1),
        { left: center - 34, top: ruleTop - 25, width: 68, height: 18 },
        { fontSize: 10.5, bold: true, color: C.charcoal, alignment: "center" },
      );
      addText(
        slide,
        `${endYear} YoY`,
        { left: center - 34, top: ruleTop + 5, width: 68, height: 14 },
        { fontSize: 8.5, color: C.note, alignment: "center" },
      );
    });
    addText(slide, "R$ bi", { left: 72, top: 150, width: 42, height: 16 }, {
      fontSize: 9.5,
      color: C.note,
    });
    addSectionLabel(slide, "LEITURA", { left: 930, top: 150, width: 290, height: 24 });
    const first = history[0];
    const last = history.at(-1);
    addMetric(slide, bn(last.pl_ex_fic, 0), `PL ex-FIC em ${stockShortLower}`, { left: 930, top: 205, width: 290, height: 100 }, true);
    addMetric(
      slide,
      `${(num(last.pl_ex_fic) / num(first.pl_ex_fic)).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}x`,
      `crescimento sobre ${first.year}`,
      { left: 930, top: 325, width: 290, height: 100 },
    );
    addMetric(slide, bn(last.pl_fic_componente, 0), "PL de FIC-FIDC, sem dupla contagem", { left: 930, top: 445, width: 290, height: 110 });
    addText(slide, "Totais e crescimentos anuais usam o PL bruto; dezembro contra dezembro.", { left: 930, top: 585, width: 290, height: 40 }, {
      fontSize: 12.5,
      color: C.note,
    });
  }

  // 4. Ofertas encerradas de renda fixa
  {
    const slide = presentation.slides.add();
    const comparison = payload.fixed_income_offer_comparison || [];
    const periodOrder = ["2023 FY", "2024 FY", "2025 FY", "2026 jan-jun"];
    const seriesValues = (view, label) =>
      periodOrder.map((period) =>
        num(
          comparison.find(
            (row) =>
              row.view === view &&
              row.series_label === label &&
              row.period_label === period,
          )?.registered_volume_brl,
        ) / 1e9,
      );
    const yoyValue = (label, period) => {
      const candidates = comparison.filter(
        (row) =>
          row.series_label === label &&
          row.period_label === period,
      );
      const row =
        candidates.find((item) => item.view === "FIDCs vs demais elegíveis") ||
        candidates[0];
      if (!row || row.yoy_growth === null || row.yoy_growth === undefined) return "N/D";
      const value = num(row.yoy_growth);
      return `${value > 0 ? "+" : ""}${pct(value, 1)}`;
    };
    const viewA = "FIDCs vs demais elegíveis";
    const viewB = "FIDCs vs instrumentos materiais de 2025";
    addHeader(
      slide,
      "OFERTAS ENCERRADAS · RENDA FIXA",
      "FIDCs cresceram 15% no 1S26; os demais instrumentos elegíveis recuaram 8%",
      "Fonte: CVM, Ofertas Públicas de Distribuição, snapshot 24/jul/26. Oferta primária, status Oferta Encerrada, Data de Encerramento e valor registrado positivo.",
      4,
    );
    addSectionLabel(slide, "FIDCs E DEMAIS INSTRUMENTOS ELEGÍVEIS · R$ BI", {
      left: 60,
      top: 132,
      width: 555,
      height: 24,
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 166, width: 555, height: 290 }),
      categories: ["2023FY", "2024FY", "2025FY", "2026 1S"],
      series: [
        {
          name: "FIDCs",
          values: seriesValues(viewA, "FIDCs"),
          valuesFormatCode: "0",
          fill: C.orange,
        },
        {
          name: "Demais elegíveis",
          values: seriesValues(viewA, "Demais elegíveis"),
          valuesFormatCode: "0",
          fill: C.charcoal,
        },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 45 },
      hasLegend: true,
      legend: {
        position: "bottom",
        overlay: false,
        textStyle: { fill: C.mid, fontSize: 10 },
      },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 10 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(9.5, "0"), min: 0 },
      dataLabels: {
        showValue: true,
        position: "outEnd",
        textStyle: { fill: C.black, fontSize: 9, bold: true },
      },
    });
    addSectionLabel(slide, "INSTRUMENTOS MAIS EMITIDOS EM 2025 · R$ BI", {
      left: 665,
      top: 132,
      width: 555,
      height: 24,
    });
    const materialSeries = [
      ["FIDCs", C.orange],
      ["Debêntures", C.black],
      ["CRI", C.mid],
      ["Notas comerciais", C.note],
      ["CRA", C.line],
    ];
    slide.charts.add("bar", {
      ...chartBase({ left: 665, top: 166, width: 555, height: 290 }),
      categories: ["2023FY", "2024FY", "2025FY", "2026 1S"],
      series: materialSeries.map(([label, color]) => ({
        name: label,
        values: seriesValues(viewB, label),
        valuesFormatCode: "0",
        fill: color,
      })),
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 34 },
      hasLegend: true,
      legend: {
        position: "bottom",
        overlay: false,
        textStyle: { fill: C.mid, fontSize: 9.5 },
      },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 10 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(9.5, "0"), min: 0 },
      dataLabels: {
        showValue: true,
        position: "outEnd",
        textStyle: { fill: C.black, fontSize: 8.5, bold: true },
      },
    });
    addNativeEditorialTable(slide, {
      left: 60,
      top: 478,
      width: 1160,
      height: 142,
      headers: ["Instrumento", "2023 YoY", "2024 YoY", "2025 YoY", "1S26 YoY"],
      rows: [
        ["FIDCs", ...periodOrder.map((period) => yoyValue("FIDCs", period))],
        ["Demais elegíveis", ...periodOrder.map((period) => yoyValue("Demais elegíveis", period))],
        ["Debêntures", ...periodOrder.map((period) => yoyValue("Debêntures", period))],
        ["CRI", ...periodOrder.map((period) => yoyValue("CRI", period))],
        ["Notas comerciais", ...periodOrder.map((period) => yoyValue("Notas comerciais", period))],
        ["CRA", ...periodOrder.map((period) => yoyValue("CRA", period))],
      ],
      columnWidths: [360, 200, 200, 200, 200],
      aligns: ["left", "right", "right", "right", "right"],
      fontSize: 8.7,
      headerFontSize: 8.7,
      rowHighlights: new Set([0]),
    });
    addText(
      slide,
      "2026 compara jan–jun/26 com jan–jun/25. Exclui cotas de fundos, ações, Units, debêntures conversíveis e os instrumentos FIAGRO especificados.",
      { left: 60, top: 628, width: 1160, height: 18 },
      { fontSize: 9.2, color: C.note, alignment: "left" },
    );
  }

  // 5. Base investidora
  {
    const slide = presentation.slides.add();
    const history = payload.investor_base_history;
    const composition = payload.investor_composition;
    addHeader(
      slide,
      "BASE INVESTIDORA",
      `A base atingiu ${(num(latestBase.cotistas_total) / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} mil contas em ${integer(latestBase.n_veiculos)} veículos; contas não são investidores únicos`,
      `Fonte: CVM, Informe Mensal de FIDC, ${stockShortLower}. Contas podem se repetir por classe ou série.`,
      4,
    );
    addSectionLabel(slide, "CONTAS DE COTISTAS", { left: 60, top: 140, width: 690, height: 24 });
    const historyCategories = history.map((row) =>
      String(row.competencia) === latestCompetence ? stockShort : String(row.year),
    );
    addStraightLineChart(slide, {
      position: { left: 60, top: 175, width: 690, height: 190 },
      categories: historyCategories,
      series: [
        {
          name: "Contas",
          values: history.map((row) => num(row.cotistas_total) / 1000),
          line: { style: "solid", fill: C.orange, width: 3 },
        },
      ],
      yAxis: { ...chartAxis(10, "0 \"mil\""), min: 0 },
      labelIndices: [0, 3, 6, 9, historyCategories.length - 1],
    });
    addSectionLabel(slide, "VEÍCULOS REPORTANTES", { left: 60, top: 382, width: 690, height: 24 });
    addStraightLineChart(slide, {
      position: { left: 60, top: 417, width: 690, height: 190 },
      categories: historyCategories,
      series: [
        {
          name: "Veículos",
          values: history.map((row) => num(row.n_veiculos)),
          line: { style: "solid", fill: C.charcoal, width: 2.5 },
        },
      ],
      yAxis: { ...chartAxis(10, "0"), min: 0 },
      labelIndices: [0, 3, 6, 9, historyCategories.length - 1],
    });
    addSectionLabel(slide, `COMPOSIÇÃO DAS CONTAS · ${stockShort.toUpperCase()}`, { left: 795, top: 140, width: 425, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 790, top: 180, width: 430, height: 335 }),
      categories: composition.map((row) => row.categoria),
      series: [
        {
          name: "Contas",
          values: composition.map((row) => num(row.share)),
          valuesFormatCode: "0.0%",
          fill: C.charcoal,
          points: composition.map((_, idx) => ({ idx, fill: idx === 0 ? C.orange : C.charcoal })),
        },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 42 },
      hasLegend: false,
      xAxis: { visible: false, majorGridlines: null },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 11, bold: true } },
    });
    addText(
      slide,
      `Composição reconciliada: ${integer(composition.reduce((s, r) => s + num(r.contas), 0))} contas; ${integer(composition.find((row) => row.categoria === "Não classificado")?.contas)} sem tipo identificado.`,
      { left: 795, top: 535, width: 425, height: 45 },
      { fontSize: 12, color: C.note },
    );
  }

  // 5. Distribuição por cotistas
  {
    const slide = presentation.slides.add();
    const history = payload.holder_distribution_history;
    const periodBefore = "2023-12";
    const periodAfter = payload.latest_complete;
    const before = history.filter((row) => row.competencia === periodBefore);
    const after = history.filter((row) => row.competencia === periodAfter);
    const bucketOrder = ["0", "1", "2–3", "4–10", "11–50", "51+"];
    const byBucket = (rows) => Object.fromEntries(rows.map((row) => [row.bucket, row]));
    const beforeMap = byBucket(before);
    const afterMap = byBucket(after);
    const above10BeforeFunds = before
      .filter((row) => ["11–50", "51+"].includes(row.bucket))
      .reduce((sum, row) => sum + num(row.share_fundos), 0);
    const above10AfterFunds = after
      .filter((row) => ["11–50", "51+"].includes(row.bucket))
      .reduce((sum, row) => sum + num(row.share_fundos), 0);
    const above10BeforePl = before
      .filter((row) => ["11–50", "51+"].includes(row.bucket))
      .reduce((sum, row) => sum + num(row.share_pl), 0);
    const above10AfterPl = after
      .filter((row) => ["11–50", "51+"].includes(row.bucket))
      .reduce((sum, row) => sum + num(row.share_pl), 0);
    const metadata = Object.fromEntries(
      payload.holder_distribution_meta_history.map((row) => [row.competencia, row]),
    );
    addHeader(
      slide,
      "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",
      `Fundos com mais de 10 contas ganharam ${pct(above10AfterFunds - above10BeforeFunds, 1).replace("%", " p.p.")} do universo e ${pct(above10AfterPl - above10BeforePl, 1).replace("%", " p.p.")} do PL desde dez/23`,
      `Fonte: CVM, dez/23 e ${stockShortLower}. Ex-FIC com PL ≥ R$ 200 mi: ${integer(metadata[periodBefore]?.eligible_funds)} → ${integer(metadata[periodAfter]?.eligible_funds)} fundos; contas por classe/série, não investidores únicos.`,
      5,
    );
    const buckets = bucketOrder;
    const chartLeft = 60;
    const chartRight = 665;
    const chartWidth = 555;
    const absoluteTop = 181;
    const shareTop = 428;
    const chartHeight = 190;

    addLegend(
      slide,
      [
        { label: "Dez/23", color: C.mid },
        { label: stockShort, color: C.orange },
      ],
      { left: 970, top: 128, width: 250, height: 22 },
      2,
    );

    addSectionLabel(slide, "QUANTIDADE DE FUNDOS · ABSOLUTO", { left: chartLeft, top: 139, width: chartWidth, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: chartLeft, top: absoluteTop, width: chartWidth, height: chartHeight }),
      categories: buckets,
      series: [
        { name: "Dez/23", values: buckets.map((bucket) => num(beforeMap[bucket]?.fundos)), fill: C.mid },
        { name: stockShort, values: buckets.map((bucket) => num(afterMap[bucket]?.fundos)), fill: C.orange },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 35 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 10.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(9.5, "0"), min: 0 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.5, bold: true } },
    });
    addSectionLabel(slide, "PL POR FAIXA · R$ BI", { left: chartRight, top: 139, width: chartWidth, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: chartRight, top: absoluteTop, width: chartWidth, height: chartHeight }),
      categories: buckets,
      series: [
        { name: "Dez/23", values: buckets.map((bucket) => num(beforeMap[bucket]?.pl) / 1e9), fill: C.mid },
        { name: stockShort, values: buckets.map((bucket) => num(afterMap[bucket]?.pl) / 1e9), fill: C.orange },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 35 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 10.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(9.5, "0"), min: 0 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.5, bold: true } },
    });

    addSectionLabel(slide, "QUANTIDADE DE FUNDOS · % DO TOTAL", { left: chartLeft, top: 392, width: chartWidth, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: chartLeft, top: shareTop, width: chartWidth, height: chartHeight }),
      categories: buckets,
      series: [
        { name: "Dez/23", values: buckets.map((bucket) => num(beforeMap[bucket]?.share_fundos)), valuesFormatCode: "0%", fill: C.mid },
        { name: stockShort, values: buckets.map((bucket) => num(afterMap[bucket]?.share_fundos)), valuesFormatCode: "0%", fill: C.orange },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 35 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 10.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(9.5, "0%"), min: 0, max: 0.35, majorUnit: 0.1 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.5, bold: true } },
    });
    addText(slide, "Soma das barras = 100%", { left: 410, top: 394, width: 205, height: 20 }, {
      fontSize: 10.5,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });

    addSectionLabel(slide, "PL POR FAIXA · % DO TOTAL", { left: chartRight, top: 392, width: chartWidth, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: chartRight, top: shareTop, width: chartWidth, height: chartHeight }),
      categories: buckets,
      series: [
        { name: "Dez/23", values: buckets.map((bucket) => num(beforeMap[bucket]?.share_pl)), valuesFormatCode: "0%", fill: C.mid },
        { name: stockShort, values: buckets.map((bucket) => num(afterMap[bucket]?.share_pl)), valuesFormatCode: "0%", fill: C.orange },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 35 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 10.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(9.5, "0%"), min: 0, max: 0.35, majorUnit: 0.1 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.5, bold: true } },
    });
    addText(slide, "Soma das barras = 100%", { left: 1015, top: 394, width: 205, height: 20 }, {
      fontSize: 10.5,
      color: C.note,
      alignment: "right",
      verticalAlignment: "middle",
    });
    addText(
      slide,
      "Comparação de duas fotografias da indústria, não de coorte constante. Corte de R$ 200 mi em valores nominais; cada histograma percentual fecha em 100%.",
      { left: 60, top: 640, width: 1160, height: 18 },
      { fontSize: 10.5, color: C.note, alignment: "right" },
    );
  }

  // 6. Mix ANBIMA
  {
    const slide = presentation.slides.add();
    const history = [...payload.type_mix_history].sort(
      (a, b) => num(a.period_order) - num(b.period_order) || num(a.category_order) - num(b.category_order),
    );
    const mixMeta = payload.type_mix_meta || {};
    const periods = (mixMeta.periods || [])
      .map((row) => ({ competencia: row.competencia, label: row.label }))
      .filter((row) => row.competencia && row.label);
    if (!periods.length) {
      [...new Set(history.map((row) => row.competencia))].sort().forEach((competencia) => {
        periods.push({ competencia, label: competenceShortPt(competencia).toLowerCase() });
      });
    }
    const categories = mixMeta.categories || [
      "Fomento Mercantil",
      "Agro, Indústria e Comércio",
      "Financeiro",
      "Outros",
    ];
    const colors = {
      "Fomento Mercantil": C.mid,
      "Agro, Indústria e Comércio": C.note,
      "Financeiro": C.orange,
      "Outros": C.line,
    };
    const rowByKey = new Map(
      history.map((row) => [`${row.competencia}::${row.anbima_tipo}`, row]),
    );
    const valueFor = (period, category, field) =>
      num(rowByKey.get(`${period.competencia}::${category}`)?.[field]);
    const volumeSeries = categories.map((category) => ({
      name: category,
      values: periods.map((period) => valueFor(period, category, "pl") / 1e9),
      valuesFormatCode: "0.0",
      fill: colors[category],
    }));
    const shareSeries = categories.map((category) => ({
      name: category,
      values: periods.map((period) => valueFor(period, category, "share")),
      valuesFormatCode: "0.0%",
      fill: colors[category],
    }));
    const latestPeriod = periods.at(-1);
    const financeAndOtherShare =
      valueFor(latestPeriod, "Financeiro", "share") + valueFor(latestPeriod, "Outros", "share");
    const maxTotalBn = Math.max(
      ...periods.map((period) =>
        categories.reduce(
          (sum, category) => sum + valueFor(period, category, "pl") / 1e9,
          0,
        ),
      ),
    );
    addHeader(
      slide,
      "TAXONOMIA VIGENTE",
      `Financeiro e Outros representam ${pct(financeAndOtherShare, 1)} do PL ex-FIC em ${latestPeriod.label}`,
      `Fonte: CVM e ANBIMA; PL ex-FIC em dez/23, dez/24, dez/25 e ${latestPeriod.label}. Fotografia ANBIMA de dez/25 aplicada às competências; N/D incorporado em Outros.`,
      6,
    );
    addSectionLabel(slide, "PL EX-FIC · R$ BILHÕES", { left: 60, top: 145, width: 550, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 185, width: 550, height: 355 }),
      categories: periods.map((row) => row.label),
      series: volumeSeries,
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 52, overlap: 100 },
      hasLegend: false,
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 11.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: {
        ...chartAxis(10.5, "0"),
        min: 0,
        max: Math.ceil(maxTotalBn / 100) * 100,
      },
      dataLabels: {
        showValue: true,
        position: "center",
        textStyle: { fill: C.black, fontSize: 9.5, bold: true },
      },
    });
    addSectionLabel(slide, "PARTICIPAÇÃO NO PL EX-FIC", { left: 670, top: 145, width: 550, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 670, top: 185, width: 550, height: 355 }),
      categories: periods.map((row) => row.label),
      series: shareSeries,
      barOptions: { direction: "column", grouping: "percentStacked", gapWidth: 52, overlap: 100 },
      hasLegend: false,
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 11.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: {
        ...chartAxis(10.5, "0%"),
        min: 0,
        max: 1,
        majorUnit: 0.2,
      },
      dataLabels: {
        showValue: true,
        position: "center",
        textStyle: { fill: C.black, fontSize: 9.5, bold: true },
      },
    });
    addLegend(
      slide,
      categories.map((category) => ({ label: category, color: colors[category] })),
      { left: 220, top: 556, width: 840, height: 28 },
      4,
    );
    addText(
      slide,
      "Tipo e Foco ANBIMA são campos distintos. Evidência documental e proxy CVM complementam os fundos sem correspondência oficial; a origem permanece identificada por fundo.",
      { left: 120, top: 600, width: 1040, height: 35 },
      { fontSize: 11.5, color: C.mid, alignment: "center", verticalAlignment: "middle" },
    );
  }

  // 7. Carteira por recebível
  addAcquiringReclassificationSlide(presentation, payload, 7);

  // 8. Carteira por recebível
  {
    const slide = presentation.slides.add();
    const history = payload.receivables_history.filter((row) => num(row.valor) > 0);
    const periodBefore = "2023-12";
    const periodAfter = payload.latest_complete;
    const before = history.filter((row) => row.competencia === periodBefore);
    const after = history.filter((row) => row.competencia === periodAfter);
    const beforeMap = Object.fromEntries(before.map((row) => [row.segmento, row]));
    const afterMap = Object.fromEntries(after.map((row) => [row.segmento, row]));
    const categories = [...after]
      .sort((a, b) => num(b.valor) - num(a.valor))
      .map((row) => row.segmento);
    const displayCategories = categories.map((category) => ({
      "Acoes judiciais": "Ações judiciais",
      "Agronegocio": "Agronegócio",
      "Cartao de credito": "Cartão",
      "Imobiliario": "Imobiliário",
      "Servicos": "Serviços",
      "Setor publico": "Setor público",
    }[category] || category));
    const financeBefore = beforeMap.Financeiro;
    const financeAfter = afterMap.Financeiro;
    addHeader(
      slide,
      "CARTEIRA POR TIPO DE RECEBÍVEL",
      `Financeiro ganhou ${pct(num(financeAfter?.share_reported) - num(financeBefore?.share_reported), 1).replace("%", " p.p.")} e explicou 67% do crescimento segmentado`,
      `Fonte: CVM, Informe Mensal, Tabela II; dez/23 e ${stockShortLower}. Percentuais sobre a soma dos segmentos reportados.`,
      7,
    );
    addSectionLabel(slide, "VALOR REPORTADO · R$ BI", { left: 60, top: 150, width: 550, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 183, width: 550, height: 445 }),
      categories: displayCategories,
      series: [
        { name: "Dez/23", values: categories.map((category) => num(beforeMap[category]?.valor) / 1e9), valuesFormatCode: "0.0", fill: C.mid },
        { name: stockShort, values: categories.map((category) => num(afterMap[category]?.valor) / 1e9), valuesFormatCode: "0.0", fill: C.orange },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 28 },
      hasLegend: false,
      xAxis: { ...chartAxis(9, "0"), min: 0 },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 9.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.2, bold: true } },
    });
    addSectionLabel(slide, "% DO VALOR SEGMENTADO DA TABELA II", { left: 670, top: 150, width: 550, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 670, top: 183, width: 550, height: 445 }),
      categories: displayCategories,
      series: [
        { name: "Dez/23", values: categories.map((category) => num(beforeMap[category]?.share_reported)), valuesFormatCode: "0.0%", fill: C.mid },
        { name: stockShort, values: categories.map((category) => num(afterMap[category]?.share_reported)), valuesFormatCode: "0.0%", fill: C.orange },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 28 },
      hasLegend: false,
      xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 9.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 8.2, bold: true } },
    });
    addRect(slide, { left: 760, top: 600, width: 460, height: 24 }, C.white);
    addText(
      slide,
      `Tabela II: R$ 439,5 bi em dez/23 e R$ 737,4 bi em ${stockShortLower}; diferenças para a Tabela I de R$ 51,7 bi e R$ 60,4 bi. Adquirência no slide anterior.`,
      { left: 60, top: 635, width: 1160, height: 24 },
      { fontSize: 10.5, color: C.charcoal, alignment: "right", verticalAlignment: "middle" },
    );
    // Reaplicados após os gráficos para evitar que o frame do chart cubra o
    // início do rótulo no PowerPoint/LibreOffice.
    addSectionLabel(slide, "VALOR REPORTADO · R$ BI", { left: 60, top: 150, width: 550, height: 24 });
    addSectionLabel(slide, "% DO VALOR SEGMENTADO DA TABELA II", { left: 670, top: 150, width: 550, height: 24 });
    addLegend(slide, [
      { label: "Dez/23", color: C.mid },
      { label: stockShort, color: C.orange },
    ], { left: 970, top: 128, width: 250, height: 22 }, 2);
  }

  // 8. Observabilidade da inadimplência
  {
    const slide = presentation.slides.add();
    const qa = payload.qa_latest;
    addHeader(
      slide,
      "OBSERVABILIDADE DA INADIMPLÊNCIA",
      `O cap retira ${bn(qa.excesso_removido_brl, 1)} de ${integer(qa.casos_inad_supera_carteira)} veículos; 10 casos explicam ${pct(qa.excesso_top10_share, 1)}`,
      `Fonte: CVM, ${stockShortLower}. Ajuste = mínimo entre inadimplência não negativa e carteira não negativa por veículo.`,
      8,
    );
    addSectionLabel(slide, "MÉTRICAS SOBRE A CARTEIRA COBERTA", { left: 60, top: 150, width: 710, height: 24 });
    const metrics = [
      ["Inadimplência bruta", num(qa.inadimplencia_bruta_pct)],
      ["Ajustada pelo cap", num(qa.inadimplencia_ajustada_pct)],
      ["Ajustada ex-NP", num(qa.inadimplencia_ajustada_ex_np_pct)],
      ["Excluindo casos acima da carteira", num(qa.sensibilidade_ex_casos_acima_carteira_pct)],
    ];
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 195, width: 710, height: 385 }),
      categories: metrics.map((row) => row[0]),
      series: [
        {
          name: "Percentual",
          values: metrics.map((row) => row[1]),
          valuesFormatCode: "0.0%",
          fill: C.charcoal,
          points: metrics.map((_, idx) => ({ idx, fill: idx === 1 ? C.orange : C.charcoal })),
        },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 45 },
      hasLegend: false,
      xAxis: {
        ...chartAxis(10.5, "0%"),
        min: 0,
        max: 0.1,
        majorUnit: 0.02,
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 12, bold: true } },
    });
    // O renderer do artifact-tool abrevia o eixo percentual como "m"; os rótulos
    // das barras já carregam a escala correta, então ocultamos apenas essa faixa.
    addRect(slide, { left: 220, top: 548, width: 560, height: 28 }, C.white);
    addSectionLabel(slide, "UNIVERSO E COBERTURA", { left: 825, top: 150, width: 395, height: 24 });
    addFlatList(
      slide,
      [
        { label: "Veículos / fundos", value: `${integer(qa.veiculos_total)} / ${integer(qa.fundos_total)}` },
        { label: "Carteira positiva", value: integer(qa.veiculos_com_carteira_positiva) },
        { label: "Campos reportados", value: integer(qa.veiculos_com_campos_reportados) },
        { label: "Cobertura por PL", value: pct(qa.cobertura_pl, 1), accent: true },
        { label: "Casos acima da carteira", value: `${integer(qa.casos_inad_supera_carteira)} · ${pct(qa.casos_inad_supera_carteira_share_pl, 2)} do PL` },
        { label: "Excesso Top 1 / 5 / 10", value: `${pct(qa.excesso_top1_share, 1)} / ${pct(qa.excesso_top5_share, 1)} / ${pct(qa.excesso_top10_share, 1)}` },
      ],
      { left: 825, top: 200, width: 395, height: 315 },
      { fontSize: 13.5 },
    );
    addText(
      slide,
      `Ex-360 bloqueado: aging = ${pct(qa.aging_reconciliacao_ratio, 1)} da Tabela I; diferença de ${bn(qa.aging_gap_vs_inadimplencia_reportada_brl, 2)}.`,
      { left: 825, top: 550, width: 395, height: 55 },
      { fontSize: 12.5, color: C.note },
    );
  }

  // 9. Evolução e quebra de série
  {
    const slide = presentation.slides.add();
    const allSeries = payload.qa_series;
    const series = allSeries.filter((row, index) => {
      const month = String(row.competencia).slice(5, 7);
      return ["03", "06", "09", "12"].includes(month)
        || ["2024-06", "2024-07"].includes(row.competencia)
        || index === allSeries.length - 1;
    });
    const categories = series.map((row) => {
      const [year, month] = String(row.competencia).split("-");
      return `${month}/${year.slice(2)}`;
    });
    const atlantic = payload.bridge_atlantico[0] || {};
    const singleRows = [...(payload.delinquency_single_receivable || [])]
      .sort((a, b) => num(b.pl_incluido_brl) - num(a.pl_incluido_brl));
    const singleSummary = payload.delinquency_single_receivable_summary || {};
    const finance = singleRows.find((row) => row.tipo_recebivel_tabela_ii === "Financeiro") || {};
    const agro = singleRows.find((row) => row.tipo_recebivel_tabela_ii === "Agronegócio") || {};
    addHeader(
      slide,
      "INADIMPLÊNCIA · EVOLUÇÃO E QUEBRA",
      `Fundos monotipo cobrem ${pct(singleSummary.cobertura_pl, 1)} do PL; Financeiro e Agro marcam ${pct(finance.inadimplencia_sobre_pl, 1)} e ${pct(agro.inadimplencia_sobre_pl, 1)} de inadimplência/PL`,
      "Fonte: CVM, Informe Mensal. Série com cap por veículo; quadro monotipo exclui casos acima da carteira e usa PL como denominador.",
      9,
    );
    addSectionLabel(slide, "SÉRIE AGREGADA · % DA CARTEIRA", { left: 60, top: 139, width: 615, height: 24 });
    addStraightLineChart(slide, {
      position: { left: 60, top: 174, width: 615, height: 338 },
      categories,
      series: [
        {
          name: "Bruta",
          values: series.map((row) => num(row.inadimplencia_bruta_pct)),
          valuesFormatCode: "0.0%",
          line: { style: "solid", fill: C.charcoal, width: 2.5 },
        },
        {
          name: "Ajustada",
          values: series.map((row) => num(row.inadimplencia_ajustada_pct)),
          valuesFormatCode: "0.0%",
          line: { style: "solid", fill: C.orange, width: 3 },
        },
      ],
      yAxis: { ...chartAxis(9.5, "0.0%"), min: 0, max: 0.21, majorUnit: 0.03 },
      labelIndices: [0, 3, 5, 6, 8, 11, categories.length - 1],
      labelFontSize: 8.5,
    });
    addLegend(
      slide,
      [
        { label: "Bruta", color: C.charcoal },
        { label: "Ajustada", color: C.orange },
      ],
      { left: 250, top: 509, width: 250, height: 24 },
      2,
    );
    addSectionLabel(slide, "FIDCs COM UM ÚNICO TIPO NA TABELA II", { left: 710, top: 139, width: 510, height: 24 });
    addNativeEditorialTable(slide, {
      left: 710,
      top: 174,
      width: 510,
      height: 360,
      headers: ["Tipo", "Fundos", "PL incl.", "Inad./PL"],
      rows: singleRows.map((row) => [
        row.tipo_recebivel_tabela_ii,
        integer(row.fundos_incluidos),
        (num(row.pl_incluido_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
        pct(row.inadimplencia_sobre_pl, 1),
      ]),
      columnWidths: [220, 75, 105, 110],
      aligns: ["left", "right", "right", "right"],
      fontSize: 8.5,
      headerFontSize: 8.3,
      rowHighlights: new Set(singleRows.map((row, idx) => row.tipo_recebivel_tabela_ii === "Financeiro" ? idx : -1).filter((idx) => idx >= 0)),
    });
    addRule(slide, 60, 555, 1160, C.line, 1);
    addText(
      slide,
      `Monotipo: ${integer(singleSummary.fundos_incluidos)} fundos e ${bn(singleSummary.pl_incluido_brl, 1)} de PL. Fora: ${integer(singleSummary.fundos_multitipo_excluidos)} multitipo, ${integer(singleSummary.fundos_inad_supera_carteira_excluidos)} acima da carteira e ${integer(singleSummary.fundos_sem_tipo_excluidos)} sem tipo; PLs no workbook.`,
      { left: 60, top: 570, width: 1160, height: 38 },
      { fontSize: 10.8, color: C.charcoal, alignment: "center", verticalAlignment: "middle" },
    );
    addText(
      slide,
      `Atlântico explica ${bn(Math.abs(num(atlantic.delta_excesso_brl)), 2)} da redução do excesso; a série ajustada não repete a queda. Caso no apêndice.`,
      { left: 60, top: 615, width: 1160, height: 30 },
      { fontSize: 10.4, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
  }

  addFrozenDelinquencyHistorySlide(presentation, payload, 10);

  // 10. Prestadores e concentração
  {
    const slide = presentation.slides.add();
    const providers = payload.provider_concentration_history;
    const roleOrder = ["administrador", "gestor", "custodiante"];
    const beforePeriod = "2025-12";
    const afterPeriod = payload.latest_complete;
    const before = roleOrder.map((role) => providers.find((row) => row.competencia === beforePeriod && row.papel === role));
    const after = roleOrder.map((role) => providers.find((row) => row.competencia === afterPeriod && row.papel === role));
    addHeader(
      slide,
      "PRESTADORES · RANKING E CONCENTRAÇÃO",
      `Top 10 mantém cerca de 72% em administração e custódia; gestão subiu a ${pct(after[1]?.top10_share, 1)}`,
      `Fonte: CVM, dez/25 e ${stockShortLower}. PL ex-FIC; Sistema Petrobras e TAPSO excluídos do numerador e denominador. Administração observada; gestão/custódia históricas reconstruídas com cadastro vigente.`,
      10,
    );
    addSectionLabel(slide, "TOP 10 · % DO PL EX-FIC", { left: 60, top: 155, width: 540, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 195, width: 540, height: 315 }),
      categories: ["Admin.", "Gestão", "Custódia"],
      series: [
        { name: "Dez/25", values: before.map((row) => num(row?.top10_share)), valuesFormatCode: "0.0%", fill: C.mid },
        { name: stockShort, values: after.map((row) => num(row?.top10_share)), valuesFormatCode: "0.0%", fill: C.orange },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 44 },
      hasLegend: false,
      xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "inEnd", fill: "none", line: { style: "solid", fill: "none", width: 0 }, textStyle: { fill: C.white, fontSize: 10, bold: false } },
    });
    addRect(slide, { left: 60, top: 486, width: 540, height: 35 }, C.white);
    addSectionLabel(slide, "TOP 5 · % DO PL EX-FIC", { left: 680, top: 155, width: 540, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 680, top: 195, width: 540, height: 315 }),
      categories: ["Admin.", "Gestão", "Custódia"],
      series: [
        { name: "Dez/25", values: before.map((row) => num(row?.top5_share)), valuesFormatCode: "0.0%", fill: C.mid },
        { name: stockShort, values: after.map((row) => num(row?.top5_share)), valuesFormatCode: "0.0%", fill: C.orange },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 44 },
      hasLegend: false,
      xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "inEnd", fill: "none", line: { style: "solid", fill: "none", width: 0 }, textStyle: { fill: C.white, fontSize: 10, bold: false } },
    });
    addRect(slide, { left: 680, top: 486, width: 540, height: 35 }, C.white);
    addRule(slide, 60, 545, 1160, C.line, 1);
    addText(
      slide,
      `Cobertura de PL, dez/25 → ${stockShort}: administração ${pct(before[0]?.coverage_pl, 1)} → ${pct(after[0]?.coverage_pl, 1)}; gestão ${pct(before[1]?.coverage_pl, 1)} → ${pct(after[1]?.coverage_pl, 1)}; custódia ${pct(before[2]?.coverage_pl, 1)} → ${pct(after[2]?.coverage_pl, 1)}.`,
      { left: 60, top: 570, width: 1160, height: 42 },
      { fontSize: 12, color: C.mid, alignment: "center", verticalAlignment: "middle" },
    );
    addLegend(slide, [
      { label: "Dez/25", color: C.mid },
      { label: stockShort, color: C.orange },
    ], { left: 970, top: 128, width: 250, height: 22 }, 2);
  }

  // 11–13. Market share por subtipo, seis focos materiais.
  const materialFocus = payload.material_focus_top6;
  addMarketShareSlide(presentation, payload, "administrador", materialFocus, 11, false);
  addMarketShareSlide(presentation, payload, "gestor", materialFocus, 12, false);
  addMarketShareSlide(presentation, payload, "custodiante", materialFocus, 13, false);

  // 14. Evolução do ranking dos prestadores.
  addProviderHistoricalRankingSlide(presentation, payload, 14);

  // 16–17. Independentes e coorte atual dos cinco bancos.
  addIndependentProviderRankingSlide(presentation, payload, 16);
  addBankFidcEvolutionSlide(presentation, payload, 17);

  // 18–20. Atribuição das lideranças e fluxos observáveis entre prestadores.
  addProviderAttributionSlide(presentation, payload, 18);
  addReagMigrationSlide(presentation, payload, 19, flowAssets.reagPngBytes);
  addProviderTransitionSlide(presentation, payload, 20, flowAssets.adminPngBytes, "administrador");
  addProviderTransitionSlide(presentation, payload, 21, flowAssets.gestorPngBytes, "gestor");
  addProviderTransitionSlide(presentation, payload, 22, flowAssets.custodiantePngBytes, "custodiante");
  const providerInsightOffset = 8;

  // 18. Top 20 FIDCs
  {
    const slide = presentation.slides.add();
    const top20 = payload.top20_fidcs;
    const totalPl = top20.reduce((sum, row) => sum + num(row.pl), 0);
    const share = top20.reduce((sum, row) => sum + num(row.market_share_ex_fic), 0);
    const topTwo = (num(top20[0]?.pl) + num(top20[1]?.pl)) / totalPl;
    addHeader(
      slide,
      "RANKING · TOP 20 FIDCs",
      `Top 20 somam ${pct(share, 1)} do PL ex-FIC; Petrobras e TAPSO são ${pct(topTwo, 1)} do bloco`,
      `Fonte: CVM e ANBIMA, ${stockShortLower}. Ranking derivado do universo completo ex-FIC; denominação legal completa no apêndice.`,
      15 + providerInsightOffset,
    );
    const tableRows = top20.map((row) => [
      String(row.rank),
      row.nome_curto,
      bn(row.pl, 1).replace("R$ ", ""),
      pct(row.market_share_ex_fic, 1),
      `${row.anbima_tipo || "N/D"}\n${row.anbima_foco || "N/D"}`,
      row.modelo_prestacao || "N/D",
    ]);
    [0, 1].forEach((block) => {
      addEditorialTable(slide, {
        left: block === 0 ? 60 : 650,
        top: 150,
        width: 570,
        height: 490,
        headers: ["#", "Fundo", "PL bi", "Share", "Tipo / Foco", "Modelo"],
        rows: tableRows.slice(block * 10, block * 10 + 10),
        columnWidths: [30, 175, 58, 55, 130, 122],
        aligns: ["right", "left", "right", "right", "left", "left"],
        fontSize: 10.7,
        headerFontSize: 10,
        rowHighlights: new Set(block === 0 ? [0, 1] : []),
      });
    });
  }

  // 19. Top 20 Outros
  {
    const slide = presentation.slides.add();
    const rows = payload.top20_outros;
    const categoryShare = rows.reduce((sum, row) => sum + num(row.market_share_outros), 0);
    addHeader(
      slide,
      "RANKING · TOP 20 OUTROS",
      `Top 20 representam ${pct(categoryShare, 1)} de Outros; oficial, hipótese e status ficam separados`,
      `Fonte: ANBIMA e documentos primários locais; ranking em ${stockShortLower}. Evidência e links completos constam no workbook.`,
      16 + providerInsightOffset,
    );
    const tableRows = rows.map((row) => [
      String(row.rank_outros),
      row.nome_curto,
      bn(row.pl, 1).replace("R$ ", ""),
      truncateWords(row.classificacao_oficial, 34),
      truncateWords(row.hipotese_revisao, 38),
      `${truncateWords(row.evidencia_revisao, 46)}\n${truncateWords(row.status_revisao, 26)}`,
    ]);
    [0, 1].forEach((block) => {
      addEditorialTable(slide, {
        left: block === 0 ? 60 : 650,
        top: 150,
        width: 570,
        height: 490,
        headers: ["#", "Fundo", "PL bi", "Oficial", "Hipótese", "Evidência / status"],
        rows: tableRows.slice(block * 10, block * 10 + 10),
        columnWidths: [28, 142, 55, 95, 105, 145],
        aligns: ["right", "left", "right", "left", "left", "left"],
        fontSize: 9.7,
        headerFontSize: 9.3,
      });
    });
  }

  // 20. Modelo de prestação
  {
    const slide = presentation.slides.add();
    const rows = payload.service_model;
    const mono = rows.find((row) => row.modelo_prestacao === "Monoestrutura");
    const missing = rows.find((row) => row.modelo_prestacao === "Dados incompletos");
    addHeader(
      slide,
      "MODELO DE PRESTAÇÃO",
      `Monoestruturas são ${pct(mono?.share_fundos, 1)} dos fundos e ${pct(mono?.share_pl, 1)} do PL; dados incompletos cobrem ${pct(missing?.share_pl, 1)}`,
      `Fonte: CVM, cadastro vigente em ${stockShortLower}. Definição mono: mesmo conglomerado normalizado em administração, gestão e custódia.`,
      17 + providerInsightOffset,
    );
    const labels = rows.map((row) => row.modelo_prestacao.replace("Administração", "Adm.").replace("Três prestadores distintos", "Três distintos"));
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 155, width: 740, height: 440 }),
      categories: labels,
      series: [
        { name: "% fundos", values: rows.map((row) => num(row.share_fundos)), valuesFormatCode: "0.0%", fill: C.line },
        { name: "% PL", values: rows.map((row) => num(row.share_pl)), valuesFormatCode: "0.0%", fill: C.orange },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 45 },
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fill: C.mid, fontSize: 12 } },
      xAxis: {
        ...chartAxis(10.5, "0%"),
        min: 0,
        max: 1,
        majorUnit: 0.2,
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 10.5, bold: true } },
    });
    addRect(slide, { left: 160, top: 531, width: 630, height: 28 }, C.white);
    addSectionLabel(slide, "VOLUME E QUANTIDADE", { left: 850, top: 155, width: 370, height: 24 });
    addFlatList(
      slide,
      rows.map((row) => ({
        label: row.modelo_prestacao,
        value: `${integer(row.fundos)} · ${bn(row.pl, 1)}`,
        accent: row.modelo_prestacao === "Monoestrutura",
      })),
      { left: 850, top: 200, width: 370, height: 355 },
      { fontSize: 12.5 },
    );
  }

  // 21. Concentração das monoestruturas
  {
    const slide = presentation.slides.add();
    const rows = [...payload.monostructure_concentration].sort((a, b) => num(a.rank_pl_mono) - num(b.rank_pl_mono)).slice(0, 6);
    const bb = rows.find((row) => String(row.grupo_economico).includes("Banco do Brasil"));
    const ot = rows.find((row) => String(row.grupo_economico).includes("Oliveira Trust"));
    addHeader(
      slide,
      "CONCENTRAÇÃO DAS MONOESTRUTURAS",
      "Sistema Petrobras é todo o PL mono do BB; TAPSO representa 54% do PL mono da Oliveira Trust",
      `Fonte: CVM, ${stockShortLower}. A evidência mostra concentração; não permite inferir preços, propostas ou contratos.`,
      18 + providerInsightOffset,
    );
    addEditorialTable(slide, {
      left: 60,
      top: 155,
      width: 735,
      height: 430,
      headers: ["Grupo", "PL mono", "Fundos", "Maior fundo", "Top 1", "Top 3", "HHI"],
      rows: rows.map((row) => [
        row.grupo_economico,
        bn(row.pl_mono_brl, 1).replace("R$ ", ""),
        integer(row.fundos_mono),
        truncateWords(row.maior_fundo, 31),
        pct(row.maior_fundo_share, 1),
        pct(row.top3_share, 1),
        integer(row.hhi_fundos),
      ]),
      columnWidths: [120, 90, 55, 220, 80, 80, 90],
      aligns: ["left", "right", "right", "left", "right", "right", "right"],
      fontSize: 11.2,
      rowHeight: 66,
      rowHighlights: new Set(rows.map((row, idx) => [bb, ot].includes(row) ? idx : -1).filter((idx) => idx >= 0)),
    });
    addSectionLabel(slide, "DOIS CASOS", { left: 845, top: 155, width: 375, height: 24 });
    [
      {
        top: 210,
        name: "FIDC Sistema Petrobras",
        group: "Banco do Brasil",
        value: bn(bb?.pl_mono_brl, 1),
        detail: `${integer(bb?.fundos_mono)} fundo; maior ticket = ${pct(bb?.maior_fundo_share, 0)} do PL mono.`,
      },
      {
        top: 390,
        name: "TAPSO FIDC",
        group: "Oliveira Trust",
        value: bn(ot?.maior_fundo_pl_brl, 1),
        detail: `${integer(ot?.fundos_mono)} fundos; TAPSO = ${pct(ot?.maior_fundo_share, 1)} do PL mono.`,
      },
    ].forEach((item, idx) => {
      addText(slide, item.group.toUpperCase(), { left: 845, top: item.top, width: 375, height: 20 }, {
        fontSize: 11,
        bold: true,
        color: C.orange,
      });
      addText(slide, item.name, { left: 845, top: item.top + 30, width: 375, height: 30 }, {
        fontSize: 18,
        bold: true,
        color: C.black,
      });
      addText(slide, item.value, { left: 845, top: item.top + 70, width: 375, height: 36 }, {
        fontSize: 27,
        bold: true,
        color: idx === 0 ? C.orange : C.black,
      });
      addText(slide, item.detail, { left: 845, top: item.top + 114, width: 375, height: 45 }, {
        fontSize: 13.5,
        color: C.mid,
      });
    });
  }

  // 28. Ofertas encerradas: volume, ritmo e ticket em seis meses fechados.
  {
    const slide = presentation.slides.add();
    const annual = [...(payload.closed_offers_annual || [])]
      .sort((a, b) => num(a.year) - num(b.year));
    const monthly = payload.closed_offers_monthly || [];
    const janJune = payload.closed_offers_jan_june || payload.closed_offers_jan_may || [2024, 2025, 2026].map((year) => {
      const scoped = monthly.filter((row) => num(row.year) === year && num(row.month) <= 6);
      const volume = scoped.reduce((sum, row) => sum + num(row.registered_volume_brl), 0);
      const offers = scoped.reduce((sum, row) => sum + num(row.closed_offers), 0);
      return {
        year,
        closed_offers: offers,
        registered_volume_brl: volume,
        mean_registered_ticket_brl: offers ? volume / offers : null,
      };
    });
    const current = annual.find((row) => num(row.year) === currentOfferYear) || {};
    const currentComparable = janJune.find((row) => num(row.year) === 2026) || {};
    const priorComparable = janJune.find((row) => num(row.year) === 2025) || {};
    const yoy = num(priorComparable.registered_volume_brl)
      ? num(currentComparable.registered_volume_brl) / num(priorComparable.registered_volume_brl) - 1
      : 0;
    const cumulative = (year) => {
      const byMonth = new Map(
        monthly
          .filter((row) => num(row.year) === year && num(row.month) <= 6)
          .map((row) => [num(row.month), row]),
      );
      let running = 0;
      return Array.from({ length: 6 }, (_, index) => {
        running += num(byMonth.get(index + 1)?.registered_volume_brl);
        return running / 1e9;
      });
    };
    addHeader(
      slide,
      "OFERTAS ENCERRADAS · VOLUME E TICKET",
      `Jan–jun/26 somou ${bn(currentComparable.registered_volume_brl, 1)} em ${integer(currentComparable.closed_offers)} ofertas, alta de ${pct(yoy, 1)} sobre 2025`,
      `Fonte: CVM, oferta_resolucao_160.csv (dados.cvm.gov.br/dataset/oferta-distrib), snapshot de ${dateShortPt(payload.offers_source_as_of || offersAsOf)}. Cotas de FIDC, oferta primária, status literal “Oferta Encerrada”, Data de Encerramento até 30/jun/26 e Valor Total Registrado positivo; unidade = Número do Requerimento.`,
      27,
    );
    addSectionLabel(slide, "JAN–JUN · VOLUME REGISTRADO E TICKET", { left: 60, top: 145, width: 550, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 180, width: 550, height: 245 }),
      categories: janJune.map((row) => String(row.year)),
      series: [
        {
          name: "Volume registrado",
          values: janJune.map((row) => num(row.registered_volume_brl) / 1e9),
          valuesFormatCode: "0.0",
          fill: C.charcoal,
          points: janJune.map((row, idx) => ({
            idx,
            fill: num(row.year) === currentOfferYear ? C.orange : C.charcoal,
          })),
          dataLabelOverrides: janJune.map((row, idx) => ({
            idx,
            showValue: true,
            position: "outEnd",
            text: `${(num(row.registered_volume_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} bi\n${integer(row.closed_offers)} · ${mm(row.mean_registered_ticket_brl, 0)}`,
            textStyle: { fill: C.black, fontSize: 9.5, bold: true },
          })),
        },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 60 },
      hasLegend: false,
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 11 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(9, "0"), min: 0 },
      dataLabels: {
        showValue: true,
        position: "outEnd",
        textStyle: { fill: C.black, fontSize: 9.5, bold: true },
      },
    });
    addSectionLabel(slide, "VOLUME ACUMULADO · JAN–JUN · R$ BI", { left: 670, top: 145, width: 550, height: 24 });
    addStraightLineChart(slide, {
      position: { left: 670, top: 180, width: 550, height: 245 },
      categories: MONTHS_SHORT_PT.slice(0, 6).map((month) => month[0].toUpperCase() + month.slice(1)),
      series: [
        { name: "2024", values: cumulative(2024), valuesFormatCode: "0.0", line: { style: "solid", fill: C.note, width: 2 } },
        { name: "2025", values: cumulative(2025), valuesFormatCode: "0.0", line: { style: "solid", fill: C.charcoal, width: 2.2 } },
        { name: "2026", values: cumulative(2026), valuesFormatCode: "0.0", line: { style: "solid", fill: C.orange, width: 3 } },
      ],
      yAxis: { ...chartAxis(9, "0"), min: 0 },
      labelIndices: [0, 1, 2, 3, 4, 5],
      labelFontSize: 8.8,
    });
    addLegend(slide, [
      { label: "2024", color: C.note },
      { label: "2025", color: C.charcoal },
      { label: "2026", color: C.orange },
    ], { left: 810, top: 420, width: 410, height: 22 }, 3);
    addNativeEditorialTable(slide, {
      left: 60,
      top: 466,
      width: 1160,
      height: 150,
      headers: ["Ano", "Ofertas encerradas", "Volume registrado", "Ticket médio", "Ticket mediano", "PF no volume colocado", "Público profissional"],
      rows: annual.map((row) => [
        num(row.year) === currentOfferYear ? `${row.year} jan–jun` : `${row.year} FY`,
        integer(row.closed_offers),
        bn(row.registered_volume_brl, 1),
        mm(row.mean_registered_ticket_brl, 1),
        mm(row.median_registered_ticket_brl, 1),
        pct(row.natural_person_placed_volume_share, 1),
        pct(row.professional_target_registered_volume_share, 1),
      ]),
      columnWidths: [100, 155, 180, 155, 155, 205, 210],
      aligns: ["left", "right", "right", "right", "right", "right", "right"],
      fontSize: 8.8,
      headerFontSize: 8.5,
      rowHighlights: new Set([annual.length - 1]),
    });
    addText(
      slide,
      `PF representa ${pct(current.natural_person_placed_volume_share, 1)} do proxy de volume colocado; a cobertura por quantidade colocada equivale a ${pct(current.placed_quantity_registered_volume_coverage, 1)} do valor registrado.`,
      { left: 60, top: 626, width: 1160, height: 30 },
      { fontSize: 10.2, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
  }

  // 29. Distribuição do ticket.
  {
    const slide = presentation.slides.add();
    const distribution = [...(payload.closed_offer_ticket_distribution || [])]
      .sort((a, b) => num(a.period_order) - num(b.period_order) || num(a.bucket_order) - num(b.bucket_order));
    const periodLabels = [...new Set(distribution.map((row) => row.period_label))];
    const buckets = [...new Set(distribution.map((row) => row.ticket_bucket))];
    const rowFor = (period, bucket) => distribution.find(
      (row) => row.period_label === period && row.ticket_bucket === bucket,
    ) || {};
    const summaries = periodLabels.map((period) => distribution.find((row) => row.period_label === period) || {});
    const current = summaries.at(-1) || {};
    const over500 = distribution.find(
      (row) => row.period_label === current.period_label && String(row.ticket_bucket).startsWith("≥"),
    ) || {};
    const compactBuckets = buckets.map((bucket) => String(bucket).replace(" mi", ""));
    addHeader(
      slide,
      "OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET",
      `${integer(over500.closed_offers)} ofertas ≥ R$ 500 mi concentram ${pct(over500.registered_volume_share, 1)} do volume em jan–jun/26`,
      "Fonte: CVM; mesma coorte do slide anterior. 2024/2025 = ano completo; 2026 = jan–jun.",
      28,
    );

    const addTicketChart = ({
      left,
      width,
      title,
      valueKey,
      formatCode,
      yAxisFormat,
    }) => {
      addSectionLabel(slide, title, { left, top: 145, width, height: 24 });
      slide.charts.add("bar", {
        ...chartBase({ left, top: 183, width, height: 390 }),
        categories: compactBuckets,
        series: periodLabels.map((period, index) => ({
          name: period === "2026 jan-jun" ? "Jan–jun/26" : period.replace(" FY", ""),
          values: buckets.map((bucket) => num(rowFor(period, bucket)[valueKey])),
          valuesFormatCode: formatCode,
          fill: [C.note, C.charcoal, C.orange][index] || C.charcoal,
        })),
        barOptions: { direction: "column", grouping: "clustered", gapWidth: 48 },
        hasLegend: false,
        xAxis: {
          visible: true,
          textStyle: { fill: C.mid, fontSize: 7.4 },
          line: { style: "solid", fill: C.line, width: 1 },
          majorGridlines: null,
        },
        yAxis: { ...chartAxis(7.6, yAxisFormat), min: 0 },
        dataLabels: {
          showValue: true,
          position: "outEnd",
          textStyle: { fill: C.black, fontSize: 6.7, bold: false },
        },
      });
    };

    addTicketChart({
      left: 60,
      width: 360,
      title: "% DAS OFERTAS",
      valueKey: "offer_share",
      formatCode: "0%",
      yAxisFormat: "0%",
    });
    addTicketChart({
      left: 450,
      width: 360,
      title: "% DO VOLUME",
      valueKey: "registered_volume_share",
      formatCode: "0%",
      yAxisFormat: "0%",
    });
    addTicketChart({
      left: 840,
      width: 380,
      title: "VOLUME · R$ BI",
      valueKey: "registered_volume_brl",
      formatCode: "0.0,,,",
      yAxisFormat: "0.0,,,",
    });
    addLegend(slide, [
      { label: "2024FY", color: C.note },
      { label: "2025FY", color: C.charcoal },
      { label: "2026 jan–jun", color: C.orange },
    ], { left: 425, top: 580, width: 430, height: 22 }, 3);
    addText(
      slide,
      `O bucket ≥ R$ 500 mi soma ${bn(over500.registered_volume_brl, 1)} em jan–jun/26; quantidade e volume fecham 100% em cada período.`,
      { left: 60, top: 614, width: 1160, height: 28 },
      { fontSize: 10.6, color: C.charcoal, alignment: "right", verticalAlignment: "middle" },
    );
  }

  // 30. Top 15 ofertas encerradas e originadores.
  {
    const slide = presentation.slides.add();
    const top15 = [...(payload.closed_offer_top15 || [])];
    const summaries = Object.fromEntries(
      (payload.closed_offer_top15_summary || []).map((row) => [row.period_label, row]),
    );
    const table2026 = top15
      .filter((row) => row.period_label === "2026 jan-jun")
      .sort((a, b) => num(a.rank) - num(b.rank));
    const table2025 = top15
      .filter((row) => row.period_label === "2025 FY")
      .sort((a, b) => num(a.rank) - num(b.rank));
    const summary2026 = summaries["2026 jan-jun"] || {};
    const summary2025 = summaries["2025 FY"] || {};
    const publicLabel = (value) => ({
      Profissional: "Prof.",
      Qualificado: "Qualif.",
      Geral: "Geral",
    }[value] || "N/D");
    const tableRows = (rows) => rows.map((row) => [
      integer(row.rank),
      row.fund_name_short,
      truncateWords(row.originator_group || "Não identificado", 22),
      (num(row.registered_volume_brl) / 1e9).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      row.ibba_coord_lead_label,
      row.firm_commitment_label,
      publicLabel(row.publico),
      Number.isFinite(num(row.investor_count))
        ? num(row.investor_count).toLocaleString("pt-BR", { maximumFractionDigits: 0 })
        : "N/D",
    ]);
    const columnWidths = [24, 170, 104, 50, 42, 35, 78, 57];
    const aligns = ["right", "left", "left", "right", "center", "center", "left", "right"];
    addHeader(
      slide,
      "TOP 15 · OFERTAS ENCERRADAS",
      `IBBA liderou ${integer(summary2026.ibba_lead_offers_top15)} das 15 maiores em jan–jun/26, somando ${bn(summary2026.ibba_lead_volume_top15_brl, 1)}`,
      "Fonte: CVM, Oferta Pública de Distribuição; Cotas de FIDC, primária, status Oferta Encerrada. Nº de Inv. = soma dos campos Num_Invest_*.",
      29,
    );
    addSectionLabel(slide, "JAN–JUN/26 · TOP 15", { left: 60, top: 138, width: 560, height: 24 });
    addNativeEditorialTable(slide, {
      left: 60,
      top: 174,
      width: 560,
      height: 440,
      headers: ["#", "FIDC", "Originador", "R$ bi", "IBBA", "GF", "Público", "Inv."],
      rows: tableRows(table2026),
      columnWidths,
      aligns,
      fontSize: 6.5,
      headerFontSize: 6.2,
      rowHighlights: new Set(
        table2026
          .map((row, index) => row.ibba_coord_lead === true ? index : null)
          .filter((index) => index !== null),
      ),
    });
    addSectionLabel(slide, "2025FY · TOP 15", { left: 660, top: 138, width: 560, height: 24 });
    addNativeEditorialTable(slide, {
      left: 660,
      top: 174,
      width: 560,
      height: 440,
      headers: ["#", "FIDC", "Originador", "R$ bi", "IBBA", "GF", "Público", "Inv."],
      rows: tableRows(table2025),
      columnWidths,
      aligns,
      fontSize: 6.5,
      headerFontSize: 6.2,
      rowHighlights: new Set(
        table2025
          .map((row, index) => row.ibba_coord_lead === true ? index : null)
          .filter((index) => index !== null),
      ),
    });
    addText(
      slide,
      `Subtotal: ${bn(summary2026.top15_registered_volume_brl, 2)} · ${pct(summary2026.top15_share_of_period_volume, 1)} do período`,
      { left: 60, top: 620, width: 560, height: 18 },
      { fontSize: 9.2, bold: true, color: C.charcoal, alignment: "right" },
    );
    addText(
      slide,
      `Subtotal: ${bn(summary2025.top15_registered_volume_brl, 2)} · ${pct(summary2025.top15_share_of_period_volume, 1)} do período`,
      { left: 660, top: 620, width: 560, height: 18 },
      { fontSize: 9.2, bold: true, color: C.charcoal, alignment: "right" },
    );
    addText(
      slide,
      "Empates usam o Número do Requerimento crescente. A base pública não contém proposta, fee ou preço de coordenação.",
      { left: 60, top: 642, width: 1160, height: 16 },
      { fontSize: 9.2, color: C.note, alignment: "right" },
    );
  }

  addConclusionsSlide(presentation, payload, 31);

  // 27. Escopo, fontes e limitações
  {
    const slide = presentation.slides.add();
    const coverage = Object.fromEntries(payload.classification_coverage.map((row) => [row.categoria, row.share]));
    addHeader(
      slide,
      "APÊNDICE · ESCOPO E FONTES",
      "Escopo, fontes e limitações",
      `• CVM, ANBIMA Data e FundosNet. ${stockPreliminaryDisclosure} Ofertas consultadas em ${offersSourceShort}.`,
      20 + providerInsightOffset,
    );
    addEditorialTable(slide, {
      left: 60,
      top: 145,
      width: 1160,
      height: 485,
      headers: ["Tema", "Universo / data", "Definição e limitação"],
      rows: [
        ["PL e base investidora", `${integer(payload.qa_latest.veiculos_total)} veículos; ${integer(payload.qa_latest.fundos_total)} fundos; ${stockLong}`, "PL bruto, ex-FIC e FIC-FIDC reconciliados. Contas se repetem por classe/série e não equivalem a investidores únicos."],
        ["Tipo e Foco ANBIMA", `${pct(coverage["Oficial ANBIMA"], 2)} oficial; ${pct(coverage["Evidência documental"], 2)} evidência; ${pct(coverage["Proxy CVM"], 2)} proxy; ${pct(coverage["N/D"], 2)} N/D`, "Tipo, Foco, origem e data permanecem separados. Séries históricas de gestor/custodiante usam cadastro vigente e não são like-for-like."],
        ["Inadimplência", `${integer(payload.qa_latest.veiculos_total)} veículos; ${stockShortLower}`, "Cap por veículo; vazio = ausência de reporte. Ex-360 indisponível por falta de reconciliação do aging."],
        ["Market share", `14 focos; 3 funções; ${stockShortLower}`, "Denominador = PL do subtipo. Top 10 fixo por função; Outros identificados e prestador não informado separados. PL negativo consta no QA."],
        ["Monoestrutura", `${integer(payload.qa_latest.fundos_total)} fundos; ${stockShortLower}`, "Mesma entidade econômica normalizada nas três funções. Concentração não prova poder de preço ou condições comerciais."],
        ["Ofertas encerradas", `2023–2025 FY; 2026 até ${offersShort}`, "Cotas de FIDC, oferta primária, status Oferta Encerrada e valor registrado positivo; coorte pela Data de Encerramento; unidade = Número do Requerimento."],
      ],
      columnWidths: [190, 340, 630],
      aligns: ["left", "left", "left"],
      fontSize: 13.2,
      rowHeight: 75,
    });
  }

  // 24–26. Universo completo dos market shares.
  const fullFocus = payload.market_share
    .filter((row) => row.papel === "administrador")
    .map((row) => ({
      tipo_anbima: row.tipo_anbima,
      foco_anbima: row.foco_anbima,
      foco_order: num(row.foco_order),
    }))
    .filter((row, index, array) =>
      array.findIndex((item) => item.tipo_anbima === row.tipo_anbima && item.foco_anbima === row.foco_anbima) === index,
    )
    .sort((a, b) => a.foco_order - b.foco_order);
  addMarketShareSlide(presentation, payload, "administrador", fullFocus, 21 + providerInsightOffset, true);
  addMarketShareSlide(presentation, payload, "gestor", fullFocus, 22 + providerInsightOffset, true);
  addMarketShareSlide(presentation, payload, "custodiante", fullFocus, 23 + providerInsightOffset, true);

  // 27–46. Fichas dos Top 20.
  payload.profiles
    .sort((a, b) => num(a.rank) - num(b.rank))
    .forEach((profile, index) => {
      const slide = presentation.slides.add();
      const title = `#${profile.rank} ${profile.nome_curto} — ${bn(profile.pl, 1)} e ${pct(profile.market_share_ex_fic, 1)} do PL ex-FIC`;
      addHeader(
        slide,
        "APÊNDICE · CURADORIA TOP 20",
        title,
        `Fonte: ${truncateWords(profile.fonte, 150)} · consulta ${profile.data_consulta}`,
        24 + providerInsightOffset + index,
      );
      addText(
        slide,
        `${profile.cnpj_fundo_formatado} · ${profile.denominacao}`,
        { left: 60, top: 126, width: 1160, height: 38 },
        { fontSize: 12.5, color: C.note, verticalAlignment: "middle" },
      );
      // O PowerPoint para macOS apresentou clipping intermitente em múltiplas
      // caixas curtas nesta ficha. Mantemos o mesmo conteúdo em dois blocos
      // editoriais contínuos, o que elimina a falha sem rasterizar o slide.
      if (num(profile.rank) === 19) {
        addSectionLabel(slide, "MECÂNICA DO FUNDO", { left: 60, top: 176, width: 555, height: 24 });
        addText(
          slide,
          [
            "CEDENTE / ORIGINADOR",
            profile.cedente_originador,
            "",
            "SACADO / PERFIL DE DEVEDORES",
            profile.sacado_devedor,
            "",
            "NATUREZA DOS RECEBÍVEIS",
            profile.natureza_recebiveis,
            "",
            "FUNCIONAMENTO ECONÔMICO",
            profile.funcionamento_economico,
          ].join("\n"),
          { left: 60, top: 216, width: 555, height: 370 },
          { fontSize: 12.5, color: C.charcoal, lineSpacing: 1.04 },
        );
        addSectionLabel(slide, "CAPITAL, EMISSÕES E GOVERNANÇA", { left: 665, top: 176, width: 555, height: 24 });
        addText(
          slide,
          [
            "EMISSÕES / EVENTOS RELEVANTES",
            profile.emissoes,
            "",
            "CLASSES, SUBORDINAÇÃO E GARANTIAS",
            profile.classes_subordinacao_garantias,
            "",
            "PRESTADORES",
            `Administrador: ${profile.administrador}`,
            `Gestor: ${profile.gestor}`,
            `Custodiante: ${profile.custodiante}`,
            "",
            "TIPO / FOCO ANBIMA",
            `${profile.anbima_tipo} · ${profile.anbima_foco}`,
            `Origem: ${profile.origem_classificacao}`,
          ].join("\n"),
          { left: 665, top: 216, width: 555, height: 370 },
          { fontSize: 12.25, color: C.charcoal, lineSpacing: 1.03 },
        );
        addRule(slide, 60, 606, 1160, C.line, 1);
        addText(slide, `Evidência: ${profile.evidencia}`, { left: 60, top: 614, width: 1160, height: 38 }, {
          fontSize: 10.5,
          color: C.note,
          lineSpacing: 0.95,
        });
        return;
      }
      addSectionLabel(slide, "MECÂNICA DO FUNDO", { left: 60, top: 176, width: 555, height: 24 });
      const leftFields = [
        ["CEDENTE / ORIGINADOR", profile.cedente_originador],
        ["SACADO / PERFIL DE DEVEDORES", profile.sacado_devedor],
        ["NATUREZA DOS RECEBÍVEIS", profile.natureza_recebiveis],
        ["FUNCIONAMENTO ECONÔMICO", profile.funcionamento_economico],
      ];
      let y = 216;
      leftFields.forEach(([label, value], fieldIndex) => {
        const heights = [68, 68, 76, 112];
        addText(slide, label, { left: 60, top: y, width: 555, height: 18 }, {
          fontSize: 10.5,
          bold: true,
          color: C.orange,
        });
        addText(slide, value, { left: 60, top: y + 22, width: 555, height: heights[fieldIndex] - 22 }, {
          fontSize: 13.5,
          color: C.charcoal,
          lineSpacing: 1.02,
        });
        y += heights[fieldIndex] + 8;
      });
      addSectionLabel(slide, "CAPITAL, EMISSÕES E GOVERNANÇA", { left: 665, top: 176, width: 555, height: 24 });
      const rightFields = [
        ["EMISSÕES / EVENTOS RELEVANTES", profile.emissoes],
        ["CLASSES, SUBORDINAÇÃO E GARANTIAS", profile.classes_subordinacao_garantias],
        ["PRESTADORES", `Administrador: ${profile.administrador}\nGestor: ${profile.gestor}\nCustodiante: ${profile.custodiante}`],
        ["TIPO / FOCO ANBIMA", `${profile.anbima_tipo} · ${profile.anbima_foco}\nOrigem: ${profile.origem_classificacao}`],
      ];
      y = 216;
      rightFields.forEach(([label, value], fieldIndex) => {
        const heights = [96, 92, 92, 62];
        addText(slide, label, { left: 665, top: y, width: 555, height: 18 }, {
          fontSize: 10.5,
          bold: true,
          color: C.orange,
        });
        addText(slide, value, { left: 665, top: y + 22, width: 555, height: heights[fieldIndex] - 22 }, {
          fontSize: 13,
          color: C.charcoal,
          lineSpacing: 1.01,
        });
        y += heights[fieldIndex] + 8;
      });
      addRule(slide, 60, 606, 1160, C.line, 1);
      addText(slide, `Evidência: ${profile.evidencia}`, { left: 60, top: 614, width: 1160, height: 38 }, {
        fontSize: 10.5,
        color: C.note,
        lineSpacing: 0.95,
      });
    });

  // 47. Caso Atlântico: estratégia NPL e quebra de reporte.
  {
    const slide = presentation.slides.add();
    const profile = payload.atlantico_profile;
    const snapshot = profile.snapshot;
    const bridge = profile.bridge_2024_06_07;
    addHeader(
      slide,
      "APÊNDICE · CASO ATLÂNTICO",
      "Atlântico compra créditos já inadimplidos; jul/24 muda a base de reporte",
      "Fontes: CVM, regulamento de 12/11/24, AGE de 08/07/24 e DFs auditadas de 2024/25. Links completos no workbook.",
      44 + providerInsightOffset,
    );
    addText(
      slide,
      `${profile.cnpj} · ${profile.denominacao}`,
      { left: 60, top: 126, width: 1160, height: 34 },
      { fontSize: 12.2, color: C.note, verticalAlignment: "middle" },
    );

    addSectionLabel(slide, "O QUE É E COMO FUNCIONA", { left: 60, top: 176, width: 555, height: 24 });
    addText(
      slide,
      [
        "ESTRATÉGIA",
        "Veículo fechado de recuperação. O regulamento descreve as carteiras, em regra, como NP, 100% inadimplidas e já baixadas pelos cedentes.",
        "",
        "MECÂNICA ECONÔMICA",
        "Compra definitiva em BIDs, com alto deságio e sem originação pelo Fundo. O retorno depende da recuperação agregada; o saldo contábil é valor esperado descontado, não valor de face.",
        "",
        "CEDENTES E DEVEDORES",
        "Mai/26 nomina Ativos S.A. (19%) e Carrefour Promotora, carteira legada (11%); 70% não são nominados. Devedores são sobretudo PF pulverizadas, com PJ pontuais.",
        "",
        "ATIVOS",
        "Empréstimos, consignado, cheque especial, cartão, CDC, varejo e serviços. Garantias podem existir caso a caso, mas a carteira massificada normalmente não tem garantia real.",
      ].join("\n"),
      { left: 60, top: 212, width: 555, height: 300 },
      { fontSize: 11.8, color: C.charcoal, lineSpacing: 1.02 },
    );
    addSectionLabel(slide, "PRESTADORES ATUAIS", { left: 60, top: 525, width: 555, height: 24 });
    addText(
      slide,
      `Administrador e custodiante: ${providerShort(profile.administrador)} · Gestor: ${providerShort(profile.gestor)}\nConsultoria: MGC Capital · Cobrança: Crediativos · Auditor: BDO`,
      { left: 60, top: 557, width: 555, height: 54 },
      { fontSize: 11.5, color: C.mid, lineSpacing: 1.02 },
    );

    addSectionLabel(slide, `POR QUE A INADIMPLÊNCIA É ALTA · ${stockShort.toUpperCase()}`, { left: 665, top: 176, width: 555, height: 24 });
    addFlatList(
      slide,
      [
        { label: "PL", value: mm(snapshot.pl, 1) },
        { label: "Carteira DC", value: mm(snapshot.carteira, 1) },
        { label: "Inadimplência", value: `${mm(snapshot.inadimplencia_bruta, 1)} · ${pct(snapshot.inadimplencia_share_carteira, 1)}`, accent: true },
        { label: "> 1.080 dias", value: `${mm(snapshot.vencidos_mais_1080d, 1)} · ${pct(snapshot.mais_1080_share_inadimplencia, 2)} da inad.` },
      ],
      { left: 665, top: 212, width: 555, height: 150 },
      { fontSize: 12.5 },
    );
    addText(
      slide,
      "O 99% é coerente com a estratégia NPL: o fundo compra créditos já vencidos. Aging mede o estado jurídico do crédito; não representa perda adicional de 100% sobre o valor contábil.",
      { left: 665, top: 374, width: 555, height: 60 },
      { fontSize: 12.2, color: C.charcoal, lineSpacing: 1.03 },
    );
    addSectionLabel(slide, "QUEBRA JUN→JUL/24 · R$ MI", { left: 665, top: 452, width: 555, height: 24 });
    addEditorialTable(slide, {
      left: 665,
      top: 486,
      width: 555,
      height: 118,
      headers: ["Métrica", "Jun/24 · Sefer", "Jul/24 · ID", "Δ"],
      rows: [
        ["Inadimplência bruta", mm(bridge.inadimplencia_bruta_jun, 1).replace("R$ ", ""), mm(bridge.inadimplencia_bruta_jul, 1).replace("R$ ", ""), mm(bridge.delta_inadimplencia_bruta, 1).replace("R$ ", "")],
        ["Carteira DC", mm(bridge.carteira_jun, 1).replace("R$ ", ""), mm(bridge.carteira_jul, 1).replace("R$ ", ""), mm(bridge.delta_carteira, 1).replace("R$ ", "")],
        ["PL", mm(bridge.pl_jun, 1).replace("R$ ", ""), mm(bridge.pl_jul, 1).replace("R$ ", ""), mm(bridge.delta_pl, 1).replace("R$ ", "")],
      ],
      columnWidths: [210, 120, 110, 115],
      aligns: ["left", "right", "right", "right"],
      fontSize: 10.5,
      rowHighlights: new Set([0]),
    });
    addRule(slide, 60, 620, 1160, C.line, 1);
    addText(
      slide,
      "A quebra no bruto coincide com a troca de administrador e não indica recuperação em caixa. As DFs têm opinião modificada para 01/01–19/07/24 por inconsistências de lastro e posição; a série não é like-for-like.",
      { left: 60, top: 630, width: 1160, height: 30 },
      { fontSize: 10.4, color: C.note, lineSpacing: 0.98 },
    );
  }

  return presentation;
}

function columnLetter(index) {
  let value = index + 1;
  let label = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

function resetSheet(workbook, name) {
  const sheet = workbook.worksheets.getOrAdd(name, {
    renameFirstIfOnlyNewSpreadsheet: true,
  });
  sheet.deleteAllDrawings();
  const used = sheet.getUsedRange();
  if (used) {
    try {
      used.unmerge();
    } catch {
      // A planilha pode não conter merges.
    }
    used.clear({ applyTo: "all" });
  }
  sheet.showGridLines = false;
  return sheet;
}

function setHeaderBand(sheet, title, subtitle, headers, rowCount, options = {}) {
  const lastColumn = columnLetter(headers.length - 1);
  sheet.getRange(`A1:${lastColumn}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A2:${lastColumn}2`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A4:${lastColumn}4`).values = [headers];

  const titleRange = sheet.getRange(`A1:${lastColumn}1`);
  titleRange.format.fill = C.black;
  titleRange.format.font = { name: "Arial", size: 16, bold: true, color: C.white };
  titleRange.format.rowHeightPx = 34;
  titleRange.format.verticalAlignment = "center";

  const subtitleRange = sheet.getRange(`A2:${lastColumn}2`);
  subtitleRange.format.fill = C.white;
  subtitleRange.format.font = { name: "Arial", size: 10, color: C.mid };
  subtitleRange.format.rowHeightPx = 30;
  subtitleRange.format.verticalAlignment = "center";

  const headerRange = sheet.getRange(`A4:${lastColumn}4`);
  headerRange.format.fill = C.black;
  headerRange.format.font = { name: "Arial", size: 10, bold: true, color: C.white };
  headerRange.format.wrapText = true;
  headerRange.format.rowHeightPx = 34;
  headerRange.format.verticalAlignment = "center";
  headerRange.format.borders = {
    bottom: { style: "thin", color: C.black },
  };

  if (rowCount > 0) {
    const body = sheet.getRange(`A5:${lastColumn}${4 + rowCount}`);
    body.format.font = { name: "Arial", size: Math.round(options.bodyFontSize || 9), color: C.charcoal };
    body.format.verticalAlignment = "center";
    body.format.borders = {
      insideHorizontal: { style: "thin", color: C.line },
      bottom: { style: "thin", color: C.line },
    };
    body.format.wrapText = options.wrapText ?? false;
    if (rowCount <= 700) {
      for (let index = 1; index < rowCount; index += 2) {
        sheet.getRange(`A${5 + index}:${lastColumn}${5 + index}`).format.fill = C.pale;
      }
    }
  }
  sheet.freezePanes.freezeRows(4);
  if (options.freezeColumns) sheet.freezePanes.freezeColumns(options.freezeColumns);
}

function applyColumnWidths(sheet, widths, rowCount) {
  widths.forEach((width, index) => {
    const letter = columnLetter(index);
    sheet.getRange(`${letter}1:${letter}${Math.max(5, rowCount + 4)}`).format.columnWidthPx = width;
  });
}

function applyFormatsByHeader(sheet, headers, rowCount) {
  if (!rowCount) return;
  headers.forEach((header, index) => {
    const letter = columnLetter(index);
    const range = sheet.getRange(`${letter}5:${letter}${rowCount + 4}`);
    const normalized = String(header).toLowerCase();
    if (/share|cobertura|percentual|pct|%|top 1|top 3|top 5|top 10/.test(normalized)) {
      range.format.numberFormat = "0.00%";
      range.format.horizontalAlignment = "right";
    } else if (/pl|carteira|inadimpl|excesso|volume|valor/.test(normalized) && !/status|motivo|regra|fonte|evid/.test(normalized)) {
      range.format.numberFormat = "R$ #,##0.00";
      range.format.horizontalAlignment = "right";
    } else if (/rank|fundos|veículos|casos|quantidade|contas|hhi/.test(normalized)) {
      range.format.numberFormat = "#,##0";
      range.format.horizontalAlignment = "right";
    } else if (/cnpj/.test(normalized)) {
      range.format.numberFormat = "@";
    }
  });
}

async function writeRowsInChunks(sheet, startRowZeroBased, headers, rows, chunkSize = 5000) {
  for (let offset = 0; offset < rows.length; offset += chunkSize) {
    const chunk = rows.slice(offset, offset + chunkSize).map((row) =>
      headers.map((header) => asCell(row[header], header)),
    );
    sheet
      .getRangeByIndexes(startRowZeroBased + offset, 0, chunk.length, headers.length)
      .values = chunk;
  }
}

function worksheetRowsFromPayload(rows, columns) {
  return rows.map((row) =>
    Object.fromEntries(columns.map(([header, key, transform]) => [header, transform ? transform(row[key], row) : row[key]])),
  );
}

async function addQaSheet(workbook) {
  const csv = await readCsv(path.join(REVISION_DIR, "qa_inadimplencia_competencia.csv"));
  const sourceRows = csvRowsAsObjects(csv);
  const headers = [
    "Competência",
    "Veículos total",
    "Fundos total",
    "Carteira positiva",
    "Campos reportados",
    "PL total",
    "PL coberto",
    "Cobertura PL",
    "Carteira total",
    "Carteira coberta",
    "Cobertura carteira",
    "Inadimplência bruta",
    "Inadimplência ajustada",
    "Bruta %",
    "Ajustada %",
    "Ajustada ex-NP %",
    "Casos acima da carteira",
    "PL dos casos",
    "Share PL dos casos",
    "Excesso removido",
    "Top 1 excesso",
    "Top 5 excesso",
    "Top 10 excesso",
    "Aging total",
    "Gap aging vs Tabela I",
    "Status aging",
    "Presença exata",
    "Qualidade cobertura",
  ];
  const keyMap = [
    "competencia",
    "veiculos_total",
    "fundos_total",
    "veiculos_com_carteira_positiva",
    "veiculos_com_campos_reportados",
    "pl_total_brl",
    "pl_coberto_brl",
    "cobertura_pl",
    "carteira_positiva_total_brl",
    "carteira_coberta_brl",
    "cobertura_carteira",
    "inadimplencia_bruta_brl",
    "inadimplencia_ajustada_brl",
    "inadimplencia_bruta_pct",
    "inadimplencia_ajustada_pct",
    "inadimplencia_ajustada_ex_np_pct",
    "casos_inad_supera_carteira",
    "casos_inad_supera_carteira_pl_brl",
    "casos_inad_supera_carteira_share_pl",
    "excesso_removido_brl",
    "excesso_top1_share",
    "excesso_top5_share",
    "excesso_top10_share",
    "aging_inadimplente_total_brl",
    "aging_gap_vs_inadimplencia_reportada_brl",
    "aging_publication_status",
    "presenca_campo_exata",
    "qualidade_cobertura",
  ];
  const rows = sourceRows.map((row) =>
    Object.fromEntries(headers.map((header, index) => [header, row[keyMap[index]]])),
  );
  const sheet = resetSheet(workbook, "QA Inadimplência");
  setHeaderBand(
    sheet,
    "QA Inadimplência",
    "Resumo por competência. Campos ausentes permanecem distintos de zero; a base detalhada está em 'Base competência-CNPJ'.",
    headers,
    rows.length,
    { freezeColumns: 1 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [85, 80, 75, 90, 95, 110, 110, 85, 110, 110, 90, 115, 115, 80, 80, 90, 95, 110, 90, 115, 80, 80, 85, 115, 115, 180, 85, 135], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["F", "G", "I", "J", "L", "M", "R", "T", "X", "Y"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`A5:AB${rows.length + 4}`).format.rowHeightPx = 22;
}

async function addVehicleCompetenceSheet(workbook, payload) {
  const csv = await readCsv(path.join(REVISION_DIR, "base_competencia_cnpj.csv.gz"));
  const competenceIndex = csv.headers.indexOf("competencia");
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  const auditMonths = new Set(["2024-06", "2024-07", payload.latest_complete]);
  const scopedCsvRows = csv.rows.filter((row) => auditMonths.has(row[competenceIndex]));
  const selected = [
    ["Competência", "competencia"],
    ["CNPJ veículo", "cnpj_formatado"],
    ["CNPJ fundo", "cnpj_fundo_formatado"],
    ["Tipo registro", "tp_registro"],
    ["Denominação", "denominacao"],
    ["PL", "pl"],
    ["Carteira DC", "carteira_dc"],
    ["Inadimplência reportada", "dc_inadimplentes"],
    ["Vincendas ligadas a inad.", "dc_a_vencer_com_parcela_inad"],
    ["Até 30d", "inad_ate_30d"],
    ["31–60d", "inad_31_60d"],
    ["61–90d", "inad_61_90d"],
    ["91–120d", "inad_91_120d"],
    ["121–150d", "inad_121_150d"],
    ["151–180d", "inad_151_180d"],
    ["181–360d", "inad_181_360d"],
    ["361–720d", "inad_361_720d"],
    ["721–1080d", "inad_721_1080d"],
    [">1080d", "inad_maior_1080d"],
    [">360d", "inad_acima_360d"],
    ["Reporta carteira", "reports_carteira_dc"],
    ["Reporta inad.", "reports_dc_inadimplentes"],
    ["Reporta aging", "reports_aging"],
    ["Presença exata", "field_presence_exact"],
    ["NP", "is_np"],
    ["Regra inclusão", "regra_inclusao"],
    ["Motivo ajuste", "motivo_ajuste"],
    ["Ajustado (fórmula)", null],
    ["Excesso (fórmula)", null],
  ];
  const headers = selected.map(([header]) => header);
  const indexBySource = Object.fromEntries(csv.headers.map((header, index) => [header, index]));
  const rows = scopedCsvRows.map((row) =>
    Object.fromEntries(
      selected.map(([header, source]) => [header, source ? row[indexBySource[source]] ?? "" : null]),
    ),
  );
  const sheet = resetSheet(workbook, "Base competência-CNPJ");
  setHeaderBand(
    sheet,
    "Base competência/CNPJ",
    `Recorte operacional de jun/24, jul/24 e ${stockShortLower}. A base longitudinal completa está em data/industry_study/generated_revision/base_competencia_cnpj.csv.gz. Ajustado e excesso são fórmulas.`,
    headers,
    rows.length,
    { freezeColumns: 3, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows, 3500);
  const portfolioCol = columnLetter(headers.indexOf("Carteira DC"));
  const inadCol = columnLetter(headers.indexOf("Inadimplência reportada"));
  const adjustedCol = columnLetter(headers.indexOf("Ajustado (fórmula)"));
  const excessCol = columnLetter(headers.indexOf("Excesso (fórmula)"));
  const lastRow = rows.length + 4;
  sheet.getRange(`${adjustedCol}5`).formulas = [[`=IF(AND(${portfolioCol}5<>"",${inadCol}5<>""),MIN(MAX(${inadCol}5,0),MAX(${portfolioCol}5,0)),"")`]];
  sheet.getRange(`${adjustedCol}5:${adjustedCol}${lastRow}`).fillDown();
  sheet.getRange(`${excessCol}5`).formulas = [[`=IF(${adjustedCol}5="","",MAX(${inadCol}5-${adjustedCol}5,0))`]];
  sheet.getRange(`${excessCol}5:${excessCol}${lastRow}`).fillDown();
  applyColumnWidths(
    sheet,
    [78, 118, 118, 86, 260, 105, 105, 115, 115, 82, 82, 82, 82, 82, 82, 82, 82, 82, 82, 82, 82, 82, 80, 82, 55, 175, 230, 115, 115],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
}

async function addFundBaseSheet(workbook, payload) {
  const csv = await readCsv(path.join(REVISION_DIR, "monoestrutura_por_fundo.csv"));
  const sourceRows = csvRowsAsObjects(csv);
  const columns = [
    ["Competência", "competencia"],
    ["CNPJ fundo", "cnpj_fundo_formatado"],
    ["Denominação", "denominacao"],
    ["PL", "pl"],
    ["Carteira DC", "carteira_dc"],
    ["Inadimplência", "dc_inadimplentes"],
    ["Ajustada", "dc_inadimplentes_ajustado_recalculado"],
    ["Tipo ANBIMA", "anbima_tipo"],
    ["Foco ANBIMA", "anbima_foco"],
    ["Origem classificação", "classification_status"],
    ["Administrador", "admin_nome"],
    ["Grupo administrador", "administrador_grupo"],
    ["Gestor", "gestor_nome"],
    ["Grupo gestor", "gestor_grupo"],
    ["Custodiante", "custodiante_nome"],
    ["Grupo custodiante", "custodiante_grupo"],
    ["Modelo prestação", "modelo_prestacao"],
    ["Monoestrutura grupo", "monoestrutura_conglomerado"],
    ["Monoestrutura entidade", "monoestrutura_entidade_legal"],
    ["Prestadores ausentes", "prestadores_ausentes"],
    ["Top 20", "is_top20_fidc"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(sourceRows, columns);
  const sheet = resetSheet(workbook, "Base por fundo-CNPJ");
  setHeaderBand(
    sheet,
    "Base por fundo/CNPJ",
    `Fotografia de ${competenceShortPt(payload.latest_complete).toLowerCase()} reconciliada a ${integer(rows.length)} fundos. A unidade legal e a entidade econômica normalizada permanecem em colunas distintas.`,
    headers,
    rows.length,
    { freezeColumns: 3, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows, 2500);
  applyColumnWidths(sheet, [80, 120, 300, 110, 110, 110, 110, 140, 170, 190, 250, 150, 250, 150, 250, 150, 160, 110, 110, 105, 70], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
}

async function addMonoConcentrationSheet(workbook) {
  const csv = await readCsv(path.join(REVISION_DIR, "monoestrutura_concentracao.csv"));
  const sourceRows = csvRowsAsObjects(csv);
  const columns = [
    ["Rank", "rank_pl_mono"],
    ["Grupo econômico", "grupo_economico"],
    ["PL monoestrutura", "pl_mono_brl"],
    ["Fundos mono", "fundos_mono"],
    ["Maior fundo", "maior_fundo"],
    ["CNPJ maior fundo", "maior_fundo_cnpj"],
    ["PL maior fundo", "maior_fundo_pl_brl"],
    ["Share maior fundo", "maior_fundo_share"],
    ["Top 3", "top3_share"],
    ["Top 5", "top5_share"],
    ["Top 10", "top10_share"],
    ["HHI", "hhi_fundos"],
    ["Fundos no Top 20", "fundos_top20"],
    ["PL no Top 20", "pl_top20_brl"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(sourceRows, columns);
  const sheet = resetSheet(workbook, "Concentração de monoestruturas");
  setHeaderBand(
    sheet,
    "Concentração de monoestruturas",
    "Definição adotada: mesmo conglomerado econômico normalizado nas três funções. HHI calculado sobre o PL dos fundos do grupo.",
    headers,
    rows.length,
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [60, 170, 120, 85, 260, 120, 120, 105, 80, 80, 80, 80, 100, 115], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
}

async function addMarketShareSheet(workbook) {
  const csv = await readCsv(path.join(REVISION_DIR, "market_share_por_subtipo.csv"));
  const sourceRows = csvRowsAsObjects(csv);
  const columns = [
    ["Competência", "competencia"],
    ["Função", "papel"],
    ["Tipo ANBIMA", "tipo_anbima"],
    ["Foco ANBIMA", "foco_anbima"],
    ["Ordem foco", "foco_order"],
    ["Bucket participante", "participante_bucket"],
    ["Tipo bucket", "bucket_kind"],
    ["Ordem stack", "stack_order"],
    ["PL bucket", "pl_brl"],
    ["PL líquido subtipo", "denominador_pl_subtipo_brl"],
    ["Denominador publicado (PL positivo)", "denominador_publicacao_pl_positivo_brl"],
    ["Share subtipo", "share_subtipo"],
    ["PL identificado", "pl_identificado_brl"],
    ["Cobertura prestador", "cobertura_prestador_pl"],
    ["Fundos subtipo", "fundos_subtipo"],
    ["Fundos PL negativo", "fundos_pl_negativo"],
    ["PL negativo", "pl_negativo_brl"],
    ["Nota qualidade", "quality_note"],
    ["Status publicação", "publication_status"],
    ["Fechamento 100%", "fechamento_100_pct"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(sourceRows, columns);
  const sheet = resetSheet(workbook, "Market share por subtipo");
  setHeaderBand(
    sheet,
    "Market share por subtipo",
    "Tipo/Foco ANBIMA; PL ex-FIC sem Sistema Petrobras/TAPSO. Top 10 fixo por função + Outros identificados + prestador N/D. PL negativo fica no QA e fora da normalização percentual sobre PL positivo.",
    headers,
    rows.length,
    { freezeColumns: 4, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [80, 105, 150, 180, 65, 250, 100, 70, 110, 125, 135, 90, 110, 100, 85, 95, 105, 240, 160, 95], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
}

async function addTop20Sheets(workbook, payload) {
  {
    const columns = [
      ["Rank", "rank"],
      ["CNPJ fundo", "cnpj_fundo_formatado"],
      ["Denominação", "denominacao"],
      ["PL", "pl"],
      ["Market share ex-FIC", "market_share_ex_fic"],
      ["Tipo ANBIMA", "anbima_tipo"],
      ["Foco ANBIMA", "anbima_foco"],
      ["Origem classificação", "classification_status"],
      ["Administrador", "admin_nome"],
      ["Gestor", "gestor_nome"],
      ["Custodiante", "custodiante_nome"],
      ["Modelo prestação", "modelo_prestacao"],
      ["Monoestrutura grupo", "monoestrutura_conglomerado"],
    ];
    const headers = columns.map(([header]) => header);
    const rows = worksheetRowsFromPayload(payload.top20_fidcs, columns);
    const sheet = resetSheet(workbook, "Top 20 FIDCs");
    setHeaderBand(sheet, "Top 20 FIDCs", `Ranking de ${competenceShortPt(payload.latest_complete).toLowerCase()} sobre o universo completo ex-FIC. Exatamente 20 fundos; ficha detalhada na aba 'Curadoria Top 20'.`, headers, rows.length, { freezeColumns: 3, wrapText: true });
    await writeRowsInChunks(sheet, 4, headers, rows);
    applyColumnWidths(sheet, [60, 120, 360, 120, 110, 150, 180, 190, 260, 260, 260, 170, 110], rows.length);
    applyFormatsByHeader(sheet, headers, rows.length);
    sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
    sheet.getRange(`A5:M${rows.length + 4}`).format.rowHeightPx = 42;
  }
  {
    const columns = [
      ["Rank Outros", "rank_outros"],
      ["CNPJ fundo", "cnpj_fundo_formatado"],
      ["Denominação", "denominacao"],
      ["PL", "pl"],
      ["Share Outros", "market_share_outros"],
      ["Classificação oficial", "classificacao_oficial"],
      ["Hipótese de revisão", "hipotese_revisao"],
      ["Evidência", "evidencia_revisao"],
      ["Fonte", "fonte_revisao"],
      ["Status", "status_revisao"],
    ];
    const headers = columns.map(([header]) => header);
    const rows = worksheetRowsFromPayload(payload.top20_outros, columns);
    const sheet = resetSheet(workbook, "Top 20 Outros");
    setHeaderBand(sheet, "Top 20 Outros", "Classificação oficial, hipótese econômica, evidência, fonte e status permanecem separados. Hipótese não altera automaticamente o cadastro ANBIMA.", headers, rows.length, { freezeColumns: 3, wrapText: true });
    await writeRowsInChunks(sheet, 4, headers, rows);
    applyColumnWidths(sheet, [70, 120, 340, 120, 95, 230, 240, 360, 250, 145], rows.length);
    applyFormatsByHeader(sheet, headers, rows.length);
    sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
    sheet.getRange(`A5:J${rows.length + 4}`).format.rowHeightPx = 88;
  }
}

async function addCurationSheet(workbook, payload) {
  const columns = [
    ["Rank", "rank"],
    ["CNPJ fundo", "cnpj_fundo_formatado"],
    ["Denominação", "denominacao"],
    ["PL", "pl"],
    ["Market share ex-FIC", "market_share_ex_fic"],
    ["Cedente / originador", "cedente_originador"],
    ["Sacado / devedor", "sacado_devedor"],
    ["Natureza dos recebíveis", "natureza_recebiveis"],
    ["Funcionamento econômico", "funcionamento_economico"],
    ["Emissões relevantes", "emissoes"],
    ["Classes / subordinação / garantias", "classes_subordinacao_garantias"],
    ["Administrador", "administrador"],
    ["Gestor", "gestor"],
    ["Custodiante", "custodiante"],
    ["Tipo ANBIMA", "anbima_tipo"],
    ["Foco ANBIMA", "anbima_foco"],
    ["Origem Tipo/Foco", "origem_classificacao"],
    ["Data referência Tipo/Foco", "data_referencia_tipo_foco"],
    ["Status curadoria", "status_curadoria"],
    ["Campos não identificados", "campos_nao_identificados"],
    ["Documentos primários", "documentos_primarios_ids"],
    ["Fonte / link", "fonte"],
    ["Data consulta", "data_consulta"],
    ["Evidência / nota", "evidencia"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.profiles, columns);
  const sheet = resetSheet(workbook, "Curadoria Top 20");
  setHeaderBand(
    sheet,
    "Curadoria Top 20",
    "Fontes primárias: CVM/FundosNet, regulamentos, ofertas, assembleias e informes. 'Não identificado' registra a lacuna; não é inferência pelo nome.",
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [55, 120, 340, 110, 100, 360, 340, 350, 430, 430, 430, 260, 260, 260, 150, 180, 180, 110, 150, 300, 150, 360, 110, 360], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:X${rows.length + 4}`).format.rowHeightPx = 120;
}

async function addHistoricalComparisonsSheet(workbook, payload) {
  const headers = [
    "Painel",
    "Competência",
    "Categoria / função",
    "Quantidade",
    "Share quantidade",
    "PL / valor",
    "Share PL / valor",
    "Denominador quantidade",
    "Denominador PL / valor",
    "Cobertura PL",
    "PL N/D",
    "Top 5",
    "Top 10",
    "Nota",
  ];
  const rows = [];
  const holderMeta = Object.fromEntries(
    payload.holder_distribution_meta_history.map((row) => [row.competencia, row]),
  );
  payload.holder_distribution_history.forEach((row) => {
    const meta = holderMeta[row.competencia] || {};
    rows.push({
      "Painel": "Número de cotistas",
      "Competência": row.competencia,
      "Categoria / função": row.bucket,
      "Quantidade": row.fundos,
      "Share quantidade": row.share_fundos,
      "PL / valor": row.pl,
      "Share PL / valor": row.share_pl,
      "Denominador quantidade": row.universo_fundos,
      "Denominador PL / valor": row.universo_pl,
      "Cobertura PL": meta.pl_coverage,
      "PL N/D": null,
      "Top 5": null,
      "Top 10": null,
      "Nota": "Ex-FIC; PL nominal ≥ R$ 200 mi; contas por classe/série.",
    });
  });
  payload.type_mix_history.forEach((row) => {
    const total = payload.type_mix_history
      .filter((item) => item.competencia === row.competencia)
      .reduce((sum, item) => sum + num(item.pl), 0);
    rows.push({
      "Painel": "Tipo ANBIMA",
      "Competência": row.competencia,
      "Categoria / função": row.anbima_tipo,
      "Quantidade": null,
      "Share quantidade": null,
      "PL / valor": row.pl,
      "Share PL / valor": row.share,
      "Denominador quantidade": null,
      "Denominador PL / valor": total,
      "Cobertura PL": null,
      "PL N/D": null,
      "Top 5": null,
      "Top 10": null,
      "Nota": "Taxonomia cadastral vigente aplicada ao histórico; FIC atual em período ex-FIC entra em N/D.",
    });
  });
  const receivablesMeta = Object.fromEntries(
    payload.receivables_meta_history.map((row) => [row.competencia, row]),
  );
  payload.receivables_history.filter((row) => num(row.valor) > 0).forEach((row) => {
    const meta = receivablesMeta[row.competencia] || {};
    rows.push({
      "Painel": "Tipo de recebível",
      "Competência": row.competencia,
      "Categoria / função": row.segmento,
      "Quantidade": null,
      "Share quantidade": null,
      "PL / valor": row.valor,
      "Share PL / valor": row.share_reported,
      "Denominador quantidade": null,
      "Denominador PL / valor": meta.reported_total,
      "Cobertura PL": null,
      "PL N/D": null,
      "Top 5": null,
      "Top 10": null,
      "Nota": `Tabela II; gap vs Tabela I: ${pct(meta.gap_pct, 2)}.`,
    });
  });
  payload.provider_concentration_history.forEach((row) => {
    rows.push({
      "Painel": "Prestadores",
      "Competência": row.competencia,
      "Categoria / função": roleLabel(row.papel),
      "Quantidade": row.n_fundos,
      "Share quantidade": null,
      "PL / valor": row.identified_pl,
      "Share PL / valor": null,
      "Denominador quantidade": row.n_fundos,
      "Denominador PL / valor": row.total_pl,
      "Cobertura PL": row.coverage_pl,
      "PL N/D": row.missing_pl,
      "Top 5": row.top5_share,
      "Top 10": row.top10_share,
      "Nota": row.source_note,
    });
  });
  const sheet = resetSheet(workbook, "Comparativos históricos");
  setHeaderBand(
    sheet,
    "Comparativos históricos",
    "Bases dos slides 5, 6, 7 e 10. Percentuais de recebíveis fecham sobre a soma segmentada da Tabela II; prestador não informado permanece no denominador.",
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [145, 85, 190, 90, 100, 115, 105, 115, 125, 90, 105, 80, 80, 360], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["F", "I", "K"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`A5:N${rows.length + 4}`).format.rowHeightPx = 36;
}

async function addProviderHistorySheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Função", "papel"],
    ["Participante", "participante"],
    ["Posição", "rank_periodo"],
    ["PL", "pl_brl"],
    ["Share", "share_pl"],
    ["Fundos", "fundos"],
    ["Denominador PL", "denominador_pl_brl"],
    ["Fundos no universo", "fundos_universo"],
    ["Origem do prestador", "fonte_prestador"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.provider_historical_ranking || [], columns);
  const sheet = resetSheet(workbook, "Ranking prestadores");
  setHeaderBand(
    sheet,
    "Ranking prestadores",
    "PL ex-FIC; Sistema Petrobras e TAPSO excluídos em todos os períodos. Administração observada; gestão e custódia históricas reconstruídas com cadastro vigente.",
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 100, 230, 75, 115, 85, 75, 125, 100, 280], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`E5:E${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`F5:F${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`H5:H${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:J${rows.length + 4}`).format.rowHeightPx = 32;
}

async function addSingleReceivableDelinquencySheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Tipo Tabela II", "tipo_recebivel_tabela_ii"],
    ["Fundos incluídos", "fundos_incluidos"],
    ["PL incluído", "pl_incluido_brl"],
    ["Carteira incluída", "carteira_incluida_brl"],
    ["Inadimplência reportada", "inadimplencia_reportada_brl"],
    ["Valor Tabela II", "valor_tabela_ii_brl"],
    ["Inadimplência / PL", "inadimplencia_sobre_pl"],
    ["Inadimplência / carteira", "inadimplencia_sobre_carteira"],
    ["Share do PL ex-FIC positivo", "share_pl_universo_ex_fic_positivo"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.delinquency_single_receivable || [], columns);
  const sheet = resetSheet(workbook, "Inadimplência por recebível");
  setHeaderBand(
    sheet,
    "Inadimplência por tipo de recebível único",
    "Ex-FIC com PL positivo e exatamente um campo superior da Tabela II diferente de zero. Inadimplência acima da carteira é excluída integralmente; numerador = inadimplência reportada; denominador = PL.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 165, 95, 125, 125, 145, 125, 115, 130, 135], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["D", "E", "F", "G"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`H5:J${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:J${rows.length + 4}`).format.rowHeightPx = 34;

  const summary = payload.delinquency_single_receivable_summary || {};
  const summaryRow = rows.length + 7;
  const summaryHeaders = ["Métrica de cobertura / exclusão", "Fundos", "PL"];
  const summaryRows = [
    ["Universo ex-FIC com PL positivo", summary.fundos_universo_ex_fic_pl_positivo, summary.pl_universo_ex_fic_positivo_brl],
    ["Incluídos", summary.fundos_incluidos, summary.pl_incluido_brl],
    ["Mais de um tipo", summary.fundos_multitipo_excluidos, summary.pl_multitipo_excluido_brl],
    ["Sem tipo", summary.fundos_sem_tipo_excluidos, summary.pl_sem_tipo_excluido_brl],
    ["Inadimplência acima da carteira", summary.fundos_inad_supera_carteira_excluidos, summary.pl_inad_supera_carteira_excluido_brl],
    ["FIC-FIDC", summary.fundos_fic_excluidos, summary.pl_fic_excluido_brl],
  ];
  sheet.getRange(`A${summaryRow}:C${summaryRow}`).values = [summaryHeaders];
  sheet.getRange(`A${summaryRow}:C${summaryRow}`).format.fill = C.black;
  sheet.getRange(`A${summaryRow}:C${summaryRow}`).format.font = { name: "Arial", size: 9, bold: true, color: C.white };
  sheet.getRangeByIndexes(summaryRow, 0, summaryRows.length, 3).values = summaryRows;
  sheet.getRange(`C${summaryRow + 1}:C${summaryRow + summaryRows.length}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
}

async function addFrozenDelinquencyHistorySheet(workbook, payload) {
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  const columns = [
    ["Competência", "competencia"],
    [`Tipo Tabela II congelado em ${stockShortLower}`, "tipo_recebivel_tabela_ii"],
    ["Fundos da coorte", "fundos_coorte"],
    ["Fundos presentes", "fundos_presentes"],
    ["Fundos incluídos", "fundos_incluidos"],
    [`PL da coorte em ${stockShortLower}`, "pl_coorte_referencia_brl"],
    ["PL presente", "pl_presente_brl"],
    ["PL incluído", "pl_incluido_brl"],
    ["Carteira incluída", "carteira_incluida_brl"],
    ["Inadimplência ajustada", "inadimplencia_ajustada_brl"],
    ["Inadimplência / PL", "inadimplencia_sobre_pl"],
    ["Inadimplência / carteira", "inadimplencia_sobre_carteira"],
    ["Cobertura dos fundos da coorte", "cobertura_fundos_coorte"],
    ["Cobertura do PL de referência", "cobertura_pl_referencia_coorte"],
    ["Excluídos: inad. > carteira", "fundos_inad_supera_carteira_excluidos"],
    ["Excluídos: campos ausentes", "fundos_campos_ausentes_excluidos"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.delinquency_frozen_cohort_history || [], columns);
  const sheet = resetSheet(workbook, "Histórico inad. coorte");
  setHeaderBand(
    sheet,
    "Inadimplência histórica da coorte atual por tipo de recebível",
    `Coorte e subtipo congelados em ${stockShortLower}. Em cada competência entram apenas os mesmos CNPJs presentes, ex-FIC, com PL positivo, campos reportados e inadimplência até a carteira. A série incorpora viés de sobrevivência.`,
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows, 2500);
  applyColumnWidths(sheet, [90, 185, 90, 90, 90, 130, 115, 115, 125, 135, 110, 125, 125, 135, 120, 120], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["F", "G", "H", "I", "J"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`K5:N${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:P${rows.length + 4}`).format.rowHeightPx = 31;
}

async function addIndependentProviderSheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Função", "papel"],
    ["Participante consolidado", "participante"],
    ["Posição entre independentes", "rank_independente"],
    ["Posição geral", "rank_geral"],
    ["PL", "pl_brl"],
    ["Fundos", "fundos"],
    ["Denominador PL", "denominador_pl_brl"],
    ["Status societário", "ownership_status"],
    ["Regra de consolidação", "ownership_notes"],
    ["Fonte", "ownership_source_url"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.provider_independent_ranking || [], columns);
  const sheet = resetSheet(workbook, "Ranking independentes");
  setHeaderBand(
    sheet,
    "Ranking de prestadores independentes",
    "PL ex-FIC; Sistema Petrobras e TAPSO excluídos. Singulare consolidada em QI Tech. Kanastra alocada ao Itaú pela regra de afiliação solicitada; posições geral e entre independentes permanecem separadas.",
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 95, 190, 120, 90, 115, 75, 125, 180, 300, 340], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`F5:F${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`H5:H${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:K${rows.length + 4}`).format.rowHeightPx = 42;
}

async function addBankFidcSheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Grupo bancário", "grupo_bancario"],
    ["Raízes listadas", "fundos_curados"],
    ["Raízes observadas", "fundos_observados"],
    ["PL bruto", "pl_bruto_brl"],
    ["PL bruto original", "pl_brl_raw"],
    ["PL oficial recuperado", "pl_recovered_official"],
    ["Sufixo", "pl_display_suffix"],
    ["Observado", "observado"],
    ["Raízes de CNPJ listadas", "raizes_cnpj_listadas"],
    ["Raízes de CNPJ observadas", "raizes_cnpj_observadas"],
    ["Raízes ausentes", "raizes_cnpj_nao_observadas"],
    ["Referências", "source_references"],
    ["Fonte do PL recuperado", "pl_source_references"],
    ["Definição", "metodologia"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.bank_fidc_evolution || [], columns);
  const sheet = resetSheet(workbook, "FIDCs por banco");
  setHeaderBand(
    sheet,
    "Evolução dos FIDCs hoje listados para cinco bancos",
    "Coorte fixa de raízes de CNPJ extraída de FIDCs.xlsx. Dez/25 inclui o PL oficial recuperado do BTG Consignados I, com valor bruto original preservado. A série não reproduz datas societárias de consolidação contábil.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 150, 95, 105, 125, 125, 95, 55, 85, 250, 250, 220, 300, 300, 520], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`C5:D${rows.length + 4}`).format.numberFormat = "#,##0";
  sheet.getRange(`E5:F${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`J5:L${rows.length + 4}`).format.numberFormat = "@";
  sheet.getRange(`A5:O${rows.length + 4}`).format.rowHeightPx = 58;
}

async function addBankFidcDetailSheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Grupo bancário", "grupo_bancario"],
    ["Raiz CNPJ", "cnpj_root8"],
    ["CNPJ fundo/classe", "cnpj_fundo"],
    ["Fundo", "denominacao"],
    ["Nome curto", "nome_curto"],
    ["PL bruto", "pl_brl"],
    ["PL bruto original", "pl_brl_raw"],
    ["PL oficial recuperado", "pl_recovered_official"],
    ["Sufixo", "pl_display_suffix"],
    ["Fonte do PL recuperado", "pl_source_reference"],
    ["Observado", "observado"],
    ["PL reportado zero", "pl_reportado_zero"],
    ["Referência da curadoria", "source_reference"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.bank_fidc_detail || [], columns);
  const sheet = resetSheet(workbook, "Detalhe coorte bancos");
  setHeaderBand(
    sheet,
    "Fundos da coorte atual dos cinco bancos",
    "Fundos listados nos conglomerados prudenciais consultados no BCB em jul/26 e reproduzidos em FIDCs.xlsx. O BTG Consignados I em dez/25 usa PL oficial recuperado do IME/DF, mantendo o zero bruto para auditoria. A visão retroativa acompanha somente o conjunto atual.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 135, 90, 125, 390, 170, 125, 125, 95, 55, 320, 80, 100, 230], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`G5:H${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:N${rows.length + 4}`).format.rowHeightPx = 52;
}

async function addAcquiringReclassificationSheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Categoria analítica", "categoria_analitica"],
    ["PL", "pl_brl"],
    ["Share PL", "share_pl"],
    ["Denominador PL ex-FIC", "denominador_pl_brl"],
    ["Fundos", "fundos"],
    ["Regra", "metodologia"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.acquiring_reclassified_mix || [], columns);
  const currentAcquiring = [...(payload.acquiring_reclassified_mix || [])]
    .filter((row) => row.categoria_analitica === "Adquirência")
    .sort((a, b) => String(b.competencia || "").localeCompare(String(a.competencia || "")))[0] || {};
  const curatedCount = integer(currentAcquiring.fundos_adquirencia_curados);
  const cardSummary = payload.card_taxonomy_summary || {};
  const sheet = resetSheet(workbook, "Adquirência reclass.");
  setHeaderBand(
    sheet,
    "Taxonomia CVM com abertura analítica de adquirência",
    `${curatedCount} CNPJs compõem a abertura de Adquirência. No bucket Cartão, ${integer(cardSummary.fundos_incluidos_adquirencia)} foram incluídos, ${integer(cardSummary.fundos_fora_adquirencia)} ficaram fora e ${integer(cardSummary.fundos_pendentes_curadoria)} permanecem pendentes. A classificação CVM reportada continua na base detalhada.`,
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 180, 125, 95, 140, 75, 520], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`C5:C${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`E5:E${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:G${rows.length + 4}`).format.rowHeightPx = 42;
}

async function addCardReceivablesCurationSheet(workbook, payload) {
  const columns = [
    ["#", "ordem_materialidade"],
    ["CNPJ", "cnpj_fundo_formatado"],
    ["Fundo", "denominacao"],
    ["PL de referência", "pl_referencia_brl"],
    ["Competência do PL", "pl_referencia_competencia"],
    ["Fallback usado", "pl_fallback_usado"],
    ["Decisão", "status_curadoria"],
    ["Cedente / originador", "cedente_originador"],
    ["Devedor / sacado", "devedor_sacado"],
    ["Instrumento", "instrumento"],
    ["Natureza econômica", "natureza_economica"],
    ["Critério", "criterio_decisao"],
    ["Evidência", "evidencia_curta"],
    ["Documento", "fonte_documento"],
    ["Data da fonte", "fonte_data"],
    ["URL", "fonte_url"],
    ["Confiança", "confianca"],
    ["Indício PF/PJ/CCB", "flag_pf_pj_ccb"],
    ["Categoria Tabela II", "categoria_tabela_ii"],
    ["Tipo ANBIMA", "anbima_tipo"],
    ["Foco ANBIMA", "anbima_foco"],
    ["Consistência", "consistencia_decisao_reclassificacao"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.card_taxonomy_audit || [], columns);
  const summary = payload.card_taxonomy_summary || {};
  const sheet = resetSheet(workbook, "Curadoria Cartão");
  setHeaderBand(
    sheet,
    "Curadoria do bucket Cartão de crédito",
    `${integer(summary.fundos_incluidos_adquirencia)} fundos foram associados à cadeia de pagamentos; ${integer(summary.fundos_fora_adquirencia)} ficaram fora por crédito PF/PJ, CCB ou natureza distinta; ${integer(summary.fundos_pendentes_curadoria)} permanecem pendentes. PL em ${competenceShortPt(summary.competencia_pl_atual || payload.latest_complete).toLowerCase()}, com fallback ao mês anterior somente quando ausente.`,
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [45, 120, 285, 125, 110, 85, 135, 220, 230, 170, 330, 300, 350, 230, 95, 300, 90, 105, 130, 145, 160, 105],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:V${rows.length + 4}`).format.rowHeightPx = 58;
}

async function addClosedOffersSheet(workbook, payload) {
  const rows = [];
  (payload.closed_offers_annual || []).forEach((row) => rows.push({ "Painel": "Ano / YTD", ...row }));
  (payload.closed_offers_jan_june || payload.closed_offers_jan_may || [])
    .forEach((row) => rows.push({ "Painel": "Jan–jun", ...row }));
  (payload.closed_offers_monthly || []).forEach((row) => rows.push({ "Painel": "Mensal", ...row }));
  const headers = [
    "Painel", "year", "month", "competence", "period_label", "period_start", "period_end",
    "closed_offers", "registered_volume_brl", "mean_registered_ticket_brl", "median_registered_ticket_brl",
    "placed_volume_proxy_brl", "placed_quantity_registered_volume_coverage", "professional_target_registered_volume_share",
    "qualified_target_registered_volume_share", "general_target_registered_volume_share", "natural_person_placed_volume_share",
  ];
  const sheet = resetSheet(workbook, "Ofertas encerradas");
  setHeaderBand(
    sheet,
    "Ofertas encerradas de cotas de FIDC",
    "CVM, Ofertas Públicas. Unidade = Número do Requerimento; coorte pela Data de Encerramento; oferta primária; status Oferta Encerrada; valor registrado positivo.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 65, 60, 85, 100, 100, 100, 95, 130, 125, 125, 130, 120, 120, 115, 110, 115], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["I", "L"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["J", "K"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,, "mi"';
  });
  sheet.getRange(`M5:Q${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:Q${rows.length + 4}`).format.rowHeightPx = 34;
}

async function addFixedIncomeOfferComparisonSheet(workbook, payload) {
  const columns = [
    ["Visão", "view"],
    ["Ordem série", "series_order"],
    ["Série", "series_label"],
    ["Instrumento oficial", "instrument_official"],
    ["Rank 2025", "selected_2025_rank"],
    ["Ordem período", "period_order"],
    ["Período", "period_label"],
    ["Início", "period_start"],
    ["Fim", "period_end"],
    ["Ano completo", "is_full_year"],
    ["Ofertas encerradas", "closed_offers"],
    ["Volume registrado", "registered_volume_brl"],
    ["Share na visão", "share_of_period_view_volume"],
    ["Período comparável", "previous_period_label"],
    ["Volume comparável", "previous_registered_volume_brl"],
    ["Crescimento YoY", "yoy_growth"],
    ["YoY comparável", "yoy_comparable"],
    ["Volume universo", "universe_registered_volume_brl"],
    ["Fonte", "source_url"],
    ["Escopo", "scope"],
    ["Instrumentos excluídos", "excluded_instruments"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(
    payload.fixed_income_offer_comparison || [],
    columns,
  );
  const sheet = resetSheet(workbook, "Comparativo renda fixa");
  setHeaderBand(
    sheet,
    "FIDCs versus demais emissões de renda fixa",
    "CVM, oferta_resolucao_160.csv. Oferta primária, status Oferta Encerrada, Data de Encerramento no período, valor registrado positivo e unidade por Número do Requerimento. 2026 compara jan–jun com o mesmo período de 2025.",
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [230, 75, 130, 260, 80, 80, 105, 100, 100, 85, 100, 130, 100, 120, 130, 105, 90, 130, 260, 430, 650],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  ["L", "O", "R"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat =
      'R$ #,##0.0,,, "bi"';
  });
  ["M", "P"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat =
      "0.0%";
  });
  sheet.getRange(`A5:U${rows.length + 4}`).format.rowHeightPx = 42;
}

async function addOfferTicketDistributionSheet(workbook, payload) {
  const columns = [
    ["Ordem período", "period_order"],
    ["Período", "period_label"],
    ["Início", "period_start"],
    ["Fim", "period_end"],
    ["Ano completo", "is_full_year"],
    ["Ordem faixa", "bucket_order"],
    ["Faixa de ticket", "ticket_bucket"],
    ["Piso", "ticket_floor_brl"],
    ["Teto", "ticket_ceiling_brl"],
    ["Ofertas encerradas", "closed_offers"],
    ["Share das ofertas", "offer_share"],
    ["Volume registrado", "registered_volume_brl"],
    ["Share do volume", "registered_volume_share"],
    ["Ofertas no período", "period_closed_offers"],
    ["Volume do período", "period_registered_volume_brl"],
    ["Ticket médio", "period_mean_ticket_brl"],
    ["Ticket mediano", "period_median_ticket_brl"],
    ["P25", "period_p25_ticket_brl"],
    ["P75", "period_p75_ticket_brl"],
    ["P90", "period_p90_ticket_brl"],
    ["Escopo", "scope"],
    ["Metodologia", "methodology"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.closed_offer_ticket_distribution || [], columns);
  const sheet = resetSheet(workbook, "Histograma ofertas");
  setHeaderBand(
    sheet,
    "Distribuição do valor registrado das ofertas encerradas",
    "2024 e 2025 usam o ano completo; 2026 usa jan–jun. Uma oferta corresponde ao Número do Requerimento. Ticket = Valor Total Registrado.",
    headers,
    rows.length,
    { freezeColumns: 7, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [70, 95, 95, 95, 80, 70, 130, 105, 105, 90, 95, 120, 95, 95, 125, 115, 115, 105, 105, 105, 420, 520], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["H", "I", "L", "O", "P", "Q", "R", "S", "T"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,, "mi"';
  });
  sheet.getRange(`K5:K${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`M5:M${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:V${rows.length + 4}`).format.rowHeightPx = 45;
}

async function addConclusionsSheet(workbook, payload) {
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  const conclusions = executiveConclusions(payload);
  const notes = executiveConclusionNotes(
    payload,
    `Fontes: CVM, ANBIMA, BCB e FIDCs.xlsx. PL em ${stockShortLower}; ofertas encerradas até 30/jun/26.`,
  );
  const rows = conclusions.map((item) => [
    item.order,
    item.title,
    `• ${item.bullets[0]}`,
    `• ${item.bullets[1]}`,
  ]);
  const headers = ["#", "Conclusão", "Leitura principal", "Evidência e magnitude"];
  const sheet = resetSheet(workbook, "Principais conclusões");
  setHeaderBand(
    sheet,
    "Principais conclusões",
    `Leitura executiva reconciliada ao fechamento de ${stockShortLower}; ofertas em jan–jun/26.`,
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  sheet.getRangeByIndexes(4, 0, rows.length, headers.length).values = rows;
  applyColumnWidths(sheet, [55, 300, 435, 435], rows.length);
  sheet.getRange(`A5:D${rows.length + 4}`).format.rowHeightPx = 66;
  sheet.getRange(`A5:A${rows.length + 4}`).format.horizontalAlignment = "right";
  const notesRow = rows.length + 6;
  sheet.getRange(`A${notesRow}:D${notesRow}`).merge();
  sheet.getRange(`A${notesRow}`).values = [[`Notas metodológicas: ${notes}`]];
  sheet.getRange(`A${notesRow}:D${notesRow}`).format.font = { name: "Arial", size: 9, color: C.mid };
  sheet.getRange(`A${notesRow}:D${notesRow}`).format.wrapText = true;
  sheet.getRange(`A${notesRow}:D${notesRow}`).format.rowHeightPx = 48;
  sheet.getRange(`A${notesRow}:D${notesRow}`).format.verticalAlignment = "center";
}

async function addOriginators2026Sheet(workbook, payload) {
  const columns = [
    ["Posição", "rank"],
    ["Originador", "originator_group"],
    ["Ofertas encerradas", "closed_offers"],
    ["Emissores", "issuer_cnpjs"],
    ["Volume registrado", "registered_volume_brl"],
    ["Ticket médio registrado", "mean_registered_ticket_brl"],
    ["Ticket mediano registrado", "median_registered_ticket_brl"],
    ["Volume colocado estimado", "placed_volume_proxy_brl"],
    ["Share do universo", "share_of_total_registered_volume"],
    ["Share do identificado", "share_of_identified_registered_volume"],
    ["Campo-fonte", "originator_source_fields"],
    ["Evidência", "originator_evidence_sample"],
    ["Confiança", "confidence"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.closed_offer_originators_2026 || [], columns);
  const sheet = resetSheet(workbook, "Originadores 2026");
  setHeaderBand(
    sheet,
    "Originadores nomináveis nas ofertas encerradas de 2026",
    "Primeiro match nominal auditável em emissor, ativos-alvo, descrição do lastro ou identificação de devedores/coobrigados. O residual não identificado permanece fora do ranking e dentro do denominador.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [75, 160, 95, 75, 125, 125, 125, 125, 100, 100, 100, 310, 180], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["E", "H"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["F", "G"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,, "mi"';
  });
  sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = "#,##0";
  sheet.getRange(`I5:J${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:M${rows.length + 4}`).format.rowHeightPx = 50;
}

async function addClosedOfferTop15Sheet(workbook, payload) {
  const columns = [
    ["Período", "period_label"],
    ["Posição", "rank"],
    ["Número do Requerimento", "offer_id"],
    ["Data de encerramento", "data_encerramento"],
    ["CNPJ emissor", "cnpj_emissor"],
    ["FIDC", "nome_emissor"],
    ["Nome curto", "fund_name_short"],
    ["Originador", "originator_group"],
    ["Volume registrado", "registered_volume_brl"],
    ["Coordenador líder", "leader_name"],
    ["IBBA Coord-Líder?", "ibba_coord_lead_label"],
    ["Regime de distribuição", "distribution_regime"],
    ["Garantia Firme?", "firm_commitment_label"],
    ["Público", "publico"],
    ["Nº de Inv.", "investor_count"],
    ["Campo-fonte do originador", "originator_source"],
    ["Evidência do originador", "originator_evidence"],
    ["Status", "status"],
    ["Tipo de oferta", "offer_type"],
    ["Valor mobiliário", "security"],
    ["Fonte", "source_url"],
    ["Escopo", "scope"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.closed_offer_top15 || [], columns);
  const summaries = Object.fromEntries(
    (payload.closed_offer_top15_summary || []).map((row) => [row.period_label, row]),
  );
  const summary2025 = summaries["2025 FY"] || {};
  const summary2026 = summaries["2026 jan-jun"] || {};
  const sheet = resetSheet(workbook, "Top 15 ofertas");
  setHeaderBand(
    sheet,
    "Top 15 ofertas encerradas por período",
    `2025FY: ${bn(summary2025.top15_registered_volume_brl, 2)} (${pct(summary2025.top15_share_of_period_volume, 1)} do período). Jan–jun/26: ${bn(summary2026.top15_registered_volume_brl, 2)} (${pct(summary2026.top15_share_of_period_volume, 1)} do período).`,
    headers,
    rows.length,
    { freezeColumns: 8, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [100, 65, 115, 105, 120, 360, 170, 170, 125, 290, 105, 170, 95, 100, 85, 125, 320, 115, 90, 100, 320, 420],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`I5:I${rows.length + 4}`).format.numberFormat = 'R$ #,##0.00,,, "bi"';
  sheet.getRange(`O5:O${rows.length + 4}`).format.numberFormat = "#,##0";
  sheet.getRange(`A5:V${rows.length + 4}`).format.rowHeightPx = 48;

  const summaryRow = rows.length + 7;
  const summaryHeaders = [
    "Período",
    "Ofertas no período",
    "Volume do período",
    "Subtotal Top 15",
    "% do total",
    "IBBA líder · ofertas",
    "IBBA líder · volume",
    "Garantia firme · ofertas",
    "Garantia firme · volume",
  ];
  sheet.getRange(`A${summaryRow}:I${summaryRow}`).values = [summaryHeaders];
  sheet.getRange(`A${summaryRow}:I${summaryRow}`).format.fill = C.black;
  sheet.getRange(`A${summaryRow}:I${summaryRow}`).format.font = {
    name: "Arial",
    size: 8,
    bold: true,
    color: C.white,
  };
  const summaryRows = [summary2025, summary2026].map((row) => [
    row.period_label,
    row.period_closed_offers,
    row.period_registered_volume_brl,
    row.top15_registered_volume_brl,
    row.top15_share_of_period_volume,
    row.ibba_lead_offers_top15,
    row.ibba_lead_volume_top15_brl,
    row.firm_commitment_offers_top15,
    row.firm_commitment_volume_top15_brl,
  ]);
  sheet.getRange(`A${summaryRow + 1}:I${summaryRow + 2}`).values = summaryRows;
  sheet.getRange(`A${summaryRow + 1}:I${summaryRow + 2}`).format.font = {
    name: "Arial",
    size: 8,
    color: C.charcoal,
  };
  ["C", "D", "G", "I"].forEach((letter) => {
    sheet.getRange(`${letter}${summaryRow + 1}:${letter}${summaryRow + 2}`).format.numberFormat =
      'R$ #,##0.00,,, "bi"';
  });
  sheet.getRange(`E${summaryRow + 1}:E${summaryRow + 2}`).format.numberFormat = "0.00%";
}

async function addProviderAttributionSheet(workbook, payload) {
  const leadership = payload.provider_leadership_attribution || {};
  const btg = leadership.btg || {};
  const qi = leadership.qi || {};
  const bankCohort = btgBankCohortContext(payload);
  const qiSource = [qi.methodology, qi.source_acquisition_url, qi.source_reorganization_url]
    .filter(Boolean)
    .join(" · ");
  const headers = [
    "Seção",
    "Participante",
    "Competência",
    "CNPJ",
    "Fundo / entidade",
    "Métrica",
    "Valor / PL",
    "Share",
    "Fundos",
    "Fonte / metodologia",
  ];
  const rows = [
    { "Seção": "Resumo", "Participante": "QI Tech", "Competência": "2024-12", "Métrica": "PL administrado do grupo", "Valor / PL": qi.admin_group_pl_2024_brl, "Fonte / metodologia": qiSource },
    { "Seção": "Resumo", "Participante": "QI Tech", "Competência": "2024-12", "Métrica": "CNPJ legado Singulare", "Valor / PL": qi.legacy_singulare_pl_2024_brl, "Share": qi.legacy_share_2024, "Fonte / metodologia": qiSource },
    { "Seção": "Resumo", "Participante": "QI Tech", "Competência": "2024-12", "Métrica": "QI DTVM original", "Valor / PL": qi.original_qi_pl_2024_brl, "Fonte / metodologia": qiSource },
    { "Seção": "Resumo", "Participante": "BTG Pactual", "Competência": payload.latest_complete, "Métrica": "PL gerido", "Valor / PL": bankCohort.managedPl, "Fonte / metodologia": "Ranking CVM; PL ex-FIC, sem Sistema Petrobras/TAPSO" },
    { "Seção": "Resumo", "Participante": "BTG Pactual", "Competência": payload.latest_complete, "Métrica": "Coorte bancária listada", "Valor / PL": bankCohort.cohortPl, "Fundos": bankCohort.observedFunds, "Fonte / metodologia": `${integer(bankCohort.listedRoots)} raízes em FIDCs.xlsx, aba BTG; PL bruto observado no Informe Mensal` },
    { "Seção": "Resumo", "Participante": "BTG Pactual", "Competência": payload.latest_complete, "Métrica": "Coorte com BTG como gestor", "Valor / PL": bankCohort.managementExcludedPl, "Share": bankCohort.managedPl ? bankCohort.managementExcludedPl / bankCohort.managedPl : 0, "Fundos": bankCohort.managementExcludedFunds, "Fonte / metodologia": `Cenário de ranking #${integer(bankCohort.currentManagementRank)} → #${integer(bankCohort.residualManagementRank)}; o recorte não atribui controle societário` },
    { "Seção": "Benchmark", "Participante": "Bradesco", "Competência": btg.competencia || payload.latest_complete, "Métrica": "PL gerido", "Valor / PL": btg.bradesco_managed_pl_brl, "Fonte / metodologia": "Mesmo universo do ranking histórico" },
  ];
  (payload.bank_fidc_detail || [])
    .filter((row) => {
      const group = row.bank_group || row.grupo_bancario;
      return row.competencia === payload.latest_complete
        && ["BTG", "BTG Pactual"].includes(String(group || ""));
    })
    .forEach((row) => {
      rows.push({
        "Seção": "BTG · coorte bancária",
        "Participante": "BTG Pactual",
        "Competência": row.competencia,
        "CNPJ": row.cnpj_fundo,
        "Fundo / entidade": row.denominacao || row.nome_curto,
        "Métrica": row.observado ? "PL bruto observado" : "Sem PL observado",
        "Valor / PL": row.pl_brl,
        "Fundos": row.observado ? 1 : 0,
        "Fonte / metodologia": row.source_reference || "FIDCs.xlsx, aba BTG; CVM, Informe Mensal",
      });
    });
  (payload.qi_legacy_attribution || []).forEach((row) => {
    rows.push({
      "Seção": "QI · entidades legais",
      "Participante": "QI Tech",
      "Competência": row.competencia,
      "CNPJ": row.provider_cnpj_formatado || row.provider_cnpj,
      "Fundo / entidade": row.provider_legal_label,
      "Métrica": row.attribution,
      "Valor / PL": row.pl_brl,
      "Share": row.share_admin_group,
      "Fundos": row.fundos,
      "Fonte / metodologia": row.methodology,
    });
  });
  (payload.btg_provider_ex_controlled_scenario || []).forEach((row) => {
    rows.push({
      "Seção": "BTG · cenário sem coorte bancária",
      "Participante": "BTG Pactual",
      "Competência": row.competencia,
      "Métrica": `${roleLabel(row.papel)} · rank ${integer(row.btg_rank)} → ${integer(row.btg_rank_ex_controlados)}`,
      "Valor / PL": row.btg_pl_ex_controlados_brl,
      "Share": row.share_pl_btg_excluido,
      "Fundos": firstFiniteNumber(row.fidcs_coorte_bancaria_excluidos, row.fidcs_controlados_excluidos),
      "Fonte / metodologia": `Cenário retira os FIDCs da coorte com BTG no papel analisado; FIDCs.xlsx, aba BTG; CVM, Informe Mensal`,
    });
  });
  const sheet = resetSheet(workbook, "Atribuição prestadores");
  setHeaderBand(
    sheet,
    "Atribuição das lideranças de prestadores",
    `QI/Singulare separados por CNPJ legal em dez/24. A coorte BTG vem de FIDCs.xlsx; PL CVM de ${competenceShortPt(payload.latest_complete).toLowerCase()}. A lista define o recorte analítico e não atribui controle societário.`,
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [150, 130, 90, 135, 340, 250, 120, 85, 75, 520], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`A5:J${rows.length + 4}`).format.rowHeightPx = 44;
}

async function addProviderTransitionSheet(workbook, payload) {
  const headers = [
    "Nível",
    "Função",
    "Competência origem",
    "Competência destino",
    "CNPJ fundo",
    "Fundo",
    "Grupo origem",
    "Grupo destino",
    "Prestador origem",
    "Prestador destino",
    "CNPJ prestador origem",
    "CNPJ prestador destino",
    "Fundos",
    "PL origem",
    "PL destino",
    "PL comparável",
    "Share PL comparável",
    "Mudou grupo",
    "Mudou entidade legal",
    "Fonte / limitação",
  ];
  const rows = [];
  (payload.provider_transition_role_availability || payload.provider_transition_summary?.role_availability || []).forEach((row) => {
    rows.push({
      "Nível": "Disponibilidade",
      "Função": row.papel,
      "Fonte / limitação": `${row.transition_status}: ${row.fonte_prestador || ""}${row.limitation ? ` · ${row.limitation}` : ""}`,
    });
  });
  (payload.provider_transition_links || []).forEach((row) => {
    rows.push({
      "Nível": "Link",
      "Função": row.papel,
      "Competência origem": row.competencia_origem,
      "Competência destino": row.competencia_destino,
      "Grupo origem": row.grupo_origem,
      "Grupo destino": row.grupo_destino,
      "Fundos": row.fundos,
      "PL origem": row.pl_origem_brl,
      "PL destino": row.pl_destino_brl,
      "PL comparável": row.pl_comparavel_brl,
      "Share PL comparável": row.share_pl_comparavel,
      "Mudou grupo": true,
      "Fonte / limitação": "Administrador observado no Informe Mensal",
    });
  });
  (payload.provider_transition_detail || []).forEach((row) => {
    rows.push({
      "Nível": "CNPJ fundo",
      "Função": row.papel,
      "Competência origem": row.competencia_origem,
      "Competência destino": row.competencia_destino,
      "CNPJ fundo": row.cnpj_fundo_formatado || row.cnpj_fundo,
      "Fundo": row.denominacao,
      "Grupo origem": row.grupo_origem,
      "Grupo destino": row.grupo_destino,
      "Prestador origem": row.admin_origem_nome,
      "Prestador destino": row.admin_destino_nome,
      "CNPJ prestador origem": row.admin_origem_cnpj,
      "CNPJ prestador destino": row.admin_destino_cnpj,
      "PL origem": row.pl_origem_brl,
      "PL destino": row.pl_destino_brl,
      "PL comparável": row.pl_comparavel_brl,
      "Mudou grupo": row.mudou_grupo,
      "Mudou entidade legal": row.mudou_entidade_legal,
      "Fonte / limitação": row.fonte_destino_url || row.fonte_origem_url,
    });
  });
  (payload.provider_history_cvm_coverage || []).forEach((row) => {
    rows.push({
      "Nível": "Cobertura histórica ICVM 555",
      "Função": row.papel,
      "Competência origem": String(row.data_referencia || "").split("→")[0]?.trim(),
      "Competência destino": String(row.data_referencia || "").split("→")[1]?.trim(),
      "Fundos": row.fundos_resolvidos_unicos,
      "PL destino": row.pl_resolvido_unico_brl,
      "Share PL comparável": row.cobertura_pl_resolvida,
      "Fonte / limitação": `${row.escopo_fonte || ""} · ${row.fonte_url || ""}`,
    });
  });
  (payload.provider_history_cvm_links || []).filter((row) => row.mudou_grupo).forEach((row) => {
    rows.push({
      "Nível": "Link histórico ICVM 555",
      "Função": row.papel,
      "Competência origem": row.data_origem,
      "Competência destino": row.data_destino,
      "Grupo origem": row.origem_prestador_grupo,
      "Grupo destino": row.destino_prestador_grupo,
      "Fundos": row.fundos,
      "PL comparável": row.pl_mai26_brl,
      "Share PL comparável": row.share_pl_comparavel,
      "Mudou grupo": true,
      "Fonte / limitação": `${row.escopo_fonte || ""} · ${row.fonte_url || ""}`,
    });
  });
  (payload.provider_history_cvm_detail || []).filter((row) => row.comparavel && row.mudou_grupo).forEach((row) => {
    rows.push({
      "Nível": "CNPJ histórico ICVM 555",
      "Função": row.papel,
      "Competência origem": row.data_origem,
      "Competência destino": row.data_destino,
      "CNPJ fundo": row.cnpj_fundo_formatado || row.cnpj_fundo,
      "Fundo": row.denominacao,
      "Grupo origem": row.origem_prestador_grupo,
      "Grupo destino": row.destino_prestador_grupo,
      "Prestador origem": row.origem_prestador_nome,
      "Prestador destino": row.destino_prestador_nome,
      "CNPJ prestador origem": row.origem_prestador_id_legal,
      "CNPJ prestador destino": row.destino_prestador_id_legal,
      "PL comparável": row.pl_mai26_brl,
      "Mudou grupo": row.mudou_grupo,
      "Mudou entidade legal": row.mudou_entidade_legal,
      "Fonte / limitação": `${row.escopo_fonte || ""} · ${row.fonte_url || ""}`,
    });
  });
  const sheet = resetSheet(workbook, "Fluxos prestadores");
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  setHeaderBand(
    sheet,
    `Fluxos de prestadores · dez/24 → ${stockShortLower}`,
    `Administração: coorte atual, administrador observado nas duas datas e largura = PL ${stockShortLower}. Gestão e custódia: amostra histórica ICVM 555 encerrada em mai/26, com cobertura explícita e sem extrapolação. Sistema Petrobras/TAPSO excluídos.`,
    headers,
    rows.length,
    { freezeColumns: 6, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows, 2500);
  applyColumnWidths(sheet, [110, 90, 95, 95, 125, 330, 160, 160, 260, 260, 125, 125, 70, 115, 115, 115, 105, 90, 115, 420], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`A5:T${rows.length + 4}`).format.rowHeightPx = 32;
}

async function addReagMigrationSheet(workbook, payload) {
  const summary = payload.reag_admin_summary || {};
  const destinationCompetence = summary.competencia_destino || payload.latest_complete;
  const destinationShortLower = competenceShortPt(destinationCompetence).toLowerCase();
  const currentPlHeader = `PL ${destinationShortLower}`;
  const currentManagerHeader = `Gestor vigente ${destinationShortLower}`;
  const currentCustodianHeader = `Custodiante vigente ${destinationShortLower}`;
  const headers = [
    "Nível",
    "Competência origem",
    "Competência destino",
    "CNPJ fundo",
    "Fundo",
    "Status destino",
    "Administrador destino",
    "Grupo destino",
    "CNPJ administrador destino",
    "Fundos",
    "PL dez/25",
    currentPlHeader,
    "PL comparável",
    "Mudou administrador",
    currentManagerHeader,
    currentCustodianHeader,
    "Fonte / limitação",
  ];
  const rows = [];
  rows.push({
    "Nível": "Resumo",
    "Competência origem": summary.competencia_origem,
    "Competência destino": summary.competencia_destino,
    "Fundos": summary.funds_origin,
    "PL dez/25": summary.pl_origin_brl,
    [currentPlHeader]: summary.continuing_pl_current_brl,
    "Fonte / limitação": [summary.source, summary.liquidation_source_url, summary.manager_custodian_history_limitation].filter(Boolean).join(" · "),
  });
  (payload.reag_admin_links || []).forEach((row) => {
    rows.push({
      "Nível": "Link",
      "Competência origem": summary.competencia_origem,
      "Competência destino": summary.competencia_destino,
      "Status destino": row.destino_grupo,
      "Grupo destino": row.destino_grupo,
      "CNPJ administrador destino": row.admin_destino_cnpj,
      "Fundos": row.fundos,
      "PL dez/25": row.pl_2025_12_brl,
      [currentPlHeader]: row.pl_current_brl ?? row.pl_2026_05_brl,
      "PL comparável": row.pl_comparavel_brl,
      "Fonte / limitação": "Administrador observado no Informe Mensal",
    });
  });
  (payload.reag_admin_detail || []).forEach((row) => {
    rows.push({
      "Nível": "CNPJ fundo",
      "Competência origem": row.competencia_origem,
      "Competência destino": row.competencia_destino,
      "CNPJ fundo": row.cnpj_fundo_formatado || row.cnpj_fundo,
      "Fundo": row.denominacao,
      "Status destino": row.status_destino,
      "Administrador destino": row.admin_destino_nome_observado,
      "Grupo destino": row.admin_destino_grupo,
      "CNPJ administrador destino": row.admin_destino_cnpj,
      "PL dez/25": row.pl_origem_brl,
      [currentPlHeader]: row.pl_destino_brl,
      "PL comparável": row.pl_comparavel_brl,
      "Mudou administrador": row.mudou_administrador,
      [currentManagerHeader]: row.gestor_destino_nome_observado,
      [currentCustodianHeader]: row.custodiante_destino_nome_observado,
      "Fonte / limitação": row.fonte_destino_url || row.fonte_origem_url,
    });
  });
  const sheet = resetSheet(workbook, "Migração CBSF");
  setHeaderBand(
    sheet,
    "CBSF / Reag Trust · destino do cohort",
    `Cohort do administrador CNPJ 34.829.992/0001-86 em dez/25 acompanhado até ${destinationShortLower}. Administração é observada; gestor e custodiante são somente a fotografia vigente, sem inferência de migração.`,
    headers,
    rows.length,
    { freezeColumns: 5, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [105, 95, 95, 125, 330, 150, 260, 150, 130, 70, 115, 115, 115, 110, 260, 260, 430], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`A5:Q${rows.length + 4}`).format.rowHeightPx = 38;
}

async function addProviderFlowVisualSheet(workbook, flowAssets) {
  const sheet = resetSheet(workbook, "Fluxos visuais");
  const lastColumn = "M";
  sheet.getRange(`A1:${lastColumn}136`).format = {
    font: { name: "Arial", size: 10, color: C.charcoal },
    rowHeightPx: 20,
  };
  for (let index = 0; index < 13; index += 1) {
    const letter = columnLetter(index);
    sheet.getRange(`${letter}1:${letter}136`).format.columnWidthPx = 100;
  }
  sheet.getRange(`A1:${lastColumn}1`).merge();
  sheet.getRange("A1").values = [["Fluxos de prestadores"]];
  sheet.getRange(`A1:${lastColumn}1`).format = {
    fill: C.black,
    font: { name: "Arial", size: 16, bold: true, color: C.white },
    rowHeightPx: 34,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${lastColumn}2`).merge();
  sheet.getRange("A2").values = [[
    "Imagens em alta resolução da mesma base do explorador HTML: administração ampla, amostras históricas de gestão e custódia, e coorte CBSF / REAG.",
  ]];
  sheet.getRange(`A2:${lastColumn}2`).format = {
    fill: C.white,
    font: { name: "Arial", size: 10, color: C.mid },
    rowHeightPx: 32,
    verticalAlignment: "center",
    wrapText: true,
  };
  sheet.images.add({
    dataUrl: flowAssets.adminPngDataUrl,
    anchor: {
      from: { row: 3, col: 0 },
      extent: { widthPx: 1280, heightPx: 620 },
    },
  });
  sheet.images.add({
    dataUrl: flowAssets.gestorPngDataUrl,
    anchor: {
      from: { row: 36, col: 0 },
      extent: { widthPx: 1280, heightPx: 620 },
    },
  });
  sheet.images.add({
    dataUrl: flowAssets.custodiantePngDataUrl,
    anchor: {
      from: { row: 69, col: 0 },
      extent: { widthPx: 1280, heightPx: 620 },
    },
  });
  sheet.images.add({
    dataUrl: flowAssets.reagPngDataUrl,
    anchor: {
      from: { row: 102, col: 0 },
      extent: { widthPx: 1280, heightPx: 620 },
    },
  });
  sheet.getRange(`A135:${lastColumn}136`).merge();
  sheet.getRange("A135").values = [[
    `Visão navegável e exportável: ${path.basename(flowAssets.html)}. Fontes e critérios permanecem nas abas “Fluxos prestadores” e “Migração CBSF”.`,
  ]];
  sheet.getRange(`A135:${lastColumn}136`).format = {
    fill: C.pale,
    font: { name: "Arial", size: 10, color: C.mid },
    rowHeightPx: 24,
    verticalAlignment: "center",
    wrapText: true,
    borders: {
      top: { style: "thin", color: C.line },
      bottom: { style: "thin", color: C.line },
    },
  };
  sheet.freezePanes.freezeRows(2);
}

async function addAcquiringTaxonomySheet(workbook, payload) {
  const columns = [
    ["#", "ordem_materialidade"],
    ["CNPJ", "cnpj_fundo_formatado"],
    ["Fundo", "denominacao"],
    ["PL de referência", "pl_referencia_brl"],
    ["Competência do PL", "pl_referencia_competencia"],
    ["Cedente / originador", "cedente_originador"],
    ["Devedor / sacado", "devedor_sacado"],
    ["Instrumento", "instrumento"],
    ["Natureza econômica", "natureza_economica"],
    ["Categoria Tabela II", "categoria_tabela_ii"],
    ["Valor em Cartão", "valor_cartao_tabela_ii_brl"],
    ["Tipo ANBIMA", "anbima_tipo"],
    ["Foco ANBIMA", "anbima_foco"],
    ["Regulamento primário", "fonte_url"],
  ];
  const headers = columns.map(([header]) => header);
  const sourceRows = payload.acquiring_curation_detail || [];
  const rows = worksheetRowsFromPayload(sourceRows, columns);
  const sheet = resetSheet(workbook, "Taxonomia adquirência");
  setHeaderBand(
    sheet,
    "Taxonomia adquirência",
    `${integer(sourceRows.length)} CNPJs compõem a abertura analítica de Adquirência. PL em ${competenceShortPt(payload.latest_complete).toLowerCase()}; a categoria reportada na Tabela II permanece preservada.`,
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [45, 120, 285, 125, 105, 210, 220, 170, 330, 130, 125, 145, 160, 300], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`K5:K${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:N${rows.length + 4}`).format.rowHeightPx = 58;
}

async function addAtlanticoSheet(workbook, payload) {
  const profile = payload.atlantico_profile;
  const atlanticoShortLower = competenceShortPt(
    profile.snapshot?.competencia || payload.latest_complete,
  ).toLowerCase();
  const factHeaders = ["Seção", "Campo", "Evidência / leitura", "Status / limitação"];
  const facts = [
    ["Identificação", "CNPJ / denominação", `${profile.cnpj} · ${profile.denominacao}`, `CVM; ${atlanticoShortLower}`],
    ["Estrutura", "Estratégia", profile.estrategia, "Política vigente; não inferida pelo nome"],
    ["Estrutura", "Classificação", profile.classificacao, `is_np do pipeline = ${String(profile.is_np_pipeline)}`],
    ["Carteira", "Cedentes / originadores", profile.cedente_originador, "Top 2 cobrem 30%; demais não nominados"],
    ["Carteira", "Sacados / devedores", profile.perfil_sacados, "Lista individual não pública"],
    ["Carteira", "Natureza dos recebíveis", profile.natureza_recebiveis, `Mix de ${atlanticoShortLower} no informe mensal`],
    ["Economia", "Funcionamento", profile.funcionamento_economico, "Valor contábil ≠ valor de face"],
    ["Governança", "Prestadores", profile.prestadores, "Sefer administrou até 19/07/24"],
    ["Governança", "Público-alvo", profile.publico_alvo, "Conta de cotista ≠ identidade do investidor"],
    ["Capital", "Subordinação", profile.subordinacao, "Requer confirmação do administrador"],
    ["Risco", "Garantias", profile.garantias, "Sem coobrigação de pagamento do cedente"],
    ["Inadimplência", "Leitura", profile.leitura_inadimplencia, "Estratégia NPL; separar de deterioração"],
    ["Quebra de série", "Jun/24 → jul/24", profile.bridge_interpretacao, "Não like-for-like"],
    ["Auditoria", "Valoração e opinião", profile.auditoria_valor_justo, "Bandeira de qualidade pré-20/07/24"],
    ["Limitações", "Pontos não observáveis", profile.limitacoes.join(" | "), "Não preencher por inferência"],
  ];
  const sheet = resetSheet(workbook, "Curadoria Atlântico");
  setHeaderBand(
    sheet,
    "Curadoria Atlântico",
    "Caso estrutural de NPL e quebra de reporte. Fontes, fatos observados, interpretação e lacunas permanecem separados.",
    factHeaders,
    facts.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  sheet.getRange(`A5:D${facts.length + 4}`).values = facts;
  applyColumnWidths(sheet, [220, 150, 680, 300], facts.length);
  sheet.getRange(`A5:D${facts.length + 4}`).format.rowHeightPx = 88;

  const sourceHeaderRow = facts.length + 7;
  const sourceHeaders = ["Fonte", "Tipo", "URL", "Data consulta"];
  sheet.getRange(`A${sourceHeaderRow}:D${sourceHeaderRow}`).values = [sourceHeaders];
  sheet.getRange(`A${sourceHeaderRow}:D${sourceHeaderRow}`).format.fill = C.black;
  sheet.getRange(`A${sourceHeaderRow}:D${sourceHeaderRow}`).format.font = { name: "Arial", size: 9, bold: true, color: C.white };
  const sourceRows = profile.fontes.map((row) => [row.label, row.tipo, row.url, row.data_consulta]);
  sheet.getRangeByIndexes(sourceHeaderRow, 0, sourceRows.length, sourceHeaders.length).values = sourceRows;
  const sourceFirst = sourceHeaderRow + 1;
  const sourceLast = sourceHeaderRow + sourceRows.length;
  sheet.getRange(`A${sourceFirst}:D${sourceLast}`).format.font = { name: "Arial", size: 9, color: C.charcoal };
  sheet.getRange(`A${sourceFirst}:D${sourceLast}`).format.wrapText = true;
  sheet.getRange(`A${sourceFirst}:D${sourceLast}`).format.rowHeightPx = 42;
}

async function addAtlanticoHistorySheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Administrador", "administrador"],
    ["PL", "pl"],
    ["Carteira DC", "carteira"],
    ["Inadimplência bruta", "inadimplencia_bruta"],
    ["Inadimplência ajustada", "inadimplencia_ajustada"],
    ["> 360d", "vencidos_mais_360d"],
    ["> 1.080d", "vencidos_mais_1080d"],
    ["Excesso", "excesso"],
    ["Bruta / carteira", "inadimplencia_share_carteira"],
    ["Ajustada / carteira", "ajustada_share_carteira"],
    ["> 360d / carteira", "mais_360_share_carteira"],
    ["Aging reportado", "aging_reportado"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.atlantico_history, columns);
  const sheet = resetSheet(workbook, "Série Atlântico");
  setHeaderBand(
    sheet,
    "Série Atlântico",
    "Valores observados no painel CVM. Campo de aging ausente permanece vazio; ajuste é o cap analítico, não uma observação econômica do fundo.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 330, 115, 115, 125, 125, 115, 115, 115, 105, 110, 110, 100], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["C", "D", "E", "F", "G", "H", "I"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`J5:L${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:M${rows.length + 4}`).format.rowHeightPx = 42;
}

async function addChecksSheet(workbook, payload) {
  const sheet = resetSheet(workbook, "Checks revisão");
  const headers = ["Teste", "Fórmula / valor", "Esperado", "Status"];
  const focusRows = payload.market_share
    .map((row) => [row.papel, row.tipo_anbima, row.foco_anbima])
    .filter((row, index, array) => array.findIndex((item) => item.join("|") === row.join("|")) === index);
  const tests = [
    ["Top 20 tem exatamente 20 fundos", "=COUNTA('Top 20 FIDCs'!A5:A24)", 20, '=IF(B5=C5,"OK","ERRO")'],
    ["Rank mínimo", "=MIN('Top 20 FIDCs'!A5:A24)", 1, '=IF(B6=C6,"OK","ERRO")'],
    ["Rank máximo", "=MAX('Top 20 FIDCs'!A5:A24)", 20, '=IF(B7=C7,"OK","ERRO")'],
    ["Classificação fecha 100%", payload.classification_coverage.reduce((s, r) => s + num(r.share), 0), 1, '=IF(ABS(B8-C8)<0.0000001,"OK","ERRO")'],
    ["Slides antes do apêndice", 27, 27, '=IF(B9=C9,"OK","ERRO")'],
    ["Perfis Top 20", payload.profiles.length, 20, '=IF(B10=C10,"OK","ERRO")'],
    ["Combinações função×foco", focusRows.length, 42, '=IF(B11=C11,"OK","ERRO")'],
    ["Histograma cotistas dez/23 fecha 100%", payload.holder_distribution_history.filter((r) => r.competencia === "2023-12").reduce((s, r) => s + num(r.share_fundos), 0), 1, '=IF(ABS(B12-C12)<0.0000001,"OK","ERRO")'],
    [`Histograma cotistas ${competenceShortPt(payload.latest_complete).toLowerCase()} fecha 100%`, payload.holder_distribution_history.filter((r) => r.competencia === payload.latest_complete).reduce((s, r) => s + num(r.share_pl), 0), 1, '=IF(ABS(B13-C13)<0.0000001,"OK","ERRO")'],
    ["Tipo ANBIMA dez/23 fecha 100%", payload.type_mix_history.filter((r) => r.competencia === "2023-12").reduce((s, r) => s + num(r.share), 0), 1, '=IF(ABS(B14-C14)<0.0000001,"OK","ERRO")'],
    [`Recebíveis ${competenceShortPt(payload.latest_complete).toLowerCase()} fecham 100%`, payload.receivables_history.filter((r) => r.competencia === payload.latest_complete).reduce((s, r) => s + num(r.share_reported), 0), 1, '=IF(ABS(B15-C15)<0.0000001,"OK","ERRO")'],
    ["Caso Atlântico presente", payload.atlantico_history.length, 5, '=IF(B16=C16,"OK","ERRO")'],
    ["Tipos únicos publicados", (payload.delinquency_single_receivable || []).length, 10, '=IF(B17=C17,"OK","ERRO")'],
    ["Prestadores independentes materializados", (payload.provider_independent_ranking || []).length > 0 ? 1 : 0, 1, '=IF(B18=C18,"OK","ERRO")'],
    ["Coorte bancária: quatro períodos × seis linhas", (payload.bank_fidc_evolution || []).length, 24, '=IF(B19=C19,"OK","ERRO")'],
    ["Ofertas anuais 2023–2026", (payload.closed_offers_annual || []).length, 4, '=IF(B20=C20,"OK","ERRO")'],
    ["Originadores nomináveis 2026", (payload.closed_offer_originators_2026 || []).length, 19, '=IF(B21=C21,"OK","ERRO")'],
    ["Comparativo renda fixa", (payload.fixed_income_offer_comparison || []).length, 28, '=IF(B22=C22,"OK","ERRO")'],
  ];
  setHeaderBand(sheet, "Checks revisão", "Controles executados no gerador. A ausência de markers é testada diretamente no OOXML do PPTX.", headers, tests.length, { freezeColumns: 1 });
  sheet.getRange(`A5:D${tests.length + 4}`).values = tests.map((row) => [row[0], null, row[2], null]);
  tests.forEach((row, index) => {
    const excelRow = 5 + index;
    if (typeof row[1] === "string" && row[1].startsWith("=")) {
      sheet.getRange(`B${excelRow}`).formulas = [[row[1]]];
    } else {
      sheet.getRange(`B${excelRow}`).values = [[row[1]]];
    }
    sheet.getRange(`D${excelRow}`).formulas = [[row[3]]];
  });
  applyColumnWidths(sheet, [300, 170, 120, 100], tests.length);
  sheet.getRange(`B5:C${tests.length + 4}`).format.numberFormat = "0.0000";
}

async function buildWorkbook(payload, flowAssets) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(INPUT_WORKBOOK));
  await addQaSheet(workbook);
  await addVehicleCompetenceSheet(workbook, payload);
  await addFundBaseSheet(workbook, payload);
  await addMonoConcentrationSheet(workbook);
  await addMarketShareSheet(workbook);
  await addTop20Sheets(workbook, payload);
  await addCurationSheet(workbook, payload);
  await addHistoricalComparisonsSheet(workbook, payload);
  await addSingleReceivableDelinquencySheet(workbook, payload);
  await addFrozenDelinquencyHistorySheet(workbook, payload);
  await addProviderHistorySheet(workbook, payload);
  await addIndependentProviderSheet(workbook, payload);
  await addBankFidcSheet(workbook, payload);
  await addBankFidcDetailSheet(workbook, payload);
  await addProviderAttributionSheet(workbook, payload);
  await addProviderFlowVisualSheet(workbook, flowAssets);
  await addProviderTransitionSheet(workbook, payload);
  await addReagMigrationSheet(workbook, payload);
  await addAcquiringTaxonomySheet(workbook, payload);
  await addAcquiringReclassificationSheet(workbook, payload);
  await addCardReceivablesCurationSheet(workbook, payload);
  await addClosedOffersSheet(workbook, payload);
  await addFixedIncomeOfferComparisonSheet(workbook, payload);
  await addOfferTicketDistributionSheet(workbook, payload);
  await addOriginators2026Sheet(workbook, payload);
  await addClosedOfferTop15Sheet(workbook, payload);
  await addConclusionsSheet(workbook, payload);
  await addAtlanticoSheet(workbook, payload);
  await addAtlanticoHistorySheet(workbook, payload);
  await addChecksSheet(workbook, payload);
  return workbook;
}

async function exportPresentation(presentation) {
  if (!SKIP_QA) {
    await fs.mkdir(QA_DIR, { recursive: true });
    const slidesDir = path.join(QA_DIR, "slides_revisados");
    await fs.mkdir(slidesDir, { recursive: true });
    for (const [index, slide] of presentation.slides.items.entries()) {
      const stem = `slide-${String(index + 1).padStart(2, "0")}`;
      await writeBlob(
        path.join(slidesDir, `${stem}.png`),
        await presentation.export({ slide, format: "png", scale: 1 }),
      );
      const layout = await slide.export({ format: "layout" });
      await fs.writeFile(path.join(slidesDir, `${stem}.layout.json`), await layout.text());
    }
    await writeBlob(
      path.join(QA_DIR, "deck_revisado_montage.webp"),
      await presentation.export({ format: "webp", montage: true, scale: 0.5 }),
    );
  }
  await fs.mkdir(path.dirname(OUTPUT_PPTX), { recursive: true });
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(OUTPUT_PPTX);
  const patcherName = "patch_pptx_native_market_charts.py";
  const patcher = [
    process.env.FIDC_NATIVE_CHART_PATCHER,
    path.join(path.dirname(__filename), patcherName),
    path.join(ROOT, "scripts", patcherName),
  ].find((candidate) => candidate && existsSync(candidate));
  if (!patcher) {
    throw new Error(`Patcher dos gráficos nativos não localizado: ${patcherName}`);
  }
  const patched = spawnSync(process.env.FIDC_PYTHON || "python3", [patcher, OUTPUT_PPTX], {
    encoding: "utf8",
  });
  if (patched.status !== 0) {
    throw new Error(`Falha ao ajustar os gráficos nativos de market share: ${patched.stderr || patched.stdout}`);
  }
}

async function exportWorkbook(workbook) {
  if (!SKIP_QA) {
    const previewSheets = [
      ["QA Inadimplência", "A1:AB26"],
      ["Base por fundo-CNPJ", "A1:U20"],
      ["Concentração de monoestruturas", "A1:N24"],
      ["Market share por subtipo", "A1:T26"],
      ["Top 20 FIDCs", "A1:M25"],
      ["Top 20 Outros", "A1:J25"],
      ["Curadoria Top 20", "A1:X16"],
      ["Comparativos históricos", "A1:N28"],
      ["Inadimplência por recebível", "A1:J24"],
      ["Histórico inad. coorte", "A1:P28"],
      ["Ranking independentes", "A1:K76"],
      ["FIDCs por banco", "A1:K28"],
      ["Detalhe coorte bancos", "A1:J28"],
      ["Atribuição prestadores", "A1:J22"],
      ["Fluxos visuais", "A1:M136"],
      ["Fluxos prestadores", "A1:T24"],
      ["Migração CBSF", "A1:Q24"],
      ["Adquirência reclass.", "A1:G28"],
      ["Taxonomia adquirência", "A1:N32"],
      ["Curadoria Cartão", "A1:V48"],
      ["Ofertas encerradas", "A1:Q58"],
      ["Histograma ofertas", "A1:V25"],
      ["Originadores 2026", "A1:M24"],
      ["Principais conclusões", "A1:E30"],
      ["Curadoria Atlântico", "A1:D36"],
      ["Série Atlântico", "A1:M12"],
      ["Checks revisão", "A1:D20"],
    ];
    const workbookQa = path.join(QA_DIR, "workbook_revisado");
    await fs.mkdir(workbookQa, { recursive: true });
    for (const [sheetName, range] of previewSheets) {
      const preview = await workbook.render({
        sheetName,
        range,
        autoCrop: "all",
        scale: 1,
        format: "png",
      });
      await writeBlob(
        path.join(workbookQa, `${sheetName.replace(/[^a-z0-9]+/gi, "_")}.png`),
        preview,
      );
    }
  }
  await fs.mkdir(path.dirname(OUTPUT_XLSX), { recursive: true });
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(OUTPUT_XLSX);
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  const payloadRaw = await fs.readFile(PAYLOAD_PATH);
  const payload = JSON.parse(payloadRaw.toString("utf8"));
  const flowAssets = await generateProviderFlowAssets();
  if (process.env.FIDC_SKIP_PRESENTATION !== "1") {
    const presentation = buildPresentation(payload, flowAssets);
    if (presentation.slides.items.length !== EXPECTED_SLIDES) {
      throw new Error(`Deck deveria ter ${EXPECTED_SLIDES} slides; gerou ${presentation.slides.items.length}.`);
    }
    await exportPresentation(presentation);
  }
  if (process.env.FIDC_SKIP_WORKBOOK !== "1") {
    const workbook = await buildWorkbook(payload, flowAssets);
    await exportWorkbook(workbook);
  }
  if (
    process.env.FIDC_SKIP_PRESENTATION !== "1" &&
    process.env.FIDC_SKIP_WORKBOOK !== "1"
  ) {
    await writeExportBundleManifest(payload, payloadRaw);
  }
  process.stdout.write(`${OUTPUT_PPTX}\n${OUTPUT_XLSX}\n${OUTPUT_HTML}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
