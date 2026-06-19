import fs from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const PptxGenJS = require(process.env.PPTXGENJS_MODULE || "pptxgenjs");

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Uso: node build_fidc_committee_pptxgen.mjs payload.json output.pptx");
}

const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Toma Conta";
pptx.company = "Toma Conta";
pptx.subject = "Modelagem FIDC";
pptx.title = "Modelagem FIDC | Comitê";
pptx.lang = "pt-BR";
pptx.theme = {
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  lang: "pt-BR",
};

const COLORS = {
  black: "1F1F1F",
  text: "2B2B2B",
  muted: "6B7280",
  grid: "D9D9D9",
  gridSoft: "E5E7EB",
  light: "F7F7F7",
  stripe: "F1F1F1",
  orange: "F28E2B",
  darkOrange: "B35C00",
  white: "FFFFFF",
};

function cleanHex(value, fallback = COLORS.black) {
  const text = String(value || fallback).replace("#", "").toUpperCase();
  return /^[0-9A-F]{6}$/.test(text) ? text : fallback;
}

function text(slide, value, x, y, w, h, options = {}) {
  slide.addText(String(value ?? ""), {
    x,
    y,
    w,
    h,
    fontFace: "Calibri",
    fontSize: options.fontSize ?? 10,
    color: options.color ?? COLORS.text,
    bold: options.bold ?? false,
    align: options.align ?? "left",
    valign: options.valign ?? "top",
    margin: options.margin ?? [0, 0, 0, 0],
    breakLine: false,
    fit: options.fit ?? "shrink",
    wrap: true,
  });
}

function addHeader(slide, title) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.48,
    y: 0.20,
    w: 0.52,
    h: 0.36,
    rectRadius: 0.12,
    fill: { color: COLORS.black },
    line: { color: COLORS.black, transparency: 100 },
  });
  text(slide, "itaú", 0.52, 0.265, 0.44, 0.16, {
    fontSize: 10,
    bold: true,
    color: COLORS.white,
    align: "center",
    valign: "mid",
  });
  text(slide, "BBA", 1.05, 0.285, 0.78, 0.18, {
    fontSize: 11,
    bold: true,
    color: COLORS.black,
  });
  text(slide, title, 1.95, 0.14, 10.95, 0.50, {
    fontSize: 23,
    bold: true,
    color: COLORS.black,
    valign: "mid",
  });
}

function addFooter(slide, page, total) {
  slide.addShape(pptx.ShapeType.line, {
    x: 0.48,
    y: 6.98,
    w: 12.34,
    h: 0,
    line: { color: COLORS.gridSoft, width: 0.6 },
  });
  text(slide, "Fonte: simulação interna Toma Conta | Modelagem FIDC", 0.58, 7.12, 4.6, 0.13, {
    fontSize: 7.5,
    color: COLORS.muted,
  });
  text(slide, `Página ${page} de ${total}`, 10.9, 7.12, 1.65, 0.13, {
    fontSize: 7.5,
    color: COLORS.muted,
    align: "right",
  });
}

function tableCell(value, options = {}) {
  return {
    text: String(value ?? ""),
    options: {
      fontFace: "Calibri",
      fontSize: options.fontSize ?? 6.6,
      bold: options.bold ?? false,
      color: options.color ?? COLORS.black,
      fill: { color: options.fill ?? COLORS.white },
      valign: "mid",
      align: options.align ?? "left",
      margin: options.margin ?? [0.02, 0.04, 0.02, 0.04],
      fit: "shrink",
      wrap: true,
      border: { color: COLORS.white, pt: 0.45 },
    },
  };
}

function addTable(slide, rows, x, y, w, h, columnWidths, options = {}) {
  const safeRows = Array.isArray(rows) && rows.length ? rows : [["", ""]];
  const tableRows = safeRows.map((row, rowIndex) => {
    const isHeader = rowIndex === 0;
    const fill = isHeader ? COLORS.black : rowIndex % 2 === 0 ? COLORS.stripe : COLORS.white;
    return row.map((value, colIndex) =>
      tableCell(value, {
        fill,
        color: isHeader ? COLORS.white : COLORS.black,
        bold: isHeader || (options.boldFirstColumn && colIndex === 0),
        fontSize: isHeader ? options.headerFontSize ?? 7.4 : options.bodyFontSize ?? 6.6,
        align: isHeader || colIndex > 0 ? "center" : "left",
      }),
    );
  });
  slide.addTable(tableRows, {
    x,
    y,
    w,
    h,
    colW: columnWidths,
    rowH: options.rowHeights,
    margin: [0.01, 0.03, 0.01, 0.03],
    border: { color: COLORS.white, pt: 0.45 },
    autoPage: false,
  });
}

