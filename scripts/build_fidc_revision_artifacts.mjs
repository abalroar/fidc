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
const DATA_DIR = path.resolve(
  process.env.FIDC_DATA_DIR || path.join(ROOT, "data/industry_study"),
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
const OUTPUT_HTML = path.resolve(
  process.env.FIDC_OUTPUT_HTML ||
    path.join(OUTPUT_DIR, "provider_flows_explorer.html"),
);
const SKIP_QA = process.env.FIDC_SKIP_QA === "1";
const EXPORT_MANIFEST_PATH = path.resolve(
  process.env.FIDC_EXPORT_MANIFEST ||
    path.join(REVISION_DIR, "industry_export_bundle.json"),
);
const RENDERER_VERSION = "industry_revision_artifacts_v35";
const SLIDE_CONTRACT_V1 = Object.freeze([
  "cover", "industry_scale", "annual_issuance", "issuance_taxonomy", "analytical_taxonomy",
  "acquiring", "receivables", "provider_ranking", "top20", "top20_fomento",
  "top20_agro", "top20_financeiro", "top20_outros", "flagship_curation",
  "portfolio_1_curation", "portfolio_1_taxonomy", "offers_volume_ticket",
  "offers_ticket_distribution", "offers_placement_regime", "top15_current",
  "top15_history", "conclusions",
  "provider_history", "provider_attribution", "investor_base", "holder_distribution",
]);
const EXPECTED_SLIDES = SLIDE_CONTRACT_V1.length;
if (EXPECTED_SLIDES !== 26) {
  throw new Error(`Contrato ordinal deveria conter 26 slides; contém ${EXPECTED_SLIDES}.`);
}
const COVER_TITLE = "Indústria de FIDCs — jun/26";
const EDITORIAL_HEADER_COPY = Object.freeze([
  {
    eyebrow: "OFERTAS ENCERRADAS · CVM E ANBIMA",
    title: "FIDCs seguem ganhando escala nas emissões",
    subtitle: "Abertura por instrumento usa o valor encerrado ANBIMA; 2023 corrigido",
  },
  {
    eyebrow: "TAXONOMIA ANALÍTICA · OUTROS ABERTO",
    title: 'Abrir "Outros" revela que 63% do mercado é crédito financeiro',
    subtitle: "Financeiro somado aos componentes de Outros, jun/26",
  },
  {
    eyebrow: "TAXONOMIA CVM · RECLASSIFICAÇÃO DE ADQUIRÊNCIA",
    title: "Adquirência é R$ 99 bi que a taxonomia oficial não mostra",
    subtitle: "33 CNPJs reclassificados, 12,1% do PL",
  },
  {
    eyebrow: "CARTEIRA POR TIPO DE RECEBÍVEL",
    title: "Financeiro explicou 70% do crescimento da carteira",
    subtitle: "Ganho de 17,5 p.p. de participação no período",
  },
  {
    eyebrow: "RANKING · TOP FUNDOS E ORIGINADORES",
    titleStartsWith: "Fomento Mercantil",
    title: "Fomento Mercantil: crescimento marginal em seis meses",
    subtitle: "Top 15 vai de R$ 30,4 bi a R$ 31,9 bi",
  },
  {
    eyebrow: "RANKING · TOP FUNDOS E ORIGINADORES",
    titleStartsWith: "Agro, Indústria e Comércio",
    title: "Agro, Indústria e Comércio: o maior salto absoluto",
    subtitle: "Top 15 sobe R$ 18,2 bi, para R$ 112,2 bi",
  },
  {
    eyebrow: "RANKING · TOP FUNDOS E ORIGINADORES",
    titleStartsWith: "Financeiro",
    title: "Financeiro: o maior bloco, e ainda crescendo",
    subtitle: "Top 15 vai a R$ 121,1 bi",
  },
  {
    eyebrow: "RANKING · TOP FUNDOS E ORIGINADORES",
    titleStartsWith: "Outros",
    title: "Outros: o único bloco que encolheu",
    subtitle: "Top 15 recua de R$ 60,9 bi para R$ 55,1 bi",
  },
  {
    eyebrow: "CARTEIRA 1 · TAXONOMIA ANALÍTICA",
    title: "A carteira lida com o mesmo critério do mercado",
    subtitle: "R$ 55,3 bi de PL observado, composição reclassificada",
  },
  {
    eyebrow: "OFERTAS ENCERRADAS · VOLUME E TICKET",
    title: "Emissões crescem 15% no semestre",
    subtitle: "R$ 65,5 bi em 771 ofertas no jan–jun/26",
  },
  {
    eyebrow: "OFERTAS ENCERRADAS · DISTRIBUIÇÃO DO TICKET",
    title: "22 ofertas concentram 42% de todo o volume",
    subtitle: "Tickets acima de R$ 500 mi, jan–jun/26",
  },
  {
    eyebrow: "TOP 15 · OFERTAS ENCERRADAS",
    title: "IBBA esteve em 8 das 15 maiores ofertas do semestre",
    subtitle: "Liderou 5 delas",
  },
  {
    eyebrow: "PRINCIPAIS CONCLUSÕES",
    title: "O que muda a leitura do mercado",
    subtitle: "Distribuição, prestadores, migração e ofertas",
  },
  {
    eyebrow: "PRESTADORES · EVOLUÇÃO E RANKING",
    title: "QI lidera administração; BTG lidera gestão e custódia",
    subtitle: "Ranking geral de jun/26",
  },
  {
    eyebrow: "PRESTADORES · LIDERANÇA EXPLICADA",
    title: "A liderança some quando se olha o que a sustenta",
    subtitle: "Singulare explica a escala da QI; sem a coorte bancária, BTG cai para #3 em gestão",
  },
  {
    eyebrow: "BASE INVESTIDORA",
    title: "Quase todo o volume vai para o investidor profissional",
    subtitle: "Entre 93% e 97% ao ano; a classificação mede elegibilidade, não alocação efetiva",
  },
]);
const WORKBOOK_SHEETS_TO_REMOVE = [
  "Conflitos Tab IV",
  "Warnings",
  "Ofertas anual",
  "Posição Itaú",
  "Ranking ofertas",
  "Cedentes",
  "Investidores hist",
  "Tipos investidor",
  "_Listas",
  "Cross-check taxonomia",
  "Taxonomia por CNPJ",
  "Reclass. adquirência",
  "Auditoria numérica",
  "Reclass. ANBIMA",
  "Reclass. CVM",
  "Fluxos visuais",
];

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

const FLAGSHIP_TYPE_STYLES = Object.freeze({
  "Adquirência": { order: 1, fill: "#DCEAF7" },
  "Agro / revenda": { order: 2, fill: "#E3F0DF" },
  "Consignado INSS": { order: 3, fill: "#DDEEDB" },
  "Consignado FGTS": { order: 4, fill: "#F8E7BF" },
  "Consignado CLT": { order: 5, fill: "#E8E2F3" },
  "Consignado estadual": { order: 6, fill: "#F3E0E8" },
  "Veículos": { order: 7, fill: "#E1E9EF" },
  "Cartão consignado": { order: 8, fill: "#ECE2F1" },
  "Factoring": { order: 9, fill: "#F1E8D9" },
  "Crédito PJ": { order: 10, fill: "#DDEDEA" },
  "Financeiro": { order: 11, fill: "#E8ECEF" },
  "Outros": { order: 12, fill: "#F1F2F3" },
});

function flagshipVisualType(row) {
  const text = normalizeProviderName([
    row.categoria,
    row.familia_flagship,
    row.familia_flagship_referencia,
    row.tipo_exibicao,
    row.foco_exibicao,
  ].filter(Boolean).join(" "));
  if (text.includes("adquirencia")) return "Adquirência";
  if (text.includes("consignado inss")) return "Consignado INSS";
  if (text.includes("consignado fgts")) return "Consignado FGTS";
  if (text.includes("consignado clt")) return "Consignado CLT";
  if (text.includes("consignado estadual")) return "Consignado estadual";
  if (text.includes("veiculo") || text.includes("auto loan") || text.includes("creditas auto")) return "Veículos";
  if (text.includes("cartao consignado")) return "Cartão consignado";
  if (text.includes("factoring") || text.includes("fomento mercantil")) return "Factoring";
  if (text.includes("credito pj")) return "Crédito PJ";
  if (text.includes("agro") || text.includes("recebiveis comerciais") || text.includes("industria e comercio")) return "Agro / revenda";
  if (text.includes("financeiro")) return "Financeiro";
  return "Outros";
}

function flagshipTypeStyle(row) {
  const label = flagshipVisualType(row);
  return { label, ...FLAGSHIP_TYPE_STYLES[label] };
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

function tn(value, digits = 3) {
  return `R$ ${(num(value) / 1e12).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} tri`;
}

function bnRoundedLabel(value) {
  return `R$ ${Math.round(num(value) / 1e9).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} bi`;
}

function mm(value, digits = 0) {
  return `R$ ${(num(value) / 1e6).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} mi`;
}

function moneyScale(value) {
  return Math.abs(num(value)) < 1e9 ? mm(value, 1) : bn(value, 1);
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
  if (cut <= 0) return text;
  return sliced.slice(0, cut).trim();
}

function fundEditorialName(value, maxChars = 34) {
  const original = String(value || "").replace(/\s+/g, " ").trim();
  const compact = original
    .replace(/\bFUNDO DE INVESTI(?:MENTO|MNTO) EM DIREITOS CRED[IÍ]T[OÓ]RIOS\b/gi, " ")
    .replace(/\bDE RESPONSABILIDADE (?:LIMITADA|ILIMITADA)\b/gi, " ")
    .replace(/\bRESPONSABILIDADE (?:LIMITADA|ILIMITADA)\b/gi, " ")
    .replace(/\bRESP(?:ONSABILIDADE)?\.?\s+(?:LIMITADA|ILIMITADA|LTDA)\b/gi, " ")
    .replace(/\bDE CLASSE [UÚ]NICA FECHADA\b/gi, " ")
    .replace(/\s+-\s*$/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return truncateWords(compact || original, maxChars);
}

function cnpjDigits(value) {
  return String(value || "").replace(/\D/g, "").padStart(14, "0");
}

function formatCnpj(value) {
  const digits = cnpjDigits(value);
  return /^\d{14}$/.test(digits)
    ? digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5")
    : "N/D";
}

function auditField(value, maxChars = 34) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || /^N\/D(?:\b|\s|—|-)/i.test(text)) return "N/D";
  return truncateWords(text, maxChars) || "N/D";
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

function top15CoordinatorLabel(value) {
  const normalized = normalizeProviderName(value);
  if (normalized.includes("banco votorantim")) return "Votorantim";
  if (normalized.includes("banco itau bba")) return "Itaú BBA";
  return truncateWords(providerShort(value), 18) || "N/D";
}

function withoutTrailingPeriod(value) {
  return String(value || "").trim().replace(/[.]+$/g, "");
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

function editorialHeaderCopy(eyebrow, currentTitle) {
  return EDITORIAL_HEADER_COPY.find(
    (entry) =>
      entry.eyebrow === eyebrow &&
      (!entry.titleStartsWith || currentTitle.startsWith(entry.titleStartsWith)),
  );
}

function addHeader(slide, eyebrow, title, source, _page) {
  automaticPageNumber += 1;
  slide.background.fill = C.white;
  const editorialCopy = editorialHeaderCopy(eyebrow, title);
  if (editorialCopy) {
    const editorialTitleFont = editorialCopy.title.length > 72 ? 25 : 28;
    addText(
      slide,
      editorialCopy.title,
      { left: 60, top: 27, width: 1160, height: 43 },
      {
        fontSize: editorialTitleFont,
        bold: true,
        color: C.black,
        verticalAlignment: "middle",
        wrap: "none",
      },
    );
    addText(
      slide,
      editorialCopy.subtitle,
      { left: 60, top: 76, width: 1160, height: 25 },
      {
        fontSize: 14,
        color: C.mid,
        verticalAlignment: "middle",
        wrap: "none",
      },
    );
  } else {
    addText(
      slide,
      eyebrow.toUpperCase().replace(/\bFIDCS\b/g, "FIDCs"),
      { left: 60, top: 27, width: 1160, height: 20 },
      { fontSize: 12, bold: true, color: C.orange, wrap: "none" },
    );
    const titleFont = title.length > 105 ? 24 : title.length > 85 ? 26 : 28;
    addText(
      slide,
      title,
      { left: 60, top: 53, width: 1160, height: 49 },
      { fontSize: titleFont, bold: true, color: C.black, verticalAlignment: "middle", wrap: "none" },
    );
  }
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
      wrap: "none",
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

function addSourceNotes(slide, sources) {
  const lines = Array.isArray(sources) ? sources.filter(Boolean) : [String(sources || "")];
  slide.speakerNotes.textFrame.setText([
    "[Sources]",
    ...lines.map((source) => `- ${source}`),
    "[/Sources]",
  ].join("\n"));
  slide.speakerNotes.setVisible(true);
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
    headerHeight = 22,
    headerFill = C.black,
    rowHighlights = new Set(),
    emphasizeHighlightedRows = false,
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
    fill: headerFill,
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
  table.rows[0].height = headerHeight;
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
    if (emphasizeHighlightedRows && rowHighlights.has(rowIndex)) {
      const emphasis = table.cells.block({
        row: rowIndex + 1,
        column: 0,
        rowCount: 1,
        columnCount: Math.min(2, headers.length),
      });
      emphasis.textStyle.bold = true;
      emphasis.textStyle.color = C.orange;
    }
    table.rows[rowIndex + 1].height = (height - headerHeight) / Math.max(rows.length, 1);
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
  const chart = slide.charts.add("line", {
    ...chartBase(position),
    categories: [""],
    series: entries.map((entry) => ({
      name: truncateWords(entry.label, 48),
      values: [null],
      line: { style: "solid", fill: entry.color, width: 3 },
      marker: { symbol: "none" },
    })),
    hasLegend: true,
    legend: {
      position: "bottom",
      textStyle: { fill: C.mid, fontSize: 10.5 },
    },
    xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
    yAxis: { visible: false, majorGridlines: null, minorGridlines: null },
  });
  return chart;
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
  const visibleLabels = new Set(labelIndices);
  const nativeCategories = categories.map((label, index) => visibleLabels.has(index) ? label : "");
  const series = (options.series || []).map((item) => {
    return {
      ...item,
      values: (item.values || []).map((value) => (
        value === null || value === undefined || !Number.isFinite(Number(value)) ? null : Number(value)
      )),
      marker: { symbol: "none" },
    };
  });
  const chart = slide.charts.add("line", {
    ...chartBase(position),
    categories: nativeCategories,
    series,
    lineOptions: { grouping: "standard" },
    ...(options.displayBlanksAs ? { displayBlanksAs: options.displayBlanksAs } : {}),
    hasLegend: false,
    xAxis: {
      visible: true,
      tickLabelPosition: "low",
      textStyle: { fill: C.mid, fontSize: options.labelFontSize ?? 10 },
      line: { style: "solid", fill: C.line, width: 1 },
      majorGridlines: null,
      minorGridlines: null,
    },
    yAxis: options.yAxis,
  });
  return chart;
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function generateProviderFlowHtml() {
  if (!FLOW_BUILDER_PATH) {
    throw new Error(`Gerador dos fluxos não localizado: ${FLOW_BUILDER_NAME}`);
  }
  await fs.mkdir(path.dirname(OUTPUT_HTML), { recursive: true });
  const generated = spawnSync(
    process.execPath,
    [
      FLOW_BUILDER_PATH,
      "--payload",
      PAYLOAD_PATH,
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
  const stat = await fs.stat(OUTPUT_HTML);
  if (!stat.isFile() || stat.size === 0) {
    throw new Error(`Explorador HTML vazio ou inválido: ${OUTPUT_HTML}`);
  }
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
      top20_by_anbima_type: payload.top20_by_anbima_type.length,
      top20_taxonomy_review: payload.top20_taxonomy_review.length,
      top100_outros_review: payload.top100_outros_review.length,
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
  const source = `Fonte: CVM/ANBIMA, ${stockShortLower}. Subtipo = Tipo+Foco ANBIMA (cadastro dez/25, evidência e proxy determinístico da Tabela II). PL ex-FIC sem Sistema Petrobras/TAPSO; cobertura de classificação por Tipo+Foco (PL): ${coverage}; fora: ${outside}.`;
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
  if (itau && !selected.some((row) => row.participante === itau.participante)) {
    selected.splice(Math.max(0, limit - 1), 1, itau);
  }
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
    `Fonte: CVM e coorte bancária curada a partir dos conglomerados prudenciais do BCB. PL ex-FIC; Sistema Petrobras e TAPSO excluídos. Na gestão, o cenário retira ${integer(managementExcludedFunds)} FIDCs e ${bn(managementExcludedPl, 1)}.`,
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

function addCombinedProviderRankingSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const stockShort = competenceShortPt(payload.latest_complete);
  addHeader(
    slide,
    "PRESTADORES · EVOLUÇÃO E RANKING",
    `QI lidera administração; BTG lidera gestão e custódia no ranking geral de ${stockShort.toLowerCase()}`,
    "Fonte: CVM, Informe Mensal e cadastro de prestadores, jun/26. Exclui Sistema Petrobras e TAPSO. *Independentes: grupos sem controlador bancário na curadoria; Singulare consolidada em QI Tech e Kanastra no Itaú.",
    page,
  );
  addLegend(
    slide,
    [
      { label: "QI Tech", color: providerColor("QI Tech") },
      { label: "BTG Pactual", color: providerColor("BTG Pactual") },
      { label: "Oliveira Trust", color: providerColor("Oliveira Trust") },
      { label: "Itaú", color: providerColor("Itaú") },
      { label: "Genial", color: providerColor("Genial") },
      { label: "CBSF / REAG", color: providerColor("CBSF") },
      { label: "Demais", color: C.mid },
    ],
    { left: 160, top: 119, width: 960, height: 22 },
    7,
  );
  addText(
    slide,
    "TODOS OS PRESTADORES",
    { left: 60, top: 143, width: 555, height: 22 },
    {
      fontSize: 12.5,
      bold: true,
      color: C.charcoal,
      alignment: "center",
      verticalAlignment: "middle",
    },
  );
  addText(
    slide,
    "INDEPENDENTES*",
    { left: 665, top: 143, width: 555, height: 22 },
    {
      fontSize: 12.5,
      bold: true,
      color: C.charcoal,
      alignment: "center",
      verticalAlignment: "middle",
    },
  );

  const bands = [
    {
      role: "administrador",
      label: "ADMINISTRAÇÃO",
      top: 166,
    },
    {
      role: "gestor",
      label: "GESTÃO",
      top: 327,
    },
    {
      role: "custodiante",
      label: "CUSTÓDIA",
      top: 488,
    },
  ];

  const addProviderBars = ({ left, top, rows, label }) => {
    const chartRows = [...rows].reverse();
    addText(
      slide,
      label,
      { left, top, width: 555, height: 18 },
      {
        fontSize: 10.5,
        bold: true,
        color: C.note,
        verticalAlignment: "middle",
      },
    );
    slide.charts.add("bar", {
      ...chartBase({ left, top: top + 18, width: 555, height: 140 }),
      categories: chartRows.map((row) => providerShort(row.participante)),
      series: [
        {
          name: `PL ${stockShort.toLowerCase()}`,
          values: chartRows.map((row) => num(row.current?.pl_brl) / 1e9),
          valuesFormatCode: "0.0",
          fill: C.charcoal,
          points: chartRows.map((row, idx) => ({
            idx,
            fill: providerColor(row.participante),
          })),
        },
      ],
      barOptions: {
        direction: "bar",
        grouping: "clustered",
        gapWidth: 26,
      },
      hasLegend: false,
      xAxis: {
        visible: false,
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 10.1 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      dataLabels: {
        showValue: true,
        position: "inEnd",
        fill: "none",
        line: { style: "solid", fill: "none", width: 0 },
        textStyle: { fill: C.white, fontSize: 10.2, bold: false },
      },
    });
  };

  bands.forEach(({ role, label, top }) => {
    addProviderBars({
      left: 60,
      top,
      rows: providerHistoricalRows(payload, role, 5),
      label: `${label} · RANKING GERAL`,
    });
    addProviderBars({
      left: 665,
      top,
      rows: independentProviderRows(payload, role, 5),
      label: `${label} · RANKING INDEPENDENTE`,
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
    "Fonte: CVM, FundosNet e conglomerados prudenciais do BCB consultados em jul/26. Coorte fixa das raízes hoje listadas; PL bruto. O histórico não recupera fundos que saíram do conglomerado atual.",
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

function addOutrosBreakdownSlide(presentation, payload) {
  const level = "foco_analitico";
  const history = (payload.taxonomy_level_history || []).filter(
    (row) => row.nivel === level && row.tipo_exibicao === "Outros",
  );
  const periods = (payload.type_mix_meta?.periods || [])
    .map((row) => ({ competencia: row.competencia, label: row.label }))
    .filter((row) => row.competencia && row.label);
  if (!periods.length || !history.length) {
    throw new Error("Abertura analítica de Outros não está disponível no payload.");
  }
  const latestPeriod = periods.at(-1);
  const latestRows = history
    .filter((row) => row.competencia === latestPeriod.competencia)
    .sort((a, b) => num(b.pl_brl) - num(a.pl_brl) || String(a.categoria).localeCompare(String(b.categoria)));
  const categories = latestRows.map((row) => row.categoria);
  const palette = [C.orange, C.charcoal, C.mid, C.line, "#A5A9AD", "#527A91"];
  const colors = Object.fromEntries(categories.map((category, index) => [category, palette[index % palette.length]]));
  const rowByKey = new Map(history.map((row) => [`${row.competencia}::${row.categoria}`, row]));
  const valueFor = (period, category, field) => num(rowByKey.get(`${period.competencia}::${category}`)?.[field]);
  const volumeSeries = categories.map((category) => ({
    name: category,
    values: periods.map((period) => valueFor(period, category, "pl_brl") / 1e9),
    valuesFormatCode: "0.0",
    fill: colors[category],
  }));
  const shareSeries = categories.map((category) => ({
    name: category,
    values: periods.map((period) => valueFor(period, category, "share_tipo")),
    valuesFormatCode: "0.0%",
    fill: colors[category],
  }));
  const maxTotalBn = Math.max(...periods.map((period) => categories.reduce(
    (sum, category) => sum + valueFor(period, category, "pl_brl") / 1e9,
    0,
  )));
  const latestTotal = latestRows.reduce((sum, row) => sum + num(row.pl_brl), 0);
  const latestLead = latestRows.slice(0, 3).map((row) => `${row.categoria} ${pct(row.share_tipo, 1)}`).join(" · ");
  const tableIiLatest = (payload.taxonomy_level_history || [])
    .filter((row) => row.nivel === "tabela_ii_analitica" && row.tipo_exibicao === "Outros" && row.competencia === latestPeriod.competencia);
  const tableIi = Object.fromEntries(tableIiLatest.map((row) => [row.categoria, row]));
  const judicial = tableIi["Ações judiciais"] || tableIi["Acoes judiciais"];
  const publicSector = tableIi["Setor público"] || tableIi["Setor publico"];
  const slide = presentation.slides.add();
  addHeader(
    slide,
    "OUTROS · ABERTURA ANALÍTICA",
    latestLead,
    "Fonte: ANBIMA Data, Informe Mensal CVM e ledger documental aprovado. O foco analítico é exclusivo; a leitura Tabela II permanece separada.",
    0,
  );
  addSectionLabel(slide, "PL DO BUCKET OUTROS · R$ BILHÕES", { left: 60, top: 145, width: 550, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 60, top: 185, width: 550, height: 350 }),
    categories: periods.map((row) => row.label),
    series: volumeSeries,
    barOptions: { direction: "column", grouping: "stacked", gapWidth: 52, overlap: 100 },
    hasLegend: false,
    xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
    yAxis: { ...chartAxis(10.5, "0"), min: 0, max: Math.ceil(maxTotalBn / 25) * 25 },
    dataLabels: { showValue: categories.length <= 6, position: "center", textStyle: { fill: C.black, fontSize: 8.4, bold: true } },
  });
  addSectionLabel(slide, "PARTICIPAÇÃO NO BUCKET OUTROS", { left: 670, top: 145, width: 550, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 670, top: 185, width: 550, height: 350 }),
    categories: periods.map((row) => row.label),
    series: shareSeries,
    barOptions: { direction: "column", grouping: "percentStacked", gapWidth: 52, overlap: 100 },
    hasLegend: false,
    xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
    yAxis: { ...chartAxis(10.5, "0%"), min: 0, max: 1, majorUnit: 0.2 },
    dataLabels: { showValue: categories.length <= 6, position: "center", textStyle: { fill: C.black, fontSize: 8.4, bold: true } },
  });
  addLegend(slide, categories.map((category) => ({ label: category, color: colors[category] })), { left: 100, top: 545, width: 1080, height: 42 }, Math.min(4, categories.length));
  addText(slide, `As categorias somam ${bn(latestTotal, 1)} e fecham 100% do Tipo analítico Outros em ${latestPeriod.label}.`, { left: 90, top: 592, width: 1100, height: 22 }, { fontSize: 10.3, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle" });
  addText(
    slide,
    `Leitura complementar da Tabela II no mesmo bucket: Ações judiciais ${judicial ? `${bn(judicial.pl_brl, 1)} · ${pct(judicial.share_tipo, 1)}` : "N/D"}; Setor público ${publicSector ? `${bn(publicSector.pl_brl, 1)} · ${pct(publicSector.share_tipo, 1)}` : "N/D"}. As duas taxonomias se sobrepõem e não devem ser somadas.`,
    { left: 80, top: 619, width: 1120, height: 35 },
    { fontSize: 9.1, color: C.note, alignment: "center", verticalAlignment: "middle" },
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
    `Bucket Cartão: ${integer(auditSummary.fundos_incluidos_adquirencia)} incluídos, ${integer(auditSummary.fundos_fora_adquirencia)} fora e ${integer(auditSummary.fundos_pendentes_curadoria)} ${num(auditSummary.fundos_pendentes_curadoria) === 1 ? "pendente" : "pendentes"}. Em ${afterShortLower}, ${integer(observedCount)} dos ${curatedCount} CNPJs selecionados têm reporte ativo; ${integer(missingCount)} não reportam.`,
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
    "Fontes: CVM; BCB, alterações societárias nov/24–nov/25; coorte bancária curada a partir dos conglomerados prudenciais. PL ex-FIC, sem Sistema Petrobras/TAPSO.",
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
    `A coorte bancária curada lista ${integer(bankCohort.listedRoots)} raízes do BTG; ${integer(bankCohort.observedFunds)} tinham PL observado em ${stockShort.toLowerCase()}, somando ${bn(bankCohort.cohortPl, 1)}. O recorte não atribui controle societário sem evidência documental.`,
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

function addProviderMigrationEvidenceSlide(presentation, payload, page) {
  const slide = presentation.slides.add();
  const metrics = payload.conclusion_metrics || {};
  const reag = payload.reag_admin_summary || {};
  const reagLinks = payload.reag_admin_links || [];
  const cieloShare = num(metrics.admin_transition_2024_2025_changed_pl_brl)
    ? num(metrics.admin_transition_2024_2025_cielo_pl_brl)
      / num(metrics.admin_transition_2024_2025_changed_pl_brl)
    : 0;
  const masterPlannerRows = reagLinks.filter((row) => {
    const label = normalizeProviderName(row.destino_grupo);
    return label.includes("banco master") || label.includes("planner");
  });
  const masterPlannerFunds = masterPlannerRows.reduce((sum, row) => sum + num(row.fundos), 0);
  const masterPlannerPl = masterPlannerRows.reduce(
    (sum, row) => sum + num(row.pl_current_brl ?? row.pl_2026_05_brl),
    0,
  );
  addHeader(
    slide,
    "PRESTADORES · EVIDÊNCIAS DE MIGRAÇÃO",
    `${pct(metrics.admin_transition_2024_2025_changed_share_pl, 1)} do PL comparável mudou em 2025; ${pct(reag.migrated_share_current, 1)} do PL continuante da coorte CBSF/Reag migrou até jun/26`,
    "Fonte: CVM, Informe Mensal. Métricas por CNPJ legal, ex-FIC-FIDC e sem Sistema Petrobras/TAPSO; PL positivo e administrador informado nos períodos comparáveis.",
    page,
  );
  addSectionLabel(slide, "INDÚSTRIA · DEZ/24 → DEZ/25", { left: 60, top: 145, width: 555, height: 24 });
  addNativeEditorialTable(slide, {
    left: 60,
    top: 180,
    width: 555,
    height: 310,
    headers: ["Métrica", "Resultado"],
    rows: [
      ["Fundos comparáveis", integer(metrics.admin_transition_2024_2025_continuing_funds)],
      ["PL comparável", bn(metrics.admin_transition_2024_2025_comparable_pl_brl, 1)],
      ["Fundos que mudaram", integer(metrics.admin_transition_2024_2025_changed_funds)],
      ["PL que mudou", bn(metrics.admin_transition_2024_2025_changed_pl_brl, 1)],
      ["PL que mudou / comparável", pct(metrics.admin_transition_2024_2025_changed_share_pl, 1)],
      ["Cielo · 2 FIDCs", `${bn(metrics.admin_transition_2024_2025_cielo_pl_brl, 1)} · ${pct(cieloShare, 1)} do PL migrado`],
    ],
    columnWidths: [300, 255],
    aligns: ["left", "right"],
    fontSize: 11.2,
    headerFontSize: 10,
    rowHighlights: new Set([4, 5]),
  });
  addSectionLabel(slide, "COORTE CBSF/REAG · DEZ/25 → JUN/26", { left: 665, top: 145, width: 555, height: 24 });
  addNativeEditorialTable(slide, {
    left: 665,
    top: 180,
    width: 555,
    height: 310,
    headers: ["Métrica", "Resultado"],
    rows: [
      ["Fundos na origem", integer(reag.funds_origin)],
      ["PL na origem", bn(reag.pl_origin_brl, 1)],
      ["Fundos continuantes", integer(reag.continuing_funds)],
      ["PL continuante atual", bn(reag.continuing_pl_current_brl, 1)],
      ["Fundos migrados", integer(reag.migrated_funds)],
      ["PL migrado / continuante", `${bn(reag.migrated_pl_current_brl, 1)} · ${pct(reag.migrated_share_current, 1)}`],
      ["Master + Planner", `${integer(masterPlannerFunds)} fundos · ${bn(masterPlannerPl, 1)}`],
      ["Saída / sem reporte", `${integer(reag.exited_funds)} fundos · ${bn(reag.exited_pl_origin_brl, 1)} na origem`],
    ],
    columnWidths: [280, 275],
    aligns: ["left", "right"],
    fontSize: 10.6,
    headerFontSize: 10,
    rowHighlights: new Set([5, 6]),
  });
  addRule(slide, 60, 518, 1160, C.line, 1);
  addText(
    slide,
    `Indústria: ${metrics.admin_transition_2024_2025_methodology || "metodologia indisponível"}.`,
    { left: 60, top: 532, width: 555, height: 72 },
    { fontSize: 10.1, color: C.charcoal, lineSpacing: 1.02 },
  );
  addText(
    slide,
    `CBSF/Reag: coorte administrada pelo CNPJ ${reag.origin_admin_cnpj_formatado || "N/D"} em dez/25; continuante exige PL positivo em jun/26. Gestor e custodiante são fotografias atuais e não comprovam transição histórica.`,
    { left: 665, top: 532, width: 555, height: 72 },
    { fontSize: 10.1, color: C.charcoal, lineSpacing: 1.02 },
  );
  addSourceNotes(slide, [
    "CVM — Informe Mensal de FIDC e cadastro de prestadores por competência.",
    "PL comparável da indústria = menor PL entre dez/24 e dez/25 para cada CNPJ elegível.",
    "Coorte CBSF/Reag: administrador de origem CNPJ 34.829.992/0001-86 em dez/25; destino em jun/26.",
    "Limitação: ausência de reporte no destino não comprova liquidação do fundo; gestor e custodiante históricos não são observáveis na mesma base.",
  ]);
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
        `A coorte bancária curada lista ${integer(bankCohort.listedRoots)} raízes do BTG; ${integer(bankCohort.observedFunds)} tinham PL observado em ${stockShortLower}, somando ${bn(bankCohort.cohortPl, 1)}.`,
        `Dentro da coorte, ${integer(bankCohort.comboFunds)} FIDCs e ${bn(bankCohort.comboPl, 1)} concentram administração, gestão e custódia no BTG.`,
      ],
    },
    {
      order: 7,
      title: "Ofertas encerradas em 2026",
      bullets: [
        `${integer(currentOfferYtd.closed_offers)} ofertas encerradas somaram ${bn(currentOfferYtd.registered_volume_brl, 1)} em jan–jun/26; alta de ${pct(offerGrowth, 0)} sobre jan–jun/25 e ${pct(offerGrowth2024, 0)} sobre jan–jun/24.`,
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
    "Fontes: CVM, ANBIMA e BCB; coorte bancária curada a partir dos conglomerados prudenciais.",
    `PF: proxy com ${pct(currentOffer.placed_quantity_registered_volume_coverage, 1)} de cobertura; contas não equivalem a investidores únicos.`,
    "Verticalização no universo elegível; Top 10 ex-Petrobras/TAPSO.",
    `BTG: ${integer(metrics.btg_bank_cohort_observed_funds)}/${integer(metrics.btg_bank_cohort_listed_roots)} raízes observadas; ofertas CVM até 30/jun/26 e ANBIMA até 31/mai/26.`,
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
  addSourceNotes(slide, [
    "CVM/SRE — análises granulares de ofertas públicas primárias encerradas, todos os ritos disponíveis, volume registrado; 2026 = jan–jun: https://dados.cvm.gov.br/dataset/oferta-distrib",
    "ANBIMA Data — comparativo de mercado por valor encerrado, snapshot mai/26; 2026 = jan–mai: https://data.anbima.com.br/publicacoes/boletim-de-mercado-de-capitais/mercado-de-capitais-segue-resiliente-com-283-bi-em-ofertas-acumuladas-no-ano",
    "FundosNet/B3 — evidência documental de ratings; rating sem documento público verificável ou sem vínculo exato = N/D.",
  ]);
  return slide;
}

function top15PublicLabel(value) {
  return ({ Profissional: "Prof.", Qualificado: "Qualif.", Geral: "Geral", "Público Geral": "Geral" }[value] || "N/D");
}

function top15AgencyLabel(value) {
  return ({
    "S&P Global Ratings": "S&P",
    "Moody's Local": "Moody's",
    "Austin Rating": "Austin",
    "Fitch Ratings": "Fitch",
    "Liberum Ratings": "Liberum",
    "SR Rating": "SR",
  }[value] || "N/D");
}

function top15SlideRows(rows, emissionAudit) {
  const auditByEmission = new Map(
    (emissionAudit || []).map((row) => [`${row.tabela}::${row.emissao_id}`, row]),
  );
  return rows.map((row) => {
    const audit = auditByEmission.get(`${row.period_label}::${row.offer_id}`) || {};
    return [
      integer(row.rank),
      `E ${row.offer_id}\n${formatCnpj(audit.cnpj || row.cnpj_emissor)}`,
      fundEditorialName(row.fund_name_short, 24),
      `O: ${auditField(audit.originador, 18)}\nC: ${auditField(audit.cedente, 18)}`,
      `S: ${auditField(audit.subordinacao_minima, 17)}\nP: ${auditField(audit.preco_por_tipo_cota, 17)}`,
      auditField(audit.sacado, 20),
      (num(row.registered_volume_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    ];
  });
}

function addHistoricalTop15PairSlide(presentation, payload, leftPeriod, rightPeriod, slideNumber) {
  const slide = presentation.slides.add();
  const top15 = payload.closed_offer_top15 || [];
  const summaries = Object.fromEntries((payload.closed_offer_top15_summary || []).map((row) => [row.period_label, row]));
  const rowsFor = (period) => top15.filter((row) => row.period_label === period).sort((a, b) => num(a.rank) - num(b.rank));
  const leftRows = rowsFor(leftPeriod);
  const rightRows = rowsFor(rightPeriod);
  const leftSummary = summaries[leftPeriod] || {};
  const rightSummary = summaries[rightPeriod] || {};
  const display = (period) => period.replace(" FY", "FY").replace("2026 jan-jun", "JAN–JUN/26");
  const emissionAudit = (payload.emission_field_audit || []).filter((row) => row.bloco === "slides 21–22");
  const columnWidths = [22, 82, 112, 105, 100, 84, 55];
  const aligns = ["right", "left", "left", "left", "left", "left", "right"];
  addHeader(
    slide,
    "TOP 15 · HISTÓRICO",
    `${display(leftPeriod)} e ${display(rightPeriod)} com campos documentais por CNPJ e emissão`,
    "Fonte: CVM/SRE, dois arquivos de ofertas, e FundosNet. Primárias encerradas, todos os ritos; volume registrado.",
    slideNumber,
  );
  [
    [leftPeriod, leftRows, leftSummary, 60],
    [rightPeriod, rightRows, rightSummary, 660],
  ].forEach(([period, rows, summary, left]) => {
    addSectionLabel(slide, `${display(period)} · TOP 15`, { left, top: 138, width: 560, height: 24 });
    addNativeEditorialTable(slide, {
      left,
      top: 174,
      width: 560,
      height: 440,
      headers: ["#", "Emissão / CNPJ", "FIDC", "Originador / cedente", "Sub. mín. / preço por cota", "Sacado", "R$ bi"],
      rows: top15SlideRows(rows, emissionAudit),
      columnWidths,
      aligns,
      fontSize: 5.5,
      headerFontSize: 5.4,
      headerHeight: 34,
      rowHighlights: new Set(),
    });
    addText(
      slide,
      `Subtotal: ${bn(summary.top15_registered_volume_brl, 2)} · ${pct(summary.top15_share_of_period_volume, 1)} do período`,
      { left, top: 620, width: 560, height: 18 },
      { fontSize: 9.2, bold: true, color: C.charcoal, alignment: "right" },
    );
  });
  addText(
    slide,
    "O = originador; C = cedente; S = subordinação mínima; P = preço de emissão por tipo de cota. Cada linha usa CNPJ e emissão como chave; lacuna documental permanece N/D.",
    { left: 60, top: 641, width: 1160, height: 22 },
    { fontSize: 8.1, color: C.note, alignment: "right", verticalAlignment: "middle" },
  );
  addSourceNotes(slide, [
    "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
    "FundosNet/B3 — mesma curadoria documental flagship; fontes linha a linha na aba Auditoria emissões.",
    "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, Valor_Total_Registrado positivo e data de encerramento no período; snapshot CVM 24/jul/26.",
    "Limitação: rating sem documento público verificável ou sem vínculo exato = N/D.",
  ]);
}

function addPartial2022Top15Slide(presentation, payload, slideNumber) {
  const slide = presentation.slides.add();
  const rows = (payload.closed_offer_top15 || [])
    .filter((row) => row.period_label === "2022 FY parcial")
    .sort((a, b) => num(a.rank) - num(b.rank));
  const summary = (payload.closed_offer_top15_summary || []).find((row) => row.period_label === "2022 FY parcial") || {};
  addHeader(
    slide,
    "TOP 15 · 2022 PARCIAL",
    `A base pública recuperada contém ${integer(rows.length)} ofertas legadas; o período não forma um Top 15 completo`,
    "Fonte: CVM/SRE, base de distribuição dos ritos ordinário e legado, e FundosNet. Registros encerrados em 2022; cobertura parcial.",
    slideNumber,
  );
  addNativeEditorialTable(slide, {
    left: 60,
    top: 155,
    width: 1160,
    height: 350,
    headers: ["#", "FIDC", "Originador", "R$ bi", "Coordenador líder", "GF", "Público", "Agência", "Rating"],
    rows: top15SlideRows(rows),
    columnWidths: [45, 260, 160, 90, 170, 65, 95, 120, 155],
    aligns: ["right", "left", "left", "right", "left", "center", "left", "left", "left"],
    fontSize: 8.5,
    headerFontSize: 8.2,
    headerHeight: 34,
    rowHighlights: new Set(),
  });
  addText(
    slide,
    `Subtotal observado: ${bn(summary.top15_registered_volume_brl, 2)}. Limitação: sete linhas legadas não sustentam comparação anual nem inferência sobre o ranking integral de 2022.`,
    { left: 60, top: 535, width: 1160, height: 32 },
    { fontSize: 11, bold: true, color: C.charcoal, alignment: "center" },
  );
  addText(
    slide,
    "Agência e rating são mantidos como N/D quando não há documento público aplicável conciliado com a oferta, emissão, série ou subclasse.",
    { left: 60, top: 590, width: 1160, height: 32 },
    { fontSize: 10, color: C.note, alignment: "center" },
  );
  addSourceNotes(slide, [
    "CVM/SRE — oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
    "FundosNet/B3 — documento público de rating mais recente conciliado com a oferta, emissão, série ou subclasse.",
    "Limitação: a base pública recuperada contém sete ofertas legadas encerradas em 2022; o período é parcial e não sustenta Top 15 anual completo.",
  ]);
}

function addTop20ByAnbimaTypeSlide(presentation, payload, typeName) {
  const reviewRows = payload.top20_taxonomy_review || [];
  const auditRows = (payload.emission_field_audit || []).filter(
    (row) => row.bloco === "slides 10–13",
  );
  const auditByFund = new Map(
    auditRows.map((row) => [`${row.tabela}::${cnpjDigits(row.cnpj)}`, row]),
  );
  const periodSpecs = [
    { competencia: payload.latest_complete, label: "JUN/26 · TOP 15", headerFill: C.orange },
    { competencia: "2025-12", label: "DEZ/25 · TOP 15", headerFill: C.black },
  ];
  const rowsFor = (competencia) => [...reviewRows]
    .filter((row) => row.tipo_exibicao === typeName && row.competencia === competencia)
    .sort((a, b) => num(a.rank_tipo) - num(b.rank_tipo))
    .slice(0, 15);
  const originatorName = (value) => {
    const text = String(value || "").trim();
    if (
      !text
      || /^(?:N\/D|AUSÊNCIA|P\.\s*\d+|CEDENTE(?:\(S\))?\b|CNPJ\b)/i.test(text)
    ) {
      return "N/D";
    }
    return truncateWords(text, 16);
  };
  const currentRows = rowsFor(payload.latest_complete);
  const priorRows = rowsFor("2025-12");
  if (currentRows.length !== 15 || priorRows.length !== 15) {
    throw new Error(`Ranking ${typeName} deveria conter Top 15 em jun/26 e dez/25.`);
  }
  const slide = presentation.slides.add();
  const currentPl = currentRows.reduce((sum, row) => sum + num(row.pl), 0);
  const priorPl = priorRows.reduce((sum, row) => sum + num(row.pl), 0);
  addHeader(
    slide,
    "RANKING · TOP FUNDOS E ORIGINADORES",
    `${typeName} · Top 15: ${bn(currentPl, 1)} em jun/26 e ${bn(priorPl, 1)} em dez/25`,
    "Fonte: CVM, Informe Mensal e ledger documental aprovado. Agrupamento pela taxonomia analítica reclassificada; campos oficiais permanecem no workbook.",
    0,
  );
  periodSpecs.forEach((period, index) => {
    const rows = index === 0 ? currentRows : priorRows;
    const left = index === 0 ? 60 : 655;
    addSectionLabel(slide, period.label, { left, top: 136, width: 565, height: 22 }, period.headerFill);
    addNativeEditorialTable(slide, {
      left,
      top: 169,
      width: 565,
      height: 428,
      headers: ["#", "FIDC", "Originador / cedente", "Sub. mín. / preço por cota", "Sacado", "R$ bi"],
      rows: rows.map((row) => {
        const audit = auditByFund.get(
          `${typeName} · ${period.competencia}::${cnpjDigits(row.cnpj_fundo)}`,
        ) || {};
        return [
          String(integer(row.rank_tipo)),
          fundEditorialName(row.denominacao || "N/D", 23),
          `O: ${originatorName(audit.originador)}\nC: ${auditField(audit.cedente, 17)}`,
          `S: ${auditField(audit.subordinacao_minima, 16)}\nP: ${auditField(audit.preco_por_tipo_cota, 16)}`,
          auditField(audit.sacado, 16),
          (num(row.pl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        ];
      }),
      columnWidths: [22, 150, 125, 115, 93, 60],
      aligns: ["right", "left", "left", "left", "left", "right"],
      fontSize: 5.35,
      headerFontSize: 5.25,
      headerHeight: 33,
      headerFill: period.headerFill,
      rowHighlights: new Set(),
    });
    addText(
      slide,
      `Subtotal Top 15 · ${bn(rows.reduce((sum, row) => sum + num(row.pl), 0), 1)}`,
      { left, top: 605, width: 565, height: 22 },
      { fontSize: 9.2, bold: true, color: period.headerFill, alignment: "right", verticalAlignment: "middle" },
    );
  });
  addSourceNotes(slide, [
    "Unidade: CNPJ do fundo, com classes agregadas; os dois painéis usam o Top 15 de cada fotografia.",
    "O = originador; C = cedente; S = subordinação mínima; P = preço de emissão por tipo de cota. Mesma curadoria documental flagship; fontes linha a linha na aba Auditoria emissões.",
    "Campo ausente, fragmento sem nome explícito ou vínculo documental insuficiente permanece N/D.",
  ]);
}

function addFlagshipCurationSlide(presentation, payload) {
  const families = [...(payload.flagship_families || [])]
    .sort((a, b) => num(a.ordem_familia) - num(b.ordem_familia));
  const summary = payload.flagship_curation_summary || {};
  if (families.length !== 26) {
    throw new Error(`Curadoria flagship deveria conter 26 famílias; contém ${families.length}.`);
  }
  const ranges = ["< 10%", "10%–15%", "15%–20%", "20%–35%", "35%–60%", "≥ 60%"];
  const slide = presentation.slides.add();
  addHeader(
    slide,
    "CURADORIA · FUNDOS FLAGSHIP",
    `${integer(summary.familias)} famílias · ${integer(summary.cnpjs)} CNPJs · ${integer(summary.cnpjs_com_minimo_junior)} mínimos júnior localizados em ${integer(summary.cnpjs_com_regulamento_lido)} regulamentos revistos`,
    `CVM, Informe Mensal, ${competenceShortPt(payload.latest_complete).toLowerCase()}; regulamentos, emissões e assembleias dos pacotes documentais versionados. Lacunas = N/D.`,
    0,
  );
  const left = 60;
  const gap = 6;
  const columnWidth = (1160 - gap * (ranges.length - 1)) / ranges.length;
  const bandTop = 136;
  const bandHeight = 29;
  ranges.forEach((range, index) => {
    const x = left + index * (columnWidth + gap);
    addRect(slide, { left: x, top: bandTop, width: columnWidth, height: bandHeight }, C.charcoal);
    addText(
      slide,
      range,
      { left: x + 5, top: bandTop + 3, width: columnWidth - 10, height: bandHeight - 6 },
      {
        fontSize: 10.5,
        bold: true,
        color: C.white,
        alignment: "center",
        verticalAlignment: "middle",
        wrap: "none",
      },
    );
  });
  addText(
    slide,
    "SUBORDINAÇÃO ATUAL / PL · FAIXAS DESCRITIVAS",
    { left: 60, top: 116, width: 1160, height: 16 },
    { fontSize: 9, bold: true, color: C.mid, alignment: "right", wrap: "none" },
  );

  const groups = ranges.map((range) => families.filter((row) => row.faixa_subordinacao_atual === range));
  if (groups.reduce((sum, rows) => sum + rows.length, 0) !== families.length) {
    throw new Error("Toda família flagship deve pertencer a uma faixa de subordinação atual.");
  }
  const cardTop = 177;
  const cardHeight = 72;
  const cardGap = 6;
  groups.forEach((rows, rangeIndex) => {
    const x = left + rangeIndex * (columnWidth + gap);
    rows.forEach((row, rowIndex) => {
      const y = cardTop + rowIndex * (cardHeight + cardGap);
      const style = flagshipTypeStyle(row);
      addRect(slide, { left: x, top: y, width: columnWidth, height: cardHeight }, style.fill);
      addText(
        slide,
        truncateWords(row.familia_flagship, 34),
        { left: x + 8, top: y + 5, width: columnWidth - 16, height: 20 },
        { fontSize: 8.7, bold: true, color: C.black, verticalAlignment: "middle" },
      );
      addText(
        slide,
        `${moneyScale(row.pl_atual_brl)} · atual ${pct(row.subordinacao_atual_pct, 1)}`,
        { left: x + 8, top: y + 27, width: columnWidth - 16, height: 16 },
        { fontSize: 8.1, bold: true, color: C.charcoal, verticalAlignment: "middle", wrap: "none" },
      );
      addText(
        slide,
        `mín. jr ${row.subordinacao_minima_junior_display || "N/D"} · emissão ${row.emissao_data_display || "N/D"}`,
        { left: x + 8, top: y + 44, width: columnWidth - 16, height: 15 },
        { fontSize: 7.2, color: C.mid, verticalAlignment: "middle", wrap: "none" },
      );
      const trackLeft = x + 8;
      const trackWidth = columnWidth - 16;
      addRect(slide, { left: trackLeft, top: y + 63, width: trackWidth, height: 2 }, C.line);
      const value = Number(row.subordinacao_atual_pct);
      const markerRatio = clamp(value / 0.75, 0, 1);
      addRect(
        slide,
        {
          left: trackLeft + markerRatio * Math.max(trackWidth - 3, 0),
          top: y + 59,
          width: 3,
          height: 10,
        },
        C.black,
      );
    });
  });
  const usedTypes = [...new Set(families.map((row) => flagshipVisualType(row)))].sort(
    (a, b) => FLAGSHIP_TYPE_STYLES[a].order - FLAGSHIP_TYPE_STYLES[b].order,
  );
  let legendX = 60;
  usedTypes.forEach((label) => {
    const width = Math.max(78, label.length * 5.1 + 24);
    addRect(slide, { left: legendX, top: 650, width: 10, height: 10 }, FLAGSHIP_TYPE_STYLES[label].fill);
    addText(slide, label, { left: legendX + 14, top: 647, width: width - 14, height: 16 }, { fontSize: 6.8, color: C.mid, wrap: "none" });
    legendX += width;
  });
  addSourceNotes(slide, [
    `CVM, Informe Mensal FIDC, competência ${payload.latest_complete}: https://dados.cvm.gov.br/dataset/fi-doc-inf_mensal`,
    "FundosNet/B3, regulamentos, emissões e assembleias: https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM",
    "Leitura documental versionada por CNPJ; documento, data, página, status e lacuna constam na aba Curadoria flagship.",
    "Faixas descritivas; não constituem nota de risco. PL e subordinação atual são agregados por família; mínimos e datas de emissão exibem somente valores localizados.",
  ]);
}

function addCarteira1CurationSlide(presentation, payload) {
  const rows = [...(payload.carteira_1_flagship_comparison || [])]
    .sort((a, b) => num(a.ordem) - num(b.ordem));
  const summary = payload.carteira_1_flagship_comparison_summary || {};
  if (rows.length !== 7 || num(summary.flagship_cnpjs) !== 47) {
    throw new Error("Comparação da Carteira 1 deve reconciliar sete tipos e 47 CNPJs flagship.");
  }
  const slide = presentation.slides.add();
  addHeader(
    slide,
    "CARTEIRA 1 VS. 47 CNPJs FLAGSHIP",
    "O perfil aceito é comparado por sacado e pela mediana da subordinação atual dentro de cada tipo",
    `CVM, Informe Mensal, ${competenceShortPt(payload.latest_complete).toLowerCase()}; taxonomia analítica e curadoria documental por CNPJ. N/D permanece ausente.`,
    0,
  );
  const leftRows = rows.slice(0, 4);
  const rightRows = rows.slice(4);
  const addComparisonPanel = (row, left, top, width, height) => {
    const styleKey = row.tipo_comparacao === "Agro / Revenda"
      ? "Agro / revenda"
      : row.tipo_comparacao;
    const style = FLAGSHIP_TYPE_STYLES[styleKey] || FLAGSHIP_TYPE_STYLES.Financeiro;
    addRect(slide, { left, top, width, height }, style.fill);
    addText(
      slide,
      `${String(row.taxonomia_rasa || "N/D").toUpperCase()} · ${String(row.tipo_comparacao || "N/D").toUpperCase()}`,
      { left: left + 10, top: top + 7, width: width - 20, height: 16 },
      { fontSize: 8.3, bold: true, color: C.charcoal, wrap: "none" },
    );
    addNativeEditorialTable(slide, {
      left: left + 10,
      top: top + 27,
      width: width - 20,
      height: 54,
      headers: ["Referência", "CNPJs", "PL", "Subord. mediana"],
      rows: [
        [
          "Carteira I",
          `${integer(row.carteira_1_cnpjs_com_subordinacao)}/${integer(row.carteira_1_cnpjs)}`,
          row.carteira_1_pl_brl == null ? "N/D" : moneyScale(row.carteira_1_pl_brl),
          row.carteira_1_subordinacao_mediana_pct == null ? "N/D" : pct(row.carteira_1_subordinacao_mediana_pct, 1),
        ],
        [
          "47 flagships",
          `${integer(row.flagship_cnpjs_com_subordinacao)}/${integer(row.flagship_cnpjs)}`,
          row.flagship_pl_brl == null ? "N/D" : moneyScale(row.flagship_pl_brl),
          row.flagship_subordinacao_mediana_pct == null ? "N/D" : pct(row.flagship_subordinacao_mediana_pct, 1),
        ],
      ],
      columnWidths: [130, 55, 95, width - 300],
      aligns: ["left", "right", "right", "right"],
      fontSize: 6.8,
      headerFontSize: 6.3,
      headerHeight: 17,
      rowHighlights: new Set([0]),
      emphasizeHighlightedRows: true,
    });
    addText(
      slide,
      `Risco aceito: ${row.perfil_risco_aceito || "N/D"}`,
      { left: left + 10, top: top + 85, width: width - 20, height: 14 },
      { fontSize: 7.2, bold: true, color: C.charcoal, wrap: "none" },
    );
    addText(
      slide,
      row.leitura_risco_estrutural || "N/D",
      { left: left + 10, top: top + 101, width: width - 20, height: 15 },
      { fontSize: 7.1, bold: true, color: String(row.leitura_risco_estrutural || "").startsWith("Mais") ? C.orange : C.black, wrap: "none" },
    );
  };
  leftRows.forEach((row, index) => addComparisonPanel(row, 60, 132 + index * 126, 560, 119));
  rightRows.forEach((row, index) => addComparisonPanel(row, 660, 132 + index * 126, 560, 119));
  addText(
    slide,
    `Cobertura: ${integer(summary.carteira_1_cnpjs_classificados)}/${integer(summary.carteira_1_cnpjs)} CNPJs da Carteira I classificados; ${integer(summary.carteira_1_cnpjs_sem_grupo)} fora do perímetro FIDC. A comparação mede proteção estrutural, com tolerância de ±2 p.p.`,
    { left: 660, top: 521, width: 560, height: 42 },
    { fontSize: 8.4, color: C.charcoal, verticalAlignment: "middle" },
  );
  addText(
    slide,
    summary.metodologia || "N/D",
    { left: 660, top: 573, width: 560, height: 70 },
    { fontSize: 7.6, color: C.note, verticalAlignment: "middle" },
  );
  addSourceNotes(slide, [
    "A aba Carteira 1 curadoria preserva o detalhe de 101 CNPJs; a aba Carteira 1 vs flagships documenta os sete grupos comparáveis e a fórmula de leitura estrutural.",
    "Carteira I e os 47 CNPJs flagship usam o mesmo PL e a mesma subordinação atual reconciliados por CNPJ.",
    "A posição de risco estrutural usa a mediana da subordinação atual dentro de cada tipo; N/D não entra na mediana.",
  ]);
}

function addCarteira1TaxonomySlide(presentation, payload) {
  const history = [...(payload.carteira_1_taxonomy_history || [])].sort(
    (a, b) => num(a.period_order) - num(b.period_order) || num(a.category_order) - num(b.category_order),
  );
  const summary = payload.carteira_1_taxonomy_summary || {};
  const periods = [...new Map(history.map((row) => [row.competencia, {
    competencia: row.competencia,
    label: row.period_label,
    order: num(row.period_order),
  }])).values()].sort((a, b) => a.order - b.order);
  const categories = ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro", "Outros"];
  if (history.length !== 16 || periods.length !== 4) {
    throw new Error(`Histórico da Carteira 1 deveria conter 16 linhas e quatro competências; contém ${history.length}.`);
  }
  const colors = {
    "Fomento Mercantil": C.mid,
    "Agro, Indústria e Comércio": C.note,
    "Financeiro": C.orange,
    "Outros": C.line,
  };
  const rowByKey = new Map(history.map((row) => [`${row.competencia}::${row.anbima_tipo}`, row]));
  const valueFor = (period, category, field) => num(rowByKey.get(`${period.competencia}::${category}`)?.[field]);
  const latestPeriod = periods.at(-1);
  const latestTotal = valueFor(latestPeriod, categories[0], "portfolio_total_brl");
  const observedStart = valueFor(periods[0], categories[0], "observed_cnpjs");
  const observedLatest = valueFor(latestPeriod, categories[0], "observed_cnpjs");
  const maxTotalBn = Math.max(...periods.map((period) => valueFor(period, categories[0], "portfolio_total_brl") / 1e9));
  const volumeSeries = categories.map((category) => ({
    name: category,
    values: periods.map((period) => valueFor(period, category, "portfolio_pl_brl") / 1e9),
    valuesFormatCode: "0.0",
    fill: colors[category],
  }));
  const shareSeries = categories.map((category) => ({
    name: category,
    values: periods.map((period) => valueFor(period, category, "portfolio_share")),
    valuesFormatCode: "0.0%",
    fill: colors[category],
  }));
  const slide = presentation.slides.add();
  addHeader(
    slide,
    "CARTEIRA 1 · TAXONOMIA ANALÍTICA",
    `PL observado chegou a ${bn(latestTotal, 1)}; composição e crescimento usam o mesmo critério reclassificado do mercado`,
    `Fonte: CVM, Informe Mensal FIDC, e ledger aprovado. ${observedStart} CNPJs observados em ${periods[0].label} e ${observedLatest} em ${latestPeriod.label}; ausências não recebem PL imputado.`,
    0,
  );
  addSectionLabel(slide, "EVOLUÇÃO DO PL · R$ BILHÕES", { left: 60, top: 145, width: 550, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 60, top: 185, width: 550, height: 350 }),
    categories: periods.map((period) => period.label),
    series: volumeSeries,
    barOptions: { direction: "column", grouping: "stacked", gapWidth: 52, overlap: 100 },
    hasLegend: false,
    xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
    yAxis: { ...chartAxis(10.5, "0"), min: 0, max: Math.ceil(maxTotalBn / 10) * 10 },
    dataLabels: { showValue: true, position: "center", textStyle: { fill: C.black, fontSize: 8.4, bold: true } },
  });
  addSectionLabel(slide, "PARTICIPAÇÃO NO PL OBSERVADO", { left: 670, top: 145, width: 550, height: 24 });
  slide.charts.add("bar", {
    ...chartBase({ left: 670, top: 185, width: 550, height: 350 }),
    categories: periods.map((period) => period.label),
    series: shareSeries,
    barOptions: { direction: "column", grouping: "percentStacked", gapWidth: 52, overlap: 100 },
    hasLegend: false,
    xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 11.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
    yAxis: { ...chartAxis(10.5, "0%"), min: 0, max: 1, majorUnit: 0.2 },
    dataLabels: { showValue: true, position: "center", textStyle: { fill: C.black, fontSize: 8.4, bold: true } },
  });
  addLegend(slide, categories.map((category) => ({ label: category, color: colors[category] })), { left: 210, top: 544, width: 860, height: 26 }, 4);
  const growthLabel = (value) => value == null || !Number.isFinite(Number(value)) ? "N/D" : `${num(value) >= 0 ? "+" : ""}${pct(value, 1)}`;
  const comparison = categories.map((category) => {
    const row = rowByKey.get(`${latestPeriod.competencia}::${category}`) || {};
    return `${category.replace("Agro, Indústria e Comércio", "Agro/Ind./Com.")}: carteira ${growthLabel(row.portfolio_growth_since_start)} · mercado ${growthLabel(row.market_growth_since_start)}`;
  });
  addText(slide, `CRESCIMENTO ${periods[0].label.toUpperCase()} → ${latestPeriod.label.toUpperCase()} · ${comparison.join("   |   ")}`, { left: 60, top: 581, width: 1160, height: 30 }, { fontSize: 8.4, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle" });
  addText(slide, summary.methodology || "N/D", { left: 70, top: 618, width: 1140, height: 34 }, { fontSize: 8.7, color: C.note, alignment: "center", verticalAlignment: "middle" });
  return slide;
}

function addDelinquencyDispersionSlides(presentation, payload) {
  const rows = [...(payload.delinquency_dispersion || [])]
    .sort((a, b) => num(b.inadimplencia_total_subcategoria_brl) - num(a.inadimplencia_total_subcategoria_brl));
  const summary = payload.delinquency_dispersion_summary || {};
  const source = summary.fonte || `CVM, Informe Mensal FIDC, ${payload.latest_complete}`;
  {
    const slide = presentation.slides.add();
    addHeader(
      slide,
      "INADIMPLÊNCIA · DISPERSÃO ENTRE REPORTANTES",
      "Concentração do valor reportado por subcategoria da Tabela II",
      `${source}. Somente fundos da coorte tipo único com inadimplência ajustada positiva.`,
      0,
    );
    addNativeEditorialTable(slide, {
      left: 60,
      top: 142,
      width: 1160,
      height: 500,
      headers: ["Subcategoria", "Fundos", "Inad. · R$ bi", "Top 1", "Top 3", "Top 5", "HHI", "Gini", "Leitura"],
      rows: rows.map((row) => [
        row.tipo_recebivel_tabela_ii,
        integer(row.fundos_reportantes_inadimplencia),
        bn(row.inadimplencia_total_subcategoria_brl, 2).replace("R$ ", ""),
        `${bn(row.top1_inadimplencia_brl, 2).replace("R$ ", "")} · ${pct(row.top1_share, 1)}`,
        `${bn(row.top3_inadimplencia_brl, 2).replace("R$ ", "")} · ${pct(row.top3_share, 1)}`,
        `${bn(row.top5_inadimplencia_brl, 2).replace("R$ ", "")} · ${pct(row.top5_share, 1)}`,
        num(row.hhi).toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
        num(row.gini).toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
        row.leitura_concentracao,
      ]),
      columnWidths: [205, 60, 105, 135, 135, 135, 70, 70, 245],
      aligns: ["left", "right", "right", "right", "right", "right", "right", "right", "left"],
      fontSize: 8.4,
      headerFontSize: 8.1,
    });
    addText(
      slide,
      "Regra analítica: concentrada se HHI ≥ 0,25 ou Top 5 ≥ 70%; dispersa se HHI < 0,10 e Top 5 < 40%; demais casos intermediários. HHI e Gini medem concentração do valor reportado.",
      { left: 60, top: 646, width: 1160, height: 17 },
      { fontSize: 8.5, color: C.note, alignment: "right" },
    );
    addSourceNotes(slide, [source, summary.metodologia, summary.limitacoes]);
  }
  {
    const slide = presentation.slides.add();
    const priority = rows.slice(0, 5);
    addHeader(
      slide,
      "INADIMPLÊNCIA · SÍNTESE EXECUTIVA",
      `${integer(summary.fundos_reportantes_inadimplencia_positiva)} fundos com inadimplência positiva representam ${pct(summary.cobertura_pl_vs_universo, 1)} do PL ex-FIC positivo`,
      `${source}. Universo: ${integer(summary.fundos_universo_ex_fic_pl_positivo)} fundos e ${bn(summary.pl_universo_ex_fic_positivo_brl, 1)}; amostra positiva: ${bn(summary.pl_reportantes_inadimplencia_positiva_brl, 1)}.`,
      0,
    );
    addSectionLabel(slide, "SUBCATEGORIAS PRIORITÁRIAS POR VALOR REPORTADO", { left: 60, top: 142, width: 1160, height: 24 });
    addNativeEditorialTable(slide, {
      left: 60,
      top: 180,
      width: 1160,
      height: 325,
      headers: ["Prioridade", "Subcategoria", "Inadimplência", "Fundos", "Top 5", "Leitura", "Interpretação cautelar"],
      rows: priority.map((row, index) => [
        String(index + 1),
        row.tipo_recebivel_tabela_ii,
        bn(row.inadimplencia_total_subcategoria_brl, 2),
        integer(row.fundos_reportantes_inadimplencia),
        pct(row.top5_share, 1),
        row.leitura_concentracao,
        row.implicacao_analitica,
      ]),
      columnWidths: [70, 205, 125, 70, 85, 220, 385],
      aligns: ["right", "left", "right", "right", "right", "left", "left"],
      fontSize: 10,
      headerFontSize: 9.2,
      rowHighlights: new Set([0]),
    });
    addRule(slide, 60, 530, 1160, C.line, 1);
    addText(
      slide,
      `Cobertura: ${integer(summary.fundos_coorte_tipo_unico)} fundos na coorte tipo único (${bn(summary.pl_coorte_tipo_unico_brl, 1)}); ${integer(summary.fundos_reportantes_inadimplencia_positiva)} reportam valor positivo. A comparação com o universo de ${bn(summary.pl_universo_ex_fic_positivo_brl, 1)} delimita a amostra.`,
      { left: 60, top: 548, width: 1160, height: 42 },
      { fontSize: 12, color: C.charcoal, alignment: "center", verticalAlignment: "middle" },
    );
    addText(
      slide,
      "Limitações: zeros e ausências de reporte ficam fora da dispersão; atrasos e inconsistências podem reduzir a cobertura. Concentração sugere prioridade de validação e não identifica causalidade nem risco sistêmico por si só.",
      { left: 60, top: 602, width: 1160, height: 38 },
      { fontSize: 10.5, color: C.note, alignment: "center", verticalAlignment: "middle" },
    );
    addSourceNotes(slide, [source, summary.metodologia, summary.limitacoes]);
  }
}

function buildPresentation(payload) {
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
    addText(slide, COVER_TITLE, { left: 60, top: 148, width: 900, height: 86 }, {
      fontSize: 48,
      bold: true,
      color: C.white,
      verticalAlignment: "middle",
    });
    addRule(slide, 60, 530, 1160, "#4B4F53", 1);
    addText(slide, `Dados de PL: ${stockLong}`, { left: 60, top: 555, width: 500, height: 28 }, {
      fontSize: 16,
      color: C.white,
    });
    addText(slide, "Ofertas CVM e comparativo ANBIMA até 30 de junho de 2026", { left: 60, top: 589, width: 720, height: 28 }, {
      fontSize: 16,
      color: C.light,
    });
    addText(slide, `Itaú BBA · ${offersDate ? `${MONTHS_LONG_PT[offersDate.month - 1][0].toUpperCase()}${MONTHS_LONG_PT[offersDate.month - 1].slice(1)} de ${offersDate.year}` : offersAsOf}`, { left: 60, top: 657, width: 500, height: 22 }, {
      fontSize: 12,
      bold: true,
      color: C.orange,
    });
    addSourceNotes(slide, [
      "CVM/SRE — Ofertas Públicas de Distribuição: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "ANBIMA Data — Boletim de Mercado de Capitais, corte em 30/jun/26: https://data.anbima.com.br/",
    ]);
  }

  // 2. Grandes números
  if (SLIDE_CONTRACT_V1.includes("grand_numbers")) {
    const slide = presentation.slides.add();
    addHeader(
      slide,
      "GRANDES NÚMEROS",
      `${bn(latestHistory.pl_ex_fic, 0)} ex-FIC; a concentração aparece em fundos, prestadores e ajustes de qualidade`,
      `Fonte: CVM, ANBIMA e FundosNet; ${stockShortLower}. Ofertas CVM até jun/26; ANBIMA até mai/26.`,
      2,
    );
    const qa = payload.qa_latest;
    const mono = payload.service_model.find((row) => row.modelo_prestacao === "Monoestrutura");
    const conclusionMetrics = payload.conclusion_metrics || {};
    const summary = [
      {
        value: bn(latestHistory.pl_ex_fic, 0),
        claim: `PL ex-FIC em ${stockShortLower}`,
        detail: `${(num(latestHistory.pl_ex_fic) / num(payload.pl_history[0]?.pl_ex_fic)).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}× ${payload.pl_history[0]?.year}; FIC-FIDC: ${bn(latestHistory.pl_fic_componente, 1)}.`,
      },
      {
        value: pct(conclusionMetrics.holder_ge_200m_share_fundos_ate_10_contas, 1),
        claim: "dos fundos com PL ≥ R$ 200 mi têm até 10 contas",
        detail: `${pct(conclusionMetrics.holder_ge_200m_share_pl_ate_10_contas, 1)} do PL no recorte de ${bn(conclusionMetrics.holder_ge_200m_pl_brl, 1)}.`,
      },
      {
        value: integer(qa.casos_inad_supera_carteira),
        claim: "veículos com inadimplência acima da carteira",
        detail: `Cap: ${bn(qa.excesso_removido_brl, 1)}; Top 10: ${pct(qa.excesso_top10_share, 1)}.`,
      },
      {
        value: pct(mono?.share_pl, 1),
        claim: "do PL em monoestruturas",
        detail: `${bn(mono?.pl, 1)} de ${bn(conclusionMetrics.service_model_universe_pl_brl, 1)} de PL direto; FICs excluídos pelo portão único.`,
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
    addSourceNotes(slide, [
      "CVM — Informe Mensal de FIDC e cadastro de fundos para PL, cotistas e prestadores.",
      "CVM/SRE — ofertas granulares até jun/26: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "ANBIMA Data — comparativo de mercado por valor encerrado até mai/26: https://data.anbima.com.br/publicacoes/boletim-de-mercado-de-capitais/mercado-de-capitais-segue-resiliente-com-283-bi-em-ofertas-acumuladas-no-ano",
      "FundosNet/B3 — documentos públicos usados nas análises documentais.",
    ]);
  }

  // 3. Evolução do PL
  {
    const slide = presentation.slides.add();
    const history = payload.pl_history;
    const cagrPeriods = payload.pl_total_cagr_periods || [];
    const expandedCredit = payload.bcb_expanded_credit || [];
    const expandedGrowth = payload.bcb_total_growth_periods || [];
    const growthSummary = (periods) => periods
      .map((period) => {
        const value = num(period.cagr);
        return `${period.period_label || period.end_year} ${value > 0 ? "+" : ""}${pct(value, 1)}`;
      })
      .join("   ·   ");
    addHeader(
      slide,
      "ESCALA DA INDÚSTRIA",
      `FIDCs ex-FIC somam ${bnRoundedLabel(latestHistory.pl_ex_fic)}; o crédito privado ampliado totaliza ${tn(expandedCredit.at(-1)?.private_expanded_credit_total_brl, 3)}`,
      `Fontes: CVM, Informe Mensal de FIDC (${stockShortLower}); BCB, SGS 28183–28192 (último mês comum: ${stockShortLower}).`,
      3,
    );
    const categories = history.map((row) =>
      String(row.competencia) === latestCompetence ? stockShort : String(row.year),
    );
    const plMax = Math.max(...history.map((row) => num(row.pl_ex_fic) / 1e9));
    const plAxisMax = Math.ceil(plMax / 100) * 100 + 100;
    addSectionLabel(slide, "PL DOS FIDCs EX-FIC · R$ BI", { left: 60, top: 133, width: 545, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 55, top: 165, width: 555, height: 330 }),
      categories,
      series: [
        {
          name: "FIDCs ex-FIC",
          values: history.map((row) => row.competencia === latestCompetence
            ? Math.round(num(row.pl_ex_fic) / 1e9)
            : num(row.pl_ex_fic) / 1e9),
          valuesFormatCode: "0.0",
          fill: C.orange,
        },
      ],
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 52 },
      hasLegend: false,
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 8.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: {
        ...chartAxis(9, "[>=1000]#\\.##0;0"),
        min: 0,
        max: plAxisMax,
        majorUnit: 200,
      },
      dataLabels: {
        showValue: true,
        position: "outEnd",
        textStyle: { fill: C.black, fontSize: 8.2, bold: true },
      },
    });
    addText(
      slide,
      growthSummary(cagrPeriods),
      { left: 60, top: 532, width: 550, height: 30 },
      { fontSize: 8.2, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle" },
    );
    addSectionLabel(slide, "CARTEIRA DE CRÉDITO PRIVADA AMPLIADA · R$ BI", { left: 645, top: 133, width: 575, height: 24 });
    const creditCategories = expandedCredit.map((row) => row.period_label);
    const creditSeries = [
      ["Empréstimos", "loans_brl", C.charcoal],
      ["Títulos privados", "private_debt_brl", C.note],
      ["FIDCs · carteira", "fidc_receivables_brl", C.orange],
      ["Outras securitizações", "other_securitization_brl", C.line],
      ["Dívida externa", "external_debt_brl", C.light],
    ].map(([name, field, fill], seriesIndex) => ({
      name,
      values: expandedCredit.map((row) => num(row[field]) / 1e9),
      valuesFormatCode: "[>=1000]#\\.##0;0",
      fill,
      dataLabelOverrides: expandedCredit.map((row, idx) => ({
        idx,
        showValue: true,
        position: "center",
        textStyle: {
          fill: [0, 2].includes(seriesIndex) ? C.white : C.black,
          fontSize: 6.1,
          bold: false,
        },
      })),
    }));
    const creditMax = Math.max(...expandedCredit.map((row) => num(row.private_expanded_credit_total_brl) / 1e9));
    slide.charts.add("bar", {
      ...chartBase({ left: 635, top: 165, width: 585, height: 355 }),
      categories: creditCategories,
      series: creditSeries,
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 48, overlap: 100 },
      hasLegend: false,
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 8.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
        minorGridlines: null,
      },
      yAxis: {
        ...chartAxis(9, "[>=1000]#\\.##0;0"),
        min: 0,
        max: Math.ceil(creditMax / 2000) * 2000,
        majorUnit: 5000,
      },
      dataLabels: {
        showValue: true,
        position: "center",
        textStyle: { fill: C.black, fontSize: 5.8, bold: false },
      },
    });
    const latestCredit = expandedCredit.at(-1) || {};
    addRect(slide, { left: 978, top: 176, width: 220, height: 44 }, C.pale);
    addText(
      slide,
      `TOTAL · ${tn(latestCredit.private_expanded_credit_total_brl, 3)}`,
      { left: 988, top: 184, width: 200, height: 25 },
      { fontSize: 11.5, bold: true, color: C.black, alignment: "center", verticalAlignment: "middle", wrap: "none" },
    );
    addLegend(slide, [
      { label: "Empréstimos", color: C.charcoal },
      { label: "Tít. privados", color: C.note },
      { label: "FIDCs", color: C.orange },
      { label: "Outras securitizações", color: C.line },
      { label: "Dívida externa", color: C.light },
    ], { left: 640, top: 516, width: 580, height: 20 }, 3);
    addText(
      slide,
      growthSummary(expandedGrowth),
      { left: 640, top: 541, width: 580, height: 34 },
      { fontSize: 8.2, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle" },
    );
    addText(
      slide,
      `${competenceShortPt(latestCredit.competencia)}: total privado ${tn(latestCredit.private_expanded_credit_total_brl, 3)}; securitização ${bn(latestCredit.securitization_brl, 0)}; carteira FIDC ${bn(latestCredit.fidc_receivables_brl, 0)}. O total BCB de ${tn(latestCredit.expanded_credit_total_brl, 3)} inclui ${bn(latestCredit.public_debt_brl, 0)} de títulos públicos e permanece no export para reconciliação.`,
      { left: 640, top: 582, width: 580, height: 42 },
      { fontSize: 8.2, color: C.note, alignment: "center", verticalAlignment: "middle" },
    );
    addText(
      slide,
      "Fonte: Banco Central do Brasil. Série de carteira de crédito ampliada, excluídos títulos públicos. Securitizações abertas entre FIDCs e demais securitizações (CRIs e CRAs). PL direto e carteira privada têm perímetros contábeis distintos.",
      { left: 60, top: 632, width: 1160, height: 22 },
      { fontSize: 8.2, color: C.note, alignment: "center", verticalAlignment: "middle", wrap: "none" },
    );
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
    const viewA = "FIDCs vs demais elegíveis";
    const taxonomy = payload.issuance_taxonomy_table || [];
    const taxonomyLong = payload.issuance_taxonomy || [];
    const reconciliation = payload.issuance_taxonomy_reconciliation || [];
    const marketReconciliation = payload.market_offer_reconciliation || [];
    const anbimaPeriods = ["2023 FY", "2024 FY", "2025 FY", "2026 jan-mai"];
    const instruments = [
      ["Debêntures", C.black],
      ["FIDCs", C.orange],
      ["CRI", C.mid],
      ["Notas comerciais", C.note],
      ["CRA", C.line],
    ];
    const marketValue = (period, instrument) => num(marketReconciliation.find(
      (row) => row.period_label === period && row.instrument_label === instrument,
    )?.anbima_closed_volume_brl) / 1e9;
    if (taxonomy.length !== 4 || taxonomyLong.length !== 20 || reconciliation.length !== 5) {
      throw new Error("Tabela Emissões por Categoria ANBIMA não fecha 4 categorias × 5 períodos.");
    }
    addHeader(
      slide,
      "OFERTAS ENCERRADAS · CVM E ANBIMA",
      "FIDCs mantêm ganho de escala; a abertura por instrumento usa o valor encerrado da ANBIMA",
      "Fontes: CVM/SRE, snapshot 24/jul/26; ANBIMA Data, Boletim de Mercado de Capitais, snapshot mai/26.",
      4,
    );
    addSectionLabel(slide, "FIDCs E DEMAIS INSTRUMENTOS ELEGÍVEIS · R$ BI", {
      left: 60,
      top: 132,
      width: 550,
      height: 24,
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 175, width: 550, height: 405 }),
      categories: ["2023FY", "2024FY", "2025FY", "2026 jan–jun"],
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
        textStyle: { fill: C.mid, fontSize: 9.2 },
      },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 9.2 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(8.5, "0"), min: 0 },
      dataLabels: {
        showValue: true,
        position: "outEnd",
        textStyle: { fill: C.black, fontSize: 8.0, bold: true },
      },
    });
    const latestTaxonomy = taxonomyLong
      .filter((row) => row.period_key === "jun26")
      .map((row) => {
        const before = taxonomyLong.find(
          (candidate) => candidate.period_key === "jun25" && candidate.categoria === row.categoria,
        );
        return { ...row, delta_brl: num(row.volume_brl) - num(before?.volume_brl) };
      })
      .sort((a, b) => b.delta_brl - a.delta_brl);
    addSectionLabel(slide, "VALOR ENCERRADO POR INSTRUMENTO · R$ BI", {
      left: 670,
      top: 132,
      width: 550,
      height: 24,
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 670, top: 175, width: 550, height: 405 }),
      categories: ["2023FY", "2024FY", "2025FY", "2026 jan–mai"],
      series: instruments.map(([instrument, color]) => ({
        name: instrument,
        values: anbimaPeriods.map((period) => marketValue(period, instrument)),
        valuesFormatCode: "0.0",
        fill: color,
      })),
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 34 },
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 8.2 } },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 9.2 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(8.5, "0"), min: 0 },
      dataLabels: {
        showValue: true,
        position: "outEnd",
        textStyle: { fill: C.black, fontSize: 7.0, bold: true },
      },
    });

    const tableColumns = [
      ["Categoria", null, "left"],
      ["2023\nR$ bi", "2023 (R$ bi)", "right"],
      ["2023\n%", "2023 (%)", "right"],
      ["2024\nR$ bi", "2024 (R$ bi)", "right"],
      ["2024\n%", "2024 (%)", "right"],
      ["Δ 23→24\nR$ bi", "Delta 2023→2024 (R$ bi)", "right"],
      ["2025\nR$ bi", "2025 (R$ bi)", "right"],
      ["2025\n%", "2025 (%)", "right"],
      ["Δ 24→25\nR$ bi", "Delta 2024→2025 (R$ bi)", "right"],
      ["jan–jun/25\nR$ bi", "jan–jun/25 (R$ bi)", "right"],
      ["jan–jun/25\n%", "jan–jun/25 (%)", "right"],
      ["jan–jun/26\nR$ bi", "jan–jun/26 (R$ bi)", "right"],
      ["jan–jun/26\n%", "jan–jun/26 (%)", "right"],
      ["Δ 1S25→1S26\nR$ bi", "Delta jan–jun/25→jan–jun/26 (R$ bi)", "right"],
    ];
    const biCell = (value) => num(value).toLocaleString("pt-BR", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    const formatTaxonomyRow = (row) => tableColumns.map(([_, key]) => {
      if (!key) return row.Categoria;
      return key.endsWith("(%)") ? pct(row[key], 1) : biCell(row[key]);
    });
    const totals = { Categoria: "Total · quatro tipos" };
    tableColumns.slice(1).forEach(([_, key]) => {
      totals[key] = key.endsWith("(%)") ? 1 : taxonomy.reduce((sum, row) => sum + num(row[key]), 0);
    });
    const byPeriod = Object.fromEntries(reconciliation.map((row) => [row.period_key, row]));
    const periodKeys = ["2023", "2024", "2025", "jun25", "jun26"];
    const volumeKeys = ["2023 (R$ bi)", "2024 (R$ bi)", "2025 (R$ bi)", "jan–jun/25 (R$ bi)", "jan–jun/26 (R$ bi)"];
    const shareKeys = ["2023 (%)", "2024 (%)", "2025 (%)", "jan–jun/25 (%)", "jan–jun/26 (%)"];
    const bridgeRow = (label, field) => {
      const row = { Categoria: label };
      periodKeys.forEach((periodKey, index) => {
        row[volumeKeys[index]] = num(byPeriod[periodKey]?.[field]) / 1e9;
        row[shareKeys[index]] = null;
      });
      row["Delta 2023→2024 (R$ bi)"] = row[volumeKeys[1]] - row[volumeKeys[0]];
      row["Delta 2024→2025 (R$ bi)"] = row[volumeKeys[2]] - row[volumeKeys[1]];
      row["Delta jan–jun/25→jan–jun/26 (R$ bi)"] = row[volumeKeys[4]] - row[volumeKeys[3]];
      return row;
    };
    const bridgeDisplay = (row) => tableColumns.map(([_, key]) => {
      if (!key) return row.Categoria;
      if (key.endsWith("(%)")) return "—";
      return biCell(row[key]);
    });
    const tableRows = [
      ...taxonomy.map(formatTaxonomyRow),
      formatTaxonomyRow(totals),
      bridgeDisplay(bridgeRow("FIC-FIDC · reconciliação", "fic_excluded_brl")),
      bridgeDisplay(bridgeRow("Total emitido", "emitted_volume_brl")),
    ];
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "ANBIMA Data — Boletim de Mercado de Capitais, snapshot mai/26, aba 02-02-Vlr. Valor encerrado; 2026 = jan–mai.",
      "FIDCs 2023 no gráfico CVM: valor encerrado ANBIMA; a correção é idempotente e preserva bundles anteriores à republicação.",
    ]);
  }

  // 4B. Série ampla de mercado ANBIMA; preserva a ordem editorial anterior.
  {
    const slide = presentation.slides.add();
    const reconciliation = payload.market_offer_reconciliation || [];
    const taxonomy = payload.issuance_taxonomy || [];
    const taxonomyReconciliation = payload.issuance_taxonomy_reconciliation || [];
    const taxonomyCategories = ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro", "Outros"];
    const taxonomyPeriods = [
      ["2023", "2023"],
      ["2024", "2024"],
      ["2025", "2025"],
      ["jun25", "jan–jun/25"],
      ["jun26", "jan–jun/26"],
    ];
    const taxonomyColors = {
      "Fomento Mercantil": C.mid,
      "Agro, Indústria e Comércio": C.note,
      "Financeiro": C.orange,
      "Outros": C.line,
    };
    const taxonomyRow = (periodKey, category) => taxonomy.find(
      (row) => row.period_key === periodKey && row.categoria === category,
    ) || {};
    const periodOrder = ["2023 FY", "2024 FY", "2025 FY", "2026 jan-mai"];
    const instruments = [
      ["Debêntures", C.black],
      ["FIDCs", C.orange],
      ["CRI", C.mid],
      ["Notas comerciais", C.note],
      ["CRA", C.line],
    ];
    const rowFor = (period, instrument) => reconciliation.find(
      (row) => row.period_label === period && row.instrument_label === instrument,
    ) || {};
    const value = (period, instrument, field) => num(rowFor(period, instrument)[field]);
    const deb2025 = rowFor("2025 FY", "Debêntures");
    const deb2026 = rowFor("2026 jan-mai", "Debêntures");
    const fidc2025 = rowFor("2025 FY", "FIDCs");
    const cri2025 = rowFor("2025 FY", "CRI");
    const cri2026 = rowFor("2026 jan-mai", "CRI");
    const note2026 = rowFor("2026 jan-mai", "Notas comerciais");
    const cra2023 = rowFor("2023 FY", "CRA");
    addHeader(
      slide,
      "EMISSÕES POR CATEGORIA ANBIMA",
      "Financeiro lidera o 1S26; a composição mostra quais categorias explicam o aumento dos FIDCs",
      "Fonte: CVM/SRE; FIDCs 2023 corrigidos pelo valor encerrado ANBIMA. Quatro tipos + FIC-FIDC reconciliam com o volume emitido.",
      5,
    );
    addSectionLabel(slide, "EMISSÕES POR SETOR · R$ BI", {
      left: 60, top: 132, width: 550, height: 24,
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 164, width: 550, height: 195 }),
      categories: taxonomyPeriods.map(([, label]) => label),
      series: taxonomyCategories.map((category) => ({
        name: category,
        values: taxonomyPeriods.map(([periodKey]) => num(taxonomyRow(periodKey, category).volume_brl) / 1e9),
        valuesFormatCode: "0.0",
        fill: taxonomyColors[category],
      })),
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 45, overlap: 100 },
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 7.5 } },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 8.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(8.0, "0"), min: 0 },
      dataLabels: {
        showValue: true,
        position: "center",
        textStyle: { fill: C.black, fontSize: 5.8, bold: false },
      },
    });
    const findings = [
      [
        "DEBÊNTURES · PONTE TAXONÔMICA",
        `2025: CVM ${bn(deb2025.cvm_registered_volume_brl, 1)} + ${bn(deb2025.cvm_harmonization_volume_brl, 1)} em Outros títulos de securitização = ${bn(deb2025.cvm_harmonized_volume_brl, 1)}, ante ${bn(deb2025.anbima_closed_volume_brl, 1)} na ANBIMA. Jan–mai/26: ${bn(deb2026.cvm_harmonized_volume_brl, 1)} ante ${bn(deb2026.anbima_closed_volume_brl, 1)}.`,
      ],
      [
        "FIDCS · MÉTRICA E COBERTURA",
        `Em 2025, a CVM registra ${bn(fidc2025.cvm_registered_volume_brl, 1)} e a ANBIMA encerra ${bn(fidc2025.anbima_closed_volume_brl, 1)}. A diferença combina valor registrado versus encerrado, cobertura e presença de ofertas secundárias na ANBIMA; a causa individual exige reconciliação por oferta.`,
      ],
      [
        "CRI E NOTAS COMERCIAIS",
        `CRI: CVM ${pct(cri2025.raw_gap_pct, 1)} em 2025 e ${pct(cri2026.raw_gap_pct, 1)} em jan–mai/26 versus ANBIMA. Notas comerciais: ${pct(note2026.raw_gap_pct, 1)} em jan–mai/26. O residual pode refletir métrica, rito, retificações e data do snapshot.`,
      ],
      [
        "CRA · PONTO PENDENTE",
        `A CVM ficou ${pct(cra2023.raw_gap_pct, 1)} acima da ANBIMA em 2023. De 2024 a jan–mai/26, o desvio ficou em até 2,7%. A causa de 2023 permanece sem comprovação oferta a oferta.`,
      ],
    ];
    addSectionLabel(slide, "EMISSÕES POR SETOR · % DO TOTAL", {
      left: 670, top: 132, width: 550, height: 24,
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 670, top: 164, width: 550, height: 195 }),
      categories: taxonomyPeriods.map(([, label]) => label),
      series: taxonomyCategories.map((category) => ({
        name: category,
        values: taxonomyPeriods.map(([periodKey]) => num(taxonomyRow(periodKey, category).share)),
        valuesFormatCode: "0.0%",
        fill: taxonomyColors[category],
      })),
      barOptions: { direction: "column", grouping: "percentStacked", gapWidth: 45, overlap: 100 },
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 7.5 } },
      xAxis: {
        visible: true,
        textStyle: { fill: C.mid, fontSize: 8.5 },
        line: { style: "solid", fill: C.line, width: 1 },
        majorGridlines: null,
      },
      yAxis: { ...chartAxis(8.0, "0%"), min: 0, max: 1, majorUnit: 0.25 },
      dataLabels: {
        showValue: true,
        position: "center",
        textStyle: { fill: C.black, fontSize: 5.6, bold: false },
      },
    });
    const biCell = (value) => num(value).toLocaleString("pt-BR", {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    const tableHeaders = [
      "Categoria",
      "2023\nR$ bi", "2023\n%",
      "2024\nR$ bi", "2024\n%",
      "2025\nR$ bi", "2025\n%",
      "jan–jun/25\nR$ bi", "jan–jun/25\n%",
      "jan–jun/26\nR$ bi", "jan–jun/26\n%",
    ];
    const categoryRows = taxonomyCategories.map((category) => [
      category,
      ...taxonomyPeriods.flatMap(([periodKey]) => [
        biCell(num(taxonomyRow(periodKey, category).volume_brl) / 1e9),
        pct(taxonomyRow(periodKey, category).share, 1),
      ]),
    ]);
    const byTaxonomyPeriod = Object.fromEntries(
      taxonomyReconciliation.map((row) => [row.period_key, row]),
    );
    const bridgeRow = (label, field) => [
      label,
      ...taxonomyPeriods.flatMap(([periodKey]) => [
        biCell(num(byTaxonomyPeriod[periodKey]?.[field]) / 1e9),
        "—",
      ]),
    ];
    const totalFourTypes = [
      "Total · quatro tipos",
      ...taxonomyPeriods.flatMap(([periodKey]) => [
        biCell(taxonomyCategories.reduce(
          (sum, category) => sum + num(taxonomyRow(periodKey, category).volume_brl) / 1e9,
          0,
        )),
        "100,0%",
      ]),
    ];
    const tableRows = [
      ...categoryRows,
      totalFourTypes,
      bridgeRow("FIC-FIDC · reconciliação", "fic_excluded_brl"),
      bridgeRow("Total emitido", "emitted_volume_brl"),
    ];
    addSectionLabel(slide, "EMISSÕES POR CATEGORIA ANBIMA", {
      left: 60, top: 374, width: 1160, height: 18,
    });
    const taxonomyTable = addNativeEditorialTable(slide, {
      left: 60,
      top: 400,
      width: 1160,
      height: 235,
      headers: tableHeaders,
      rows: tableRows,
      columnWidths: [210, 85, 52, 85, 52, 85, 52, 100, 62, 100, 62],
      aligns: ["left", "right", "right", "right", "right", "right", "right", "right", "right", "right", "right"],
      fontSize: 6.9,
      headerFontSize: 6.8,
      headerHeight: 30,
      rowHighlights: new Set([4, 6]),
    });
    const shareComparisons = [
      [4, "2024", "2023"],
      [6, "2025", "2024"],
      [10, "jun26", "jun25"],
    ];
    taxonomyCategories.forEach((category, rowIndex) => {
      shareComparisons.forEach(([columnIndex, currentPeriod, priorPeriod]) => {
        const currentShare = num(taxonomyRow(currentPeriod, category).share);
        const priorShare = num(taxonomyRow(priorPeriod, category).share);
        const relativeChange = priorShare ? currentShare / priorShare - 1 : 0;
        if (relativeChange <= 0.02 && relativeChange >= -0.02) return;
        const cell = taxonomyTable.cells.block({ row: rowIndex + 1, column: columnIndex, rowCount: 1, columnCount: 1 });
        cell.textStyle.bold = true;
        cell.textStyle.color = relativeChange > 0.02 ? "#007A3D" : "#7A1F3D";
      });
    });
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "FIDCs 2023: valor encerrado ANBIMA (snapshot mai/26, aba 02-02-Vlr); composição não observada escalada pela composição CVM.",
      "Destaque: variação relativa da participação versus o período comparável anterior; verde > +2%, vinho < −2%, sem destaque dentro de ±2%.",
    ]);
  }

  // 5. Base investidora
  const addInvestorBaseSlide = () => {
    const slide = presentation.slides.add();
    const history = payload.investor_base_history;
    const composition = payload.investor_composition;
    const targetHistory = payload.offer_target_public_shares || [];
    const targetPeriods = ["2023 FY", "2024 FY", "2025 FY", "2026 jan-jun"];
    const targetValue = (period, category) => num(
      targetHistory.find((row) => row.period_label === period && row.target_public === category)?.share_registered_volume,
    );
    addHeader(
      slide,
      "BASE INVESTIDORA",
      `Entre 92,8% e 96,8% do volume anual foi destinado ao público profissional; a classificação mede elegibilidade, não alocação final`,
      "Fonte: CVM/SRE, dois arquivos de ofertas; 24/jul/26. Primárias encerradas, todos os ritos. Definições: RCVM 30.",
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
    addSectionLabel(slide, "% DO VOLUME EMITIDO POR PÚBLICO-ALVO CVM", { left: 60, top: 382, width: 690, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 417, width: 690, height: 190 }),
      categories: ["2023FY", "2024FY", "2025FY", "Jan–jun/26"],
      series: [
        {
          name: "Profissional",
          values: targetPeriods.map((period) => targetValue(period, "Profissional")),
          valuesFormatCode: "0.0%",
          fill: C.orange,
        },
        {
          name: "Qualificado",
          values: targetPeriods.map((period) => targetValue(period, "Qualificado")),
          valuesFormatCode: "0.0%",
          fill: C.charcoal,
        },
        {
          name: "Geral",
          values: targetPeriods.map((period) => targetValue(period, "Público Geral")),
          valuesFormatCode: "0.0%",
          fill: C.mid,
        },
        {
          name: "N/D",
          values: targetPeriods.map((period) => targetValue(period, "N/D")),
          valuesFormatCode: "0.0%",
          fill: C.light,
        },
      ],
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 45, overlap: 100 },
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 8.5 } },
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 9 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(8.5, "0%"), min: 0, max: 1, majorUnit: 0.25 },
      dataLabels: { showValue: true, position: "center", textStyle: { fill: C.white, fontSize: 7.5, bold: true } },
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
      `A emissão é majoritariamente elegível a investidores profissionais, padrão compatível com demanda institucional/gestoras. A base de público-alvo não separa pessoa física de pessoa jurídica; Público Geral foi 0,0% em 2024 e 0,5% em jan–jun/26. N/D: 1,1% em 2023 e 0,5% em 2025.`,
      { left: 795, top: 535, width: 425, height: 70 },
      { fontSize: 10.2, color: C.note },
    );
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "Resolução CVM 30 — categorias de investidor profissional e qualificado: https://conteudo.cvm.gov.br/legislacao/resolucoes/resolucao030.html",
      "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, valor registrado positivo e data de encerramento no período; 2026 = jan–jun.",
      "Limitação: público-alvo mede elegibilidade e não alocação final; não separa pessoa física de pessoa jurídica. Campo ausente em registros legados = N/D.",
    ]);
  };

  // 5. Distribuição por cotistas
  const addHolderDistributionSlide = () => {
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
  };

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
    const broadCategories = (mixMeta.categories || [
      "Fomento Mercantil",
      "Agro, Indústria e Comércio",
      "Financeiro",
      "Outros",
    ]).filter((category) => category !== "Outros");
    const outrosDisplay = {
      "Poder Público": "Precatórios e/ou Ações Judiciais",
      "Multicarteira Outros": "Multicedente/Multisacado",
      "Recuperação": "Recuperação / FIDCs NP",
      "N/D": "N/D",
    };
    const outrosCategories = ["Poder Público", "Multicarteira Outros", "Recuperação", "N/D"];
    const categories = [...broadCategories, ...outrosCategories];
    const colors = {
      "Fomento Mercantil": C.mid,
      "Agro, Indústria e Comércio": C.charcoal,
      "Financeiro": C.orange,
      "Poder Público": C.black,
      "Multicarteira Outros": C.note,
      "Recuperação": C.light,
      "N/D": C.line,
    };
    const rowByKey = new Map(
      history.map((row) => [`${row.competencia}::${row.anbima_tipo}`, row]),
    );
    const outrosRows = (payload.taxonomy_level_history || []).filter(
      (row) => row.nivel === "foco_analitico" && row.tipo_exibicao === "Outros",
    );
    const outrosByKey = new Map(
      outrosRows.map((row) => [`${row.competencia}::${row.categoria}`, row]),
    );
    const valueFor = (period, category, field) => {
      if (broadCategories.includes(category)) {
        return num(rowByKey.get(`${period.competencia}::${category}`)?.[field]);
      }
      const outrosRow = outrosByKey.get(`${period.competencia}::${category}`);
      return num(outrosRow?.[field === "pl" ? "pl_brl" : "share_total"]);
    };
    const volumeSeries = categories.map((category, seriesIndex) => ({
      name: outrosDisplay[category] || category,
      values: periods.map((period) => valueFor(period, category, "pl") / 1e9),
      valuesFormatCode: "0.0",
      fill: colors[category],
      dataLabelOverrides: periods.map((_, idx) => ({
        idx,
        showValue: true,
        position: "center",
        textStyle: {
          fill: [0, 1, 2, 3, 4].includes(seriesIndex) ? C.white : C.black,
          fontSize: 6.4,
          bold: true,
        },
      })),
    }));
    const shareSeries = categories.map((category, seriesIndex) => ({
      name: outrosDisplay[category] || category,
      values: periods.map((period) => valueFor(period, category, "share")),
      valuesFormatCode: "0.0%",
      fill: colors[category],
      dataLabelOverrides: periods.map((_, idx) => ({
        idx,
        showValue: true,
        position: "center",
        textStyle: {
          fill: [0, 1, 2, 3, 4].includes(seriesIndex) ? C.white : C.black,
          fontSize: 6.4,
          bold: true,
        },
      })),
    }));
    const latestPeriod = periods.at(-1);
    const latestTotal = categories.reduce(
      (sum, category) => sum + valueFor(latestPeriod, category, "pl"),
      0,
    );
    const financeAndOtherShare = valueFor(latestPeriod, "Financeiro", "share")
      + outrosCategories.reduce((sum, category) => sum + valueFor(latestPeriod, category, "share"), 0);
    const taxonomySummary = payload.top100_outros_summary || {};
    const approvedReduction = num(taxonomySummary.reducao_aprovada_brl);
    const approvedOutflows = integer(taxonomySummary.decisoes_aprovadas_com_saida);
    const hasAnalyticalOverlay = approvedReduction > 0 || approvedOutflows > 0;
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
      "TAXONOMIA ANALÍTICA · OUTROS ABERTO",
      `Financeiro + componentes de Outros = ${pct(financeAndOtherShare, 1)} do PL ex-FIC · ${latestPeriod.label}`,
      hasAnalyticalOverlay
        ? `Fonte: ANBIMA Data (Tipo/Foco, dez/25), Informe Mensal CVM (${latestPeriod.label}) e ledger documental aprovado; classificação oficial preservada no workbook.`
        : `Fonte: ANBIMA Data (Tipo/Foco, dez/25) + Informe Mensal CVM (${latestPeriod.label}).`,
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
      dataLabels: { showValue: true, position: "center" },
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
      dataLabels: { showValue: true, position: "center" },
    });
    addLegend(
      slide,
      categories.map((category) => ({ label: outrosDisplay[category] || category, color: colors[category] })),
      { left: 90, top: 548, width: 1100, height: 45 },
      4,
    );
    addText(
      slide,
      `Os sete blocos somam ${bn(latestTotal, 1)} e fecham 100% do PL ex-FIC de ${latestPeriod.label}.`,
      { left: 120, top: 596, width: 1040, height: 22 },
      { fontSize: 10.5, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle" },
    );
    addText(
      slide,
      `Rótulos de exibição: Poder Público → Precatórios e/ou Ações Judiciais; Multicarteira Outros → Multicedente/Multisacado; Recuperação → Recuperação / FIDCs NP. N/D permanece como residual observado. Tipo/Foco oficial e evidências seguem no workbook.`,
      { left: 70, top: 620, width: 1140, height: 34 },
      { fontSize: 8.7, color: C.note, alignment: "center", verticalAlignment: "middle" },
    );
  }

  // Adquirência
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
    const reconciliationRows = payload.receivables_reconciliation_summary || [];
    const reconciliationBefore = reconciliationRows.find((row) => row.competencia === periodBefore) || {};
    const reconciliationAfter = reconciliationRows.find((row) => row.competencia === periodAfter) || {};
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
    const financeDelta = num(financeAfter?.valor) - num(financeBefore?.valor);
    const totalSegmentedDelta = after.reduce((sum, row) => sum + num(row.valor), 0)
      - before.reduce((sum, row) => sum + num(row.valor), 0);
    const financeContribution = totalSegmentedDelta ? financeDelta / totalSegmentedDelta : 0;
    addHeader(
      slide,
      "CARTEIRA POR TIPO DE RECEBÍVEL",
      `Financeiro ganhou ${pct(num(financeAfter?.share_reported) - num(financeBefore?.share_reported), 1).replace("%", " p.p.")} e explicou ${pct(financeContribution, 1)} do aumento líquido do valor segmentado`,
      `Fonte: CVM, Informe Mensal, Tabela II; dez/23 e ${stockShortLower}. Percentuais sobre a soma dos segmentos reportados; contribuição = Δ Financeiro / Δ total líquido.`,
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
      `Diferença Tabela II − Tabela I: ${bn(reconciliationBefore.gap_tabela_ii_menos_i_brl, 1)} em dez/23 e ${bn(reconciliationAfter.gap_tabela_ii_menos_i_brl, 1)} em ${stockShortLower}. Em ${stockShortLower}, ${integer(reconciliationAfter.fundos_sem_abertura_tabela_ii)} fundos sem abertura (${bn(reconciliationAfter.pl_sem_abertura_tabela_ii_brl, 1)} de PL); Top 20 explicam ${pct(reconciliationAfter.gap_positivo_top20_share, 1)} do gap positivo.`,
      { left: 60, top: 635, width: 1160, height: 24 },
      { fontSize: 9.8, color: C.charcoal, alignment: "right", verticalAlignment: "middle" },
    );
    addLegend(slide, [
      { label: "Dez/23", color: C.mid },
      { label: stockShort, color: C.orange },
    ], { left: 970, top: 128, width: 250, height: 22 }, 2);
  }

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

  // Market shares detalhados passam ao apêndice.
  const materialFocus = payload.material_focus_top6;

  const providerInsightOffset = 0;

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
      `Fonte: CVM, ANBIMA e ledger analítico aprovado, ${stockShortLower}. Ranking derivado do universo completo ex-FIC; denominação legal completa no apêndice.`,
      15 + providerInsightOffset,
    );
    const tableRows = top20.map((row) => [
      String(row.rank),
      row.nome_curto,
      bn(row.pl, 1).replace("R$ ", ""),
      pct(row.market_share_ex_fic, 1),
      `${row.anbima_tipo_curado || row.anbima_tipo || "N/D"}\n${row.anbima_foco_curado || row.anbima_foco || "N/D"}`,
    ]);
    [0, 1].forEach((block) => {
      addNativeEditorialTable(slide, {
        left: block === 0 ? 60 : 650,
        top: 150,
        width: 570,
        height: 490,
        headers: ["#", "Fundo", "PL bi", "Share", "Tipo / Foco"],
        rows: tableRows.slice(block * 10, block * 10 + 10),
        columnWidths: [30, 235, 70, 65, 170],
        aligns: ["right", "left", "right", "right", "left"],
        fontSize: 10.7,
        headerFontSize: 10,
        rowHighlights: new Set(block === 0 ? [0, 1] : []),
      });
    });
  }

  ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro", "Outros"]
    .forEach((typeName) => addTop20ByAnbimaTypeSlide(presentation, payload, typeName));
  addFlagshipCurationSlide(presentation, payload);
  addCarteira1CurationSlide(presentation, payload);
  addCarteira1TaxonomySlide(presentation, payload);

  // 20. Modelo de prestação
  if (SLIDE_CONTRACT_V1.includes("service_model")) {
    const slide = presentation.slides.add();
    const rows = payload.service_model;
    const mono = rows.find((row) => row.modelo_prestacao === "Monoestrutura");
    const missing = rows.find((row) => row.modelo_prestacao === "Dados incompletos");
    addHeader(
      slide,
      "MODELO DE PRESTAÇÃO",
      `Monoestruturas são ${pct(mono?.share_fundos, 1)} dos fundos e ${pct(mono?.share_pl, 1)} do PL; dados incompletos cobrem ${pct(missing?.share_pl, 1)}`,
      `Fonte: CVM, cadastro vigente em ${stockShortLower}. PL direto; FICs excluídos pelo portão único. Definição mono: mesmo conglomerado normalizado nas três funções.`,
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
    addText(
      slide,
      "Conglomerado econômico normalizado: Kanastra permanece separada do Itaú e CBSF da REAG. A afiliação Kanastra→Itaú é exclusiva do ranking de independentes.",
      { left: 60, top: 622, width: 1160, height: 25 },
      { fontSize: 9.1, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
  }

  // 21. Concentração das monoestruturas
  if (SLIDE_CONTRACT_V1.includes("monostructure")) {
    const slide = presentation.slides.add();
    const rows = [...payload.monostructure_concentration].sort((a, b) => num(a.rank_pl_mono) - num(b.rank_pl_mono)).slice(0, 6);
    const bb = rows.find((row) => String(row.grupo_economico).includes("Banco do Brasil"));
    const ot = rows.find((row) => String(row.grupo_economico).includes("Oliveira Trust"));
    addHeader(
      slide,
      "CONCENTRAÇÃO DAS MONOESTRUTURAS",
      "Sistema Petrobras é todo o PL mono do BB; TAPSO representa 54% do PL mono da Oliveira Trust",
      `Fonte: CVM, ${stockShortLower}. Preço, propostas e contratos não integram a base.`,
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
        row.maior_fundo_nome_curto || row.maior_fundo,
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
    addText(
      slide,
      "HHI em pontos de 0 a 10.000; 10.000 corresponde a um único fundo.",
      { left: 60, top: 594, width: 735, height: 20 },
      { fontSize: 9.5, color: C.note, alignment: "right" },
    );
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
    const annualComparison = [2024, 2025, 2026]
      .map((year) => annual.find((row) => num(row.year) === year))
      .filter(Boolean);
    const currentComparable = janJune.find((row) => num(row.year) === 2026) || {};
    const priorComparable = janJune.find((row) => num(row.year) === 2025) || {};
    const yoy = num(priorComparable.registered_volume_brl)
      ? num(currentComparable.registered_volume_brl) / num(priorComparable.registered_volume_brl) - 1
      : 0;
    const naturalPersonShareLabel = (row) => num(row.placed_quantity_registered_volume_coverage) > 0
      ? pct(row.natural_person_placed_volume_share, 1)
      : "N/D";
    const professionalShareLabel = (row) => (
      num(row.target_public_registered_volume_coverage) > 0 && num(row.registered_volume_brl) > 0
        ? pct(num(row.professional_target_registered_volume_brl) / num(row.registered_volume_brl), 1)
        : "N/D"
    );
    const cumulative = (year) => {
      const maxMonth = year === currentOfferYear ? 6 : 12;
      const byMonth = new Map(
        monthly
          .filter((row) => num(row.year) === year && num(row.month) <= maxMonth)
          .map((row) => [num(row.month), row]),
      );
      let running = 0;
      return Array.from({ length: maxMonth }, (_, index) => {
        running += num(byMonth.get(index + 1)?.registered_volume_brl);
        return running / 1e9;
      });
    };
    addHeader(
      slide,
      "OFERTAS ENCERRADAS · VOLUME E TICKET",
      `Jan–jun/26 somou ${bn(currentComparable.registered_volume_brl, 1)} em ${integer(currentComparable.closed_offers)} ofertas, alta de ${pct(yoy, 1)} sobre jan–jun/25`,
      `Fonte: CVM/SRE, dois arquivos de ofertas, snapshot ${dateShortPt(payload.offers_source_as_of || offersAsOf)}. Primárias encerradas, todos os ritos; volume registrado.`,
      27,
    );
    addSectionLabel(slide, "VOLUME REGISTRADO E TICKET · FY / YTD", { left: 60, top: 145, width: 550, height: 24 });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 180, width: 550, height: 245 }),
      categories: annualComparison.map((row) => num(row.year) === 2026 ? "2026YTD" : `${row.year}FY`),
      series: [
        {
          name: "Volume registrado",
          values: annualComparison.map((row) => num(row.registered_volume_brl) / 1e9),
          valuesFormatCode: "0.0",
          fill: C.charcoal,
          points: annualComparison.map((row, idx) => ({
            idx,
            fill: num(row.year) === currentOfferYear ? C.orange : C.charcoal,
          })),
          dataLabelOverrides: annualComparison.map((row, idx) => ({
            idx,
            showValue: true,
            position: "outEnd",
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
    addSectionLabel(slide, "VOLUME ACUMULADO · JAN–DEZ · R$ BI", { left: 670, top: 145, width: 550, height: 24 });
    addStraightLineChart(slide, {
      position: { left: 670, top: 180, width: 550, height: 245 },
      categories: MONTHS_SHORT_PT.map((month) => month[0].toUpperCase() + month.slice(1)),
      series: [
        { name: "2024", values: cumulative(2024), valuesFormatCode: "0.0", line: { style: "solid", fill: C.note, width: 2 } },
        { name: "2025", values: cumulative(2025), valuesFormatCode: "0.0", line: { style: "solid", fill: C.charcoal, width: 2.2 } },
        { name: "2026", values: cumulative(2026), valuesFormatCode: "0.0", line: { style: "solid", fill: C.orange, width: 3 } },
      ],
      yAxis: { ...chartAxis(9, "0"), min: 0 },
      labelIndices: [0, 2, 4, 5, 7, 9, 11],
      labelFontSize: 8.8,
      displayBlanksAs: "gap",
    });
    addLegend(slide, [
      { label: "2024", color: C.note },
      { label: "2025", color: C.charcoal },
      { label: "2026", color: C.orange },
    ], { left: 810, top: 420, width: 410, height: 22 }, 3);
    addText(
      slide,
      "2026 encerra em jun/26; as curvas de 2024 e 2025 seguem até dezembro.",
      { left: 670, top: 443, width: 550, height: 16 },
      { fontSize: 8.5, color: C.note, alignment: "right" },
    );
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
        naturalPersonShareLabel(row),
        professionalShareLabel(row),
      ]),
      columnWidths: [100, 155, 180, 155, 155, 205, 210],
      aligns: ["left", "right", "right", "right", "right", "right", "right"],
      fontSize: 8.8,
      headerFontSize: 8.5,
      rowHighlights: new Set([annual.length - 1]),
    });
    addText(
      slide,
      `PF representa ${pct(current.natural_person_placed_volume_share, 1)} do proxy colocado; cobertura ${pct(current.placed_quantity_registered_volume_coverage, 1)}. Público profissional usa o volume registrado total como denominador, incluindo N/D; 2022 = N/D por ausência de reporte.`,
      { left: 60, top: 626, width: 1160, height: 30 },
      { fontSize: 10.2, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, valor registrado positivo e data de encerramento no período; 2026 = jan–jun.",
      "Métrica: volume = Valor_Total_Registrado; ticket = volume registrado por oferta deduplicada. PF usa quantidade colocada e depende da cobertura do campo.",
      "Limitação: valor registrado pode diferir do valor encerrado informado à ANBIMA.",
    ]);
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
      "Fonte: CVM/SRE, dois arquivos de ofertas; mesma coorte primária encerrada do slide anterior. 2026 = jan–jun.",
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
    ], { left: 425, top: 576, width: 430, height: 22 }, 3);
    addText(
      slide,
      "Faixas fecham no limite inferior; “> R$ 100 mi” é estrito e exclui ofertas exatamente iguais a R$ 100 mi.",
      { left: 60, top: 599, width: 1160, height: 14 },
      { fontSize: 8.2, color: C.note, alignment: "center", verticalAlignment: "middle" },
    );
    summaries.forEach((summary, index) => {
      const label = summary.period_label === "2026 jan-jun"
        ? "2026 YTD"
        : String(summary.period_label).replace(" FY", "FY");
      const left = 60 + index * 390;
      addText(
        slide,
        `${label} · > R$ 100 mi`,
        { left, top: 616, width: 360, height: 16 },
        { fontSize: 8.8, bold: true, color: index === 2 ? C.orange : C.charcoal },
      );
      addText(
        slide,
        `${bn(summary.over_100m_registered_volume_brl, 1)} · ${pct(summary.over_100m_registered_volume_share, 1)} do volume · ${integer(summary.over_100m_closed_offers)} ofertas (${pct(summary.over_100m_offer_share, 1)})`,
        { left, top: 635, width: 360, height: 22 },
        { fontSize: 8.7, color: C.note },
      );
      if (index < 2) addRule(slide, left + 375, 616, 1, C.line, 1);
    });
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, Valor_Total_Registrado positivo e data de encerramento no período; 2024/2025 = FY e 2026 = jan–jun.",
      "Limitação: faixas e participações usam o valor registrado, que pode diferir do valor encerrado informado à ANBIMA.",
    ]);
  }

  // 30. Evolução do número, volume e regime de colocação.
  {
    const slide = presentation.slides.add();
    const regimeRows = [...(payload.closed_offer_placement_regime || [])]
      .sort(
        (a, b) =>
          num(a.period_order) - num(b.period_order)
          || num(a.regime_order) - num(b.regime_order),
      );
    const periodLabels = [
      ...new Set(regimeRows.map((row) => row.period_label)),
    ];
    const periodColors = [C.note, C.charcoal, C.orange];
    const periodDisplay = {
      "2024 FY": "2024FY",
      "2025 FY": "2025FY",
      "2026 jan-jun": "2026 jan–jun",
    };
    const regimeLabels = regimeRows
      .filter((row) => row.placement_regime !== "Não informado")
      .sort((a, b) => num(a.regime_order) - num(b.regime_order))
      .map((row) => row.placement_regime)
      .filter((value, index, values) => values.indexOf(value) === index);
    const rowFor = (period, regime) =>
      regimeRows.find(
        (row) =>
          row.period_label === period
          && row.placement_regime === regime,
      ) || {};
    const periodTotal = (period) =>
      regimeRows.find((row) => row.period_label === period) || {};
    const currentBestEfforts = rowFor(
      "2026 jan-jun",
      "Melhores esforços",
    );
    addHeader(
      slide,
      "OFERTAS · VOLUME E REGIME",
      `Melhores esforços concentram ${pct(currentBestEfforts.closed_offers_share, 0)} das ofertas e ${pct(currentBestEfforts.registered_volume_share, 0)} do volume em jan–jun/26`,
      "Fonte: CVM/SRE, dois arquivos de ofertas, snapshot 24/jul/26. Regime declarado; campo ausente = Não informado.",
      30,
    );

    const addTotalChart = ({
      left,
      title,
      valueKey,
      formatCode,
      yAxisFormat,
    }) => {
      addSectionLabel(
        slide,
        title,
        { left, top: 137, width: 555, height: 24 },
      );
      slide.charts.add("bar", {
        ...chartBase({ left, top: 171, width: 555, height: 198 }),
        categories: periodLabels.map(
          (period) => periodDisplay[period] || period,
        ),
        series: [
          {
            name: title,
            values: periodLabels.map(
              (period) => num(periodTotal(period)[valueKey]),
            ),
            valuesFormatCode: formatCode,
            fill: C.charcoal,
            points: periodLabels.map((period, idx) => ({
              idx,
              fill: periodColors[idx],
            })),
          },
        ],
        barOptions: {
          direction: "column",
          grouping: "clustered",
          gapWidth: 58,
        },
        hasLegend: false,
        xAxis: {
          visible: true,
          textStyle: { fill: C.mid, fontSize: 10 },
          line: { style: "solid", fill: C.line, width: 1 },
          majorGridlines: null,
        },
        yAxis: { ...chartAxis(8.5, yAxisFormat), min: 0 },
        dataLabels: {
          showValue: true,
          position: "outEnd",
          textStyle: { fill: C.black, fontSize: 9.2, bold: true },
        },
      });
    };
    addTotalChart({
      left: 60,
      title: "NÚMERO DE OFERTAS",
      valueKey: "period_closed_offers",
      formatCode: "0",
      yAxisFormat: "0",
    });
    addTotalChart({
      left: 665,
      title: "VOLUME REGISTRADO · R$ BI",
      valueKey: "period_registered_volume_brl",
      formatCode: "0.0,,,",
      yAxisFormat: "0.0,,,",
    });

    addLegend(
      slide,
      periodLabels.map((period, index) => ({
        label: periodDisplay[period] || period,
        color: periodColors[index],
      })),
      { left: 455, top: 373, width: 370, height: 22 },
      3,
    );
    addText(
      slide,
      `% do período (Melhores esforços / Garantia firme / Misto) · ${periodLabels
        .map((period) => {
          const label = periodDisplay[period] || period;
          const shares = regimeLabels.map((regime) =>
            pct(rowFor(period, regime).closed_offers_share, 0).replace("%", ""),
          );
          return `${label}: ${shares.join(" / ")}%`;
        })
        .join("   ·   ")}`,
      { left: 60, top: 391, width: 555, height: 14 },
      { fontSize: 7.2, color: C.note },
    );

    const addRegimeChart = ({
      left,
      title,
      valueKey,
      formatCode,
      xAxisFormat,
    }) => {
      addSectionLabel(
        slide,
        title,
        { left, top: 406, width: 555, height: 24 },
      );
      slide.charts.add("bar", {
        ...chartBase({ left, top: 438, width: 555, height: 195 }),
        categories: [...regimeLabels].reverse(),
        series: [...periodLabels].reverse().map((period) => {
          const periodIndex = periodLabels.indexOf(period);
          const chartRegimes = [...regimeLabels].reverse();
          return {
            name: periodDisplay[period] || period,
            values: chartRegimes.map((regime) => num(rowFor(period, regime)[valueKey])),
            valuesFormatCode: formatCode,
            fill: periodColors[periodIndex],
          };
        }),
        barOptions: {
          direction: "bar",
          grouping: "clustered",
          gapWidth: 42,
        },
        hasLegend: false,
        xAxis: {
          visible: true,
          textStyle: { fill: C.mid, fontSize: 7.5 },
          line: { style: "solid", fill: C.line, width: 1 },
          majorGridlines: null,
        },
        yAxis: {
          ...chartAxis(1, xAxisFormat),
          visible: false,
          textStyle: { fill: C.white, fontSize: 1 },
          line: { style: "solid", fill: C.white, width: 0.1 },
          min: 0,
          majorGridlines: null,
        },
        dataLabels: {
          showValue: true,
          position: "outEnd",
          textStyle: { fill: C.black, fontSize: 7.5, bold: false },
        },
      });
    };
    addRegimeChart({
      left: 60,
      title: "REGIME DE COLOCAÇÃO · NÚMERO DE OFERTAS",
      valueKey: "closed_offers",
      formatCode: "0",
      xAxisFormat: "0",
    });
    addRegimeChart({
      left: 665,
      title: "REGIME DE COLOCAÇÃO · VOLUME · R$ BI",
      valueKey: "registered_volume_brl",
      formatCode: "0.0,,,",
      xAxisFormat: "0.0,,,",
    });
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, Valor_Total_Registrado positivo e data de encerramento no período; 2026 = jan–jun.",
      "Métrica: regime de colocação conforme declarado na oferta; campo ausente nos arquivos consultados = Não informado.",
      "Limitação: volume registrado pode diferir do valor encerrado informado à ANBIMA.",
    ]);
  }

  // 31. Top 15 ofertas encerradas e originadores.
  {
    const slide = presentation.slides.add();
    const top15 = [...(payload.closed_offer_top15 || [])];
    const emissionAudit = (payload.emission_field_audit || []).filter(
      (row) => row.bloco === "slides 21–22",
    );
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
    const tableRows = (rows) => top15SlideRows(rows, emissionAudit);
    const columnWidths = [22, 82, 112, 105, 100, 84, 55];
    const aligns = ["right", "left", "left", "left", "left", "left", "right"];
    addHeader(
      slide,
      "TOP 15 · OFERTAS ENCERRADAS",
      `IBBA participou de ${integer(summary2026.ibba_participation_offers_top15)} das 15 maiores em jan–jun/26; liderou ${integer(summary2026.ibba_lead_offers_top15)}`,
      "Fonte: CVM/SRE, dois arquivos de ofertas, e FundosNet. Primárias encerradas, todos os ritos; volume registrado.",
      29,
    );
    addSectionLabel(slide, "JAN–JUN/26 · TOP 15", { left: 60, top: 138, width: 560, height: 24 });
    addNativeEditorialTable(slide, {
      left: 60,
      top: 174,
      width: 560,
      height: 440,
      headers: ["#", "Emissão / CNPJ", "FIDC", "Originador / cedente", "Sub. mín. / preço por cota", "Sacado", "R$ bi"],
      rows: tableRows(table2026),
      columnWidths,
      aligns,
      fontSize: 5.5,
      headerFontSize: 5.4,
      headerHeight: 34,
      rowHighlights: new Set(
        table2026
          .map((row, index) => row.ibba_participant === true ? index : null)
          .filter((index) => index !== null),
      ),
      emphasizeHighlightedRows: true,
    });
    addSectionLabel(slide, "2025FY · TOP 15", { left: 660, top: 138, width: 560, height: 24 });
    addNativeEditorialTable(slide, {
      left: 660,
      top: 174,
      width: 560,
      height: 440,
      headers: ["#", "Emissão / CNPJ", "FIDC", "Originador / cedente", "Sub. mín. / preço por cota", "Sacado", "R$ bi"],
      rows: tableRows(table2025),
      columnWidths,
      aligns,
      fontSize: 5.5,
      headerFontSize: 5.4,
      headerHeight: 34,
      rowHighlights: new Set(
        table2025
          .map((row, index) => row.ibba_participant === true ? index : null)
          .filter((index) => index !== null),
      ),
      emphasizeHighlightedRows: true,
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
      "O = originador; C = cedente; S = subordinação mínima; P = preço de emissão por tipo de cota. CNPJ e emissão formam a chave de cada linha; N/D indica lacuna documental.",
      { left: 60, top: 641, width: 1160, height: 22 },
      { fontSize: 7.9, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "FundosNet/B3 — mesma curadoria documental flagship; fontes linha a linha na aba Auditoria emissões.",
      "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, Valor_Total_Registrado positivo e data de encerramento no período; snapshot CVM 24/jul/26.",
      "Limitação: rating sem documento público verificável ou sem vínculo exato = N/D; o volume registrado pode diferir do valor encerrado informado à ANBIMA.",
    ]);
  }

  addHistoricalTop15PairSlide(presentation, payload, "2024 FY", "2023 FY", 30);

  addConclusionsSlide(presentation, payload, 32);

  // Prestadores permanecem contíguos; market shares seguem no workbook e no explorador.
  addCombinedProviderRankingSlide(presentation, payload, 0);
  if (SLIDE_CONTRACT_V1.includes("bank_cohort")) {
    addBankFidcEvolutionSlide(presentation, payload, 0);
  }
  addProviderAttributionSlide(presentation, payload, 0);
  // A evidência detalhada de migração permanece no workbook e no
  // explorador. O slide isolado era redundante com Liderança explicada e
  // deixaria a sequência executiva acima do contrato ordinal publicado.

  addInvestorBaseSlide();
  addHolderDistributionSlide();

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
    sheet.dataValidations.clear(used.address);
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

function removeWorkbookSheets(workbook) {
  for (const sheetName of WORKBOOK_SHEETS_TO_REMOVE) {
    const sheet = workbook.worksheets.getItemOrNullObject(sheetName);
    if (!sheet.isNullObject) {
      sheet.delete();
    }
  }
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

function auditColumnWidth(header) {
  const normalized = String(header).toLowerCase();
  if (/evidencia|motivo|notas|regra|reason|source/.test(normalized)) return 420;
  if (/denominacao|nome_fidc/.test(normalized)) return 360;
  if (/classificacao|taxonomia|fic_detection/.test(normalized)) return 240;
  if (/cnpj/.test(normalized)) return 130;
  if (/competencia|updated|documento_data/.test(normalized)) return 115;
  if (/pl|valor/.test(normalized)) return 125;
  return 150;
}

function auditCellValue(header, value) {
  if (!/^cnpj(?:$|_fundo$|_formatado$|_fundo_formatado$)/i.test(String(header))) return value;
  const digits = String(value || "").replace(/\D/g, "").padStart(14, "0").slice(-14);
  if (!digits || /^0+$/.test(digits)) return value;
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
}

async function addCsvAuditSheet(workbook, {
  filePath,
  sheetName,
  title,
  subtitle,
  sourceHeaders = null,
  filter = null,
  uniqueBy = null,
}) {
  const csv = await readCsv(filePath);
  const headers = sourceHeaders || csv.headers;
  const indexByHeader = Object.fromEntries(csv.headers.map((header, index) => [header, index]));
  const selected = [];
  const selectedByKey = new Map();
  for (const values of csv.rows) {
    const row = Object.fromEntries(csv.headers.map((header, index) => [header, values[index] ?? ""]));
    if (filter && !filter(row)) continue;
    const record = Object.fromEntries(
      headers.map((header) => [header, auditCellValue(header, values[indexByHeader[header]] ?? "")]),
    );
    if (!uniqueBy) {
      selected.push(record);
      continue;
    }
    const key = String(row[uniqueBy] || "");
    const previous = selectedByKey.get(key);
    if (!previous || String(row.competencia || "") >= previous.competencia) {
      selectedByKey.set(key, { competencia: String(row.competencia || ""), record });
    }
  }
  if (uniqueBy) selected.push(...[...selectedByKey.values()].map((item) => item.record));
  const sheet = resetSheet(workbook, sheetName);
  setHeaderBand(sheet, title, subtitle, headers, selected.length, {
    freezeColumns: 2,
    wrapText: false,
    bodyFontSize: 8.5,
  });
  await writeRowsInChunks(sheet, 4, headers, selected);
  applyColumnWidths(sheet, headers.map(auditColumnWidth), selected.length);
  applyFormatsByHeader(sheet, headers, selected.length);
  headers.forEach((header, index) => {
    if (/evidencia|motivo|notas|regra|reason|source|denominacao|classificacao|taxonomia/i.test(header)) {
      const letter = columnLetter(index);
      sheet.getRange(`${letter}5:${letter}${selected.length + 4}`).format.wrapText = true;
    }
  });
  return { headers, rows: selected };
}

async function addPerimeterAuditSheets(workbook, payload) {
  const generatedAt = String(payload.generated_at || "N/D");
  const universeColumns = [
    "competencia", "cnpj", "cnpj_formatado", "cnpj_fundo", "cnpj_fundo_formatado",
    "tp_registro", "denominacao", "pl", "carteira_dc", "dc_inadimplentes",
    "dc_a_vencer_com_parcela_inad", "cotistas", "publico_alvo", "classificacao_anbima",
    "segmento_principal", "segmento_financeiro_principal", "reports_carteira_dc",
    "reports_dc_inadimplentes", "reports_aging", "is_fic", "fic_detection_method",
    "fic_detection_evidence", "fic_exclusion_reason", "regra_inclusao",
  ];
  const universe = await addCsvAuditSheet(workbook, {
    filePath: path.join(REVISION_DIR, "base_competencia_cnpj.csv.gz"),
    sheetName: "Universo elegível",
    title: "Universo elegível após o portão único de FICs",
    subtitle: `Competência ${payload.latest_complete}; fonte CVM/Informe Mensal; atualização ${generatedAt}. Regra: exclui is_fic=true antes de gráficos, rankings e agregações; a série histórica permanece nos CSVs do bundle.`,
    sourceHeaders: universeColumns,
    filter: (row) => String(row.competencia || "") === String(payload.latest_complete || "") && String(row.is_fic || "").toLowerCase() !== "true",
  });
  if (universe.rows.some((row) => row.is_fic === true || String(row.is_fic).toLowerCase() === "true")) {
    throw new Error("aba Universo elegível contém is_fic=true");
  }
  await addCsvAuditSheet(workbook, {
    filePath: path.join(DATA_DIR, "industry_fic_detection_audit.csv"),
    sheetName: "FICs excluídos",
    title: "FICs excluídos do universo analítico",
    subtitle: `Fonte industry_fic_detection_audit.csv; atualização ${generatedAt}; uma linha por CNPJ, na última competência observada. Regra: sinal nominal legado derivado da denominação social ou VL_DICRED zerado em toda a série com cotas de FIDC ≥ 50% das aplicações; o histórico completo permanece no CSV.`,
    filter: (row) => String(row.is_fic || "").toLowerCase() === "true",
    uniqueBy: "cnpj_fundo",
  });
  await addCsvAuditSheet(workbook, {
    filePath: path.join(DATA_DIR, "taxonomy_review_actions.csv"),
    sheetName: "Decisões do ledger",
    title: "Decisões completas do ledger de taxonomia",
    subtitle: `Fonte taxonomy_review_actions.csv; atualização ${generatedAt}. Todas as aprovações, rejeições, revisões e pendências permanecem no histórico auditável; nenhuma linha é deduzida pelo nome do fundo.`,
  });
}

function patchLegacyPlSheets(workbook, ficAuditRows) {
  const detected = ficAuditRows.filter((row) => String(row.is_fic || "").toLowerCase() === "true");
  const stats = new Map();
  for (const row of detected) {
    const competence = String(row.competencia || "");
    const current = stats.get(competence) || { pl: 0, cnpjs: new Set() };
    current.pl += num(row.pl);
    current.cnpjs.add(String(row.cnpj_fundo || ""));
    stats.set(competence, current);
  }
  for (const sheetName of ["PL histórico", "PL anual"]) {
    const sheet = workbook.worksheets.getItem(sheetName);
    const used = sheet.getUsedRange();
    const values = used.values;
    if (!values.length) continue;
    const headers = values[0].map((value) => String(value || "").toLowerCase());
    const competenceCol = headers.indexOf("competencia");
    const totalCol = headers.findIndex((value) => ["pl_total", "pl_total_brl"].includes(value));
    const ficCol = headers.findIndex((value) => ["pl_fic_fidc", "pl_fic_fidc_brl"].includes(value));
    const directCol = headers.findIndex((value) => ["pl_ex_fic", "pl_ex_fic_brl"].includes(value));
    const ficFundsCol = headers.indexOf("funds_fic_fidc");
    const growthCol = headers.indexOf("pl_ex_fic_growth");
    if ([competenceCol, totalCol, ficCol, directCol].some((index) => index < 0)) continue;
    let previousDirect = null;
    for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
      const competence = String(values[rowIndex][competenceCol] || "");
      const period = stats.get(competence);
      if (!period) continue;
      const total = num(values[rowIndex][totalCol]);
      const direct = total - period.pl;
      sheet.getCell(rowIndex, ficCol).values = [[period.pl]];
      sheet.getCell(rowIndex, directCol).values = [[direct]];
      if (ficFundsCol >= 0) sheet.getCell(rowIndex, ficFundsCol).values = [[period.cnpjs.size]];
      if (growthCol >= 0) {
        sheet.getCell(rowIndex, growthCol).values = [[previousDirect && previousDirect > 0 ? direct / previousDirect - 1 : null]];
      }
      previousDirect = direct;
    }
  }
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
    "Tabela I completa para aging",
    "Parcelas vincendas ligadas a inad.",
    "Gap aging vs Tabela I completa",
    "Veículos com parcelas vinculadas",
    "Veículos só com parcelas vinculadas",
    "PL dos veículos com parcelas",
    "Top 10 das parcelas",
    "Ex-360 ajustada %",
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
    "aging_tabela_i_referencia_brl",
    "aging_parcelas_inadimplentes_brl",
    "aging_gap_vs_tabela_i_completa_brl",
    "veiculos_parcelas_inadimplentes_positivas",
    "veiculos_so_parcelas_inadimplentes",
    "pl_veiculos_parcelas_inadimplentes_brl",
    "aging_parcelas_top10_share",
    "inadimplencia_ex_360d_ajustada_pct_sobre_cobertura",
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
  applyColumnWidths(sheet, [85, 80, 75, 90, 95, 110, 110, 85, 110, 110, 90, 115, 115, 80, 80, 90, 95, 110, 90, 115, 80, 80, 85, 115, 125, 125, 125, 100, 100, 125, 95, 95, 180, 85, 135], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["F", "G", "I", "J", "L", "M", "R", "T", "X", "Y", "Z", "AC"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`A5:${columnLetter(headers.length - 1)}${rows.length + 4}`).format.rowHeightPx = 22;
}

async function addVehicleCompetenceSheet(workbook, payload) {
  const csv = await readCsv(path.join(REVISION_DIR, "base_competencia_cnpj.csv.gz"));
  const competenceIndex = csv.headers.indexOf("competencia");
  const isFicIndex = csv.headers.indexOf("is_fic");
  const stockShortLower = competenceShortPt(payload.latest_complete).toLowerCase();
  const auditMonths = new Set(["2024-06", "2024-07", payload.latest_complete]);
  const scopedCsvRows = csv.rows.filter(
    (row) => auditMonths.has(row[competenceIndex]) && String(row[isFicIndex] || "").toLowerCase() !== "true",
  );
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
    ["Parcelas inad. em créditos vincendos", "dc_parcelas_inadimplentes"],
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
    `Recorte operacional de jun/24, jul/24 e ${stockShortLower}. A base longitudinal completa integra o bundle analítico da revisão. Ajustado e excesso são fórmulas.`,
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
  const sourceRows = csvRowsAsObjects(csv).filter(
    (row) => String(row.is_fic_fidc || "").toLowerCase() !== "true",
  );
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
    "Definição adotada: mesmo conglomerado econômico normalizado nas três funções. HHI em pontos de 0 a 10.000; 10.000 corresponde a um único fundo.",
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
      ["CNPJ fundo", "cnpj_fundo"],
      ["Denominação", "nome_fidc"],
      ["PL atual", "pl_atual_brl"],
      ["Competência PL", "competencia_pl"],
      ["Existente/ativo", "existente_ativo"],
      ["Cedente / originador expresso", "cedent_originator_explicit"],
      ["Evidência", "evidence_summary"],
      ["Data do regulamento", "document_reference_date"],
      ["ID do documento", "document_id"],
      ["URL FundosNet", "document_url"],
      ["Categoria proposta", "proposed_category"],
      ["Status de reclassificação", "reclassification_status"],
      ["Validação manual", "manual_validation_reason"],
      ["Método de leitura", "reading_method"],
      ["Limitações", "source_limitations"],
    ];
    const headers = columns.map(([header]) => header);
    const rows = worksheetRowsFromPayload(payload.top20_outros_regulation_review || [], columns);
    const sheet = resetSheet(workbook, "Top 20 Outros");
    const summary = payload.top20_outros_reclassification_summary || {};
    const currentOutrosBucket = (payload.type_mix_history || []).find(
      (row) => row.competencia === payload.latest_complete && row.anbima_tipo === "Outros",
    ) || {};
    const candidateShareExpandedOutros = num(currentOutrosBucket.pl)
      ? num(summary.candidate_pl_brl) / num(currentOutrosBucket.pl)
      : 0;
    setHeaderBand(sheet, "Top 20 Outros · regulamentos", `${integer(summary.candidate_funds)} candidatos somam ${bn(summary.candidate_pl_brl, 1)}: ${pct(summary.candidate_share_of_outros, 1)} do Tipo literal Outros e ${pct(candidateShareExpandedOutros, 1)} do bucket Outros do slide 8, que inclui N/D. Nenhuma mudança taxonômica foi aplicada; todos os candidatos requerem validação manual.`, headers, rows.length, { freezeColumns: 3, wrapText: true });
    await writeRowsInChunks(sheet, 4, headers, rows);
    applyColumnWidths(sheet, [70, 120, 340, 120, 90, 90, 360, 420, 110, 95, 360, 220, 160, 390, 390, 390], rows.length);
    applyFormatsByHeader(sheet, headers, rows.length);
    sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
    sheet.getRange(`A5:P${rows.length + 4}`).format.rowHeightPx = 110;
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
    ["Cobertura documental", "cobertura_documental"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.profiles, columns);
  const sheet = resetSheet(workbook, "Curadoria Top 20");
  setHeaderBand(
    sheet,
    "Curadoria Top 20",
    "Fontes primárias: CVM/FundosNet, regulamentos, ofertas, assembleias e informes. Campos lacunares permanecem vazios; o preenchimento exclui deduções pelo nome do fundo.",
    headers,
    rows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [55, 120, 340, 110, 100, 360, 340, 350, 430, 430, 430, 260, 260, 260, 150, 180, 180, 110, 150, 300, 150, 360, 110, 360, 210], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`D5:D${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`A5:Y${rows.length + 4}`).format.rowHeightPx = 120;
}

async function addReceivablesReconciliationSheet(workbook, payload) {
  const summary = payload.receivables_reconciliation_summary || [];
  const detail = (payload.receivables_reconciliation_detail || []).filter(
    (row) => num(row.rank_gap_positivo) <= 100 || row.tabela_ii_reportada === false,
  );
  const headers = [
    "Tipo de linha",
    "Competência",
    "CNPJ fundo",
    "Denominação",
    "PL",
    "Veículos",
    "Tabela I · carteira",
    "Tabela II · abertura",
    "Gap Tabela II − I",
    "Tabela II reportada",
    "Gap positivo",
    "Gap negativo",
    "Rank gap positivo",
    "Share acumulado gap positivo",
    "Fundos total",
    "Fundos sem abertura",
    "PL sem abertura",
    "Top 20 do gap positivo",
    "Fonte",
  ];
  const rows = [
    ...summary.map((row) => ({
      "Tipo de linha": "Resumo",
      "Competência": row.competencia,
      "CNPJ fundo": "",
      "Denominação": "",
      "PL": row.pl_total_brl,
      "Veículos": "",
      "Tabela I · carteira": row.tabela_i_carteira_brl,
      "Tabela II · abertura": row.tabela_ii_total_brl,
      "Gap Tabela II − I": row.gap_tabela_ii_menos_i_brl,
      "Tabela II reportada": "",
      "Gap positivo": row.gap_positivo_brl,
      "Gap negativo": row.gap_negativo_brl,
      "Rank gap positivo": "",
      "Share acumulado gap positivo": "",
      "Fundos total": row.fundos_total,
      "Fundos sem abertura": row.fundos_sem_abertura_tabela_ii,
      "PL sem abertura": row.pl_sem_abertura_tabela_ii_brl,
      "Top 20 do gap positivo": row.gap_positivo_top20_share,
      "Fonte": row.fonte,
    })),
    ...detail.map((row) => ({
      "Tipo de linha": "Fundo",
      "Competência": row.competencia,
      "CNPJ fundo": row.cnpj_fundo,
      "Denominação": row.denominacao,
      "PL": row.pl_brl,
      "Veículos": row.veiculos,
      "Tabela I · carteira": row.tabela_i_carteira_brl,
      "Tabela II · abertura": row.tabela_ii_total_brl,
      "Gap Tabela II − I": row.gap_tabela_ii_menos_i_brl,
      "Tabela II reportada": row.tabela_ii_reportada,
      "Gap positivo": row.gap_positivo_brl,
      "Gap negativo": row.gap_negativo_brl,
      "Rank gap positivo": row.rank_gap_positivo,
      "Share acumulado gap positivo": row.share_gap_positivo_acumulado,
      "Fundos total": "",
      "Fundos sem abertura": "",
      "PL sem abertura": "",
      "Top 20 do gap positivo": "",
      "Fonte": "CVM, Informe Mensal de FIDC, Tabelas I e II",
    })),
  ];
  const sheet = resetSheet(workbook, "Reconciliação Tabelas I-II");
  setHeaderBand(
    sheet,
    "Reconciliação Tabelas I e II",
    "Resumo completo, Top 100 gaps positivos por data e todos os fundos sem abertura. O detalhe integral permanece na base analítica publicada; campo ausente não é tratado como zero.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 85, 120, 300, 110, 70, 120, 120, 120, 100, 110, 110, 90, 105, 80, 105, 110, 105, 250], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
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
  payload.pl_history.forEach((row) => {
    const total = num(row.pl_ex_fic) + num(row.pl_fic_componente);
    [
      ["PL direto", row.pl_ex_fic],
      ["Saldo FIC", row.pl_fic_componente],
      ["PL total reconciliado", total],
    ].forEach(([label, value]) => rows.push({
      "Painel": "PL e saldo FIC",
      "Competência": row.competencia,
      "Categoria / função": label,
      "Quantidade": label === "Saldo FIC" ? row.fundos_fic_detectados : null,
      "Share quantidade": null,
      "PL / valor": value,
      "Share PL / valor": total ? num(value) / total : null,
      "Denominador quantidade": null,
      "Denominador PL / valor": total,
      "Cobertura PL": 1,
      "PL N/D": null,
      "Top 5": null,
      "Top 10": null,
      "Nota": row.fic_detection_rule || "Portão único de FICs.",
    }));
  });
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
    "Bases dos slides 3, 5, 6, 7 e 10. PL direto e saldo FIC reconciliam o total; recebíveis fecham sobre a soma segmentada da Tabela II.",
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
    ["Fundos com inadimplência positiva", "fundos_inadimplencia_positiva"],
    ["PL ex-zeros", "pl_inadimplencia_positiva_brl"],
    ["Carteira ex-zeros", "carteira_inadimplencia_positiva_brl"],
    ["Inadimplência ex-zeros", "inadimplencia_positiva_brl"],
    ["Inadimplência / PL ex-zeros", "inadimplencia_sobre_pl_ex_zeros"],
    ["Inadimplência / carteira ex-zeros", "inadimplencia_sobre_carteira_ex_zeros"],
    ["Variação / PL (p.p.)", "variacao_inadimplencia_sobre_pl_pp"],
    ["Variação / carteira (p.p.)", "variacao_inadimplencia_sobre_carteira_pp"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.delinquency_single_receivable || [], columns);
  const sheet = resetSheet(workbook, "Inadimplência por recebível");
  setHeaderBand(
    sheet,
    "Inadimplência por tipo de recebível único",
    "Ex-FIC com PL positivo e exatamente um campo superior da Tabela II diferente de zero. A base original inclui reportes iguais a zero; a sensibilidade ex-zeros remove esses fundos do numerador e dos denominadores.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 165, 95, 125, 125, 145, 125, 115, 130, 135, 110, 125, 125, 125, 125, 145, 115, 130], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["D", "E", "F", "G", "L", "M", "N"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`H5:J${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`O5:R${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:R${rows.length + 4}`).format.rowHeightPx = 34;

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
    ["Fundos com inadimplência positiva", "fundos_inadimplencia_positiva"],
    ["PL ex-zeros", "pl_inadimplencia_positiva_brl"],
    ["Carteira ex-zeros", "carteira_inadimplencia_positiva_brl"],
    ["Inadimplência ex-zeros", "inadimplencia_positiva_brl"],
    ["Inadimplência / PL ex-zeros", "inadimplencia_sobre_pl_ex_zeros"],
    ["Inadimplência / carteira ex-zeros", "inadimplencia_sobre_carteira_ex_zeros"],
    ["Variação / PL (p.p.)", "variacao_inadimplencia_sobre_pl_pp"],
    ["Variação / carteira (p.p.)", "variacao_inadimplencia_sobre_carteira_pp"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.delinquency_frozen_cohort_history || [], columns);
  const sheet = resetSheet(workbook, "Histórico inad. coorte");
  setHeaderBand(
    sheet,
    "Inadimplência histórica da coorte atual por tipo de recebível",
    `Coorte e subtipo congelados em ${stockShortLower}. A base original inclui reportes iguais a zero; a sensibilidade ex-zeros remove esses fundos do numerador e dos denominadores. A série incorpora viés de sobrevivência.`,
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows, 2500);
  applyColumnWidths(sheet, [90, 185, 90, 90, 90, 130, 115, 115, 125, 135, 110, 125, 125, 135, 120, 120, 110, 120, 125, 125, 125, 145, 115, 130], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["F", "G", "H", "I", "J", "R", "S", "T"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`K5:N${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`U5:X${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:X${rows.length + 4}`).format.rowHeightPx = 31;
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
    "Coorte fixa de raízes de CNPJ dos conglomerados prudenciais consultados no BCB. Dez/25 inclui o PL oficial recuperado do BTG Consignados I, com valor bruto original preservado.",
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
    "Fundos listados nos conglomerados prudenciais consultados no BCB em jul/26. O BTG Consignados I em dez/25 usa PL oficial recuperado do IME/DF, mantendo o zero bruto para auditoria. A visão retroativa acompanha somente o conjunto atual.",
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
    `${curatedCount} CNPJs compõem a abertura de Adquirência. No bucket Cartão, ${integer(cardSummary.fundos_incluidos_adquirencia)} foram incluídos, ${integer(cardSummary.fundos_fora_adquirencia)} ficaram fora e ${integer(cardSummary.fundos_pendentes_curadoria)} ${num(cardSummary.fundos_pendentes_curadoria) === 1 ? "permanece pendente" : "permanecem pendentes"}. A classificação CVM reportada continua na base detalhada.`,
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
    `${integer(summary.fundos_incluidos_adquirencia)} fundos foram associados à cadeia de pagamentos; ${integer(summary.fundos_fora_adquirencia)} ficaram fora por crédito PF/PJ, CCB ou natureza distinta; ${integer(summary.fundos_pendentes_curadoria)} ${num(summary.fundos_pendentes_curadoria) === 1 ? "permanece pendente" : "permanecem pendentes"}. PL em ${competenceShortPt(summary.competencia_pl_atual || payload.latest_complete).toLowerCase()}, com fallback ao mês anterior somente quando ausente.`,
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

async function addTop20ByTypeSheets(workbook, payload) {
  const columns = [
    ["Tipo exibido", "tipo_exibicao"],
    ["Rank", "rank_tipo"],
    ["FIDC", "denominacao"],
    ["CNPJ", "cnpj_fundo_formatado"],
    ["PL", "pl"],
    ["% do bucket", "share_tipo"],
    ["Competência", "competencia_pl"],
    ["Mai/26 disponível", "pl_anterior_positivo"],
    ["Fonte PL", "pl_source"],
    ["Tipo ANBIMA original", "anbima_tipo"],
    ["Foco ANBIMA", "anbima_foco"],
    ["Nível classificação", "classification_tier"],
    ["Status classificação", "classification_status"],
    ["Fonte classificação", "classification_source"],
    ["Data classificação", "classification_reference_date"],
    ["Limitação classificação", "classification_limitation"],
    ["Classes agregadas", "cnpj_classe_count"],
    ["Administrador", "administrador"],
    ["Fonte administrador", "administrador_source"],
    ["Gestor", "gestor"],
    ["Fonte gestor", "gestor_source"],
    ["Custodiante", "custodiante"],
    ["Fonte custodiante", "custodiante_source"],
    ["Cedente/originador expresso", "cedente_originador"],
    ["Status cedente", "cedente_status"],
    ["Regulamento ID", "regulamento_id"],
    ["Data regulamento", "regulamento_data"],
    ["URL regulamento", "regulamento_url"],
    ["Página/cláusula", "pagina_clausula"],
    ["Evidência", "evidencia_cedente"],
    ["Confiança", "confianca_cedente"],
    ["Limitação cedente", "limitacao_cedente"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.top20_by_anbima_type || [], columns);
  const sheet = resetSheet(workbook, "Top 20 por Tipo ANBIMA");
  setHeaderBand(
    sheet,
    "Top 20 FIDCs por Tipo ANBIMA",
    "Jun/26 foi escolhida por ser a competência completa mais recente: 80/80 fundos possuem PL positivo em mai/26 e jun/26. O bucket Outros incorpora N/D como no slide 8. Campos sem leitura documental concluída permanecem N/D.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [180, 65, 360, 120, 125, 95, 95, 110, 420, 170, 180, 150, 210, 300, 105, 360, 90, 260, 260, 260, 260, 260, 260, 430, 220, 95, 105, 350, 190, 480, 130, 440], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`E5:E${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  sheet.getRange(`F5:F${rows.length + 4}`).format.numberFormat = "0.0%";
  sheet.getRange(`A5:AF${rows.length + 4}`).format.rowHeightPx = 72;

  const coverageColumns = [
    ["Tipo exibido", "tipo_exibicao"],
    ["Fundos", "fundos"],
    ["PL", "pl_brl"],
    ["Administrador preenchido", "administrador_preenchido"],
    ["Gestor preenchido", "gestor_preenchido"],
    ["Custodiante preenchido", "custodiante_preenchido"],
    ["Cedente com curadoria", "cedente_curadoria_concluida"],
    ["Regulamento local sem curadoria", "regulamento_local_sem_curadoria"],
    ["Sem regulamento local", "sem_regulamento_local"],
    ["Competência PL", "competencia_pl"],
    ["Competência anterior verificada", "competencia_anterior_verificada"],
    ["Fundos com PL anterior positivo", "fundos_pl_anterior_positivo"],
    ["Critério", "criterio_competencia"],
  ];
  const coverageHeaders = coverageColumns.map(([header]) => header);
  const coverageRows = worksheetRowsFromPayload(payload.top20_by_anbima_type_coverage || [], coverageColumns);
  const coverageSheet = resetSheet(workbook, "Auditoria Top 20 Tipo");
  setHeaderBand(
    coverageSheet,
    "Cobertura · Top 20 por Tipo ANBIMA",
    "Contagens documentais e cadastrais do ranking. Sinais automáticos pendentes de cedente não são promovidos a preenchimento definitivo.",
    coverageHeaders,
    coverageRows.length,
    { freezeColumns: 1, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(coverageSheet, 4, coverageHeaders, coverageRows);
  applyColumnWidths(coverageSheet, [210, 75, 130, 145, 130, 145, 150, 175, 150, 100, 135, 160, 620], coverageRows.length);
  applyFormatsByHeader(coverageSheet, coverageHeaders, coverageRows.length);
  coverageSheet.getRange(`C5:C${coverageRows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  coverageSheet.getRange(`A5:M${coverageRows.length + 4}`).format.rowHeightPx = 54;
}

async function addTaxonomyLevelSheet(workbook, payload) {
  const levelLabels = {
    foco_analitico: "Foco analítico",
    tabela_ii_analitica: "Tabela II analítica",
    taxonomia_funcional_n1: "Taxonomia funcional N1",
    taxonomia_funcional_n2: "Taxonomia funcional N2",
  };
  const columns = [
    ["Nível", "nivel", (value) => levelLabels[value] || value],
    ["Competência", "competencia"],
    ["Tipo analítico", "tipo_exibicao"],
    ["Categoria", "categoria"],
    ["PL", "pl_brl"],
    ["PL do tipo", "pl_tipo_brl"],
    ["PL ex-FIC", "pl_total_brl"],
    ["% do tipo", "share_tipo"],
    ["% do PL ex-FIC", "share_total"],
    ["Fundos", "fundos"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.taxonomy_level_history || [], columns);
  const sheet = resetSheet(workbook, "Taxonomia por nível");
  setHeaderBand(
    sheet,
    "Taxonomia analítica por nível",
    "Foco analítico, Tabela II analítica e taxonomia funcional N1/N2. A série preserva os quatro níveis que deixaram de ocupar slides próprios; filtros por Tipo analítico permitem detalhar o bucket Outros.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: false, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [180, 95, 185, 260, 125, 125, 125, 95, 105, 75], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["E", "F", "G"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["H", "I"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  sheet.getRange(`A5:J${rows.length + 4}`).format.rowHeightPx = 24;
}

async function addFlagshipCurationSheet(workbook, payload) {
  const columns = [
    ["# família", "ordem_familia"],
    ["Categoria", "categoria"],
    ["Família flagship", "familia_flagship"],
    ["Representante", "representante_familia", (value) => num(value) === 1 ? "Sim" : "Não"],
    ["CNPJ", "cnpj_fundo_formatado"],
    ["Fundo", "denominacao"],
    ["PL atual", "pl_atual_brl"],
    ["PL subordinado atual", "pl_subordinado_atual_brl"],
    ["Subordinação atual / PL", "subordinacao_atual_pct"],
    ["Faixa atual", "faixa_subordinacao_atual"],
    ["PL das classes reportadas", "pl_classes_reportadas_brl"],
    ["Delta PL classes", "pl_reconciliacao_delta_pct", (value) => value == null ? null : num(value) / 100],
    ["Status subordinação atual", "subordinacao_atual_status"],
    ["Mínimo júnior", "subordinacao_minima_junior_pct", (value) => value == null ? null : num(value) / 100],
    ["Mínimo júnior · leitura", "subordinacao_minima_junior_display"],
    ["Subordinação contratual localizada", "subordinacao_minima_texto"],
    ["Fonte subordinação contratual", "subordinacao_minima_fonte"],
    ["Preço/VNU numérico", "preco_emissao_brl"],
    ["Preço/VNU · leitura", "preco_emissao_display"],
    ["Classe/série da emissão", "preco_emissao_classe"],
    ["Data da emissão", "preco_emissao_data"],
    ["Fonte preço/VNU", "preco_emissao_fonte"],
    ["Emissão considerada · mês/ano", "emissao_data_display"],
    ["Fonte da emissão considerada", "emissao_fonte"],
    ["Cota mezanino comprovada", "cota_mezanino"],
    ["Fonte mezanino", "cota_mezanino_fonte"],
    ["Vencimento antecipado / avaliação", "vencimento_antecipado"],
    ["Fonte vencimento antecipado", "vencimento_antecipado_fonte"],
    ["Status do pacote", "pacote_documental_status"],
    ["Pacote documental", "pacote_documental_path"],
    ["Documento do regulamento revisto", "documento_id_regulamento"],
    ["Data do regulamento revisto", "documento_data_regulamento"],
    ["Página / cláusula", "pagina_clausula"],
    ["Extensão da leitura", "paginas_lidas"],
    ["Status da curadoria documental", "status_curadoria_documental"],
    ["Observação documental", "observacao_documental"],
    ["FundosNet", "fundosnet_url"],
    ["Lacunas", "lacunas"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.flagship_curation || [], columns);
  const summary = payload.flagship_curation_summary || {};
  const sheet = resetSheet(workbook, "Curadoria flagship");
  setHeaderBand(
    sheet,
    "Curadoria comparável dos fundos flagship",
    `${integer(summary.familias)} famílias e ${integer(summary.cnpjs)} CNPJs em ${competenceShortPt(summary.competencia || payload.latest_complete).toLowerCase()}; ${integer(summary.cnpjs_com_subordinacao_atual)} com subordinação atual, ${integer(summary.cnpjs_com_minimo_junior)} com mínimo júnior e ${integer(summary.cnpjs_com_preco_vnu)} com preço/VNU localizado. Ausências permanecem N/D.`,
    headers,
    rows.length,
    { freezeColumns: 6, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [70, 190, 260, 95, 125, 390, 125, 135, 120, 95, 135, 105, 300, 100, 125, 520, 440, 115, 135, 220, 105, 440, 120, 440, 125, 420, 620, 440, 230, 260, 170, 115, 150, 120, 230, 420, 360, 360],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  ["G", "H", "K"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["I", "L", "N"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  sheet.getRange(`R5:R${rows.length + 4}`).format.numberFormat = 'R$ #,##0.00';
  const rangeColors = {
    "< 10%": "#ECEEEF",
    "10%–15%": "#D7DADD",
    "15%–20%": "#BEC2C5",
    "20%–35%": "#E8BE9D",
    "35%–60%": "#F29A52",
    "≥ 60%": C.orange,
  };
  rows.forEach((row, index) => {
    const fill = rangeColors[row["Faixa atual"]] || C.white;
    const cell = sheet.getRange(`J${index + 5}:J${index + 5}`);
    cell.format.fill = fill;
    cell.format.font = {
      name: "Arial",
      size: 9,
      bold: true,
      color: row["Faixa atual"] === "≥ 60%" ? C.white : C.charcoal,
    };
  });
  sheet.getRange(`A5:AL${rows.length + 4}`).format.rowHeightPx = 72;
}

async function addCarteira1CurationSheet(workbook, payload) {
  const columns = [
    ["#", "ordem"],
    ["Imagem", "imagem"],
    ["Raiz CNPJ · foto", "raiz_cnpj_foto"],
    ["Nome · foto", "nome_foto"],
    ["Status identidade", "status_identidade"],
    ["Regra identidade", "regra_identidade"],
    ["Observação identidade", "observacao_identidade"],
    ["CNPJ", "cnpj_fundo_formatado"],
    ["Denominação oficial", "denominacao"],
    ["PL atual", "pl_atual_brl"],
    ["PL subordinado atual", "pl_subordinado_atual_brl"],
    ["Subordinação atual / PL", "subordinacao_atual_pct"],
    ["Faixa atual", "faixa_subordinacao_atual"],
    ["Status subordinação atual", "subordinacao_atual_status"],
    ["Mínimo júnior", "subordinacao_minima_junior_pct", (value) => value == null ? null : num(value) / 100],
    ["Mínimo júnior · leitura", "subordinacao_minima_junior_display"],
    ["Cláusula / leitura", "subordinacao_minima_texto"],
    ["Fonte do mínimo", "subordinacao_minima_fonte"],
    ["Data da emissão considerada", "emissao_data"],
    ["Emissão · mês/ano", "emissao_data_display"],
    ["Fonte da emissão", "emissao_fonte"],
    ["Tipo exibido", "tipo_exibicao"],
    ["Foco exibido", "foco_exibicao"],
    ["Competência da classificação", "competencia_classificacao"],
    ["Fonte classificação", "classificacao_fonte"],
    ["Família flagship de referência", "familia_flagship_referencia"],
    ["Regra da família", "familia_flagship_regra"],
    ["Documento do regulamento", "documento_id_regulamento"],
    ["Data do regulamento", "documento_data_regulamento"],
    ["Página / cláusula", "pagina_clausula"],
    ["Páginas lidas", "paginas_lidas"],
    ["Status curadoria documental", "status_curadoria_documental"],
    ["Observação documental", "observacao_documental"],
    ["FundosNet", "fundosnet_url"],
    ["Lacunas", "lacunas"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.carteira_1_curation || [], columns);
  const summary = payload.carteira_1_curation_summary || {};
  if (rows.length !== 101) {
    throw new Error(`Carteira 1 deveria conter 101 linhas; contém ${rows.length}.`);
  }
  const sheet = resetSheet(workbook, "Carteira 1 curadoria");
  setHeaderBand(
    sheet,
    "Carteira 1 · curadoria comparável",
    `101 CNPJs transcritos das três imagens; ${integer(summary.cnpjs_localizados_base_fidc)} com PL em ${competenceShortPt(summary.competencia || payload.latest_complete).toLowerCase()}, ${integer(summary.cnpjs_com_subordinacao_atual)} com subordinação atual, ${integer(summary.cnpjs_com_minimo_junior)} com mínimo júnior e ${integer(summary.cnpjs_com_data_emissao)} com data de emissão. Lacunas permanecem N/D.`,
    headers,
    rows.length,
    { freezeColumns: 9, wrapText: true, bodyFontSize: 8.2 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [45, 105, 95, 260, 125, 225, 280, 125, 390, 120, 135, 120, 95, 300, 100, 125, 520, 430, 110, 105, 430, 170, 235, 105, 185, 230, 270, 120, 110, 150, 90, 220, 380, 360, 360],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  ["J", "K"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.00';
  });
  ["L", "O"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  const rangeColors = {
    "< 10%": "#ECEEEF",
    "10%–15%": "#D7DADD",
    "15%–20%": "#BEC2C5",
    "20%–35%": "#E8BE9D",
    "35%–60%": "#F29A52",
    "≥ 60%": C.orange,
    "N/D": C.pale,
  };
  rows.forEach((row, index) => {
    const value = row["Faixa atual"];
    const cell = sheet.getRange(`M${index + 5}:M${index + 5}`);
    cell.format.fill = rangeColors[value] || C.white;
    cell.format.font = {
      name: "Arial",
      size: 9,
      bold: true,
      color: value === "≥ 60%" ? C.white : C.charcoal,
    };
  });
  sheet.getRange(`A5:AI${rows.length + 4}`).format.rowHeightPx = 78;
}

async function addCarteira1TaxonomySheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Período", "period_label"],
    ["Ordem período", "period_order"],
    ["Ordem categoria", "category_order"],
    ["Tipo ANBIMA reclassificado", "anbima_tipo"],
    ["PL Carteira 1", "portfolio_pl_brl"],
    ["% PL Carteira 1", "portfolio_share"],
    ["Fundos observados na categoria", "portfolio_funds"],
    ["PL total Carteira 1", "portfolio_total_brl"],
    ["CNPJs no escopo", "scope_cnpjs"],
    ["CNPJs observados", "observed_cnpjs"],
    ["Cobertura do escopo", "coverage_scope_share"],
    ["PL mercado ex-FIC", "market_pl_brl"],
    ["% PL mercado ex-FIC", "market_share"],
    ["PL total mercado ex-FIC", "market_total_brl"],
    ["Crescimento Carteira 1 desde dez/23", "portfolio_growth_since_start"],
    ["Crescimento mercado desde dez/23", "market_growth_since_start"],
    ["Δ participação Carteira 1", "portfolio_share_delta_pp"],
    ["Δ participação mercado", "market_share_delta_pp"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.carteira_1_taxonomy_history || [], columns);
  const summary = payload.carteira_1_taxonomy_summary || {};
  if (rows.length !== 16) {
    throw new Error(`Carteira 1 evolução deveria conter 16 linhas; contém ${rows.length}.`);
  }
  const sheet = resetSheet(workbook, "Carteira 1 evolução");
  setHeaderBand(
    sheet,
    "Carteira 1 · evolução pela taxonomia reclassificada",
    `${integer(summary.scope_cnpjs)} CNPJs salvos; ${integer(summary.latest_observed_cnpjs)} observados em ${competenceShortPt(payload.latest_complete).toLowerCase()}. Mercado e carteira usam as mesmas quatro categorias; ausência não recebe PL imputado.`,
    headers,
    rows.length,
    { freezeColumns: 5, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [95, 75, 75, 85, 215, 125, 105, 115, 130, 90, 100, 105, 130, 105, 135, 130, 130, 120, 120], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["F", "I", "M", "O"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["G", "L", "N", "P", "Q", "R", "S"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  sheet.getRange(`A5:S${rows.length + 4}`).format.rowHeightPx = 32;
}

async function addCarteira1FlagshipComparisonSheet(workbook, payload) {
  const columns = [
    ["Ordem", "ordem"],
    ["Taxonomia rasa", "taxonomia_rasa"],
    ["Tipo", "tipo_comparacao"],
    ["Perfil de risco aceito", "perfil_risco_aceito"],
    ["Fonte do perfil", "perfil_risco_fonte"],
    ["Carteira I · CNPJs", "carteira_1_cnpjs"],
    ["Carteira I · CNPJs com subordinação", "carteira_1_cnpjs_com_subordinacao"],
    ["Carteira I · PL", "carteira_1_pl_brl"],
    ["Carteira I · subordinação mediana", "carteira_1_subordinacao_mediana_pct"],
    ["Carteira I · mínimo júnior mediano", "carteira_1_minimo_junior_mediano_pct", (value) => value == null ? null : num(value) / 100],
    ["Flagships · CNPJs", "flagship_cnpjs"],
    ["Flagships · CNPJs com subordinação", "flagship_cnpjs_com_subordinacao"],
    ["Flagships · PL", "flagship_pl_brl"],
    ["Flagships · subordinação mediana", "flagship_subordinacao_mediana_pct"],
    ["Flagships · mínimo júnior mediano", "flagship_minimo_junior_mediano_pct", (value) => value == null ? null : num(value) / 100],
    ["Δ subordinação mediana", "delta_subordinacao_mediana_pp", (value) => value == null ? null : num(value) / 100],
    ["Leitura de risco estrutural", "leitura_risco_estrutural"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.carteira_1_flagship_comparison || [], columns);
  const summary = payload.carteira_1_flagship_comparison_summary || {};
  if (rows.length !== 7 || num(summary.flagship_cnpjs) !== 47) {
    throw new Error("Carteira 1 vs flagships deveria conter sete tipos e 47 CNPJs flagship.");
  }
  const sheet = resetSheet(workbook, "Carteira 1 vs flagships");
  setHeaderBand(
    sheet,
    "Carteira 1 vs. 47 CNPJs flagship",
    `${integer(summary.carteira_1_cnpjs_classificados)}/${integer(summary.carteira_1_cnpjs)} CNPJs da Carteira I classificados em sete tipos. ${summary.metodologia || ""}`,
    headers,
    rows.length,
    { freezeColumns: 5, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [60, 190, 145, 285, 280, 90, 145, 125, 145, 145, 90, 145, 125, 145, 145, 125, 290], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["H", "M"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["I", "J", "N", "O", "P"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  sheet.getRange(`A5:Q${rows.length + 4}`).format.rowHeightPx = 46;
}

async function addTop100OutrosSheet(workbook, payload) {
  const columns = [
    ["Competência PL", "competencia_pl"],
    ["# Outros slide", "rank_outros_slide"],
    ["CNPJ", "cnpj_fundo_formatado"],
    ["FIDC", "denominacao"],
    ["PL", "pl"],
    ["Bucket slide atual", "bucket_slide_atual"],
    ["Tipo ANBIMA oficial", "anbima_tipo_oficial"],
    ["Foco ANBIMA oficial", "anbima_foco_oficial"],
    ["Fonte ANBIMA", "classification_source"],
    ["Data ANBIMA", "anbima_referencia"],
    ["Tabela II reportada", "tabela_ii_reportada"],
    ["Tabela II dominante", "tabela_ii_dominante"],
    ["Multissegmento", "tabela_ii_multisegmento"],
    ["Documento ID", "documento_id_base"],
    ["Data documento", "documento_data_base"],
    ["URL documento", "documento_url_base"],
    ["Página/cláusula", "pagina_clausula_base"],
    ["Evidência documental", "evidencia_documental"],
    ["Cedente/originador expresso", "cedente_originador_expresso"],
    ["Taxonomia funcional N1", "taxonomia_funcional_n1_sugerida"],
    ["Taxonomia funcional N2", "taxonomia_funcional_n2_sugerida"],
    ["Tipo ANBIMA proposto", "tipo_anbima_sugerido"],
    ["Foco ANBIMA proposto", "foco_anbima_sugerido"],
    ["Tabela II proposta", "tabela_ii_sugerida"],
    ["Correção de perímetro", "perimeter_proposal"],
    ["FIC-FIDC sugerido", "is_fic_fidc_sugerido"],
    ["Confiança", "confianca_base"],
    ["Status revisão", "status_revisao_base"],
    ["Motivo validação manual", "motivo_validacao_manual_base"],
    ["Status ação", "acao_status"],
    ["Tipo analítico aplicado", "anbima_tipo_curado"],
    ["Foco analítico aplicado", "anbima_foco_curado"],
    ["Tabela II aplicada", "tabela_ii_curada"],
    ["Decisão aplicada", "taxonomy_review_applied"],
    ["PL candidato", "pl_candidato_documental_brl"],
    ["PL correção perímetro", "pl_correcao_perimetro_candidata_brl"],
    ["PL aprovado", "pl_reclassificado_aprovado_brl"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.top100_outros_review || [], columns);
  const summary = payload.top100_outros_summary || {};
  const sheet = resetSheet(workbook, "Curadoria Outros Top 100");
  setHeaderBand(
    sheet,
    "100 maiores FIDCs do bucket Outros",
    `Bucket publicado: ${bn(summary.outros_oficial_brl, 1)}. ${integer(summary.candidatos_documentais)} propostas documentais somam ${bn(summary.candidatos_documentais_brl, 1)} — ${bn(summary.candidatos_reclassificacao_tipo_brl, 1)} por Tipo e ${bn(summary.candidatos_correcao_perimetro_brl, 1)} por perímetro ex-FIC — e deixariam ${bn(summary.outros_pos_candidatos_brl, 1)}. Mesmo a migração integral do Top 100 deixaria ${bn(summary.residual_minimo_top100_brl, 1)}.`,
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [95, 75, 120, 370, 125, 120, 155, 170, 300, 100, 520, 160, 100, 95, 105, 350, 180, 480, 420, 200, 220, 190, 210, 210, 105, 150, 95, 150, 440, 120, 180, 190, 150, 95, 125, 135, 125], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`E5:E${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  ["PL candidato", "PL correção perímetro", "PL aprovado"].forEach((header) => {
    const letter = columnLetter(headers.indexOf(header));
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  const lastColumn = columnLetter(headers.length - 1);
  sheet.getRange(`A5:${lastColumn}${rows.length + 4}`).format.rowHeightPx = 92;
}

async function addDelinquencyDispersionSheet(workbook, payload) {
  const columns = [
    ["Competência", "competencia"],
    ["Subcategoria Tabela II", "tipo_recebivel_tabela_ii"],
    ["Fundos reportantes", "fundos_reportantes_inadimplencia"],
    ["PL reportantes", "pl_reportantes_inadimplencia_brl"],
    ["Carteira reportantes", "carteira_reportantes_inadimplencia_brl"],
    ["Inadimplência total", "inadimplencia_total_subcategoria_brl"],
    ["Top 1 · R$", "top1_inadimplencia_brl"],
    ["Top 1 · %", "top1_share"],
    ["Top 3 · R$", "top3_inadimplencia_brl"],
    ["Top 3 · %", "top3_share"],
    ["Top 5 · R$", "top5_inadimplencia_brl"],
    ["Top 5 · %", "top5_share"],
    ["HHI", "hhi"],
    ["Número efetivo", "numero_efetivo_fundos"],
    ["Gini", "gini"],
    ["Leitura", "leitura_concentracao"],
    ["Implicação", "implicacao_analitica"],
    ["Regra", "regra_leitura"],
    ["Fonte", "fonte"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.delinquency_dispersion || [], columns);
  const summary = payload.delinquency_dispersion_summary || {};
  const sheet = resetSheet(workbook, "Dispersão inadimplência");
  setHeaderBand(
    sheet,
    "Dispersão da inadimplência entre fundos com reporte positivo",
    `${integer(summary.fundos_reportantes_inadimplencia_positiva)} fundos positivos em uma coorte tipo único de ${integer(summary.fundos_coorte_tipo_unico)}; universo ex-FIC positivo de ${integer(summary.fundos_universo_ex_fic_pl_positivo)} fundos e ${bn(summary.pl_universo_ex_fic_positivo_brl, 1)}.`,
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [90, 210, 95, 125, 135, 130, 115, 85, 115, 85, 115, 85, 75, 100, 75, 220, 430, 450, 330], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["D", "E", "F", "G", "I", "K"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["H", "J", "L"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.00%";
  });
  sheet.getRange(`M5:O${rows.length + 4}`).format.numberFormat = "0.000";
  sheet.getRange(`A5:S${rows.length + 4}`).format.rowHeightPx = 48;
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
    "CVM/SRE, oferta_resolucao_160.csv + oferta_distribuicao.csv, snapshot 24/jul/26. Ofertas públicas primárias encerradas, todos os ritos disponíveis, data de encerramento no período e valor registrado positivo.",
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
    "CVM/SRE, oferta_resolucao_160.csv + oferta_distribuicao.csv, snapshot 24/jul/26. Ofertas públicas primárias encerradas, todos os ritos disponíveis, volume registrado; 2026 compara jan–jun com jan–jun/25.",
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

async function addBcbExpandedCreditSheet(workbook, payload) {
  const columns = [
    ["Ordem", "period_order"],
    ["Competência", "competencia"],
    ["Período", "period_label"],
    ["Último ponto", "is_latest"],
    ["Carteira de Crédito Privada Ampliada", "private_expanded_credit_total_brl"],
    ["Crédito Ampliado BCB · inclui títulos públicos", "expanded_credit_total_brl"],
    ["Empréstimos", "loans_brl"],
    ["Títulos públicos", "public_debt_brl"],
    ["Títulos privados", "private_debt_brl"],
    ["FIDCs · carteira", "fidc_receivables_brl"],
    ["Outras securitizações", "other_securitization_brl"],
    ["Dívida externa", "external_debt_brl"],
    ["Títulos de dívida", "debt_securities_brl"],
    ["Securitização BCB", "securitization_brl"],
    ["Reconciliação total", "bcb_total_reconciliation_brl"],
    ["Reconciliação títulos", "bcb_debt_reconciliation_brl"],
    ["Reconciliação empréstimos", "bcb_loans_reconciliation_brl"],
    ["Fonte BCB", "source_bcb"],
    ["Fonte CVM", "source_cvm"],
    ["Metodologia", "methodology"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.bcb_expanded_credit || [], columns);
  const sheet = resetSheet(workbook, "Crédito Privado Ampliado");
  setHeaderBand(
    sheet,
    "Carteira de Crédito Privada Ampliada e FIDCs",
    "Fonte: Banco Central do Brasil. Série de carteira de crédito ampliada, excluídos títulos públicos. As securitizações são abertas entre (i) FIDCs e (ii) demais securitizações, correspondentes a CRIs e CRAs. O total BCB com títulos públicos permanece em coluna separada para reconciliação.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [65, 95, 80, 80, 155, 155, 115, 115, 115, 115, 130, 115, 115, 115, 110, 110, 125, 360, 360, 620],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  ["E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat =
      'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`A5:T${rows.length + 4}`).format.rowHeightPx = 42;
}

async function addClosedOfferPlacementRegimeSheet(workbook, payload) {
  const columns = [
    ["Ordem período", "period_order"],
    ["Período", "period_label"],
    ["Início", "period_start"],
    ["Fim", "period_end"],
    ["Ano completo", "is_full_year"],
    ["Ordem regime", "regime_order"],
    ["Regime de colocação", "placement_regime"],
    ["Ofertas encerradas", "closed_offers"],
    ["Share das ofertas", "closed_offers_share"],
    ["Volume registrado", "registered_volume_brl"],
    ["Share do volume", "registered_volume_share"],
    ["Ofertas no período", "period_closed_offers"],
    ["Volume do período", "period_registered_volume_brl"],
    ["Fonte", "source_url"],
    ["Escopo", "scope"],
    ["Metodologia", "methodology"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(
    payload.closed_offer_placement_regime || [],
    columns,
  );
  const sheet = resetSheet(workbook, "Regime de colocação");
  setHeaderBand(
    sheet,
    "Ofertas encerradas por regime de colocação",
    "CVM, campo Regime_distribuicao. Garantia Firme de Colocação e de Liquidação são consolidadas em Garantia firme; cada período reconcilia com a coorte de ofertas encerradas.",
    headers,
    rows.length,
    { freezeColumns: 7, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [75, 105, 95, 95, 85, 75, 155, 100, 100, 130, 100, 105, 135, 300, 420, 560],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  ["J", "M"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat =
      'R$ #,##0.0,,, "bi"';
  });
  ["I", "K"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat =
      "0.00%";
  });
  sheet.getRange(`A5:P${rows.length + 4}`).format.rowHeightPx = 42;
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
    "2024 e 2025 usam o ano completo; 2026 usa jan–jun. Ticket = volume registrado por oferta reconciliada; classes do mesmo FIDC são somadas nos ritos ordinários/legados.",
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
    `Fontes: CVM, ANBIMA e BCB; coorte bancária dos conglomerados prudenciais. PL em ${stockShortLower}; ofertas encerradas até 30/jun/26.`,
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
    ["IBBA Coord?", "ibba_participant_label"],
    ["Entidades Itaú participantes", "ibba_participant_entities"],
    ["Papéis Itaú", "ibba_participant_roles"],
    ["Fonte participação", "ibba_participation_source"],
    ["URL participantes SRE", "participants_source_url"],
    ["Anúncio de encerramento", "closing_document_url"],
    ["Regime de distribuição", "distribution_regime"],
    ["Garantia Firme?", "firm_commitment_label"],
    ["Público", "publico"],
    ["Nº de Inv.", "investor_count"],
    ["Abertura de investidores", "investor_categories"],
    ["Pessoa física", "investor_person_natural"],
    ["Fundos", "investor_funds"],
    ["Instituições financeiras", "investor_financial_institutions"],
    ["Demais pessoas jurídicas", "investor_other_legal_entities"],
    ["Previdência", "investor_pension"],
    ["Seguradoras", "investor_insurers"],
    ["Investidor estrangeiro", "investor_foreign"],
    ["Clubes", "investor_clubs"],
    ["Coordenadores", "coordinator_entities"],
    ["Coordenadores com garantia firme", "firm_commitment_coordinators"],
    ["Valor garantido por coordenador", "firm_commitment_amount_by_coordinator"],
    ["Limitação garantia firme", "firm_commitment_source_limitation"],
    ["Agência de rating", "rating_agency"],
    ["Rating", "rating_assigned"],
    ["Escopo do rating", "rating_scope"],
    ["ID documento rating", "latest_document_id"],
    ["Data documento rating", "latest_document_date"],
    ["Fonte documental rating", "rating_source_type"],
    ["URL documento rating", "rating_source_url"],
    ["Vínculo rating-oferta", "rating_match_status"],
    ["Evidência rating-oferta", "rating_evidence"],
    ["Disponibilidade rating", "rating_availability_status"],
    ["Limitação rating", "rating_limitation"],
    ["Campo-fonte do originador", "originator_source"],
    ["Evidência do originador", "originator_evidence"],
    ["Evidência documental do originador", "originator_evidence_document"],
    ["Confiança da curadoria", "originator_confidence"],
    ["Método de leitura", "document_text_method"],
    ["Status da revisão", "review_status"],
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
  const orderedSummaries = (payload.closed_offer_top15_summary || [])
    .slice()
    .sort((a, b) => num(a.period_order) - num(b.period_order));
  const summary2023 = summaries["2023 FY"] || {};
  const summary2024 = summaries["2024 FY"] || {};
  const sheet = resetSheet(workbook, "Top 15 ofertas");
  setHeaderBand(
    sheet,
    "Top 15 ofertas encerradas por período",
    `2024FY: ${bn(summary2024.top15_registered_volume_brl, 2)} (${pct(summary2024.top15_share_of_period_volume, 1)} do período), ante ${bn(summary2023.top15_registered_volume_brl, 2)} em 2023FY. 2022 possui sete observações legadas e é parcial, sem comparabilidade anual.`,
    headers,
    rows.length,
    { freezeColumns: 8, wrapText: true, bodyFontSize: 8 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [100, 65, 115, 105, 120, 360, 170, 170, 125, 290, 105, 105, 280, 120, 180, 320, 320, 170, 95, 100, 85, 360, 85, 85, 105, 110, 85, 85, 105, 70, 320, 340, 210, 360, 130, 160, 260, 110, 110, 130, 360, 240, 360, 190, 360, 125, 320, 360, 110, 120, 115, 90, 100, 320, 420, 420],
    rows.length,
  );
  applyFormatsByHeader(sheet, headers, rows.length);
  sheet.getRange(`I5:I${rows.length + 4}`).format.numberFormat = 'R$ #,##0.00,,, "bi"';
  sheet.getRange(`U5:U${rows.length + 4}`).format.numberFormat = "#,##0";
  sheet.getRange(`A5:${columnLetter(headers.length - 1)}${rows.length + 4}`).format.rowHeightPx = 54;

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
    "% rito automático · volume",
    "Comparabilidade",
  ];
  sheet.getRange(`A${summaryRow}:K${summaryRow}`).values = [summaryHeaders];
  sheet.getRange(`A${summaryRow}:K${summaryRow}`).format.fill = C.black;
  sheet.getRange(`A${summaryRow}:K${summaryRow}`).format.font = {
    name: "Arial",
    size: 8,
    bold: true,
    color: C.white,
  };
  const summaryRows = orderedSummaries.map((row) => [
    row.period_label,
    row.period_closed_offers,
    row.period_registered_volume_brl,
    row.top15_registered_volume_brl,
    row.top15_share_of_period_volume,
    row.ibba_lead_offers_top15,
    row.ibba_lead_volume_top15_brl,
    row.firm_commitment_offers_top15,
    row.firm_commitment_volume_top15_brl,
    row.automatic_rite_registered_volume_share,
    row.comparability_status,
  ]);
  sheet.getRange(`A${summaryRow + 1}:K${summaryRow + summaryRows.length}`).values = summaryRows;
  sheet.getRange(`A${summaryRow + 1}:K${summaryRow + summaryRows.length}`).format.font = {
    name: "Arial",
    size: 8,
    color: C.charcoal,
  };
  ["C", "D", "G", "I"].forEach((letter) => {
    sheet.getRange(`${letter}${summaryRow + 1}:${letter}${summaryRow + summaryRows.length}`).format.numberFormat =
      'R$ #,##0.00,,, "bi"';
  });
  ["E", "J"].forEach((letter) => {
    sheet.getRange(`${letter}${summaryRow + 1}:${letter}${summaryRow + summaryRows.length}`).format.numberFormat = "0.00%";
  });
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
    { "Seção": "Resumo", "Participante": "BTG Pactual", "Competência": payload.latest_complete, "Métrica": "Coorte bancária listada", "Valor / PL": bankCohort.cohortPl, "Fundos": bankCohort.observedFunds, "Fonte / metodologia": `${integer(bankCohort.listedRoots)} raízes na coorte bancária curada a partir do BCB; PL bruto observado no Informe Mensal` },
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
        "Fonte / metodologia": row.source_reference || "Coorte bancária curada a partir do BCB; CVM, Informe Mensal",
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
      "Fonte / metodologia": "Cenário retira os FIDCs da coorte com BTG no papel analisado; coorte bancária curada a partir do BCB; CVM, Informe Mensal",
    });
  });
  const sheet = resetSheet(workbook, "Atribuição prestadores");
  setHeaderBand(
    sheet,
    "Atribuição das lideranças de prestadores",
    `QI/Singulare separados por CNPJ legal em dez/24. A coorte BTG vem dos conglomerados prudenciais do BCB; PL CVM de ${competenceShortPt(payload.latest_complete).toLowerCase()}. O recorte não atribui controle societário.`,
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
    ["Slides no contrato ordinal", EXPECTED_SLIDES, 26, '=IF(B9=C9,"OK","ERRO")'],
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
    ["Ofertas anuais 2022–2026", (payload.closed_offers_annual || []).length, 5, '=IF(B20=C20,"OK","ERRO")'],
    ["Originadores nomináveis 2026", (payload.closed_offer_originators_2026 || []).length, 17, '=IF(B21=C21,"OK","ERRO")'],
    ["Comparativo renda fixa", (payload.fixed_income_offer_comparison || []).length, 28, '=IF(B22=C22,"OK","ERRO")'],
    ["Regime de colocação", (payload.closed_offer_placement_regime || []).length, 12, '=IF(B23=C23,"OK","ERRO")'],
    ["Reconciliação CVM x ANBIMA", (payload.market_offer_reconciliation || []).length, 20, '=IF(B24=C24,"OK","ERRO")'],
    ["Auditoria de emissões", (payload.emission_field_audit || []).length, 180, '=IF(B25=C25,"OK","ERRO")'],
    ["Emissões por categoria: 4 tipos × 5 períodos", (payload.issuance_taxonomy || []).length, 20, '=IF(B26=C26,"OK","ERRO")'],
    ["Reconciliação da taxonomia de emissões", (payload.issuance_taxonomy_reconciliation || []).every((row) => Math.abs(num(row.total_brl) + num(row.fic_excluded_brl) - num(row.emitted_volume_brl)) <= 0.01) ? 1 : 0, 1, '=IF(B27=C27,"OK","ERRO")'],
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

async function addOfferValidationSheet(workbook, payload) {
  const columns = [
    ["Período", "period_label"],
    ["Instrumento", "instrument_label"],
    ["CVM · volume registrado", "cvm_registered_volume_brl"],
    ["Ponte taxonômica", "cvm_harmonization_volume_brl"],
    ["CVM harmonizado", "cvm_harmonized_volume_brl"],
    ["ANBIMA · valor encerrado", "anbima_closed_volume_brl"],
    ["Diferença bruta", "raw_gap_brl"],
    ["Diferença bruta %", "raw_gap_pct"],
    ["Diferença harmonizada", "harmonized_gap_brl"],
    ["Diferença harmonizada %", "harmonized_gap_pct"],
    ["Explicação principal", "primary_explanation"],
    ["Fonte CVM", "cvm_source_url"],
    ["Data CVM", "cvm_source_as_of_date"],
    ["Métrica CVM", "cvm_metric"],
    ["Escopo CVM", "cvm_scope"],
    ["Fonte ANBIMA", "anbima_source_url"],
    ["Snapshot ANBIMA", "anbima_source_snapshot"],
    ["Aba ANBIMA", "anbima_source_sheet"],
    ["Métrica ANBIMA", "anbima_metric"],
    ["Escopo ANBIMA", "anbima_scope"],
    ["Limitação", "limitation"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.market_offer_reconciliation || [], columns);
  const sheet = resetSheet(workbook, "Validação emissões");
  setHeaderBand(
    sheet,
    "Reconciliação CVM x ANBIMA por instrumento",
    "CVM: ofertas públicas primárias encerradas, todos os ritos disponíveis, valor registrado. ANBIMA: ofertas públicas encerradas, Valor Encerrado; 2026 = jan–mai. A ponte taxonômica soma Outros títulos de securitização somente a debêntures.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [105, 125, 135, 125, 135, 140, 125, 100, 145, 115, 480, 320, 105, 105, 520, 320, 110, 105, 115, 420, 560], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["C", "D", "E", "F", "G", "I"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  ["H", "J"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  sheet.getRange(`A5:U${rows.length + 4}`).format.rowHeightPx = 78;
}

async function addIssuanceTaxonomySheet(workbook, payload) {
  const table = payload.issuance_taxonomy_table || [];
  const reconciliation = payload.issuance_taxonomy_reconciliation || [];
  if (table.length !== 4 || reconciliation.length !== 5) {
    throw new Error("Emissões por categoria deveria conter quatro categorias e cinco períodos.");
  }
  const headers = [
    "Categoria",
    "2023 (R$ bi)",
    "2023 (%)",
    "2024 (R$ bi)",
    "2024 (%)",
    "Delta 2023→2024 (R$ bi)",
    "2025 (R$ bi)",
    "2025 (%)",
    "Delta 2024→2025 (R$ bi)",
    "jan–jun/25 (R$ bi)",
    "jan–jun/25 (%)",
    "jan–jun/26 (R$ bi)",
    "jan–jun/26 (%)",
    "Delta jan–jun/25→jan–jun/26 (R$ bi)",
  ];
  const total = { Categoria: "Total (quatro tipos ANBIMA)" };
  headers.slice(1).forEach((header) => {
    total[header] = header.endsWith("(%)")
      ? 1
      : table.reduce((sum, row) => sum + num(row[header]), 0);
  });
  const byPeriod = Object.fromEntries(reconciliation.map((row) => [row.period_key, row]));
  const periodKeys = ["2023", "2024", "2025", "jun25", "jun26"];
  const volumeKeys = [
    "2023 (R$ bi)", "2024 (R$ bi)", "2025 (R$ bi)",
    "jan–jun/25 (R$ bi)", "jan–jun/26 (R$ bi)",
  ];
  const shareKeys = [
    "2023 (%)", "2024 (%)", "2025 (%)", "jan–jun/25 (%)", "jan–jun/26 (%)",
  ];
  const bridge = (label, field) => {
    const row = { Categoria: label };
    periodKeys.forEach((periodKey, index) => {
      row[volumeKeys[index]] = num(byPeriod[periodKey]?.[field]) / 1e9;
      row[shareKeys[index]] = null;
    });
    row["Delta 2023→2024 (R$ bi)"] = row[volumeKeys[1]] - row[volumeKeys[0]];
    row["Delta 2024→2025 (R$ bi)"] = row[volumeKeys[2]] - row[volumeKeys[1]];
    row["Delta jan–jun/25→jan–jun/26 (R$ bi)"] = row[volumeKeys[4]] - row[volumeKeys[3]];
    return row;
  };
  const materialized = [
    ...table,
    total,
    bridge("FIC-FIDC (fora dos quatro tipos)", "fic_excluded_brl"),
    bridge("Total emitido", "emitted_volume_brl"),
  ];
  const rows = materialized.map((row) => headers.map((header) => row[header] ?? null));
  const sheet = resetSheet(workbook, "Emissões por categoria");
  setHeaderBand(
    sheet,
    "Emissões por Categoria ANBIMA",
    "Mesma tabela do slide anual e do explorador. Quatro tipos analíticos; FIC-FIDC fica na ponte e os dois blocos reconciliam com o volume emitido. 2023 usa o nível encerrado ANBIMA e a composição observada na CVM.",
    headers,
    rows.length,
    { freezeColumns: 1, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [230, 105, 90, 105, 90, 140, 105, 90, 140, 115, 100, 115, 100, 180], rows.length);
  ["B", "D", "F", "G", "I", "J", "L", "N"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = '0.0 "bi"';
  });
  ["C", "E", "H", "K", "M"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = "0.0%";
  });
  sheet.getRange(`A5:N${rows.length + 4}`).format.rowHeightPx = 28;
}

async function addOfferTargetPublicSheet(workbook, payload) {
  const columns = [
    ["Período", "period_label"],
    ["Público-alvo CVM", "target_public"],
    ["Ofertas", "offers"],
    ["Volume registrado", "registered_volume_brl"],
    ["% do volume do período", "share_registered_volume"],
    ["Volume do período", "period_registered_volume_brl"],
    ["Fonte", "source"],
    ["Link", "source_url"],
    ["Data da fonte", "source_as_of_date"],
    ["Limitação", "limitation"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.offer_target_public_shares || [], columns);
  const sheet = resetSheet(workbook, "Público-alvo ofertas");
  setHeaderBand(
    sheet,
    "Volume emitido por público-alvo CVM",
    "CVM/SRE, dois arquivos de ofertas; mesma coorte primária encerrada, todos os ritos, por volume registrado. Público-alvo mede elegibilidade regulatória; a base não identifica alocação efetiva entre pessoas físicas, instituições e gestoras. Campo ausente em registros legados = N/D.",
    headers,
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(sheet, [105, 130, 75, 130, 115, 130, 300, 420, 105, 600], rows.length);
  applyFormatsByHeader(sheet, headers, rows.length);
  ["D", "F"].forEach((letter) => {
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  });
  sheet.getRange(`E5:E${rows.length + 4}`).format.numberFormat = "0.00%";
  sheet.getRange(`A5:J${rows.length + 4}`).format.rowHeightPx = 58;
}

async function addEmissionFieldAuditSheet(workbook, payload) {
  const columns = [
    ["Bloco do deck", "bloco"],
    ["Tabela / período", "tabela"],
    ["CNPJ", "cnpj", (value) => formatCnpj(value)],
    ["ID da emissão", "emissao_id", (value) => String(value).startsWith("N/D") ? value : `E ${value}`],
    ["Fundo", "fundo"],
    ["Originador", "originador"],
    ["Subordinação mínima", "subordinacao_minima"],
    ["Preço por tipo de cota", "preco_por_tipo_cota"],
    ["Cedente", "cedente"],
    ["Sacado", "sacado"],
    ["Fonte originador / cedente", "fonte_originador_cedente"],
    ["Fonte subordinação", "fonte_subordinacao"],
    ["Fonte preço", "fonte_preco"],
    ["Fonte sacado", "fonte_sacado"],
    ["Status", "status"],
  ];
  const headers = columns.map(([header]) => header);
  const rows = worksheetRowsFromPayload(payload.emission_field_audit || [], columns);
  if (rows.length !== 180) {
    throw new Error(`Auditoria emissões deveria conter 180 linhas; contém ${rows.length}.`);
  }
  const sheet = resetSheet(workbook, "Auditoria emissões");
  setHeaderBand(
    sheet,
    "Auditoria dos campos documentais exibidos nos slides 10–13 e 21–22",
    "Uma linha por fundo/período nos slides 10–13 e por emissão nos slides 21–22. Todo campo exibido conserva a fonte; ausência de evidência suficiente permanece N/D.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 7.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [110, 180, 105, 95, 300, 180, 150, 155, 210, 180, 360, 360, 420, 300, 260],
    rows.length,
  );
  sheet.getRange(`A5:O${rows.length + 4}`).format.rowHeightPx = 52;
}

async function buildWorkbook(payload) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(INPUT_WORKBOOK));
  const ficAudit = await readCsv(path.join(DATA_DIR, "industry_fic_detection_audit.csv"));
  patchLegacyPlSheets(workbook, csvRowsAsObjects(ficAudit));
  await addQaSheet(workbook);
  await addVehicleCompetenceSheet(workbook, payload);
  await addFundBaseSheet(workbook, payload);
  await addPerimeterAuditSheets(workbook, payload);
  await addMonoConcentrationSheet(workbook);
  await addMarketShareSheet(workbook);
  await addTop20Sheets(workbook, payload);
  await addCurationSheet(workbook, payload);
  await addHistoricalComparisonsSheet(workbook, payload);
  await addReceivablesReconciliationSheet(workbook, payload);
  await addSingleReceivableDelinquencySheet(workbook, payload);
  await addFrozenDelinquencyHistorySheet(workbook, payload);
  await addProviderHistorySheet(workbook, payload);
  await addIndependentProviderSheet(workbook, payload);
  await addBankFidcSheet(workbook, payload);
  await addBankFidcDetailSheet(workbook, payload);
  await addProviderAttributionSheet(workbook, payload);
  await addProviderTransitionSheet(workbook, payload);
  await addReagMigrationSheet(workbook, payload);
  await addAcquiringTaxonomySheet(workbook, payload);
  await addAcquiringReclassificationSheet(workbook, payload);
  await addCardReceivablesCurationSheet(workbook, payload);
  await addTop20ByTypeSheets(workbook, payload);
  await addTaxonomyLevelSheet(workbook, payload);
  await addFlagshipCurationSheet(workbook, payload);
  await addCarteira1CurationSheet(workbook, payload);
  await addCarteira1FlagshipComparisonSheet(workbook, payload);
  await addCarteira1TaxonomySheet(workbook, payload);
  await addTop100OutrosSheet(workbook, payload);
  await addDelinquencyDispersionSheet(workbook, payload);
  await addClosedOffersSheet(workbook, payload);
  await addFixedIncomeOfferComparisonSheet(workbook, payload);
  await addIssuanceTaxonomySheet(workbook, payload);
  await addOfferValidationSheet(workbook, payload);
  await addOfferTargetPublicSheet(workbook, payload);
  await addBcbExpandedCreditSheet(workbook, payload);
  await addClosedOfferPlacementRegimeSheet(workbook, payload);
  await addOfferTicketDistributionSheet(workbook, payload);
  await addOriginators2026Sheet(workbook, payload);
  await addClosedOfferTop15Sheet(workbook, payload);
  await addEmissionFieldAuditSheet(workbook, payload);
  await addConclusionsSheet(workbook, payload);
  await addAtlanticoSheet(workbook, payload);
  await addAtlanticoHistorySheet(workbook, payload);
  await addChecksSheet(workbook, payload);
  removeWorkbookSheets(workbook);
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
    throw new Error(`Falha ao ajustar os gráficos nativos: ${patched.stderr || patched.stdout}`);
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
      ["Top 20 Outros", "A1:P25"],
      ["Curadoria Top 20", "A1:X16"],
      ["Comparativos históricos", "A1:N28"],
      ["Reconciliação Tabelas I-II", "A1:S30"],
      ["Inadimplência por recebível", "A1:J24"],
      ["Histórico inad. coorte", "A1:P28"],
      ["Ranking independentes", "A1:K76"],
      ["FIDCs por banco", "A1:K28"],
      ["Detalhe coorte bancos", "A1:J28"],
      ["Atribuição prestadores", "A1:J22"],
      ["Fluxos prestadores", "A1:T24"],
      ["Migração CBSF", "A1:Q24"],
      ["Adquirência reclass.", "A1:G28"],
      ["Taxonomia adquirência", "A1:N32"],
      ["Curadoria Cartão", "A1:V48"],
      ["Top 20 por Tipo ANBIMA", "A1:AF28"],
      ["Auditoria Top 20 Tipo", "A1:M10"],
      ["Taxonomia por nível", "A1:J32"],
      ["Curadoria flagship", "A1:AL28"],
      ["Carteira 1 curadoria", "A1:AI28"],
      ["Carteira 1 vs flagships", "A1:P12"],
      ["Carteira 1 evolução", "A1:S20"],
      ["Curadoria Outros Top 100", "A1:AH28"],
      ["Dispersão inadimplência", "A1:S24"],
      ["Ofertas encerradas", "A1:Q58"],
      ["Regime de colocação", "A1:P16"],
      ["Histograma ofertas", "A1:V25"],
      ["Crédito Privado Ampliado", "A1:T16"],
      ["Originadores 2026", "A1:M24"],
      ["Top 15 ofertas", "A1:AZ28"],
      ["Auditoria emissões", "A1:O28"],
      ["Validação emissões", "A1:U25"],
      ["Emissões por categoria", "A1:N12"],
      ["Público-alvo ofertas", "A1:J24"],
      ["Principais conclusões", "A1:E30"],
      ["Curadoria Atlântico", "A1:D36"],
      ["Série Atlântico", "A1:M12"],
      ["Checks revisão", "A1:D28"],
      ["Universo elegível", "A1:P25"],
      ["FICs excluídos", "A1:J25"],
      ["Decisões do ledger", "A1:U25"],
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
  await generateProviderFlowHtml();
  if (process.env.FIDC_SKIP_PRESENTATION !== "1") {
    const presentation = buildPresentation(payload);
    if (presentation.slides.items.length !== EXPECTED_SLIDES) {
      throw new Error(`Deck deveria ter ${EXPECTED_SLIDES} slides; gerou ${presentation.slides.items.length}.`);
    }
    await exportPresentation(presentation);
  }
  if (process.env.FIDC_SKIP_WORKBOOK !== "1") {
    const workbook = await buildWorkbook(payload);
    await exportWorkbook(workbook);
  }
  if (
    process.env.FIDC_WRITE_MANIFEST === "1" ||
    (process.env.FIDC_SKIP_PRESENTATION !== "1" &&
      process.env.FIDC_SKIP_WORKBOOK !== "1")
  ) {
    await writeExportBundleManifest(payload, payloadRaw);
  }
  process.stdout.write(`${OUTPUT_PPTX}\n${OUTPUT_XLSX}\n${OUTPUT_HTML}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
