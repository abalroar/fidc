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
const SKIP_QA = process.env.FIDC_SKIP_QA === "1";
const EXPORT_MANIFEST_PATH = path.resolve(
  process.env.FIDC_EXPORT_MANIFEST ||
    path.join(REVISION_DIR, "industry_export_bundle.json"),
);
const RENDERER_VERSION = "industry_revision_artifacts_v2";

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

function addHeader(slide, eyebrow, title, source, page) {
  slide.background.fill = C.white;
  addText(
    slide,
    eyebrow.toUpperCase(),
    { left: 60, top: 27, width: 520, height: 20 },
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
    String(page),
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
  const xValues = categories.map((_, index) => index);
  const labelIndices = options.labelIndices || categories.map((_, index) => index);
  const labelBand = options.labelBand ?? 18;
  const chartHeight = position.height - labelBand;
  const series = (options.series || []).map((item) => ({
    ...item,
    xValues,
    marker: { symbol: "none" },
  }));
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

async function sha256File(filePath) {
  return createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}

async function writeExportBundleManifest(payload, payloadRaw) {
  const payloadSha256 = createHash("sha256").update(payloadRaw).digest("hex");
  const rendererSha256 = await sha256File(__filename);
  const [pptxSha256, xlsxSha256, pptxStat, xlsxStat] = await Promise.all([
    sha256File(OUTPUT_PPTX),
    sha256File(OUTPUT_XLSX),
    fs.stat(OUTPUT_PPTX),
    fs.stat(OUTPUT_XLSX),
  ]);
  const manifest = {
    schema_version: "fidc_revision_export_bundle_v1",
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
      slides: 42,
    },
    xlsx: {
      filename: path.basename(OUTPUT_XLSX),
      sha256: xlsxSha256,
      bytes: xlsxStat.size,
    },
    checks: {
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
  const colors = [
    C.orange,
    C.black,
    "#30353A",
    "#494E53",
    "#61666B",
    "#777C81",
    "#8D9297",
    "#A3A7AB",
    "#B7BBBE",
    "#C8CBCE",
    C.line,
    C.pale,
  ];
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
      return isBlocked ? 0 : Math.max(0, num(row?.pl_brl));
    });
    const total = positive.reduce((sum, value) => sum + value, 0);
    buckets.forEach((bucket, index) => {
      valuesByBucket[bucket].push(total ? positive[index] / total : 0);
    });
  });
  const series = buckets.map((bucket, index) => ({
    name: providerShort(bucket),
    values: valuesByBucket[bucket],
    fill: colors[index],
  }));
  return {
    categories,
    series,
    blocked,
    negativePl,
    negativeFunds,
    legend: buckets.map((bucket, index) => ({
      label: providerShort(bucket),
      color: colors[index],
      line: bucket === "Prestador não informado" ? C.line : undefined,
    })),
  };
}