function addBulletBlock(slide, title, bullets, x, y, w, h = 1.45) {
  text(slide, title, x, y, w, 0.26, {
    fontSize: 13.5,
    bold: true,
    color: COLORS.black,
  });
  text(slide, (bullets || []).map((item) => `•  ${item}`).join("\n"), x, y + 0.38, w, h, {
    fontSize: 10,
    color: COLORS.text,
    margin: [0, 0, 0, 0],
  });
}

function addKpiStrip(slide, cards) {
  const left = 0.55;
  const top = 0.78;
  const gap = 0.12;
  const width = (12.25 - gap * 6) / 7;
  (cards || []).slice(0, 7).forEach((card, index) => {
    const x = left + index * (width + gap);
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: top,
      w: width,
      h: 0.50,
      rectRadius: 0.05,
      fill: { color: COLORS.light },
      line: { color: COLORS.grid, width: 0.75 },
      shadow: { type: "outer", color: "000000", opacity: 0.10, blur: 1, angle: 45, distance: 1 },
    });
    text(slide, String(card.label || "").toUpperCase(), x + 0.08, top + 0.04, width - 0.16, 0.10, {
      fontSize: 4.8,
      bold: true,
      color: COLORS.muted,
      align: "center",
    });
    text(slide, String(card.value || "N/D"), x + 0.08, top + 0.19, width - 0.16, 0.16, {
      fontSize: 8,
      bold: true,
      color: COLORS.black,
      align: "center",
    });
    text(slide, String(card.context || ""), x + 0.08, top + 0.36, width - 0.16, 0.10, {
      fontSize: 4.8,
      color: COLORS.muted,
      align: "center",
    });
  });
}

function seriesFromPayload(chartPayload) {
  const categories =
    Array.isArray(chartPayload?.categories) && chartPayload.categories.length
      ? chartPayload.categories.map((item) => String(item))
      : ["M0"];
  const series =
    Array.isArray(chartPayload?.series) && chartPayload.series.length
      ? chartPayload.series
      : [{ name: "Série", values: [0], fill: `#${COLORS.black}` }];
  return series.map((item) => ({
    name: String(item.name || "Série"),
    labels: categories,
    values: categories.map((_, index) => Number(item.values?.[index] ?? 0)),
  }));
}

function colorsFromPayload(chartPayload, fallback) {
  const colors = (chartPayload?.series || []).map((item) => cleanHex(item.fill, fallback[0]));
  return colors.length ? colors : fallback;
}

function addAreaChart(slide, chartPayload) {
  text(slide, "Evolução do Saldo das Cotas", 2.10, 1.29, 3.20, 0.20, {
    fontSize: 12,
    bold: true,
    color: COLORS.black,
    align: "center",
  });
  slide.addChart(pptx.ChartType.area, seriesFromPayload(chartPayload), {
    x: 0.55,
    y: 1.42,
    w: 6.25,
    h: 2.70,
    title: "Evolução do Saldo das Cotas",
    titleFontFace: "Calibri",
    titleFontSize: 12,
    titleBold: true,
    titleColor: COLORS.black,
    showTitle: true,
    chartColors: colorsFromPayload(chartPayload, [COLORS.black, "9C9C9C", COLORS.orange, COLORS.darkOrange]),
    barGrouping: "stacked",
    showLegend: true,
    legendPos: "b",
    legendFontFace: "Calibri",
    legendFontSize: 8,
    legendColor: COLORS.muted,
    showValue: false,
    showCatName: false,
    showValAxisTitle: true,
    valAxisTitle: "R$ milhões",
    valAxisTitleFontFace: "Calibri",
    valAxisTitleFontSize: 9,
    valAxisTitleColor: COLORS.muted,
    valAxisLabelFontFace: "Calibri",
    valAxisLabelFontSize: 8,
    valAxisLabelColor: COLORS.muted,
    valAxisLabelFormatCode: "#,##0",
    valAxisLineColor: COLORS.gridSoft,
    catAxisLabelFontFace: "Calibri",
    catAxisLabelFontSize: 8,
    catAxisLabelColor: COLORS.muted,
    catAxisLineColor: COLORS.gridSoft,
    valGridLine: { color: COLORS.gridSoft, size: 0.6, style: "solid" },
    chartArea: { fill: { color: COLORS.white, transparency: 100 }, border: { color: COLORS.white, transparency: 100 } },
    plotArea: { fill: { color: COLORS.white, transparency: 100 }, border: { color: COLORS.white, transparency: 100 } },
  });
}

