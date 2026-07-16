import fs from "node:fs/promises";
import path from "node:path";

export const W = 1600;
export const H = 900;

export const C = {
  ink: "#101820",
  ink2: "#1B2733",
  paper: "#F7F3EA",
  stone: "#ECE5D8",
  white: "#FFFFFF",
  gray900: "#24303A",
  gray700: "#53606B",
  gray500: "#7F8892",
  gray300: "#C9C3B7",
  gray200: "#E3DCCF",
  copper: "#C66A32",
  copper2: "#E49A66",
  teal: "#237B7B",
  blue: "#365D85",
  green: "#557A46",
  red: "#9A3B3B",
  amber: "#B58B2A",
};

let cachedData = null;

export async function loadData(ctx) {
  if (!cachedData) {
    const raw = await fs.readFile(path.join(ctx.workspaceDir, "data.json"), "utf8");
    cachedData = JSON.parse(raw);
  }
  return cachedData;
}

export function fmtInt(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "";
  return Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

export function fmtBn(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "";
  return `R$ ${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} bi`;
}

export function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "";
  return `${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

export function truncate(text, len = 56) {
  const s = String(text ?? "");
  return s.length > len ? `${s.slice(0, len - 1)}…` : s;
}

export function addRect(slide, { left, top, width, height, fill = C.white, line = null, radius = false }) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left, top, width, height },
    fill,
    line: line ? { fill: line, width: 1 } : { fill: { type: "none" } },
  });
}

export function addCircle(slide, { left, top, size, fill = C.teal, line = null }) {
  return slide.shapes.add({
    geometry: "ellipse",
    position: { left, top, width: size, height: size },
    fill,
    line: line ? { fill: line, width: 1 } : { fill: { type: "none" } },
  });
}

export function addText(slide, text, opts) {
  const {
    left, top, width, height,
    size = 18,
    color = C.ink,
    bold = false,
    italic = false,
    align = "left",
    valign = "top",
    fill = { type: "none" },
    line = null,
  } = opts;
  const shape = slide.shapes.add({
    geometry: "rect",
    position: { left, top, width, height },
    fill,
    line: line ? { fill: line, width: 1 } : { fill: { type: "none" } },
  });
  shape.text.set(String(text ?? ""));
  shape.text.fontSize = size;
  shape.text.color = color;
  shape.text.bold = bold;
  shape.text.italic = italic;
  shape.text.alignment = align;
  shape.text.verticalAlignment = valign;
  return shape;
}

export function addRule(slide, x, y, w, color = C.copper, h = 2) {
  addRect(slide, { left: x, top: y, width: w, height: h, fill: color });
}

export function addKicker(slide, text, x = 72, y = 44, color = C.copper) {
  addRect(slide, { left: x, top: y + 8, width: 42, height: 3, fill: color });
  addText(slide, text.toUpperCase(), {
    left: x + 56, top: y, width: 780, height: 20, size: 12.5, color: C.gray700, bold: true, valign: "middle",
  });
}

export function addTitle(slide, kicker, title, subtitle, page) {
  addKicker(slide, kicker);
  addText(slide, title, { left: 72, top: 74, width: 1220, height: 78, size: 36, color: C.ink, bold: true });
  if (subtitle) {
    addText(slide, subtitle, { left: 74, top: 162, width: 1030, height: 38, size: 16, color: C.gray700 });
  }
  addText(slide, String(page).padStart(2, "0"), { left: 1475, top: 48, width: 54, height: 26, size: 14, color: C.gray700, align: "right" });
}

export function addFooter(slide, page, note = "Fonte: CVM open data, FNET/documentos locais e saídas do estudo FIDC geradas em 09/06/2026. Valores em R$ nominais.") {
  addRule(slide, 72, 842, 1450, C.gray300, 1.2);
  addText(slide, note, { left: 72, top: 854, width: 1220, height: 26, size: 10.8, color: C.gray700 });
  addText(slide, `FIDC Market Diagnostic | ${String(page).padStart(2, "0")}`, { left: 1315, top: 854, width: 205, height: 22, size: 10.8, color: C.gray700, align: "right" });
}

export function metric(slide, value, label, detail, x, y, w, opts = {}) {
  const { fill = C.white, accent = C.copper, dark = false } = opts;
  addRect(slide, { left: x, top: y, width: w, height: 116, fill, line: dark ? C.ink2 : C.gray200, radius: true });
  addRule(slide, x + 18, y + 18, 44, accent, 4);
  addText(slide, value, { left: x + 18, top: y + 28, width: w - 36, height: 38, size: 28, bold: true, color: dark ? C.white : C.ink });
  addText(slide, label, { left: x + 18, top: y + 68, width: w - 36, height: 18, size: 13.6, bold: true, color: dark ? C.paper : C.ink });
  addText(slide, detail, { left: x + 18, top: y + 90, width: w - 36, height: 14, size: 9.4, color: dark ? C.gray300 : C.gray700 });
}

export function miniMetric(slide, value, label, x, y, w, color = C.ink) {
  addText(slide, value, { left: x, top: y, width: w, height: 34, size: 27, bold: true, color });
  addText(slide, label, { left: x, top: y + 36, width: w, height: 26, size: 12.4, color: C.gray700 });
}

export function table(slide, { x, y, colWidths, rowHeight = 42, headerHeight = 36, headers, rows, fontSize = 12, headerFontSize = 12, fills = {}, totalRows = [] }) {
  let cx = x;
  for (let i = 0; i < headers.length; i += 1) {
    addRect(slide, { left: cx, top: y, width: colWidths[i], height: headerHeight, fill: C.ink, line: C.white });
    addText(slide, headers[i], { left: cx + 8, top: y + 4, width: colWidths[i] - 16, height: headerHeight - 8, size: headerFontSize, color: C.white, bold: true, valign: "middle" });
    cx += colWidths[i];
  }
  rows.forEach((row, r) => {
    const top = y + headerHeight + r * rowHeight;
    const isTotal = totalRows.includes(r);
    cx = x;
    for (let c = 0; c < headers.length; c += 1) {
      const key = `${r}:${c}`;
      const fill = fills[key] || (isTotal ? C.ink : (r % 2 === 0 ? C.white : "#F2EDE3"));
      addRect(slide, { left: cx, top, width: colWidths[c], height: rowHeight, fill, line: C.white });
      addText(slide, row[c] ?? "", {
        left: cx + 8, top: top + 3, width: colWidths[c] - 16, height: rowHeight - 6,
        size: fontSize, color: isTotal ? C.white : C.ink, bold: isTotal || c === 0, valign: "middle",
      });
      cx += colWidths[c];
    }
  });
}

export function bulletList(slide, bullets, x, y, w, opts = {}) {
  const { size = 15, gap = 40, color = C.ink, bulletColor = C.copper } = opts;
  bullets.forEach((b, i) => {
    const yy = y + i * gap;
    addCircle(slide, { left: x, top: yy + 8, size: 7, fill: bulletColor });
    addText(slide, b, { left: x + 20, top: yy, width: w - 20, height: Math.max(24, gap - 7), size, color });
  });
}

export function horizontalBars(slide, data, { x, y, w, rowH = 42, labelW = 250, valueKey, labelKey = "label", max = null, color = C.copper, valueFmt = fmtBn, footKey = null }) {
  const m = max ?? Math.max(1, ...data.map((d) => Number(d[valueKey] || 0)));
  data.forEach((d, i) => {
    const yy = y + i * rowH;
    const val = Number(d[valueKey] || 0);
    const barW = Math.max(3, (w - labelW - 86) * val / m);
    addText(slide, truncate(d[labelKey], 38), { left: x, top: yy - 2, width: labelW, height: rowH - 4, size: 12.5, bold: i < 3, color: C.ink, valign: "middle" });
    addRect(slide, { left: x + labelW, top: yy + 8, width: w - labelW - 86, height: 18, fill: C.gray200 });
    addRect(slide, { left: x + labelW, top: yy + 8, width: barW, height: 18, fill: color });
    addText(slide, valueFmt(val), { left: x + labelW + w - labelW - 76, top: yy + 1, width: 76, height: 28, size: 11.5, bold: true, color: C.ink, align: "right", valign: "middle" });
    if (footKey && d[footKey]) {
      addText(slide, String(d[footKey]), { left: x + labelW, top: yy + 27, width: w - labelW - 102, height: 14, size: 9.2, color: C.gray700 });
    }
  });
}

export function verticalGroupedBars(slide, periods, { x, y, w, h }) {
  const max = Math.max(...periods.flatMap((p) => [p.closed_bn, p.valid_open_bn]));
  const groupW = w / periods.length;
  addRule(slide, x, y + h, w, C.gray300, 1.2);
  periods.forEach((p, i) => {
    const gx = x + i * groupW + 28;
    const barW = 58;
    const closedH = h * p.closed_bn / max;
    const openH = h * p.valid_open_bn / max;
    addRect(slide, { left: gx, top: y + h - openH, width: barW, height: openH, fill: C.blue });
    addRect(slide, { left: gx + 74, top: y + h - closedH, width: barW, height: closedH, fill: C.copper });
    addText(slide, fmtBn(p.valid_open_bn), { left: gx - 42, top: y + h - openH - 26, width: 96, height: 20, size: 10.5, color: C.blue, bold: true, align: "center" });
    addText(slide, fmtBn(p.closed_bn), { left: gx + 58, top: y + h - closedH - 26, width: 104, height: 20, size: 10.5, color: C.copper, bold: true, align: "center" });
    addText(slide, p.period, { left: gx - 2, top: y + h + 12, width: 140, height: 24, size: 13, bold: true, color: C.ink, align: "center" });
    addText(slide, `${fmtInt(p.closed_rows)} encerradas`, { left: gx - 5, top: y + h + 36, width: 146, height: 18, size: 10.5, color: C.gray700, align: "center" });
  });
  addRect(slide, { left: x + w - 236, top: y - 48, width: 12, height: 12, fill: C.blue });
  addText(slide, "válidas ou abertas", { left: x + w - 218, top: y - 54, width: 118, height: 24, size: 11.5, color: C.gray700, valign: "middle" });
  addRect(slide, { left: x + w - 92, top: y - 48, width: 12, height: 12, fill: C.copper });
  addText(slide, "encerradas", { left: x + w - 74, top: y - 54, width: 90, height: 24, size: 11.5, color: C.gray700, valign: "middle" });
}

export function stackedBornBars(slide, data, { x, y, w, rowH = 78 }) {
  const periods = [...new Set(data.map((d) => d.period))];
  periods.forEach((period, i) => {
    const rows = data.filter((d) => d.period === period);
    const legacy = rows.find((d) => d.group.startsWith("Legado")) || {};
    const born = rows.find((d) => d.group.startsWith("Nascidos")) || {};
    const total = Number(legacy.volume_closed_bn || 0) + Number(born.volume_closed_bn || 0);
    const yy = y + i * rowH;
    addText(slide, period, { left: x, top: yy + 8, width: 100, height: 24, size: 16, bold: true });
    addRect(slide, { left: x + 112, top: yy + 9, width: w - 260, height: 30, fill: C.gray200 });
    const bornW = total ? (w - 260) * Number(born.volume_closed_bn || 0) / total : 0;
    const legacyW = Math.max(0, w - 260 - bornW);
    addRect(slide, { left: x + 112, top: yy + 9, width: legacyW, height: 30, fill: C.gray500 });
    addRect(slide, { left: x + 112 + legacyW, top: yy + 9, width: bornW, height: 30, fill: C.copper });
    addText(slide, fmtBn(total), { left: x + w - 138, top: yy + 4, width: 120, height: 30, size: 13, bold: true, align: "right" });
    addText(slide, `nascidos: ${fmtPct(born.share_closed_pct)} | ${fmtBn(born.volume_closed_bn)} | ${fmtInt(born.issuers)} emissores`, {
      left: x + 112, top: yy + 43, width: w - 120, height: 24, size: 12, color: C.gray700,
    });
  });
}

export function heatmap(slide, rows, features, { x, y, w, h }) {
  const labelW = 360;
  const fundW = 54;
  const colW = (w - labelW - fundW) / features.length;
  addText(slide, "Subtipo", { left: x, top: y, width: labelW, height: 26, size: 11.5, bold: true, color: C.gray700 });
  addText(slide, "n", { left: x + labelW, top: y, width: fundW, height: 26, size: 11.5, bold: true, color: C.gray700, align: "center" });
  features.forEach((f, i) => {
    addText(slide, f, { left: x + labelW + fundW + i * colW, top: y - 2, width: colW - 6, height: 28, size: 9.5, bold: true, color: C.gray700, align: "center", valign: "middle" });
  });
  rows.forEach((row, r) => {
    const yy = y + 34 + r * h;
    addRect(slide, { left: x, top: yy, width: labelW + fundW + features.length * colW, height: h - 2, fill: r % 2 ? C.white : "#F1EADF" });
    addText(slide, truncate(row.label, 43), { left: x + 8, top: yy + 10, width: labelW - 12, height: 20, size: 9.7, bold: true, valign: "middle" });
    addText(slide, String(row.funds), { left: x + labelW, top: yy + 10, width: fundW, height: 20, size: 9.7, bold: true, align: "center", valign: "middle" });
    features.forEach((f, i) => {
      const v = row.values[f] ?? 0;
      let fill = C.gray200;
      if (v >= 80) fill = C.green;
      else if (v >= 60) fill = C.teal;
      else if (v >= 35) fill = C.copper2;
      else if (v > 0) fill = "#DEC7AA";
      addRect(slide, { left: x + labelW + fundW + i * colW + 5, top: yy + 8, width: colW - 10, height: h - 20, fill });
      addText(slide, fmtPct(v), { left: x + labelW + fundW + i * colW + 5, top: yy + 10, width: colW - 10, height: 20, size: 8.8, color: v >= 60 ? C.white : C.ink, bold: v >= 60, align: "center", valign: "middle" });
    });
  });
}

export function pricingBarDot(slide, rows, { x, y, w, rowH = 45 }) {
  const labelW = 350;
  const barW = 490;
  const dotW = 245;
  const maxVol = Math.max(...rows.map((r) => Number(r.volume_bn || 0)), 1);
  const maxSpread = Math.max(...rows.map((r) => Number(r.spread_cdi_pct || 0)), 6);
  addText(slide, "Setor / cota", { left: x, top: y - 30, width: labelW, height: 24, size: 11.5, bold: true, color: C.gray700 });
  addText(slide, "Volume", { left: x + labelW, top: y - 30, width: barW, height: 24, size: 11.5, bold: true, color: C.gray700 });
  addText(slide, "CDI+x% a.a. mediano", { left: x + labelW + barW + 35, top: y - 30, width: dotW, height: 24, size: 11.5, bold: true, color: C.gray700 });
  rows.forEach((r, i) => {
    const yy = y + i * rowH;
    addText(slide, truncate(`${r.sector} | ${r.quota}`, 38), { left: x, top: yy, width: labelW, height: 28, size: 11.7, bold: i < 3, valign: "middle" });
    addRect(slide, { left: x + labelW, top: yy + 7, width: barW, height: 18, fill: C.gray200 });
    const bw = Math.max(3, barW * Number(r.volume_bn || 0) / maxVol);
    addRect(slide, { left: x + labelW, top: yy + 7, width: bw, height: 18, fill: r.quota === "Sênior" ? C.copper : r.quota === "Mezanino" ? C.blue : C.copper2 });
    addText(slide, fmtBn(r.volume_bn), { left: x + labelW + barW + 8, top: yy + 1, width: 86, height: 26, size: 10.8, bold: true, color: C.ink, align: "right", valign: "middle" });
    addRect(slide, { left: x + labelW + barW + 118, top: yy + 15, width: dotW, height: 2, fill: C.gray300 });
    if (r.spread_cdi_pct !== null && r.spread_cdi_pct !== undefined) {
      const dx = x + labelW + barW + 118 + dotW * Math.min(maxSpread, Number(r.spread_cdi_pct)) / maxSpread;
      addCircle(slide, { left: dx - 7, top: yy + 8, size: 14, fill: C.teal, line: C.white });
      addText(slide, fmtPct(r.spread_cdi_pct), { left: dx + 9, top: yy + 2, width: 62, height: 24, size: 10.5, bold: true, color: C.teal });
    } else {
      addText(slide, "s/d", { left: x + labelW + barW + 118 + dotW - 40, top: yy + 1, width: 40, height: 24, size: 10.5, color: C.gray700, align: "right" });
    }
    addText(slide, `${fmtPct(r.spread_coverage_pct)} linhas c/ spread`, { left: x + labelW + barW + 290, top: yy + 27, width: 185, height: 18, size: 9.1, color: C.gray700, align: "right" });
  });
}

export function slideBase(p, dark = false) {
  const slide = p.slides.add({ width: W, height: H });
  slide.background.fill = dark ? C.ink : C.paper;
  return slide;
}

export async function addSlideByNumber(n, p, ctx) {
  const data = await loadData(ctx);
  switch (n) {
    case 1: return slide01(p, data);
    case 2: return slide02(p, data);
    case 3: return slide03(p, data);
    case 4: return slide04(p, data);
    case 5: return slide05(p, data);
    case 6: return slide06(p, data);
    case 7: return slide07(p, data);
    case 8: return slide08(p, data);
    case 9: return slide09(p, data);
    case 10: return slide10(p, data);
    case 11: return slide11(p, data);
    case 12: return slide12(p, data);
    default: throw new Error(`Unknown slide ${n}`);
  }
}

function slide01(p, data) {
  const s = slideBase(p, true);
  addKicker(s, "Diagnóstico IA | FIDCs Brasil", 82, 58, C.copper2);
  addText(s, "O mercado de FIDCs desde Jan-2024 já pode ser explicado por dados, documentos e revisão manual dirigida.", {
    left: 82, top: 120, width: 920, height: 172, size: 44, bold: true, color: C.white,
  });
  addText(s, "Estudo executivo para diretoria | 2024FY, 2025FY, 2026YTD", {
    left: 86, top: 314, width: 860, height: 36, size: 18, color: C.gray300,
  });
  addRule(s, 84, 394, 760, C.copper2, 4);
  addText(s, "Tese", { left: 84, top: 432, width: 120, height: 28, size: 17, bold: true, color: C.copper2 });
  addText(s, "O volume agregado mostra o tamanho do mercado; a leitura de regulamentos mostra o que é comum em cada subtipo. O trabalho de um mês deve transformar a triagem em playbooks defensáveis por setor.", {
    left: 84, top: 468, width: 780, height: 92, size: 19, color: C.paper,
  });
  const sum = data.summary;
  metric(s, fmtInt(sum.offer_rows), "linhas de ofertas CVM", "universo 2024FY-2026YTD", 1050, 112, 390, { fill: C.ink2, accent: C.copper2, dark: true });
  metric(s, fmtInt(sum.feature_matrix_count), "regulamentos lidos", `${fmtInt(sum.regulation_pdf_count)} PDFs regulatórios`, 1050, 252, 390, { fill: C.ink2, accent: C.teal, dark: true });
  metric(s, fmtInt(sum.pricing_rows_in_period), "linhas de tranche no período", `${fmtInt(sum.pricing_cdi_rows)} com CDI+ extraído`, 1050, 392, 390, { fill: C.ink2, accent: C.blue, dark: true });
  metric(s, fmtInt(sum.cedentes_sacados_candidate_rows), "candidatos cedente/sacado", "extração textual para QA manual", 1050, 532, 390, { fill: C.ink2, accent: C.green, dark: true });
  addText(s, "Gerado em 09/06/2026 com dados CVM/FNET e documentos locais. Sem uso de métricas inventadas.", {
    left: 84, top: 792, width: 900, height: 28, size: 12.5, color: C.gray300,
  });
  addText(s, "01", { left: 1475, top: 792, width: 50, height: 28, size: 12.5, color: C.gray300, align: "right" });
  return s;
}

function slide02(p, data) {
  const s = slideBase(p);
  addTitle(s, "Market Size", "FIDC segue acima de R$100 bi/ano; 2026YTD ainda tem grande estoque em aberto.", "Volume registrado válido/aberto e volume encerrado conservador por período.", 2);
  verticalGroupedBars(s, data.market, { x: 125, y: 278, w: 820, h: 410 });
  addText(s, "Leitura", { left: 1015, top: 250, width: 140, height: 26, size: 17, bold: true, color: C.copper });
  bulletList(s, [
    `2024FY fechou em ${fmtBn(data.market[0].closed_bn)} encerrados, com ${fmtInt(data.market[0].closed_issuers)} emissores.`,
    `2025FY foi maior em volume encerrado: ${fmtBn(data.market[1].closed_bn)}.`,
    `2026YTD tem ${fmtBn(data.market[2].valid_open_bn)} válido/aberto, mas só ${fmtBn(data.market[2].closed_bn)} encerrado até 09/06/2026.`,
    "Para diretoria: separar pipeline aberto de emissão efetivamente encerrada evita superestimar o mercado de 2026."
  ], 1015, 292, 420, { size: 15.5, gap: 58 });
  metric(s, fmtBn(data.market.reduce((a, b) => a + b.closed_bn, 0)), "encerrado conservador 2024-2026YTD", "soma dos três períodos", 1015, 592, 420, { accent: C.copper });
  addFooter(s, 2);
  return s;
}

function slide03(p, data) {
  const s = slideBase(p);
  addTitle(s, "CVM-born", "Fundos nascidos desde Jan-2024 já explicam a maior parte do volume recente.", "Split de volume encerrado conservador entre emissores nascidos desde Jan-2024 e legado/recadastrado.", 3);
  stackedBornBars(s, data.born, { x: 110, y: 290, w: 970 });
  addRect(s, { left: 110, top: 236, width: 14, height: 14, fill: C.gray500 });
  addText(s, "legado/recadastrado", { left: 132, top: 229, width: 190, height: 25, size: 12, color: C.gray700, valign: "middle" });
  addRect(s, { left: 330, top: 236, width: 14, height: 14, fill: C.copper });
  addText(s, "nascidos desde Jan-24", { left: 352, top: 229, width: 210, height: 25, size: 12, color: C.gray700, valign: "middle" });
  const born2025 = data.born.find((d) => d.period === "2025FY" && d.group.startsWith("Nascidos"));
  const born2026 = data.born.find((d) => d.period === "2026YTD" && d.group.startsWith("Nascidos"));
  addText(s, "Implicação", { left: 1135, top: 248, width: 180, height: 28, size: 18, bold: true, color: C.copper });
  metric(s, fmtPct(born2025.share_closed_pct), "share 2025FY", `${fmtBn(born2025.volume_closed_bn)} encerrados`, 1135, 292, 325, { accent: C.copper });
  metric(s, fmtPct(born2026.share_closed_pct), "share 2026YTD", `${fmtBn(born2026.volume_closed_bn)} encerrados`, 1135, 432, 325, { accent: C.teal });
  addText(s, "A pergunta para o estudo deixa de ser “quem emitiu mais?” e passa a ser “quais arquiteturas novas viraram padrão por tipo de FIDC?”.", {
    left: 1135, top: 592, width: 330, height: 92, size: 17, bold: true, color: C.ink,
  });
  addFooter(s, 3);
  return s;
}

function slide04(p, data) {
  const s = slideBase(p);
  addTitle(s, "Document Engine", "A cobertura documental já transforma revisão manual em fila dirigida.", "Downloads FNET/local + extração de PDFs + matriz regulatória por CNPJ.", 4);
  const sum = data.summary;
  const steps = [
    [`${fmtInt(sum.local_document_cnpj_count)} CNPJs`, "com documentos locais/FNET"],
    [`${fmtInt(sum.local_pdf_count)} PDFs`, "inventário documental"],
    [`${fmtInt(sum.regulation_pdf_count)} regulamentos`, "base para leitura jurídica"],
    [`${fmtInt(sum.feature_matrix_count)} matrizes`, "tem/não tem por fundo"],
  ];
  steps.forEach((st, i) => {
    const x = 95 + i * 355;
    addRect(s, { left: x, top: 266, width: 280, height: 136, fill: i % 2 ? C.white : "#F1EADF", line: C.gray200, radius: true });
    addText(s, st[0], { left: x + 22, top: 292, width: 230, height: 38, size: 28, bold: true, color: i === 2 ? C.teal : C.copper });
    addText(s, st[1], { left: x + 22, top: 344, width: 228, height: 42, size: 15, color: C.gray700 });
    if (i < steps.length - 1) addText(s, "→", { left: x + 295, top: 310, width: 45, height: 46, size: 34, bold: true, color: C.gray500, align: "center" });
  });
  addRect(s, { left: 105, top: 500, width: 620, height: 190, fill: C.white, line: C.gray200, radius: true });
  addText(s, "Status FNET da onda expandida", { left: 130, top: 526, width: 360, height: 28, size: 18, bold: true });
  metric(s, fmtInt(data.download_status.ok || 0), "ok", "downloads completos", 130, 570, 150, { accent: C.green });
  metric(s, fmtInt(data.download_status.parcial || 0), "parcial", "registrado para QA", 300, 570, 150, { accent: C.red });
  addText(s, "Único parcial: VSI 123QRED, 17 de 18 documentos selecionados baixados.", { left: 468, top: 586, width: 240, height: 60, size: 13.4, color: C.gray700 });
  addRect(s, { left: 760, top: 500, width: 525, height: 212, fill: C.white, line: C.gray200, radius: true });
  addText(s, "Resultado prático", { left: 785, top: 526, width: 250, height: 28, size: 18, bold: true });
  bulletList(s, [
    "A fila manual passa a priorizar baixa cobertura, alto volume e classificação fraca.",
    "A matriz permite comparar práticas por subtipo sem ponderar só pelo maior fundo.",
    "A base de texto fica cacheada para refinamento de regras."
  ], 785, 572, 460, { size: 14.2, gap: 43, bulletColor: C.teal });
  addFooter(s, 4);
  return s;
}

function slide05(p, data) {
  const s = slideBase(p);
  addTitle(s, "Taxonomia", "A classificação inicial já separa mercados, mas a cauda sem classe vira a fila de revisão.", "Quantidade de fundos com regulamento lido por subtipo; leitura equal-weight.", 5);
  const bars = data.sector_counts.slice(0, 11).map((r) => ({
    label: `${r.sector} | ${r.subsector}`,
    funds: r.funds,
    foot: `mediana feature hit ${fmtPct(r.feature_median)}`
  }));
  horizontalBars(s, bars, { x: 95, y: 248, w: 930, rowH: 51, labelW: 390, valueKey: "funds", valueFmt: fmtInt, color: C.blue, footKey: "foot" });
  addRect(s, { left: 1095, top: 248, width: 375, height: 330, fill: C.white, line: C.gray200, radius: true });
  addText(s, "O que já aparece", { left: 1120, top: 275, width: 300, height: 30, size: 19, bold: true, color: C.copper });
  bulletList(s, [
    "Crédito PF e PJ dominam a cobertura por número de fundos.",
    "Agro e risco sacado já têm massa suficiente para playbooks próprios.",
    "Meios de pagamento/cartões tem alta frequência de subordinação e rating.",
    "Não classificados continuam relevantes e devem ser tratados como revisão, não como setor."
  ], 1120, 322, 320, { size: 14.2, gap: 54 });
  metric(s, "109", "fundos não classificados", "regulamento lido, setor pendente", 1095, 616, 375, { accent: C.red });
  addFooter(s, 5);
  return s;
}

function slide06(p, data) {
  const s = slideBase(p);
  addTitle(s, "Práticas por subtipo", "O que é comum muda bastante por tipo de FIDC; a leitura equal-weight evita distorção por grandes emissões.", "Frequência de cláusulas/práticas detectadas em regulamentos por subtipo.", 6);
  heatmap(s, data.heatmap.slice(0, 8), data.heatmap_features, { x: 70, y: 248, w: 1490, h: 44 });
  addText(s, "Como ler: cada célula é % de fundos do subtipo com evidência textual da prática no regulamento. Não é ponderado por volume.", {
    left: 78, top: 760, width: 960, height: 32, size: 13, color: C.gray700, italic: true,
  });
  addRect(s, { left: 1110, top: 736, width: 18, height: 18, fill: C.green });
  addText(s, ">=80%", { left: 1135, top: 732, width: 70, height: 24, size: 11.5, color: C.gray700, valign: "middle" });
  addRect(s, { left: 1210, top: 736, width: 18, height: 18, fill: C.teal });
  addText(s, "60-79%", { left: 1235, top: 732, width: 80, height: 24, size: 11.5, color: C.gray700, valign: "middle" });
  addRect(s, { left: 1325, top: 736, width: 18, height: 18, fill: C.copper2 });
  addText(s, "35-59%", { left: 1350, top: 732, width: 80, height: 24, size: 11.5, color: C.gray700, valign: "middle" });
  addFooter(s, 6);
  return s;
}

function slide07(p, data) {
  const s = slideBase(p);
  addTitle(s, "Subordinação", "Subordinação é prática recorrente, mas o número exato ainda exige QA jurídico.", "O slide separa detecção de cláusula da extração numérica do percentual.", 7);
  const shareRows = data.sector_counts
    .filter((r) => r.subord_share !== null)
    .slice(0, 10)
    .map((r) => ({ label: `${r.sector} | ${r.subsector}`, share: r.subord_share, foot: `${r.funds} fundos` }));
  addText(s, "Frequência de cláusula de subordinação", { left: 88, top: 220, width: 560, height: 28, size: 18, bold: true });
  horizontalBars(s, shareRows, { x: 88, y: 270, w: 690, rowH: 44, labelW: 360, valueKey: "share", valueFmt: fmtPct, color: C.teal, footKey: "foot", max: 100 });
  addText(s, "Percentuais numéricos extraídos", { left: 842, top: 220, width: 520, height: 28, size: 18, bold: true });
  const rows = data.subordination.slice(0, 7).map((r) => [truncate(r.label, 38), fmtInt(r.funds_numeric), fmtPct(r.median_pct), `${fmtPct(r.p25_pct)}-${fmtPct(r.p75_pct)}`, truncate(r.common, 34)]);
  table(s, {
    x: 842, y: 270,
    colWidths: [290, 45, 82, 104, 170],
    headers: ["Subtipo", "n", "mediana", "p25-p75", "valores comuns"],
    rows,
    rowHeight: 48,
    fontSize: 10.4,
    headerFontSize: 10.6,
  });
  addRect(s, { left: 842, top: 680, width: 718, height: 88, fill: "#F1EADF", line: C.gray200, radius: true });
  addText(s, "Nota de governança", { left: 864, top: 700, width: 170, height: 24, size: 15, bold: true, color: C.red });
  addText(s, "A extração textual pega muitos regulamentos que dizem haver subordinação, mas o percentual pode aparecer em anexos, suplementos ou fórmulas. Para memo final, revisar manualmente os subtipos com maior materialidade.", {
    left: 1036, top: 696, width: 500, height: 54, size: 12.8, color: C.gray700,
  });
  addFooter(s, 7);
  return s;
}

function slide08(p, data) {
  const s = slideBase(p);
  addTitle(s, "Pricing", "O gráfico barra+ponto já é possível, mas o CDI+ tem cobertura desigual.", "Barras mostram volume por setor/cota; pontos mostram spread CDI+x% mediano quando extraído.", 8);
  pricingBarDot(s, data.pricing_top.slice(0, 10), { x: 72, y: 245, w: 1430, rowH: 47 });
  addRect(s, { left: 1020, top: 724, width: 482, height: 92, fill: C.white, line: C.gray200, radius: true });
  addText(s, "Uso recomendado", { left: 1042, top: 740, width: 180, height: 22, size: 14.5, bold: true, color: C.copper });
  addText(s, "Usar este slide para discussão de hipóteses. Antes do comitê, deduplicar anúncios/atas/suplementos e conferir CDI+ nos termos finais.", {
    left: 1042, top: 768, width: 430, height: 38, size: 11.5, color: C.gray700,
  });
  addFooter(s, 8);
  return s;
}

function slide09(p, data) {
  const s = slideBase(p);
  addTitle(s, "Prestadores", "O ecossistema tem líderes por papel; não basta olhar o ranking agregado.", "Ranking agregado por volume mapeado em ofertas/CVM, separado por função.", 9);
  const roles = data.participants_global.slice(0, 4);
  roles.forEach((role, i) => {
    const x = 78 + i * 375;
    addRect(s, { left: x, top: 236, width: 335, height: 438, fill: C.white, line: C.gray200, radius: true });
    addText(s, role.role, { left: x + 18, top: 258, width: 300, height: 28, size: 16.5, bold: true, color: i % 2 ? C.teal : C.copper });
    role.leaders.slice(0, 5).forEach((leader, j) => {
      const yy = 310 + j * 70;
      addText(s, `${j + 1}. ${truncate(leader.name, 34)}`, { left: x + 18, top: yy, width: 290, height: 24, size: 12.5, bold: j === 0 });
      addText(s, `${fmtBn(leader.volume_bn)} | ${fmtInt(leader.cnpjs)} CNPJs`, { left: x + 34, top: yy + 26, width: 260, height: 20, size: 10.8, color: C.gray700 });
    });
  });
  addRect(s, { left: 90, top: 716, width: 1410, height: 62, fill: "#F1EADF", line: C.gray200, radius: true });
  addText(s, "Diretor deve pedir duas visões complementares: concentração por volume e presença por número de CNPJs. Gestores/administradores muito fortes em um subtipo podem não ser os mesmos em outro.", {
    left: 116, top: 734, width: 1340, height: 32, size: 15, color: C.ink, bold: true,
  });
  addFooter(s, 9);
  return s;
}

function slide10(p, data) {
  const s = slideBase(p);
  addTitle(s, "Cedentes e sacados", "A IA já reduz a lista de leitura, mas os nomes ainda são candidatos.", "Extração de contexto textual em regulamentos: cedentes, originadores, sacados, devedores e consultoras.", 10);
  const counts = data.cedente_sacado_counts;
  metric(s, fmtInt(counts.cedente_originador || 0), "cedente/originador", "candidatos textuais", 96, 250, 300, { accent: C.copper });
  metric(s, fmtInt(counts.sacado_devedor || 0), "sacado/devedor", "candidatos textuais", 430, 250, 300, { accent: C.teal });
  metric(s, fmtInt(counts.consultora || 0), "consultora", "candidatos textuais", 764, 250, 300, { accent: C.blue });
  metric(s, fmtInt(counts.indeterminado || 0), "indeterminado", "contexto exige QA", 1098, 250, 300, { accent: C.red });
  const rows = data.cedente_sacado_by_sector.slice(0, 8).map((r) => [truncate(r.setor_n1 || "sem setor", 28), r.participant_type, fmtInt(r.count)]);
  table(s, {
    x: 96, y: 442,
    colWidths: [300, 270, 110],
    headers: ["Setor", "Tipo extraído", "Linhas"],
    rows,
    rowHeight: 43,
    fontSize: 11.8,
  });
  addRect(s, { left: 820, top: 442, width: 580, height: 296, fill: C.white, line: C.gray200, radius: true });
  addText(s, "Quality gate obrigatório", { left: 850, top: 472, width: 310, height: 30, size: 20, bold: true, color: C.red });
  bulletList(s, [
    "Confirmar se o CNPJ é de cedente, sacado, consultora, prestador ou apenas parte relacionada.",
    "Separar devedor final de banco emissor/arranjo de pagamento quando o regulamento usa ambos.",
    "Criar dicionário de aliases para grupos econômicos antes de ranking final.",
    "Manter evidência textual por fundo no apêndice de revisão."
  ], 850, 524, 500, { size: 14.5, gap: 47, bulletColor: C.red });
  addFooter(s, 10);
  return s;
}

function slide11(p, data) {
  const s = slideBase(p);
  addTitle(s, "Review manual", "O mês de trabalho deve ser uma esteira de QA, não leitura linear de todos os PDFs.", "Fila manual enriquecida por volume, cobertura documental e classificação.", 11);
  const waves = [
    ["Onda 1", "Top volume + baixa confiança", "diretor-grade sizing e setores"],
    ["Onda 2", "Subtipos materiais", "Agro, PF, PJ, risco sacado, cartões"],
    ["Onda 3", "Pricing e duplicatas", "CDI+, cota, prazo, status de oferta"],
    ["Onda 4", "Cedentes/sacados", "ranking final e evidência textual"],
  ];
  waves.forEach((w, i) => {
    const x = 86 + i * 360;
    addRect(s, { left: x, top: 242, width: 300, height: 154, fill: i % 2 ? C.white : "#F1EADF", line: C.gray200, radius: true });
    addText(s, w[0], { left: x + 20, top: 266, width: 120, height: 26, size: 19, bold: true, color: C.copper });
    addText(s, w[1], { left: x + 20, top: 306, width: 250, height: 34, size: 14.5, bold: true });
    addText(s, w[2], { left: x + 20, top: 350, width: 250, height: 34, size: 12.5, color: C.gray700 });
    if (i < waves.length - 1) addText(s, "→", { left: x + 314, top: 292, width: 42, height: 40, size: 30, color: C.gray500, bold: true, align: "center" });
  });
  const topRows = data.review_top.slice(0, 7).map((r) => [truncate(r.fund, 42), r.sector || "s/class.", fmtBn(r.volume_bn), r.coverage === null ? "s/d" : fmtPct(r.coverage)]);
  table(s, {
    x: 90, y: 486,
    colWidths: [575, 165, 150, 120],
    headers: ["Primeiros alvos por volume", "Setor", "Volume", "Cobertura"],
    rows: topRows,
    rowHeight: 42,
    fontSize: 11.3,
  });
  addRect(s, { left: 1128, top: 486, width: 358, height: 294, fill: C.white, line: C.gray200, radius: true });
  addText(s, "Critérios de saída", { left: 1152, top: 512, width: 250, height: 28, size: 18, bold: true, color: C.teal });
  bulletList(s, [
    "Setor confirmado por regulamento.",
    "Tem/não tem revisado para cláusulas-chave.",
    "Subordinação numérica validada.",
    "Pricing deduplicado por emissão.",
    "Cedentes/sacados com evidência e alias."
  ], 1152, 560, 300, { size: 13.8, gap: 41, bulletColor: C.teal });
  addFooter(s, 11);
  return s;
}

function slide12(p, data) {
  const s = slideBase(p, true);
  addKicker(s, "Director Close", 82, 58, C.copper2);
  addText(s, "Decisão: transformar a triagem em playbooks de mercado por subtipo.", {
    left: 82, top: 112, width: 1050, height: 98, size: 42, bold: true, color: C.white,
  });
  addText(s, "O pacote atual prova que a IA consegue cobrir o mercado e organizar o trabalho duro. O próximo mês precisa priorizar QA, não volume bruto de PDFs.", {
    left: 86, top: 224, width: 980, height: 56, size: 19, color: C.paper,
  });
  const asks = [
    ["1", "Travar taxonomia", "Agro, Crédito PF, Crédito PJ, Cartões/Bancos emissores, Risco sacado, Imobiliário, Judicial/NPL."],
    ["2", "Deduplicar pricing", "Separar anúncio, ata, suplemento e termo final; padronizar CDI+, IPCA+, %CDI e tipo de cota."],
    ["3", "Validar práticas comuns", "Subordinação, reserva, triggers, elegibilidade, concentração, rating e derivativos por subtipo."],
    ["4", "Fechar ecossistema", "Administradores, custodiantes, gestores, coordenadores, cedentes e sacados por universo."],
  ];
  asks.forEach((a, i) => {
    const x = 92 + (i % 2) * 690;
    const y = 350 + Math.floor(i / 2) * 168;
    addRect(s, { left: x, top: y, width: 610, height: 126, fill: C.ink2, line: C.gray700, radius: true });
    addCircle(s, { left: x + 24, top: y + 26, size: 42, fill: i % 2 ? C.teal : C.copper });
    addText(s, a[0], { left: x + 24, top: y + 30, width: 42, height: 34, size: 20, bold: true, color: C.white, align: "center", valign: "middle" });
    addText(s, a[1], { left: x + 86, top: y + 26, width: 430, height: 28, size: 19, bold: true, color: C.white });
    addText(s, a[2], { left: x + 86, top: y + 62, width: 470, height: 48, size: 13.8, color: C.gray300 });
  });
  addRect(s, { left: 92, top: 728, width: 1292, height: 58, fill: "#24303A", line: C.gray700, radius: true });
  addText(s, "Limitação honesta: isto é triagem quantitativa/documental, não parecer jurídico final. O deck deve ser usado para aprovar o plano de revisão e a narrativa, não para fechar recomendações legais sem QA.", {
    left: 118, top: 744, width: 1220, height: 32, size: 14.8, color: C.paper, bold: true,
  });
  addText(s, "Fonte: CVM open data + FNET/documentos locais + outputs do estudo. Data-base 09/06/2026.", {
    left: 84, top: 836, width: 950, height: 24, size: 11.8, color: C.gray300,
  });
  addText(s, "12", { left: 1475, top: 836, width: 50, height: 24, size: 11.8, color: C.gray300, align: "right" });
  return s;
}