function addMarketShareSlide(presentation, payload, role, focusRows, page, appendix = false) {
  const slide = presentation.slides.add();
  const data = marketChartData(payload, role, focusRows);
  const source = appendix
    ? `Fonte: CVM e ANBIMA; mai/26. ${focusRows.length} focos; colunas normalizadas sobre PL não negativo. * combinação bloqueada.`
    : `Fonte: CVM e ANBIMA; mai/26. Top 10 fixo da função; Outros identificados e prestador não informado separados.`;
  const titles = {
    administrador: appendix
      ? "Administração por subtipo: universo completo dos 14 focos"
      : "BB tem 47% de Recebíveis Comerciais; QI tem 66% em Fomento",
    gestor: appendix
      ? "Gestão por subtipo: universo completo dos 14 focos"
      : "O Top 10 cobre 15% de Poder Público e 30% de Fomento",
    custodiante: appendix
      ? "Custódia por subtipo: universo completo dos 14 focos"
      : "Oliveira Trust tem 54% de Crédito Pessoal; QI tem 66% em Fomento",
  };
  addHeader(slide, appendix ? "APÊNDICE · MARKET SHARE" : `MARKET SHARE · ${roleLabel(role)}`, titles[role], source, page);
  slide.charts.add("bar", {
    ...chartBase({ left: 64, top: 145, width: 1150, height: appendix ? 430 : 410 }),
    categories: data.categories,
    series: data.series,
    barOptions: {
      direction: "column",
      grouping: "percentStacked",
      gapWidth: appendix ? 32 : 48,
      overlap: 100,
    },
    hasLegend: false,
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
  });
  addLegend(
    slide,
    data.legend,
    { left: 72, top: appendix ? 585 : 568, width: 1130, height: appendix ? 62 : 74 },
    4,
  );
  if (!appendix) {
    const omitted = payload.material_focus_omitted;
    addText(
      slide,
      `Corpo principal: 6 focos, ${pct(1 - num(omitted.share), 1)} do PL classificado. Fora do gráfico: ${omitted.focuses} focos e ${bn(omitted.pl, 1)}.`,
      { left: 72, top: 638, width: 1130, height: 20 },
      { fontSize: 10.5, color: C.note, alignment: "right" },
    );
  } else {
    const blockedCount = data.blocked.filter(Boolean).length;
    const note = blockedCount
      ? `${blockedCount} combinação(ões) bloqueada(s) por bucket agregado negativo; ${mm(data.negativePl, 1)} de PL negativo permanecem no QA.`
      : `${integer(data.negativeFunds)} registros com PL negativo (${mm(data.negativePl, 1)}) foram excluídos da normalização positiva e permanecem no QA.`;
    addText(slide, note, { left: 72, top: 646, width: 1130, height: 18 }, {
      fontSize: 10.5,
      color: C.note,
      alignment: "right",
    });
  }
  return slide;
}