function addLineChart(slide, chartPayload) {
  text(slide, "Proteção da estrutura", 5.00, 4.41, 3.20, 0.20, {
    fontSize: 12,
    bold: true,
    color: COLORS.black,
    align: "center",
  });
  slide.addChart(pptx.ChartType.line, seriesFromPayload(chartPayload), {
    x: 0.72,
    y: 4.62,
    w: 11.70,
    h: 1.78,
    title: "Proteção da estrutura",
    titleFontFace: "Calibri",
    titleFontSize: 12,
    titleBold: true,
    titleColor: COLORS.black,
    showTitle: true,
    chartColors: colorsFromPayload(chartPayload, [COLORS.black, COLORS.orange]),
    showLegend: true,
    legendPos: "b",
    legendFontFace: "Calibri",
    legendFontSize: 8,
    legendColor: COLORS.muted,
    showValue: false,
    lineSize: 2,
    lineDataSymbol: "circle",
    lineDataSymbolSize: 5,
    lineSmooth: false,
    showValAxisTitle: true,
    valAxisTitle: "Proteção da estrutura (%)",
    valAxisTitleFontFace: "Calibri",
    valAxisTitleFontSize: 9,
    valAxisTitleColor: COLORS.muted,
    valAxisLabelFontFace: "Calibri",
    valAxisLabelFontSize: 8,
    valAxisLabelColor: COLORS.muted,
    valAxisLabelFormatCode: "0%",
    valAxisMinVal: 0,
    valAxisLineColor: COLORS.gridSoft,
    catAxisLabelFontFace: "Calibri",
    catAxisLabelFontSize: 8,
    catAxisLabelColor: COLORS.muted,
    catAxisLineColor: COLORS.gridSoft,
    valGridLine: { color: COLORS.gridSoft, size: 0.6, style: "solid" },
    chartArea: { fill: { color: COLORS.white, transparency: 100 }, border: { color: COLORS.white, transparency: 100 } },
    plotArea: { fill: { color: COLORS.white, transparency: 100 }, border: { color: COLORS.white, transparency: 100 } },
  });
}

function addPremissasSlide() {
  const slide = pptx.addSlide();
  slide.background = { color: COLORS.white };
  addHeader(slide, "Modelagem FIDC | Fluxo Econômico e Mecânica Reinvestimento");
  addTable(slide, payload.premissasTable, 0.55, 0.82, 5.45, 5.84, [2.80, 2.65], {
    bodyFontSize: 6.15,
    headerFontSize: 7.5,
  });
  addBulletBlock(slide, "Premissas Principais", payload.premissasBullets, 6.45, 0.92, 5.95, 1.40);
  addBulletBlock(slide, "Fluxo Simplificado", payload.flowBullets, 6.45, 2.78, 5.95, 1.22);
  addTable(slide, payload.flowTable, 6.50, 4.55, 6.08, 1.82, [2.15, 1.25, 2.68], {
    bodyFontSize: 6.2,
    headerFontSize: 7.2,
  });
}

function addLockSlide() {
  const slide = pptx.addSlide();
  slide.background = { color: COLORS.white };
  addHeader(slide, "Modelagem FIDC | Subordinação e Reinvestimento");
  addBulletBlock(slide, "Regra de modelagem", payload.lockBullets, 0.62, 0.95, 5.60, 1.65);
  addTable(slide, payload.formulaTable, 6.55, 0.98, 5.95, 2.20, [1.70, 4.25], {
    bodyFontSize: 6.35,
    headerFontSize: 7.2,
  });
  addTable(slide, payload.lockTable, 0.62, 3.60, 11.88, 2.30, [0.90, 2.25, 2.25, 2.15, 2.15, 2.18], {
    bodyFontSize: 6.15,
    headerFontSize: 6.8,
  });
  text(
    slide,
    "Leitura: giro do principal não aumenta o denominador; a originada acumulada cresce apenas com excesso de caixa reinvestido.",
    0.65,
    6.08,
    11.80,
    0.30,
    { fontSize: 8.4, color: COLORS.muted },
  );
}

function addOutputsSlide() {
  const slide = pptx.addSlide();
  slide.background = { color: COLORS.white };
  addHeader(slide, "Modelagem FIDC | Fluxo Econômico e Mecânica Reinvestimento");
  addKpiStrip(slide, payload.cards);
  addAreaChart(slide, payload.balanceChart);
  addBulletBlock(slide, "Outputs", payload.outputs, 7.20, 1.48, 5.35, 1.60);
  addLineChart(slide, payload.protectionChart);
}

addPremissasSlide();
addLockSlide();
addOutputsSlide();
pptx._slides.forEach((slide, index) => addFooter(slide, index + 1, pptx._slides.length));

await pptx.writeFile({ fileName: outputPath, compression: true });