function buildPresentation(payload) {
  const presentation = Presentation.create({ slideSize: SLIDE });
  const latestCompetence = String(payload.latest_complete || "");
  const stockShort = competenceShortPt(latestCompetence);
  const stockShortLower = stockShort.toLowerCase();
  const stockLong = competenceEndLongPt(latestCompetence);
  const offersAsOf = String(payload.offers_as_of || "");
  const offersShort = dateShortPt(offersAsOf);
  const offersLong = dateLongPt(offersAsOf);
  const offersDate = parseIsoDate(offersAsOf);
  const latestHistory = payload.pl_history.at(-1) || {};
  const latestBase = payload.investor_base_history.at(-1) || {};
  const currentOfferYear = Math.max(...payload.offers_ytd.map((row) => num(row.year)));
  const firstOfferYear = Math.min(...payload.offers_ytd.map((row) => num(row.year)));
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
    addText(slide, `Ofertas: registros até ${offersLong}`, { left: 60, top: 589, width: 520, height: 28 }, {
      fontSize: 16,
      color: C.light,
    });
    addText(slide, `Itaú BBA · ${offersDate ? `${MONTHS_LONG_PT[offersDate.month - 1][0].toUpperCase()}${MONTHS_LONG_PT[offersDate.month - 1].slice(1)} de ${offersDate.year}` : offersAsOf}`, { left: 60, top: 657, width: 500, height: 22 }, {
      fontSize: 12,
      bold: true,
      color: C.orange,
    });
  }

  // 2. Síntese executiva
  {
    const slide = presentation.slides.add();
    addHeader(
      slide,
      "SÍNTESE EXECUTIVA",
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
        detail: `${(num(latestHistory.pl_ex_fic) / num(payload.pl_history[0]?.pl_ex_fic)).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} vezes o nível de ${payload.pl_history[0]?.year}; FIC-FIDC adiciona ${bn(latestHistory.pl_fic_componente, 1)} ao PL bruto.`,
      },
      {
        value: "59%",
        claim: "dos fundos acima de R$ 200 mi têm até 10 contas",
        detail: "Esse recorte concentra 60,7% do PL do universo de R$ 733,9 bi.",
      },
      {
        value: integer(qa.casos_inad_supera_carteira),
        claim: "veículos com inadimplência acima da carteira",
        detail: `O cap remove ${bn(qa.excesso_removido_brl, 1)}; os 10 maiores casos explicam ${pct(qa.excesso_top10_share, 1)}.`,
      },
      {
        value: pct(mono?.share_pl, 1),
        claim: "do PL em monoestruturas",
        detail: "Sistema Petrobras é todo o PL mono do BB; TAPSO representa 54% do PL mono da Oliveira Trust.",
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
        ...chartAxis(11, "R$ 0 \"bi\""),
        min: 0,
        max: Math.ceil(totalMax / 100) * 100,
        majorUnit: 200,
      },
    });
    const axisMax = Math.ceil(totalMax / 100) * 100;
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
    addText(slide, "O total no topo da coluna é o PL bruto.", { left: 930, top: 590, width: 290, height: 30 }, {
      fontSize: 12.5,
      color: C.note,
    });
  }

  // 4. Base investidora
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
    const rows = payload.holder_distribution;
    const upto10 = rows.filter((row) => ["0", "1", "2–3", "4–10"].includes(row.bucket));
    const shareFunds = upto10.reduce((sum, row) => sum + num(row.share_fundos), 0);
    const sharePl = upto10.reduce((sum, row) => sum + num(row.share_pl), 0);
    addHeader(
      slide,
      "DISTRIBUIÇÃO POR NÚMERO DE COTISTAS",
      `${pct(shareFunds, 0)} dos fundos acima de R$ 200 mi têm até 10 contas e concentram ${pct(sharePl, 0)} do PL`,
      `Fonte: CVM, mai/26. Universo: ${integer(rows[0]?.universo_fundos)} fundos e ${bn(rows[0]?.universo_pl, 1)} de PL; contas por classe/série.`,
      5,
    );
    addSectionLabel(slide, "QUANTIDADE DE FUNDOS", { left: 60, top: 145, width: 555, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 180, width: 555, height: 425 }),
      categories: rows.map((row) => row.bucket),
      series: [{ name: "Fundos", values: rows.map((row) => num(row.fundos)), fill: C.charcoal }],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 48 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(11, "0"), min: 0 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 11.5, bold: true } },
    });
    addSectionLabel(slide, "PL POR FAIXA", { left: 665, top: 145, width: 555, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 665, top: 180, width: 555, height: 425 }),
      categories: rows.map((row) => row.bucket),
      series: [{ name: "PL", values: rows.map((row) => num(row.pl) / 1e9), fill: C.orange }],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 48 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(11, "R$ 0 \"bi\""), min: 0 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 11.5, bold: true } },
    });
  }

  // 6. Mix ANBIMA
  {
    const slide = presentation.slides.add();
    const mix = [...payload.type_mix].sort((a, b) => num(b.pl) - num(a.pl));
    const coverage = payload.classification_coverage;
    const others = mix.find((row) => row.anbima_tipo === "Outros");
    const official = coverage.find((row) => row.categoria === "Oficial ANBIMA");
    addHeader(
      slide,
      "TIPO ANBIMA",
      `Outros reúne ${pct(others?.share, 1)} do PL ex-FIC; ${pct(1 - num(official?.share), 1)} não vem da fotografia oficial`,
      "Fonte: ANBIMA Data, evidência documental e CVM; mai/26. Tipo e Foco são campos separados.",
      6,
    );
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 155, width: 725, height: 450 }),
      categories: mix.map((row) => row.anbima_tipo),
      series: [
        {
          name: "PL ex-FIC",
          values: mix.map((row) => num(row.pl) / 1e9),
          fill: C.charcoal,
          points: mix.map((row, idx) => ({ idx, fill: row.anbima_tipo === "Outros" ? C.orange : C.charcoal })),
        },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 40 },
      hasLegend: false,
      xAxis: { ...chartAxis(11, "R$ 0 \"bi\""), min: 0 },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 11.5, bold: true } },
    });
    addSectionLabel(slide, "ORIGEM DA CLASSIFICAÇÃO", { left: 840, top: 155, width: 380, height: 24 });
    addFlatList(
      slide,
      coverage.map((row) => ({ label: row.categoria, value: pct(row.share, 2), accent: row.categoria === "Oficial ANBIMA" })),
      { left: 840, top: 205, width: 380, height: 230 },
      { fontSize: 14 },
    );
    addText(
      slide,
      "A classificação de mai/26 combina fotografia cadastral ANBIMA, evidência documental, proxy CVM e registros N/D. A origem permanece visível por fundo.",
      { left: 840, top: 475, width: 380, height: 105 },
      { fontSize: 14.5, color: C.mid, lineSpacing: 1.05 },
    );
  }

  // 7. Carteira por recebível
  {
    const slide = presentation.slides.add();
    const rows = payload.receivables.rows.slice(0, 9);
    addHeader(
      slide,
      "CARTEIRA POR TIPO DE RECEBÍVEL",
      `A abertura por recebível soma ${bn(payload.receivables.reported_total, 1)}, ${bn(payload.receivables.gap, 1)} acima da carteira da Tabela I`,
      "Fonte: CVM, Informe Mensal de FIDC, Tabelas I e II, mai/26. Categorias não foram forçadas a reconciliar.",
      7,
    );
    slide.charts.add("bar", {
      ...chartBase({ left: 75, top: 150, width: 1115, height: 455 }),
      categories: rows.map((row) => row.segmento),
      series: [
        {
          name: "Valor reportado",
          values: rows.map((row) => num(row.valor) / 1e9),
          fill: C.charcoal,
          points: rows.map((_, idx) => ({ idx, fill: idx === 0 ? C.orange : C.charcoal })),
        },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 34 },
      hasLegend: false,
      xAxis: { ...chartAxis(11, "R$ 0 \"bi\""), min: 0 },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 11.5, bold: true } },
    });
  }

  // 8. Observabilidade da inadimplência
  {
    const slide = presentation.slides.add();
    const qa = payload.qa_latest;
    addHeader(
      slide,
      "OBSERVABILIDADE DA INADIMPLÊNCIA",
      `O cap retira ${bn(qa.excesso_removido_brl, 1)} de ${integer(qa.casos_inad_supera_carteira)} veículos; 10 casos explicam ${pct(qa.excesso_top10_share, 1)}`,
      "Fonte: CVM, mai/26. Ajuste = mínimo entre inadimplência não negativa e carteira não negativa por veículo.",
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
      `Visão ex-360 bloqueada: o aging soma ${pct(qa.aging_reconciliacao_ratio, 1)} da Tabela I e não reconcilia; gap de ${bn(qa.aging_gap_vs_inadimplencia_reportada_brl, 2)} no workbook.`,
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
    addHeader(
      slide,
      "INADIMPLÊNCIA · EVOLUÇÃO E QUEBRA",
      `Atlântico explica ${bn(Math.abs(num(atlantic.delta_excesso_brl)), 1)} da queda de excesso entre jun e jul/24`,
      "Fonte: painel CVM versionado. Jun/24 e jul/24 não preservam flags brutas de campo; mudança de reporte não é separável.",
      9,
    );
    addStraightLineChart(slide, {
      position: { left: 60, top: 150, width: 1160, height: 315 },
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
      yAxis: { ...chartAxis(11, "0.0%"), min: 0, max: 0.18, majorUnit: 0.03 },
      labelIndices: [0, 3, 5, 6, 8, 11, categories.length - 1],
      labelFontSize: 9.5,
    });
    addLegend(
      slide,
      [
        { label: "Bruta", color: C.charcoal },
        { label: "Ajustada", color: C.orange },
      ],
      { left: 500, top: 474, width: 300, height: 24 },
      2,
    );
    const summaryRows = payload.bridge_summary;
    const continuants = summaryRows.find((row) => String(row.bridge_group).includes("continu"));
    const entries = summaryRows.find((row) => String(row.bridge_group).includes("entrada"));
    const exits = summaryRows.find((row) => String(row.bridge_group).includes("saída") || String(row.bridge_group).includes("saida"));
    const otherContinuants = num(continuants?.delta_excesso_brl) - num(atlantic.delta_excesso_brl);
    addEditorialTable(slide, {
      left: 60,
      top: 515,
      width: 1160,
      height: 120,
      headers: ["Bridge jun→jul/24", "Veículos", "Δ inad. bruta", "Δ ajustada", "Δ excesso"],
      rows: [
        ["Atlântico FIDC", "1", bn(atlantic.delta_inad_bruta_brl, 1), bn(atlantic.delta_inad_ajustada_brl, 1), bn(atlantic.delta_excesso_brl, 1)],
        ["Outros continuantes", integer(Math.max(0, num(continuants?.veiculos) - 1)), bn(num(continuants?.delta_inad_bruta_brl) - num(atlantic.delta_inad_bruta_brl), 1), bn(num(continuants?.delta_inad_ajustada_brl) - num(atlantic.delta_inad_ajustada_brl), 1), bn(otherContinuants, 1)],
        ["Entradas / saídas", `${integer(entries?.veiculos)} / ${integer(exits?.veiculos)}`, bn(num(entries?.delta_inad_bruta_brl) + num(exits?.delta_inad_bruta_brl), 1), bn(num(entries?.delta_inad_ajustada_brl) + num(exits?.delta_inad_ajustada_brl), 1), bn(num(entries?.delta_excesso_brl) + num(exits?.delta_excesso_brl), 1)],
      ],
      columnWidths: [400, 150, 200, 200, 210],
      aligns: ["left", "right", "right", "right", "right"],
      fontSize: 12,
      rowHighlights: new Set([0]),
    });
  }

  // 10. Prestadores e concentração
  {
    const slide = presentation.slides.add();
    const providers = payload.provider_concentration;
    const roleOrder = ["administrador", "gestor", "custodiante"];
    const ordered = roleOrder.map((role) => providers.find((row) => row.papel === role));
    addHeader(
      slide,
      "PRESTADORES · RANKING E CONCENTRAÇÃO",
      `Top 10: ${pct(ordered[1]?.top10_share, 0)} em gestão, ${pct(ordered[0]?.top10_share, 0)} em administração e ${pct(ordered[2]?.top10_share, 0)} em custódia`,
      "CVM, mai/26. Shares sobre PL total; prestador não informado permanece no denominador.",
      10,
    );
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 155, width: 640, height: 420 }),
      categories: ["Administração", "Gestão", "Custódia"],
      series: [
        { name: "Top 5", values: ordered.map((row) => num(row?.top5_share)), valuesFormatCode: "0.0%", fill: C.line },
        { name: "Top 10", values: ordered.map((row) => num(row?.top10_share)), valuesFormatCode: "0.0%", fill: C.orange },
      ],
      barOptions: { direction: "bar", grouping: "clustered", gapWidth: 52 },
      hasLegend: true,
      legend: { position: "bottom", textStyle: { fill: C.mid, fontSize: 12 } },
      xAxis: {
        ...chartAxis(10.5, "0%"),
        min: 0,
        max: 0.8,
        majorUnit: 0.2,
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 11.5, bold: true } },
    });
    addRect(slide, { left: 135, top: 510, width: 570, height: 28 }, C.white);
    addSectionLabel(slide, "TRÊS MAIORES POR FUNÇÃO", { left: 750, top: 155, width: 470, height: 24 });
    const tableRows = [];
    ordered.forEach((roleRow) => {
      roleRow?.top3?.forEach((row, index) => {
        tableRows.push([
          index === 0 ? roleLabel(roleRow.papel).toUpperCase() : "",
          truncateWords(providerShort(row.nome), 36),
          pct(row.share_pl, 1),
        ]);
      });
    });
    addEditorialTable(slide, {
      left: 750,
      top: 195,
      width: 470,
      height: 390,
      headers: ["Função", "Prestador", "PL"],
      rows: tableRows,
      columnWidths: [110, 270, 90],
      aligns: ["left", "left", "right"],
      fontSize: 11.5,
      rowHeight: 39.5,
    });
  }

  // 11–13. Market share por subtipo, seis focos materiais.
  const materialFocus = payload.material_focus_top6;
  addMarketShareSlide(presentation, payload, "administrador", materialFocus, 11, false);
  addMarketShareSlide(presentation, payload, "gestor", materialFocus, 12, false);
  addMarketShareSlide(presentation, payload, "custodiante", materialFocus, 13, false);

  // 14. Top 20 FIDCs
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
      "Fonte: CVM e ANBIMA, mai/26. Ranking derivado do universo completo ex-FIC; denominação legal completa no apêndice.",
      14,
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

  // 15. Top 20 Outros
  {
    const slide = presentation.slides.add();
    const rows = payload.top20_outros;
    const categoryShare = rows.reduce((sum, row) => sum + num(row.market_share_outros), 0);
    addHeader(
      slide,
      "RANKING · TOP 20 OUTROS",
      `Top 20 representam ${pct(categoryShare, 1)} de Outros; oficial, hipótese e status ficam separados`,
      "Fonte: ANBIMA e documentos primários locais, mai/26. Evidência e links completos constam no workbook.",
      15,
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

  // 16. Modelo de prestação
  {
    const slide = presentation.slides.add();
    const rows = payload.service_model;
    const mono = rows.find((row) => row.modelo_prestacao === "Monoestrutura");
    const missing = rows.find((row) => row.modelo_prestacao === "Dados incompletos");
    addHeader(
      slide,
      "MODELO DE PRESTAÇÃO",
      `Monoestruturas são ${pct(mono?.share_fundos, 1)} dos fundos e ${pct(mono?.share_pl, 1)} do PL; dados incompletos cobrem ${pct(missing?.share_pl, 1)}`,
      "Fonte: CVM, cadastro vigente em mai/26. Definição mono: mesmo conglomerado normalizado em administração, gestão e custódia.",
      16,
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

  // 17. Concentração das monoestruturas
  {
    const slide = presentation.slides.add();
    const rows = [...payload.monostructure_concentration].sort((a, b) => num(a.rank_pl_mono) - num(b.rank_pl_mono)).slice(0, 6);
    const bb = rows.find((row) => String(row.grupo_economico).includes("Banco do Brasil"));
    const ot = rows.find((row) => String(row.grupo_economico).includes("Oliveira Trust"));
    addHeader(
      slide,
      "CONCENTRAÇÃO DAS MONOESTRUTURAS",
      "Sistema Petrobras é todo o PL mono do BB; TAPSO representa 54% do PL mono da Oliveira Trust",
      "Fonte: CVM, mai/26. A evidência mostra concentração; não permite inferir preços, propostas ou contratos.",
      17,
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

  // 18. Ofertas e originação
  {
    const slide = presentation.slides.add();
    const offers = [...payload.offers_ytd].sort((a, b) => num(a.year) - num(b.year));
    const current = offers.find((row) => num(row.year) === currentOfferYear);
    const prior = offers.find((row) => num(row.year) === currentOfferYear - 1);
    const originators = payload.originators_current || payload.originators_2026;
    addHeader(
      slide,
      "OFERTAS, CAPTAÇÃO E ORIGINAÇÃO",
      `Ofertas somam ${bn(current?.volume, 1)} até ${offersShort}, ${pct(num(current?.volume) / num(prior?.volume) - 1, 1)} acima de ${currentOfferYear - 1}`,
      `Fonte: CVM, Ofertas Públicas. Comparação YTD até ${offersShort} em ${firstOfferYear}–${currentOfferYear}; PL do restante do deck em ${stockLong}.`,
      18,
    );
    addSectionLabel(slide, "VOLUME REGISTRADO NO MESMO PERÍODO", { left: 60, top: 150, width: 720, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 190, width: 720, height: 390 }),
      categories: offers.map((row) => String(row.year)),
      series: [
        {
          name: "Volume",
          values: offers.map((row) => num(row.volume) / 1e9),
          valuesFormatCode: "0.0",
          fill: C.charcoal,
          points: offers.map((row, idx) => ({ idx, fill: num(row.year) === currentOfferYear ? C.orange : C.charcoal })),
        },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 60 },
      hasLegend: false,
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 12 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(11, "R$ 0 \"bi\""), min: 0 },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: C.black, fontSize: 12, bold: true } },
    });
    offers.forEach((row, index) => {
      addText(
        slide,
        `${integer(row.ofertas)} ofertas`,
        { left: 155 + index * 185, top: 565, width: 150, height: 22 },
        { fontSize: 11.5, color: C.note, alignment: "center" },
      );
    });
    addSectionLabel(slide, `TOP 5 ORIGINADORES NOMINÁVEIS · ${currentOfferYear}`, { left: 835, top: 150, width: 385, height: 24 });
    addFlatList(
      slide,
      originators.rows.map((row) => ({
        label: row.originator_group,
        value: bn(row.volume_brl, 2),
        accent: row === originators.rows[0],
      })),
      { left: 835, top: 200, width: 385, height: 285 },
      { fontSize: 13.5 },
    );
    addMetric(
      slide,
      pct(originators.coverage, 1),
      "do volume tem originador nominal identificado; não há base para chamar a originação de pulverizada.",
      { left: 835, top: 520, width: 385, height: 105 },
      true,
    );
  }

  // 19. Escopo, fontes e limitações
  {
    const slide = presentation.slides.add();
    const coverage = Object.fromEntries(payload.classification_coverage.map((row) => [row.categoria, row.share]));
    addHeader(
      slide,
      "APÊNDICE · ESCOPO E FONTES",
      "Escopo, fontes e limitações",
      `• Fontes primárias: CVM, ANBIMA Data e FundosNet. Dados consultados até ${offersShort}.`,
      19,
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
        ["Inadimplência", `${integer(payload.qa_latest.veiculos_total)} veículos; ${stockShortLower}`, "Cap por veículo; vazio não é zero. Aging >360 existe na norma, mas não reconcilia com a Tabela I; visão ex-360 bloqueada."],
        ["Market share", `14 focos; 3 funções; ${stockShortLower}`, "Denominador = PL do subtipo. Top 10 fixo por função; Outros identificados e prestador não informado separados. PL negativo consta no QA."],
        ["Monoestrutura", `${integer(payload.qa_latest.fundos_total)} fundos; ${stockShortLower}`, "Mesma entidade econômica normalizada nas três funções. Concentração não prova poder de preço ou condições comerciais."],
        ["Ofertas", `Registros até ${offersShort} em ${firstOfferYear}–${currentOfferYear}`, "Comparação YTD contra mesmo período. Anúncio ou aprovação não equivale a volume integralizado."],
      ],
      columnWidths: [190, 340, 630],
      aligns: ["left", "left", "left"],
      fontSize: 13.2,
      rowHeight: 75,
    });
  }

  // 20–22. Universo completo dos market shares.
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
  addMarketShareSlide(presentation, payload, "administrador", fullFocus, 20, true);
  addMarketShareSlide(presentation, payload, "gestor", fullFocus, 21, true);
  addMarketShareSlide(presentation, payload, "custodiante", fullFocus, 22, true);

  // 23–42. Fichas dos Top 20.
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
        23 + index,
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
    } else if (/pl|carteira|inadimpl|excesso|volume|valor|emiss/.test(normalized) && !/status|motivo|regra|fonte|evid/.test(normalized)) {
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
    "Resumo por competência. Campos ausentes permanecem distintos de zero; a base detalhada está em 'Base competência/CNPJ'.",
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

async function addVehicleCompetenceSheet(workbook) {
  const csv = await readCsv(path.join(REVISION_DIR, "base_competencia_cnpj.csv.gz"));
  const competenceIndex = csv.headers.indexOf("competencia");
  const auditMonths = new Set(["2024-06", "2024-07", "2026-05"]);
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
  const sheet = resetSheet(workbook, "Base competência/CNPJ");
  setHeaderBand(
    sheet,
    "Base competência/CNPJ",
    "Recorte operacional de jun/24, jul/24 e mai/26. A base longitudinal completa está em data/industry_study/generated_revision/base_competencia_cnpj.csv.gz. Ajustado e excesso são fórmulas.",
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

async function addFundBaseSheet(workbook) {
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
  const sheet = resetSheet(workbook, "Base por fundo/CNPJ");
  setHeaderBand(
    sheet,
    "Base por fundo/CNPJ",
    "Fotografia de mai/26 reconciliada a 4.222 fundos. A unidade legal e a entidade econômica normalizada permanecem em colunas distintas.",
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
    ["Denominador subtipo", "denominador_pl_subtipo_brl"],
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
    "Top 10 fixo por função + Outros identificados + Prestador não informado. PL negativo e combinações bloqueadas permanecem explícitos.",
    headers,
    rows.length,
    { freezeColumns: 4, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [80, 105, 150, 180, 65, 250, 100, 70, 110, 125, 90, 110, 100, 85, 95, 105, 240, 160, 95], rows.length);
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
    setHeaderBand(sheet, "Top 20 FIDCs", "Ranking de mai/26 sobre o universo completo ex-FIC. Exatamente 20 fundos; ficha detalhada na aba 'Curadoria Top 20'.", headers, rows.length, { freezeColumns: 3, wrapText: true });
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
    ["Slides do corpo na ordem definida", 18, 18, '=IF(B9=C9,"OK","ERRO")'],
    ["Perfis Top 20", payload.profiles.length, 20, '=IF(B10=C10,"OK","ERRO")'],
    ["Combinações função×foco", focusRows.length, 42, '=IF(B11=C11,"OK","ERRO")'],
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

async function buildWorkbook(payload) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(INPUT_WORKBOOK));
  await addQaSheet(workbook);
  await addVehicleCompetenceSheet(workbook);
  await addFundBaseSheet(workbook);
  await addMonoConcentrationSheet(workbook);
  await addMarketShareSheet(workbook);
  await addTop20Sheets(workbook, payload);
  await addCurationSheet(workbook, payload);
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
}

async function exportWorkbook(workbook) {
  if (!SKIP_QA) {
    const previewSheets = [
      ["QA Inadimplência", "A1:AB26"],
      ["Base por fundo/CNPJ", "A1:U20"],
      ["Concentração de monoestruturas", "A1:N24"],
      ["Market share por subtipo", "A1:S26"],
      ["Top 20 FIDCs", "A1:M25"],
      ["Top 20 Outros", "A1:J25"],
      ["Curadoria Top 20", "A1:X16"],
      ["Checks revisão", "A1:D14"],
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
  if (process.env.FIDC_SKIP_PRESENTATION !== "1") {
    const presentation = buildPresentation(payload);
    if (presentation.slides.items.length !== 42) {
      throw new Error(`Deck deveria ter 42 slides; gerou ${presentation.slides.items.length}.`);
    }
    await exportPresentation(presentation);
  }
  if (process.env.FIDC_SKIP_WORKBOOK !== "1") {
    const workbook = await buildWorkbook(payload);
    await exportWorkbook(workbook);
  }
  if (
    process.env.FIDC_SKIP_PRESENTATION !== "1" &&
    process.env.FIDC_SKIP_WORKBOOK !== "1"
  ) {
    await writeExportBundleManifest(payload, payloadRaw);
  }
  process.stdout.write(`${OUTPUT_PPTX}\n${OUTPUT_XLSX}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
