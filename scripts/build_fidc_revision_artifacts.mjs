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
  Workbook,
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
const OUTPUT_PORTFOLIO_XLSX = path.resolve(
  process.env.FIDC_OUTPUT_PORTFOLIO_XLSX ||
    path.join(OUTPUT_DIR, "carteira_101_flagships.xlsx"),
);
const OUTPUT_TOP100_XLSX = path.resolve(
  process.env.FIDC_OUTPUT_TOP100_XLSX ||
    path.join(OUTPUT_DIR, "top100_fidcs_middle_market.xlsx"),
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
const RENDERER_VERSION = "industry_revision_artifacts_v46";
const STRUCTURAL_MVP_SLIDE_SEQUENCE = Object.freeze([
  { id: "structural_mvp_financeiro", group: "Financeiro", sourceGroups: ["Financeiro"] },
  { id: "structural_mvp_adquirencia", group: "Adquirência", sourceGroups: ["Adquirência"] },
  { id: "structural_mvp_agro_revenda", group: "Agro / Revenda", sourceGroups: ["Agro / Revenda"] },
  { id: "structural_mvp_risco_corporativo", group: "Risco Corporativo", sourceGroups: [] },
  {
    id: "structural_mvp_consignado",
    group: "Consignado INSS e FGTS",
    sourceGroups: ["Consignado INSS", "Consignado FGTS"],
  },
  { id: "structural_mvp_factoring", group: "Factoring", sourceGroups: ["Factoring"] },
]);
const STRUCTURAL_DETAIL_SLIDE_SEQUENCE = Object.freeze([
  { id: "structural_detail_factoring_1_1", group: "Factoring", page: 1, pages: 1 },
  { id: "structural_detail_agro_revenda_1_8", group: "Agro / Revenda", page: 1, pages: 8 },
  { id: "structural_detail_agro_revenda_2_8", group: "Agro / Revenda", page: 2, pages: 8 },
  { id: "structural_detail_agro_revenda_3_8", group: "Agro / Revenda", page: 3, pages: 8 },
  { id: "structural_detail_agro_revenda_4_8", group: "Agro / Revenda", page: 4, pages: 8 },
  { id: "structural_detail_agro_revenda_5_8", group: "Agro / Revenda", page: 5, pages: 8 },
  { id: "structural_detail_agro_revenda_6_8", group: "Agro / Revenda", page: 6, pages: 8 },
  { id: "structural_detail_agro_revenda_7_8", group: "Agro / Revenda", page: 7, pages: 8 },
  { id: "structural_detail_agro_revenda_8_8", group: "Agro / Revenda", page: 8, pages: 8 },
  { id: "structural_detail_adquirencia_1_3", group: "Adquirência", page: 1, pages: 3 },
  { id: "structural_detail_adquirencia_2_3", group: "Adquirência", page: 2, pages: 3 },
  { id: "structural_detail_adquirencia_3_3", group: "Adquirência", page: 3, pages: 3 },
  { id: "structural_detail_consignado_inss_1_2", group: "Consignado INSS", page: 1, pages: 2 },
  { id: "structural_detail_consignado_inss_2_2", group: "Consignado INSS", page: 2, pages: 2 },
  { id: "structural_detail_consignado_fgts_1_2", group: "Consignado FGTS", page: 1, pages: 2 },
  { id: "structural_detail_consignado_fgts_2_2", group: "Consignado FGTS", page: 2, pages: 2 },
  { id: "structural_detail_veiculos_1_2", group: "Veículos", page: 1, pages: 2 },
  { id: "structural_detail_veiculos_2_2", group: "Veículos", page: 2, pages: 2 },
  { id: "structural_detail_financeiro_1_5", group: "Financeiro", page: 1, pages: 5 },
  { id: "structural_detail_financeiro_2_5", group: "Financeiro", page: 2, pages: 5 },
  { id: "structural_detail_financeiro_3_5", group: "Financeiro", page: 3, pages: 5 },
  { id: "structural_detail_financeiro_4_5", group: "Financeiro", page: 4, pages: 5 },
  { id: "structural_detail_financeiro_5_5", group: "Financeiro", page: 5, pages: 5 },
  { id: "structural_detail_nd_1_1", group: "N/D", page: 1, pages: 1 },
]);
const STRUCTURAL_ROWS_PER_SLIDE = Object.freeze({
  "Agro / Revenda": 7,
  "Adquirência": 7,
  "Financeiro": 7,
  Factoring: 7,
  "Consignado INSS": 7,
  "Consignado FGTS": 7,
  "Veículos": 7,
  "N/D": 7,
});
const SLIDE_CONTRACT_V1 = Object.freeze([
  "cover", "industry_scale", "annual_issuance", "issuance_taxonomy_summary",
  "issuance_taxonomy_detail", "analytical_taxonomy", "acquiring", "receivables",
  "top20",
  "top20_fomento_2026", "top20_fomento_2025",
  "top20_agro_2026", "top20_agro_2025",
  "top20_financeiro_2026", "top20_financeiro_2025",
  "top20_outros_2026", "top20_outros_2025",
  ...STRUCTURAL_MVP_SLIDE_SEQUENCE.map((entry) => entry.id),
  "offers_volume_ticket",
  "offers_ticket_distribution", "offers_placement_regime",
  "top15_current_2026", "top15_current_2025",
  "top15_history_2024_1_2", "top15_history_2024_2_2",
  "top15_history_2023_1_2", "top15_history_2023_2_2", "conclusions",
  "provider_history", "provider_ranking", "investor_base", "holder_distribution",
]);
const EXPECTED_SLIDES = SLIDE_CONTRACT_V1.length;
const COVER_TITLE = "Indústria de FIDCs — ago-26";
const EDITORIAL_HEADER_COPY = Object.freeze([
  {
    eyebrow: "OFERTAS ENCERRADAS · CVM E ANBIMA",
    title: "Emissões | FIDCs seguem ganhando escala nas emissões",
    subtitle: "No 1S26, FIDCs +14,6%; demais instrumentos −7,8%",
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
    titleStartsWith: "IBBA participou de",
    title: "IBBA esteve em 8 das 15 maiores ofertas do semestre",
    subtitle: "Liderou 5 delas",
  },
  {
    eyebrow: "TOP 15 · OFERTAS ENCERRADAS",
    titleStartsWith: "As 15 maiores ofertas de 2025",
    title: "As 15 maiores ofertas de 2025 mantêm a base anual de comparação",
    subtitle: "2025FY · ofertas primárias encerradas",
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

// @oai/artifact-tool recebe tamanhos em px e o PowerPoint materializa 0,75 pt
// por unidade. Estes pisos resultam em 12 pt para corpo/data label, 13 pt para
// cabeçalho e 10 pt para eixos/legendas no PPTX final.
const TYPOGRAPHY = Object.freeze({
  tableBody: 16,
  tableHeader: 17.333333,
  dataLabel: 16,
  axis: 13.333333,
  legend: 13.333333,
});

function fontAtLeast(value, minimum) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(parsed, minimum) : minimum;
}

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
  if (cut <= 0) {
    const nextSpace = text.indexOf(" ", maxChars);
    if (nextSpace > 0 && nextSpace <= maxChars + 6) {
      return text.slice(0, nextSpace).trim();
    }
    return text.slice(0, maxChars).trim();
  }
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

function topTypeFundName(value, maxChars = 20) {
  const original = fundEditorialName(value, 120);
  const replacements = [
    [/\bFIDC DO SISTEMA PETROBRAS\b/i, "Sistema Petrobras"],
    [/.*\bACR BEM\b.*/i, "ACR Bem"],
    [/\bBTG PACTUAL CONSIGNADOS II\b/i, "BTG Consignados II"],
    [/\bBTG PACTUAL CONSIGNADOS\b/i, "BTG Consignados"],
    [/\bCLASSE CONSIGNADO PRIVADO DO MT\b/i, "MT Consignado Privado"],
    [/\bSELLER FIDC SEGMENTO(?: MEIOS DE PAGAMENTO)?\b/i, "Seller"],
    [/\bCLOUDWALK PI SEGMENTO(?: MEIOS DE PAGAMENTO)?\b/i, "CloudWalk PI"],
    [/^HAVAN\b.*/i, "Havan"],
    [/^ALTERNATIVE ASSETS III$/i, "Alt. Assets III"],
    [/^ALTERNATIVE ASSETS I$/i, "Alt. Assets I"],
    [/^RIO VERMELHO\b.*/i, "Rio Vermelho"],
    [/^ACONC[AÁ]GUA\b.*/i, "Aconcágua"],
    [/^ITAL\b.*/i, "Ital"],
    [/\bFIDC GM\s*-?\s*VENDA DE VE[IÍ]CULOS\b/i, "FIDC GM"],
    [/^CATERPILLAR\b.*/i, "Caterpillar"],
    [/\bMAROB[AÁ].*$/i, "Marobá"],
  ];
  const compact = replacements.reduce(
    (text, [pattern, replacement]) => text.replace(pattern, replacement),
    original,
  );
  return truncateWords(compact, maxChars);
}

function cnpjDigits(value) {
  const raw = String(value ?? "").trim();
  const numericRaw = /e/i.test(raw) ? raw.replace(",", ".") : raw;
  let digits = raw.replace(/\D/g, "");
  if (/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(numericRaw)) {
    const parsed = Number(numericRaw);
    if (Number.isSafeInteger(parsed) && parsed >= 0) digits = String(parsed);
  }
  return !digits || digits.length > 14 ? "" : digits.padStart(14, "0");
}

function numericCnpjText(value) {
  return cnpjDigits(value) || "N/D";
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

function auditPartyField(value, maxChars = 34) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || /^N\/D(?:\b|\s|—|-)/i.test(text)) return "N/D";
  if (/\bestabelecimentos comerciais\b/i.test(text) && /\bmercado cr[eé]dito\b/i.test(text)) {
    return "Estab./M.Cred.";
  }
  const compact = auditField(text, maxChars);
  if (!/^(?:o|a|os|as|e|de|da|do|das|dos)$/i.test(compact)) return compact;
  const withoutLeadingArticle = text.replace(/^(?:o|a|os|as)\s+/i, "");
  return auditField(withoutLeadingArticle, maxChars);
}

function isMissingAuditValue(value) {
  const text = String(value || "").trim();
  return !text || /^N\/D(?:\b|\s|—|-)/i.test(text);
}

function entityDisplayKey(value) {
  return String(value || "")
    .replace(/\*+/g, "")
    .replace(/—\s*CNPJ\s*[0-9./-]+\.?/gi, "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\bs\s*\.?\s*a\.?\b|\bltda\.?\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function entityDisplayShort(value, maxChars = 24) {
  const raw = String(value || "").replace(/\s+/g, " ").trim();
  if (isMissingAuditValue(raw)) return "N/D";
  if (/\bestabelecimentos comerciais\b/i.test(raw) && /\bmercado cr[eé]dito\b/i.test(raw)) {
    return "Estab./M.Cred.";
  }
  const manual = /\*/.test(raw);
  const entities = raw
    .replace(/\*+/g, "")
    .split(/\s*\|\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
  let first = entities[0] || raw;
  first = first
    .replace(/—\s*CNPJ\s*[0-9./-]+\.?/gi, "")
    .replace(/\bBRF\s+S\s*\.\s*A\s*\./gi, "BRF S.A.")
    .replace(/\bNissan,\s*Renault\s+e\s+Geely\s*\(RCI\)/i, "RCI")
    .replace(/\bPETROLEO BRASILEIRO S\.?\s*A\.?\s+PETROBRAS\b/i, "Petrobras")
    .replace(/\bGAZIN INDUSTRIA E COMERCIO DE MOVEIS E ELETRODOMESTICOS S\.?\s*A\.?\b/i, "Gazin")
    .replace(/\bHYUNDAI MOTOR BRASIL MONTADORA DE AUTOMOVEIS LTDA\.?\b/i, "Hyundai")
    .replace(/\bHONDA AUTOMOVEIS DO BRASIL LTDA\.?\b/i, "Honda Brasil")
    .replace(/\bBMP SOCIEDADE DE CREDITO DIRETO S\.?\s*A\.?\b/i, "BMP SCD")
    .replace(/\bASA SOCIEDADE DE CREDITO FINANCIAMENTO E INVESTIMENTO S\.?\s*A\.?\b/i, "ASA SCD")
    .replace(/\bCOMEXPORT TRADING COMERCIO EXTERIOR LTDA\.?\b/i, "Comexport")
    .replace(/\bSANTANDER SOCIEDADE DE CREDITO,? FINANCIAMENTO E INVESTIMENTO S\.?\s*A\.?\b/i, "Santander SCFI")
    .replace(/\bMULTIPLIKE FINANCEIRA S\.?\s*A\.? SOCIEDADE DE CREDITO,? FINANCIAMENTO E INVESTIMENTO\b/i, "Multiplike")
    .replace(/\bARC LOG[IÍ]STICA E ALIMENTOS\b/i, "ARC Logística")
    .replace(/HAVAN S\.?\s*A\.?/i, "Havan")
    .replace(/[ÂA]MBAR ENERGIA S\.?\s*A\.?/i, "Âmbar")
    .replace(/\bCLOUDWALK INSTITUI[CÇ][AÃ]O DE PAGAMENTO E SERVI[CÇ]OS LTDA\.?/i, "CloudWalk")
    .replace(/\bFACTA FINANCEIRA S\.?A\.? CR[EÉ]DITO FINANCIAMENTO E INVESTIMENTO\b/i, "Facta")
    .replace(/\bSTONE INSTITUI[CÇ][AÃ]O DE PAGAMENTO S\.?A\.?/i, "Stone IP")
    .replace(/\bPICPAY INSTITUI[CÇ][AÃ]O DE PAGAMENTO S\/?A\b/i, "PicPay IP")
    .replace(/\bPARATI CR[EÉ]DITO FINANCIAMENTO E INVESTIMENTO S\.?A\.?/i, "Parati Crédito")
    .replace(/\bRENAULT DO BRASIL S\.?A\.?/i, "Renault")
    .replace(/\bQI SOCIEDADE DE CREDITO DIRETO S\.?A\.?/i, "QI SCD")
    .replace(/\bPETROLEO BRASILEIRO S\.?A\.?/i, "Petrobras")
    .replace(/\bBRF ENERGIA S\.?A\.?/i, "BRF Energia")
    .replace(/\bTRANSPORTES FRAMENTO\b/i, "Framento")
    .replace(/\bGENERAL MOTORS DO BRASIL\b/i, "GM Brasil")
    .replace(/\bGAZIN INDUSTRIA E COMERCIO\b/i, "Gazin")
    .replace(/\bSTELLANTIS AUTOMOVEIS BRASIL\b/i, "Stellantis")
    .replace(/\b[ÂA]MBAR ENERGIA S\.?A\.?/i, "Âmbar")
    .replace(/\bSYNGENTA PROTECAO DE CULTIVOS\b/i, "Syngenta")
    .replace(/\bHYUNDAI MOTOR BRASIL\b/i, "Hyundai")
    .replace(/\bGRUPO CASAS BAHIA\b/i, "Casas Bahia")
    .replace(/\bCATERPILLAR BRASIL\b/i, "Caterpillar")
    .replace(/\bMULTIPLIKE FINANCEIRA S\.?A\.?/i, "Multiplike")
    .replace(/\bCOMEXPORT TRADING\b/i, "Comexport")
    .replace(/\bBMP SOCIEDADE DE CREDITO\b/i, "BMP SCD")
    .replace(/\bASA SOCIEDADE DE CREDITO\b/i, "ASA SCD")
    .replace(/\bSTM PARTICIPACOES\b/i, "STM")
    .replace(/\bA\.?\s*R\.?\s*C\.?\s*LOGISTICA\b/i, "ARC Logística")
    .replace(/\s+/g, " ")
    .trim();
  first = providerShort(first) || first;
  const suffix = entities.length > 1 ? ` +${entities.length - 1} ent.` : "";
  const marker = manual ? "*" : "";
  const budget = Math.max(4, maxChars - suffix.length - marker.length);
  return `${truncateWords(first, budget)}${suffix}${marker}`;
}

function combinedPartyField(row, maxChars = 31) {
  const originator = row?.originador;
  const cedent = row?.cedente;
  const hasOriginator = !isMissingAuditValue(originator);
  const hasCedent = !isMissingAuditValue(cedent);
  if (!hasOriginator && !hasCedent) return "N/D";
  if (hasOriginator && hasCedent && entityDisplayKey(originator) === entityDisplayKey(cedent)) {
    return `C: ${entityDisplayShort(cedent, maxChars - 3)}`;
  }
  if (hasOriginator && hasCedent) {
    const perRoleBudget = Math.max(8, Math.floor((maxChars - 9) / 2) + 3);
    const cedentShort = entityDisplayShort(cedent, perRoleBudget);
    const originatorShort = entityDisplayShort(originator, perRoleBudget);
    return `C: ${cedentShort} · O: ${originatorShort}`;
  }
  if (hasCedent) return `C: ${entityDisplayShort(cedent, maxChars - 3)}`;
  return `O: ${entityDisplayShort(originator, maxChars - 3)}`;
}

function auditMinimumField(row, maxChars = 16) {
  const raw = String(row?.subordinacao_minima || "").replace(/\s+/g, " ").trim();
  if (isMissingAuditValue(raw)) return "N/D";
  const percentages = [...raw.matchAll(/\d{1,3}(?:[.,]\d+)?\s*%/g)].map((match) => match[0]);
  if (/at[eé]\s+D\+180/i.test(raw) && /ap[oó]s\s+D\+180/i.test(raw) && percentages.length >= 2) {
    return `${percentages[0].replace(/\s+/g, "")}→${percentages[1].replace(/\s+/g, "")}`;
  }
  const minimumType = normalizeProviderName(row?.tipo_subordinacao_minima || "");
  const percentage = percentages[0]?.replace(/\s+/g, "") || "";
  if (minimumType.includes("suporte combinado") && percentage) return `${percentage} comb.`;
  if (minimumType.includes("suporte total") && percentage) return `${percentage} total`;
  const manualSource = /coment[aá]rio manual|\bIMG_/i.test(String(row?.fonte_subordinacao || ""));
  const compact = raw.replace(/\*+/g, "");
  const marker = manualSource ? "*" : "";
  return `${auditField(compact, Math.max(1, maxChars - marker.length))}${marker}`;
}

function brlUnitPriceNumber(value) {
  const normalized = String(value || "").replace(/\s+/g, "").replace(/^R\$/i, "");
  const parsed = Number(normalized.replace(/\./g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function compactBrlUnitPrice(value) {
  const parsed = brlUnitPriceNumber(value);
  if (parsed === null) return String(value || "").trim();
  if (parsed >= 1_000_000 && parsed % 1_000_000 === 0) return `R$${parsed / 1_000_000}mi`;
  if (parsed >= 1_000 && parsed % 1_000 === 0) return `R$${parsed / 1_000}mil`;
  return `R$${parsed.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}`;
}

function auditUnitPrice(value, maxChars = 34) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || /^N\/D(?:\b|\s|—|-)/i.test(text)) return "N/D";
  const normalized = normalizeProviderName(text);
  if (["quantidade", "spread", "remuneracao", "taxa da cota"].some((token) => normalized.includes(token))) {
    return "N/D";
  }
  const multipleOrException = /[;|]/.test(text) || /\b(?:senior|mezanino|junior)\b.*\b(?:senior|mezanino|junior)\b/i.test(normalized);
  const prices = [...text.matchAll(/R\$\s*[0-9.]+(?:,[0-9]+)?/gi)].map((match) => match[0]);
  const uniquePrices = [...new Map(prices.map((price) => [
    brlUnitPriceNumber(price) ?? price.replace(/\s+/g, "").toUpperCase(),
    price.replace(/^R\$\s*/i, "R$ "),
  ])).values()];
  if (uniquePrices.length > 0) {
    const marker = multipleOrException || /\*$/.test(text) ? "*" : "";
    const exact = uniquePrices.join(" / ");
    if (`${exact}${marker}`.length <= maxChars) return `${exact}${marker}`;
    const compact = uniquePrices.map(compactBrlUnitPrice).join("/");
    return `${compact}${marker}`;
  }
  const compact = auditField(text.replace(/\*+$/g, ""), Math.max(1, maxChars - (multipleOrException ? 1 : 0)));
  return compact === "N/D" ? compact : `${compact}${multipleOrException || /\*$/.test(text) ? "*" : ""}`;
}

function targetRemunerationRates(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || /^N\/D(?:\b|\s|—|-)/i.test(text)) return [];
  const rates = [];
  const seen = new Set();
  const append = (rate) => {
    const compact = String(rate || "")
      .replace(/IGP[\s-]*M/gi, "IGP-M")
      .replace(/\bDI\b/gi, "DI")
      .replace(/\bCDI\b/gi, "CDI")
      .replace(/\bIPCA\b/gi, "IPCA")
      .replace(/\bSELIC\b/gi, "SELIC")
      .replace(/\s*\+\s*/g, "+")
      .replace(/(\d)\.(\d)/g, "$1,$2")
      .replace(/\s*%/g, "%")
      .replace(/\s+a\.?a\.?$/i, "")
      .replace(/\s+/g, " ")
      .trim();
    const key = normalizeProviderName(compact);
    if (!compact || seen.has(key)) return;
    seen.add(key);
    rates.push(compact);
  };
  for (const match of text.matchAll(
    /\b(CDI|DI|IPCA|SELIC|IGP[\s-]*M)\s*(?:\+|acrescid[ao]\s+de)\s*(\d{1,3}(?:[.,]\d+)?)\s*%(?:\s*a\.?a\.?)?/gi,
  )) {
    append(`${match[1]}+${match[2]}%`);
  }
  for (const match of text.matchAll(
    /\b(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:do|da)\s*(CDI|DI|IPCA|SELIC|IGP[\s-]*M)\b/gi,
  )) {
    append(`${match[1]}% do ${match[2]}`);
  }
  for (const match of text.matchAll(
    /\b(?:benchmark\s+)?prefixad[ao]\s*:?[\s]*(\d{1,3}(?:[.,]\d+)?)\s*%\s*a\.?a\.?/gi,
  )) {
    append(`Prefix. ${match[1]}% a.a.`);
  }
  return rates;
}

function targetRemunerationIsValid(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || /^N\/D(?:\b|\s|—|-)/i.test(text)) return false;
  const normalized = normalizeProviderName(text);
  if (
    /R\$/i.test(text)
    || ["quantidade", "preco unitario", "valor unitario", "vnu"]
      .some((token) => normalized.includes(token))
  ) {
    return false;
  }
  return targetRemunerationRates(text).length > 0;
}

function auditTargetRemuneration(value, maxChars = 34) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!targetRemunerationIsValid(text)) return "N/D";
  const rates = targetRemunerationRates(text);
  const observations = text
    .replace(/\*+\s*$/g, "")
    .split(/\s*[;|]\s*/)
    .filter((item) => targetRemunerationIsValid(item));
  const seriesCount = Math.max(observations.length, rates.length, 1);
  // Contrato editorial do slide: taxa primeiro; multiplicidade aparece como
  // quantidade autoexplicativa, sem reutilizar o asterisco de dado manual.
  const primary = String(rates[0] || "")
    .replace(/%\s+do\s+/i, "% ")
    .replace(/\s+/g, " ")
    .trim();
  if (seriesCount > 1) {
    return truncateWords(`${primary} · ${seriesCount} séries`, maxChars);
  }
  const exact = rates.join(" / ");
  return truncateWords(exact, maxChars);
}

function remunerationClassSeries(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  const separator = text.indexOf(":");
  if (separator <= 0) return "N/D";
  return text.slice(0, separator).trim() || "N/D";
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

function sentenceCaseInternalTitle(value) {
  let text = String(value || "").trim();
  const protectedTokens = [];
  const protect = (pattern, canonical) => {
    text = text.replace(pattern, () => {
      const marker = `§${protectedTokens.length}§`;
      protectedTokens.push(canonical);
      return marker;
    });
  };
  [
    [/\bFIDCs\b/gi, "FIDCs"],
    [/\bFIDC\b/gi, "FIDC"],
    [/\bCNPJs\b/gi, "CNPJs"],
    [/\bCNPJ\b/gi, "CNPJ"],
    [/\bANBIMA\b/gi, "ANBIMA"],
    [/\bCVM\b/gi, "CVM"],
    [/\bFGTS\b/gi, "FGTS"],
    [/\bINSS\b/gi, "INSS"],
    [/\bYTD\b/gi, "YTD"],
    [/\bYoY\b/gi, "YoY"],
    [/\bCBSF\b/gi, "CBSF"],
    [/\bREAG\b/gi, "REAG"],
    [/\bBTG\b/gi, "BTG"],
    [/\bQI\b/gi, "QI"],
    [/\bIBBA\b/gi, "IBBA"],
    [/\bPL\b/gi, "PL"],
    [/FY\b/gi, "FY"],
    [/\bN\/D\b/gi, "N/D"],
    [/\bex-FIC\b/gi, "ex-FIC"],
    [/\bTop\b/gi, "Top"],
    [/\bII\b/g, "II"],
    [/R\$/g, "R$"],
  ].forEach(([pattern, canonical]) => protect(pattern, canonical));
  text = text.toLocaleLowerCase("pt-BR");
  protectedTokens.forEach((token, index) => {
    text = text.replace(`§${index}§`, token);
  });
  text = text.replace(/^\p{Ll}/u, (letter) => letter.toLocaleUpperCase("pt-BR"));
  return text
    .replace(/^(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)(?=\/\d|–)/, (month) => month.toLocaleLowerCase("pt-BR"))
    .replace(/(\d{4})FY\b/g, "$1 FY")
    .replace(/\bQI tech\b/g, "QI Tech")
    .replace(/\bBTG pactual\b/g, "BTG Pactual");
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
    fill: options.fill ?? "none",
    line: {
      style: "solid",
      fill: options.lineFill ?? "none",
      width: options.lineWidth ?? 0,
    },
  });
  shape.text = String(text ?? "");
  shape.text.style = {
    typeface: "Arial",
    // Tamanhos são informados em px e exportados a 0,75 pt por unidade.
    // O piso de 13,333 px garante 10 pt no PPTX final para qualquer texto.
    fontSize: fontAtLeast(options.fontSize ?? 16, TYPOGRAPHY.axis),
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
  addText(slide, sentenceCaseInternalTitle(text), position, {
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
    fontSize: requestedFontSize = TYPOGRAPHY.tableBody,
    headerFontSize: requestedHeaderFontSize = TYPOGRAPHY.tableHeader,
    rowHighlights = new Set(),
    rowHeight,
  } = options;
  const fontSize = fontAtLeast(requestedFontSize, TYPOGRAPHY.tableBody);
  const headerFontSize = fontAtLeast(requestedHeaderFontSize, TYPOGRAPHY.tableHeader);
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
    fontSize: requestedFontSize = TYPOGRAPHY.tableBody,
    headerFontSize: requestedHeaderFontSize = TYPOGRAPHY.tableHeader,
    minimumFontSize = TYPOGRAPHY.tableBody,
    minimumHeaderFontSize = TYPOGRAPHY.tableHeader,
    headerHeight = 22,
    headerFill = C.black,
    rowHighlights = new Set(),
    emphasizeHighlightedRows = false,
  } = options;
  const fontSize = fontAtLeast(requestedFontSize, minimumFontSize);
  const headerFontSize = fontAtLeast(requestedHeaderFontSize, minimumHeaderFontSize);
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
  // Positions and table bounds use the renderer's CSS-pixel grid, while the
  // native Office row-height setter is expressed in points.  Keep the same
  // visual height in the exported PPTX (1 px = 0.75 pt); otherwise PowerPoint
  // expands every row by 4/3 and long tables leave the slide canvas.
  table.rows[0].height = headerHeight * 0.75;
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
    table.rows[rowIndex + 1].height = (
      (height - headerHeight) / Math.max(rows.length, 1)
    ) * 0.75;
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

function chartAxis(fontSize = TYPOGRAPHY.axis, numberFormatCode) {
  return {
    visible: true,
    numberFormatCode,
    textStyle: { fill: C.note, fontSize: fontAtLeast(fontSize, TYPOGRAPHY.axis) },
    line: { style: "solid", fill: C.line, width: 1 },
    majorGridlines: { style: "solid", fill: C.light, width: 1 },
    minorGridlines: null,
  };
}

function textStyleWithMinimum(textStyle, minimum) {
  return {
    ...(textStyle || {}),
    fontSize: fontAtLeast(textStyle?.fontSize, minimum),
  };
}

function dataLabelsWithMinimum(dataLabels) {
  if (!dataLabels || dataLabels.showValue === false) return dataLabels;
  return {
    ...dataLabels,
    textStyle: textStyleWithMinimum(dataLabels.textStyle, TYPOGRAPHY.dataLabel),
  };
}

function normalizeChartTypography(options = {}) {
  const normalized = { ...options };
  ["xAxis", "yAxis"].forEach((axisKey) => {
    const axis = normalized[axisKey];
    if (!axis || axis.visible === false) return;
    normalized[axisKey] = {
      ...axis,
      textStyle: textStyleWithMinimum(axis.textStyle, TYPOGRAPHY.axis),
    };
  });
  if (normalized.hasLegend && normalized.legend) {
    normalized.legend = {
      ...normalized.legend,
      textStyle: textStyleWithMinimum(normalized.legend.textStyle, TYPOGRAPHY.legend),
    };
  }
  if (normalized.dataLabels) {
    normalized.dataLabels = dataLabelsWithMinimum(normalized.dataLabels);
  }
  if (Array.isArray(normalized.series)) {
    normalized.series = normalized.series.map((series) => ({
      ...series,
      ...(series.dataLabels ? { dataLabels: dataLabelsWithMinimum(series.dataLabels) } : {}),
      ...(Array.isArray(series.dataLabelOverrides)
        ? {
            dataLabelOverrides: series.dataLabelOverrides.map((override) => (
              override?.showValue === false
                ? override
                : {
                    ...override,
                    textStyle: textStyleWithMinimum(override?.textStyle, TYPOGRAPHY.dataLabel),
                  }
            )),
          }
        : {}),
    }));
  }
  return normalized;
}

function installPresentationTypography(presentation) {
  const nativeSlideAdd = presentation.slides.add;
  presentation.slides.add = function addSlideWithTypography(...args) {
    const slide = nativeSlideAdd.apply(this, args);
    const nativeChartAdd = slide.charts.add;
    slide.charts.add = function addChartWithTypography(chartType, options, ...rest) {
      return nativeChartAdd.call(this, chartType, normalizeChartTypography(options), ...rest);
    };
    return slide;
  };
  return presentation;
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
      textStyle: { fill: C.mid, fontSize: TYPOGRAPHY.legend },
    },
    xAxis: { visible: false, majorGridlines: null, minorGridlines: null },
    yAxis: { visible: false, majorGridlines: null, minorGridlines: null },
  });
  return chart;
}

function addShapeLegend(slide, entries, position, columns = 4, options = {}) {
  const columnWidth = position.width / columns;
  const rows = Math.max(1, Math.ceil(entries.length / columns));
  const rowHeight = position.height / rows;
  entries.forEach((entry, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const left = position.left + column * columnWidth;
    const top = position.top + row * rowHeight;
    const swatchSize = Math.min(options.swatchSize ?? 8, rowHeight - 2);
    addRect(
      slide,
      {
        left,
        top: top + (rowHeight - swatchSize) / 2,
        width: swatchSize,
        height: swatchSize,
      },
      entry.color,
    );
    addText(
      slide,
      truncateWords(entry.label, options.maxLabelLength ?? 42),
      {
        left: left + swatchSize + 5,
        top,
        width: columnWidth - swatchSize - 8,
        height: rowHeight,
      },
      {
        fontSize: fontAtLeast(options.fontSize, TYPOGRAPHY.legend),
        color: C.mid,
        verticalAlignment: "middle",
        autoFit: "shrinkText",
      },
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
  const visibleLabels = new Set(labelIndices);
  // Categorias vazias repetidas são colapsadas pelo Office e fazem a linha
  // voltar no eixo X. Zeros invisíveis mantêm posições distintas sem exibir
  // os rótulos intermediários.
  const nativeCategories = categories.map((label, index) => (
    visibleLabels.has(index) ? label : "\u200B".repeat(index + 1)
  ));
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
  const [
    pptxSha256,
    xlsxSha256,
    portfolioXlsxSha256,
    top100XlsxSha256,
    htmlSha256,
    pptxStat,
    xlsxStat,
    portfolioXlsxStat,
    top100XlsxStat,
    htmlStat,
  ] = await Promise.all([
    sha256File(OUTPUT_PPTX),
    sha256File(OUTPUT_XLSX),
    sha256File(OUTPUT_PORTFOLIO_XLSX),
    sha256File(OUTPUT_TOP100_XLSX),
    sha256File(OUTPUT_HTML),
    fs.stat(OUTPUT_PPTX),
    fs.stat(OUTPUT_XLSX),
    fs.stat(OUTPUT_PORTFOLIO_XLSX),
    fs.stat(OUTPUT_TOP100_XLSX),
    fs.stat(OUTPUT_HTML),
  ]);
  const manifest = {
    schema_version: "fidc_revision_export_bundle_v5",
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
    portfolio_xlsx: {
      filename: path.basename(OUTPUT_PORTFOLIO_XLSX),
      sha256: portfolioXlsxSha256,
      bytes: portfolioXlsxStat.size,
    },
    top100_xlsx: {
      filename: path.basename(OUTPUT_TOP100_XLSX),
      sha256: top100XlsxSha256,
      bytes: top100XlsxStat.size,
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
      portfolio_export_carteira_101: (payload.portfolio_export_carteira_101 || []).length,
      portfolio_export_cases_99: (payload.portfolio_export_cases_99 || []).length,
      portfolio_export_flagships: (payload.portfolio_export_flagships || []).length,
      top100_fidcs_middle_market: (payload.top100_fidcs_middle_market || []).length,
      portfolio_export_coverage: (payload.portfolio_export_coverage || []).length,
      portfolio_export_gaps: (payload.portfolio_export_gaps || []).length,
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

function sanitizePublishedText(value, sourceLabel = "artefato") {
  const text = String(value ?? "");
  const marker = text.includes("√")
    ? "√"
    : text.match(/Ã[\u0080-\u00BF]|Â[\u0080-\u00BF]/u)?.[0];
  if (marker != null) {
    throw new Error(`${sourceLabel} contém mojibake bloqueado: ${marker}`);
  }
  return text
    .replace(/^\uFEFF/, "")
    .replace(/\uFFFD+/g, " [trecho ilegível na extração] ")
    .replace(/[ \t]+\n/g, "\n");
}

async function readCsv(filePath) {
  const raw = await fs.readFile(filePath);
  const bytes = filePath.endsWith(".gz") ? zlib.gunzipSync(raw) : raw;
  const decoded = sanitizePublishedText(bytes.toString("utf8"), filePath);
  const matrix = parseCsv(decoded);
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
    sentenceCaseInternalTitle("TODOS OS PRESTADORES"),
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
    sentenceCaseInternalTitle("INDEPENDENTES*"),
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
      sentenceCaseInternalTitle(label),
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
    `BTG: ${integer(metrics.btg_bank_cohort_observed_funds)}/${integer(metrics.btg_bank_cohort_listed_roots)} raízes observadas; ofertas CVM e ANBIMA até 30/jun/26.`,
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
    "ANBIMA — Coletiva de Mercado de Capitais 1S26, valor encerrado, snapshot jun/26; 2026 = jan–jun: https://www.anbima.com.br/data/files/8E/86/DB/07/325AF91098D078F9692BA2A8/Apresentacao%20_%20coletiva%20Mercado%20de%20Capitais%20_%201S26.pdf",
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

function top15SlideRows(rows, emissionAudit, { includeRating = false } = {}) {
  const auditByEmission = new Map(
    (emissionAudit || []).map((row) => [`${row.tabela}::${row.emissao_id}`, row]),
  );
  return rows.map((row) => {
    const audit = auditByEmission.get(`${row.period_label}::${row.offer_id}`) || {};
    const base = [
      integer(row.rank),
      truncateWords(row.offer_id, 8) || "N/D",
      numericCnpjText(audit.cnpj || row.cnpj_emissor),
      fundEditorialName(row.fund_name_short, includeRating ? 18 : 22),
      auditField(audit.originador, includeRating ? 11 : 14),
      auditField(audit.cedente, includeRating ? 11 : 14),
      auditField(audit.subordinacao_minima, includeRating ? 10 : 12),
      auditUnitPrice(audit.preco_por_tipo_cota, includeRating ? 16 : 18),
      auditField(audit.sacado, includeRating ? 14 : 16),
    ];
    if (includeRating) {
      base.push(top15AgencyLabel(row.rating_agency), auditField(row.rating_assigned, 10));
    }
    base.push(
      (num(row.registered_volume_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    );
    return base;
  });
}

function addHistoricalTop15Slide(presentation, payload, period, page, pages, slideNumber) {
  const slide = presentation.slides.add();
  const top15 = payload.closed_offer_top15 || [];
  const summaries = Object.fromEntries((payload.closed_offer_top15_summary || []).map((row) => [row.period_label, row]));
  const rows = top15
    .filter((row) => row.period_label === period)
    .sort((a, b) => num(a.rank) - num(b.rank));
  if (rows.length !== 15) {
    throw new Error(`Histórico Top 15 ${period} deveria conter 15 linhas; contém ${rows.length}.`);
  }
  const rowsPerPage = 8;
  const pageRows = rows.slice((page - 1) * rowsPerPage, page * rowsPerPage);
  if (!pageRows.length || pages !== 2) {
    throw new Error(`Paginação histórica de ${period} inválida: ${page}/${pages}.`);
  }
  const summary = summaries[period] || {};
  const display = (value) => value.replace(" FY", "FY").replace("2026 jan-jun", "jan–jun/26");
  const emissionAudit = (payload.emission_field_audit || []).filter((row) => row.bloco === "slides 21–22");
  addHeader(
    slide,
    "TOP 15 · HISTÓRICO",
    `As maiores ofertas de ${String(period).slice(0, 4)}, com agência e nota em colunas separadas`,
    `Fonte: CVM/SRE e FundosNet. ${display(period)}, ofertas primárias encerradas; volume registrado.`,
    slideNumber,
  );
  addSectionLabel(slide, `${display(period)} · Top 15 · ${page}/${pages}`, { left: 60, top: 120, width: 1160, height: 22 });
  addNativeEditorialTable(slide, {
    left: 60,
    top: 151,
    width: 1160,
    height: 430,
    headers: ["#", "Emis.", "CNPJ", "FIDC", "Originador", "Cedente", "Sub. mín.", "Preço por cota", "Sacado", "Agência", "Rating", "R$ bi"],
    rows: top15SlideRows(pageRows, emissionAudit, { includeRating: true }),
    columnWidths: [30, 60, 133, 150, 100, 100, 92, 135, 115, 90, 95, 60],
    aligns: ["right", "left", "left", "left", "left", "left", "left", "left", "left", "left", "left", "right"],
    fontSize: TYPOGRAPHY.tableBody,
    headerFontSize: TYPOGRAPHY.tableHeader,
    headerHeight: 31,
    rowHighlights: new Set(),
  });
  addText(
    slide,
    page === pages
      ? `Subtotal Top 15: ${bn(summary.top15_registered_volume_brl, 2)} · ${pct(summary.top15_share_of_period_volume, 1)} do período. * = exceção ou múltiplas classes.`
      : `Continua em ${page + 1}/${pages}. Preço = valor unitário por cota; quantidade fica fora. * = exceção ou múltiplas classes.`,
    { left: 60, top: 600, width: 1160, height: 34 },
    { fontSize: TYPOGRAPHY.axis, color: C.note, alignment: "right", verticalAlignment: "middle", wrap: "none" },
  );
  addSourceNotes(slide, [
    "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
    "FundosNet/B3 — mesma curadoria documental flagship; fontes linha a linha na aba Auditoria emissões.",
    "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, Valor_Total_Registrado positivo e data de encerramento no período; snapshot CVM 24/jul/26.",
    "Limitação: rating sem documento público verificável ou sem vínculo exato = N/D.",
  ]);
}

function addCurrentTop15Slide(presentation, payload, period, slideNumber) {
  const slide = presentation.slides.add();
  const rows = [...(payload.closed_offer_top15 || [])]
    .filter((row) => row.period_label === period)
    .sort((a, b) => num(a.rank) - num(b.rank));
  if (rows.length !== 15) {
    throw new Error(`Top 15 ${period} deveria conter 15 linhas; contém ${rows.length}.`);
  }
  const summary = (payload.closed_offer_top15_summary || [])
    .find((row) => row.period_label === period) || {};
  const emissionAudit = (payload.emission_field_audit || []).filter(
    (row) => row.bloco === "slides 21–22",
  );
  const display = period === "2026 jan-jun" ? "jan–jun/26" : "2025FY";
  const title = period === "2026 jan-jun"
    ? `IBBA participou de ${integer(summary.ibba_participation_offers_top15)} das 15 maiores em jan–jun/26; liderou ${integer(summary.ibba_lead_offers_top15)}`
    : "As 15 maiores ofertas de 2025 mantêm a base anual de comparação";
  addHeader(
    slide,
    "TOP 15 · OFERTAS ENCERRADAS",
    title,
    `Fonte: CVM/SRE e FundosNet. ${display}, ofertas primárias encerradas; volume registrado.`,
    slideNumber,
  );
  addSectionLabel(slide, `${display} · Top 15`, { left: 60, top: 120, width: 1160, height: 22 });
  addNativeEditorialTable(slide, {
    left: 60,
    top: 151,
    width: 1160,
    height: 494,
    headers: ["#", "Emis.", "CNPJ", "FIDC", "Originador", "Cedente", "Sub. mín.", "Preço por cota", "Sacado", "R$ bi"],
    rows: top15SlideRows(rows, emissionAudit),
    columnWidths: [32, 58, 140, 210, 125, 125, 110, 150, 135, 75],
    aligns: ["right", "left", "left", "left", "left", "left", "left", "left", "left", "right"],
    fontSize: TYPOGRAPHY.tableBody,
    headerFontSize: TYPOGRAPHY.tableHeader,
    headerHeight: 31,
    rowHighlights: new Set(
      rows
        .map((row, index) => row.ibba_participant === true ? index : null)
        .filter((index) => index !== null),
    ),
    emphasizeHighlightedRows: true,
  });
  addText(
    slide,
    `Subtotal: ${bn(summary.top15_registered_volume_brl, 2)} · ${pct(summary.top15_share_of_period_volume, 1)} do período. * = exceção/múltiplas classes; campos integrais: aba Auditoria emissões.`,
    { left: 60, top: 648, width: 1160, height: 16 },
    { fontSize: TYPOGRAPHY.axis, color: C.note, alignment: "right", verticalAlignment: "middle", wrap: "none" },
  );
  addSourceNotes(slide, [
    "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
    "FundosNet/B3 — mesma curadoria documental flagship; fontes linha a linha na aba Auditoria emissões.",
    "Universo: Cotas de FIDC, ofertas públicas primárias encerradas, todos os ritos disponíveis, Valor_Total_Registrado positivo e data de encerramento no período; snapshot CVM 24/jul/26.",
    "Limitação: campo sem vínculo documental suficiente permanece N/D; o volume registrado pode diferir do valor encerrado informado à ANBIMA.",
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
    rows: rows.map((row) => [
      integer(row.rank),
      fundEditorialName(row.fund_name_short, 30),
      auditField(row.originator_name || row.originator, 20),
      (num(row.registered_volume_brl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      top15CoordinatorLabel(row.lead_coordinator || row.coordinator_lead),
      row.firm_commitment_label || "N/D",
      top15PublicLabel(row.publico),
      top15AgencyLabel(row.rating_agency),
      auditField(row.rating_assigned, 16),
    ]),
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

function addRemunerationComparisonStrip(slide, payload, mode) {
  const tier = payload.emission_remuneration_tier_summary || {};
  const matched = payload.emission_remuneration_matched_summary || {};
  const changed = (payload.emission_remuneration_matched_pairs || []).filter(
    (row) => row.changed === true || String(row.changed).toLowerCase() === "true",
  );
  if (num(tier.pairs) <= 0 || num(matched.pairs) <= 0 || changed.length !== num(matched.changed_pairs)) {
    throw new Error("Resumo de remuneração comparável ausente ou inconsistente.");
  }
  const change = changed[0] || {};
  const changeName = fundEditorialName(change.fundo || "N/D", 16).toUpperCase();
  const delta = Number(change.delta_bps);
  const deltaText = Number.isFinite(delta)
    ? `${delta < 0 ? "−" : "+"}${Math.abs(delta).toLocaleString("pt-BR")} bps`
    : "N/D";
  const cardsByMode = {
    tier: [
      {
        left: 60,
        width: 1160,
        title: "Prêmio de remuneração Mz.–Sr. · mesmo fundo e corte · base dos slides 10–17",
        value: `N=${integer(tier.pairs)} fundo-corte · mediana +${integer(tier.median_bps)} bps · faixa +${integer(tier.min_bps)}–${integer(tier.max_bps)} bps`,
      },
    ],
    matched: [
      {
        left: 60,
        width: 1160,
        title: "Movimento semestral · mesma classe e CNPJ · amostra casada",
        value: `N=${integer(matched.pairs)} fundo-classe · ${integer(matched.changed_pairs)} mudança · ${changeName} ${change.tranche_family || ""} ${deltaText}`,
      },
    ],
  };
  const cards = cardsByMode[mode] || [];
  if (!cards.length) throw new Error(`Modo de quadro de remuneração inválido: ${mode}.`);
  cards.forEach((card) => {
    addRect(
      slide,
      { left: card.left, top: 607, width: card.width, height: 36 },
      C.pale,
      { lineFill: C.line, lineWidth: 0.6 },
    );
    addText(slide, card.title, { left: card.left + 8, top: 610, width: card.width - 16, height: 12 }, {
      fontSize: 10.5,
      bold: true,
      color: C.charcoal,
      verticalAlignment: "middle",
      wrap: "none",
    });
    addText(slide, card.value, { left: card.left + 8, top: 624, width: card.width - 16, height: 14 }, {
      fontSize: 10.5,
      color: C.mid,
      verticalAlignment: "middle",
      wrap: "none",
    });
  });
}

function addTop20ByAnbimaTypeSlide(presentation, payload, typeName, competencia) {
  const reviewRows = payload.top20_taxonomy_review || [];
  const auditRows = (payload.emission_field_audit || []).filter(
    (row) => row.bloco === "slides 10–17",
  );
  const auditByFund = new Map(
    auditRows.map((row) => [`${row.tabela}::${cnpjDigits(row.cnpj)}`, row]),
  );
  const period = competencia === payload.latest_complete
    ? { competencia, label: "jun/26 · Top 15", headerFill: C.orange }
    : competencia === "2025-12"
      ? { competencia, label: "dez/25 · Top 15", headerFill: C.black }
      : null;
  if (!period) {
    throw new Error(`Competência não suportada no Top 15 por tipo: ${competencia}.`);
  }
  const rowsFor = (competencia) => [...reviewRows]
    .filter((row) => row.tipo_exibicao === typeName && row.competencia === competencia)
    .sort((a, b) => num(a.rank_tipo) - num(b.rank_tipo))
    .slice(0, 15);
  const rows = rowsFor(competencia);
  if (rows.length !== 15) {
    throw new Error(`Ranking ${typeName} deveria conter 15 linhas em ${competencia}; contém ${rows.length}.`);
  }
  const slide = presentation.slides.add();
  const currentPl = rowsFor(payload.latest_complete).reduce((sum, row) => sum + num(row.pl), 0);
  const priorPl = rowsFor("2025-12").reduce((sum, row) => sum + num(row.pl), 0);
  const executiveTitle = {
    "Fomento Mercantil": "Fomento Mercantil: crescimento marginal em seis meses",
    "Agro, Indústria e Comércio": "Agro, Indústria e Comércio: o maior salto absoluto",
    Financeiro: "Financeiro: o maior bloco, e ainda crescendo",
    Outros: "Outros: o único bloco que encolheu",
  }[typeName] || typeName;
  addHeader(
    slide,
    "RANKING · TOP FUNDOS E ORIGINADORES",
    executiveTitle,
    `${period.label}: ${bn(rows.reduce((sum, row) => sum + num(row.pl), 0), 1)}. Comparação: ${bn(priorPl, 1)} em dez/25 e ${bn(currentPl, 1)} em jun/26.`,
    0,
  );
  addSectionLabel(slide, period.label, { left: 60, top: 120, width: 1160, height: 22 });
  const comparisonMode = typeName === "Fomento Mercantil"
    ? competencia === payload.latest_complete ? "tier" : "matched"
    : null;
  addNativeEditorialTable(slide, {
    left: 60,
    top: 151,
    width: 1160,
    height: comparisonMode ? 450 : 494,
    headers: ["#", "FIDC", "CNPJ", "Cedente / originador", "Sub. mín.", "Remuneração-alvo", "Sacado", "R$ bi"],
    rows: rows.map((row) => {
      const audit = auditByFund.get(
        `${typeName} · ${period.competencia}::${cnpjDigits(row.cnpj_fundo)}`,
      ) || {};
      return [
        String(integer(row.rank_tipo)),
        topTypeFundName(row.denominacao || "N/D", 20),
        numericCnpjText(row.cnpj_fundo),
        combinedPartyField(audit, 36),
        auditMinimumField(audit, 16),
        auditTargetRemuneration(audit.remuneracao_por_tipo_cota, 27),
        auditField(audit.sacado_exibicao, 25),
        (num(row.pl) / 1e9).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      ];
    }),
    columnWidths: [30, 195, 135, 220, 100, 215, 185, 80],
    aligns: ["right", "left", "left", "left", "left", "left", "left", "right"],
    fontSize: 13,
    headerFontSize: 14,
    minimumFontSize: 13,
    minimumHeaderFontSize: 14,
    headerHeight: 31,
    headerFill: period.headerFill,
    rowHighlights: new Set(),
  });
  if (comparisonMode) addRemunerationComparisonStrip(slide, payload, comparisonMode);
  addText(
    slide,
    "C/O = cedente/originador; +N ent./séries = itens adicionais; comb./total = natureza do mínimo; * = complemento manual; N/D = lacuna. Texto integral: Auditoria emissões.",
    { left: 60, top: 648, width: 1160, height: 16 },
    { fontSize: TYPOGRAPHY.axis, color: C.note, alignment: "right", verticalAlignment: "middle", wrap: "none" },
  );
  addSourceNotes(slide, [
    `Unidade: CNPJ do fundo, com classes agregadas; página ${period.label}.`,
    "Cedente: CVM, Informe Mensal, Tabela I, quando declarado; a informação identifica o cedente legal e não é tratada como originador econômico.",
    "Originador, sacado, subordinação mínima e remuneração-alvo: documentos identificados ou curadoria documental por CNPJ; fontes linha a linha na aba Auditoria emissões.",
    "Remuneração-alvo preserva o benchmark e o spread da cota/série (por exemplo, CDI + x% a.a.); VNU, quantidade, taxa da carteira e preço unitário ficam fora desta coluna.",
    "O Informe Mensal da CVM não identifica sacado/devedor nomeado. Campo ausente, fragmento sem papel explícito ou vínculo documental insuficiente permanece N/D.",
    "Prêmio Mz.–Sr.: menor spread CDI/DI+ documentado por nível no mesmo fundo e corte; N = fundo-corte. Movimento semestral: mesmo CNPJ e família de tranche nos dois rankings; N = fundo-classe.",
    "Amostras entre fundos só são comparáveis quando subordinação, prazo e lastro também coincidem. * = complemento manual; classes/séries e natureza do mínimo aparecem na própria célula e na auditoria.",
  ]);
}

function legacyAddFlagshipCurationSlide(presentation, payload) {
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

function legacyAddCarteira1CurationSlide(presentation, payload) {
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

function legacyAddCarteira1TaxonomySlide(presentation, payload) {
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

function structuralTaxonomyStyle(label) {
  const key = label === "Agro / Revenda" ? "Agro / revenda" : label;
  return FLAGSHIP_TYPE_STYLES[key] || FLAGSHIP_TYPE_STYLES.Financeiro;
}

function addStructuralRowStrips(slide, rows, { left, top, height, headerHeight = 25 }) {
  const rowHeight = (height - headerHeight) / Math.max(rows.length, 1);
  rows.forEach((row, index) => {
    addRect(
      slide,
      { left, top: top + headerHeight + index * rowHeight, width: 5, height: rowHeight },
      structuralTaxonomyStyle(row.taxonomia || row.categoria).fill,
    );
  });
}

function structuralNatureLabel(value) {
  const labels = {
    junior_pl: "Jr",
    junior_pl_calculado: "Jr calc.*",
    junior_pl_ajustado: "Jr ajust.*",
    suporte_total_pl: "Total*",
    suporte_combinado_pl: "Combinado*",
  };
  return labels[String(value || "")] || "N/D";
}

function isMissingStructuralText(value) {
  const normalized = normalizeProviderName(value);
  return !normalized || ["n/d", "nd", "nan", "none", "null"].includes(normalized);
}

function structuralBoolean(value) {
  if (typeof value === "boolean") return value;
  return ["1", "true", "sim", "yes"].includes(normalizeProviderName(value));
}

function structuralNumeric(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizedStructuralGroup(value) {
  const key = normalizeProviderName(value);
  const labels = {
    factoring: "Factoring",
    "agro / revenda": "Agro / Revenda",
    agro: "Agro / Revenda",
    adquirencia: "Adquirência",
    "consignado inss": "Consignado INSS",
    "consignado fgts": "Consignado FGTS",
    veiculos: "Veículos",
    financeiro: "Financeiro",
    "n/d": "N/D",
    nd: "N/D",
  };
  return labels[key] || "N/D";
}

function structuralFundName(row, maxChars = 18) {
  const name = !isMissingStructuralText(row.nome_oficial_cvm)
    ? row.nome_oficial_cvm
    : row.nome_referencia;
  if (isMissingStructuralText(name)) return "N/D";
  const editorialOverride = structuralBoolean(row.mvp_slide_categoria_override_flag);
  if (
    editorialOverride
    && normalizeProviderName(row.mvp_slide_categoria_motivo).includes("risco corporativo")
  ) {
    return "MÉDICI · BRF/MARFRIG*";
  }
  const label = fundEditorialName(name, editorialOverride ? maxChars - 1 : maxChars);
  return editorialOverride ? `${label}*` : label;
}

function structuralPartyLabel(row, maxChars = 31) {
  const originator = isMissingStructuralText(row.originador) ? "" : String(row.originador);
  const assignor = isMissingStructuralText(row.cedente) ? "" : String(row.cedente);
  if (originator && assignor && normalizeProviderName(originator) === normalizeProviderName(assignor)) {
    return truncateWords(`O/C: ${originator}`, maxChars);
  }
  if (originator && assignor) return truncateWords(`O: ${originator} · C: ${assignor}`, maxChars);
  if (originator) return truncateWords(`O: ${originator}`, maxChars);
  if (assignor) return truncateWords(`C: ${assignor}`, maxChars);
  if (!isMissingStructuralText(row.cedente_originador_literal)) {
    const role = normalizeProviderName(row.papel_literal);
    const prefix = role.includes("originador") ? "O: " : role.includes("cedente") ? "C: " : "";
    return truncateWords(`${prefix}${row.cedente_originador_literal}`, maxChars);
  }
  return "N/D";
}

function structuralMinimumLabel(row) {
  let display = isMissingStructuralText(row.minimo_estrutural_display)
    ? ""
    : String(row.minimo_estrutural_display);
  const numeric = structuralNumeric(row.minimo_estrutural_usado);
  if (!display && numeric !== null) display = pct(numeric, 1);
  if (!display) return "N/D";
  const nature = structuralNatureLabel(row.minimo_estrutural_natureza);
  const exceptionalNature = !["Jr", "N/D"].includes(nature);
  const marker = structuralBoolean(row.excecao_asterisco_flag) || exceptionalNature ? "*" : "";
  return `${display} · ${nature}${marker && !nature.endsWith("*") ? marker : ""}`;
}

function compactStructuralPriceAmount(amount) {
  const normalized = String(amount || "").replace(/\s+/g, " ").trim();
  const numeric = Number(
    normalized
      .replace(/^R\$\s*/i, "")
      .replace(/\./g, "")
      .replace(",", "."),
  );
  if (!Number.isFinite(numeric)) return normalized;
  if (numeric >= 1_000_000) {
    return `R$ ${(numeric / 1_000_000).toLocaleString("pt-BR", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    })} mi`;
  }
  if (numeric >= 10_000) {
    return `R$ ${(numeric / 1_000).toLocaleString("pt-BR", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    })} mil`;
  }
  return `R$ ${numeric.toLocaleString("pt-BR", {
    minimumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
    maximumFractionDigits: 2,
  })}`;
}

function structuralPriceLabel(row) {
  const display = isMissingStructuralText(row.preco_cota_display)
    ? ""
    : String(row.preco_cota_display);
  if (!display) return "N/D";
  const priceContext = normalizeProviderName([
    display,
    row.preco_cota_natureza,
    row.preco_cota_status,
  ].filter(Boolean).join(" "));
  if (["spread", "remuneracao", "quantidade"].some((token) => priceContext.includes(token))) {
    return "N/D*";
  }
  const prices = display.split(/\s+\|\s+/).filter(Boolean);
  const classes = isMissingStructuralText(row.preco_cota_classe_serie)
    ? []
    : String(row.preco_cota_classe_serie).split(/\s+\|\s+/).filter(Boolean);
  const firstClass = normalizeProviderName(classes[0]);
  const classLabel = firstClass.includes("senior")
    ? "Sên."
    : firstClass.includes("junior")
      ? "Jr"
      : firstClass.includes("mezanino")
        ? "Mez."
        : firstClass.includes("subordinad")
          ? "Sub."
          : "Cota";
  const amount = prices[0]?.match(
    /R\$\s*\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,6})?|R\$\s*\d+(?:,\d{1,6})?/i,
  )?.[0];
  if (!amount) return "N/D*";
  const multiple = prices.length > 1 || classes.length > 1;
  const exceptional = structuralBoolean(row.preco_cota_excecao_asterisco_flag)
    || multiple
    || classes.length === 0;
  const suffix = multiple ? ` +${Math.max(prices.length, classes.length) - 1}` : "";
  // Duas linhas preservam sempre o valor numérico. A descrição integral por
  // classe/série permanece no workbook quando há múltiplos preços.
  return `${classLabel}\n${compactStructuralPriceAmount(amount)}${suffix}${exceptional ? "*" : ""}`;
}

function structuralHeadroomLabel(value) {
  const number = structuralNumeric(value);
  if (number === null) return "N/D";
  return `${number >= 0 ? "+" : ""}${(number * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} p.p.`;
}

function structuralMarketLabel(value) {
  const key = normalizeProviderName(value);
  if (key.includes("acima do mercado")) return "↑ pares";
  if (key.includes("abaixo do mercado")) return "↓ pares";
  if (key.includes("em linha")) return "→ pares";
  if (key.includes("sem benchmark")) return "— sem benchmark";
  return "— N/D";
}

function structuralSituationStyle(value) {
  const key = normalizeProviderName(value);
  if (key.includes("abaixo do minimo")) {
    return { fill: "#F8D7DA", color: "#7A1F3D" };
  }
  if (key.includes("folga estreita")) {
    return { fill: "#FFF0D6", color: "#A65A00" };
  }
  if (key.includes("acima do minimo") || key.includes("colchao alto")) {
    return { fill: "#DCEFE2", color: "#006B3C" };
  }
  return { fill: C.pale, color: C.mid };
}

function structuralSituationLabel(value) {
  const key = normalizeProviderName(value);
  if (key.includes("abaixo do minimo")) return "abaixo mín.";
  if (key.includes("folga estreita")) return "folga estreita";
  if (key.includes("colchao alto")) return "colchão alto";
  if (key.includes("acima do minimo")) return "acima mín.";
  return "não medido";
}

function structuralReferenceText(group, payload) {
  const row = (payload.carteira_1_structural_taxonomy || []).find(
    (candidate) => normalizedStructuralGroup(candidate.taxonomia) === group,
  );
  if (!row) {
    return "Referência da taxonomia · Sem grupo comparável; mediana e média PL-ponderada permanecem N/D.";
  }
  const portfolioMedian = structuralNumeric(row.carteira_sub_atual_mediana);
  const portfolioWeighted = structuralNumeric(row.carteira_sub_atual_ponderada);
  const flagshipMedian = structuralNumeric(row.flagship_sub_atual_mediana);
  const format = (value) => value === null ? "N/D" : pct(value, 1);
  return [
    "Referência da taxonomia",
    `Carteira I · mediana ${format(portfolioMedian)} · média PL-ponderada ${format(portfolioWeighted)}`,
    `Flagships · mediana ${format(flagshipMedian)} · ${integer(row.flagship_cnpjs_com_subordinacao)}/${integer(row.flagship_cnpjs)} com dado`,
    row.posicao_vs_mercado || "N/D",
  ].join("   |   ");
}

function top20PartyLookup(payload) {
  const exportCandidates = [
    ...(payload.portfolio_export_carteira_101 || []),
    ...(payload.portfolio_export_flagships || []),
  ];
  const byCnpj = new Map();
  exportCandidates.forEach((row) => {
    const cnpj = cnpjDigits(row.cnpj || row.cnpj_numerico);
    if (!cnpj || /^0+$/.test(cnpj)) return;
    const label = structuralPartyLabel(row);
    const score = label === "N/D"
      ? 0
      : 1
        + (!isMissingStructuralText(row.originador) ? 1 : 0)
        + (!isMissingStructuralText(row.cedente) ? 1 : 0)
        + (normalizeProviderName(row.status_complemento_manual).includes("manual") ? 0 : 2);
    const current = byCnpj.get(cnpj);
    if (!current || score > current.score) {
      byCnpj.set(cnpj, {
        label,
        score,
        manual: normalizeProviderName(row.status_complemento_manual).includes("manual"),
      });
    }
  });

  const manualByRoot = new Map();
  (payload.manual_cnpj_enrichment || []).forEach((row) => {
    const root = String(row.raiz_cnpj_foto || "").replace(/\D/g, "").padStart(8, "0");
    const confirmed = structuralBoolean(row.status_confirmado)
      || normalizeProviderName(row.status_transcricao).includes("confirmado");
    if (!confirmed || !/^\d{8}$/.test(root) || /^0+$/.test(root) || manualByRoot.has(root)) return;
    const label = structuralPartyLabel(row);
    if (label !== "N/D") manualByRoot.set(root, label);
  });

  return (row) => {
    const cnpj = cnpjDigits(row.cnpj_fundo || row.cnpj_veiculo || row.fund_key);
    const exported = byCnpj.get(cnpj);
    if (exported?.label && exported.label !== "N/D") {
      return exported.manual ? `${exported.label}*` : exported.label;
    }
    const manual = manualByRoot.get(cnpj.slice(0, 8));
    return manual ? `${manual}*` : "N/D";
  };
}

const STRUCTURAL_MVP_BANDS = Object.freeze([
  "< 10%", "10%–15%", "15%–20%", "20%–35%", "35%–60%", "≥ 60%",
]);

function structuralMvpMinima(row) {
  const literal = structuralNumeric(row.minimo_junior_literal);
  const calculated = structuralNumeric(row.minimo_junior_calculado);
  const adjusted = structuralNumeric(row.minimo_junior_ajustado);
  const junior = literal ?? calculated ?? adjusted;
  const juniorMarker = literal === null && junior !== null ? "*" : "";
  const total = structuralNumeric(row.suporte_total);
  const combined = structuralNumeric(row.suporte_combinado_junior_mezanino);
  const structural = total ?? combined;
  const structuralMarker = (
    combined !== null
    || structuralBoolean(row.excecao_asterisco_flag)
    || !structuralBoolean(row.comparavel_flag)
  ) ? "*" : "";
  return `Jr ${junior === null ? "N/D" : `${pct(junior, 1)}${juniorMarker}`} · Estr. ${structural === null ? "N/D" : pct(structural, 1)}${structuralMarker}`;
}

function structuralMvpCardStyle(status) {
  const key = normalizeProviderName(status);
  if (key.includes("incomparavel") || key === "n/d") {
    return { fill: "#F5F6F7", color: "#5E646A", line: "#B8BDC2" };
  }
  if (key.includes("abaixo do piso")) {
    return { fill: "#7A1F3D", color: C.white, line: "#7A1F3D" };
  }
  if (key.includes("ate 2 p.p. acima")) {
    return { fill: "#FFF0D6", color: "#7A1F3D", line: "#EC7000" };
  }
  return { fill: "#EAF0F7", color: "#002B5C", line: "#AFC5DD" };
}

function structuralMvpMedian(rows, field) {
  const values = rows
    .map((row) => structuralNumeric(row[field]))
    .filter((value) => value !== null)
    .sort((a, b) => a - b);
  if (!values.length) return null;
  const middle = Math.floor(values.length / 2);
  return values.length % 2 ? values[middle] : (values[middle - 1] + values[middle]) / 2;
}

function structuralMvpTaxonomyRows(payload, sourceGroups) {
  return (payload.carteira_1_structural_taxonomy || []).filter((row) =>
    sourceGroups.includes(normalizedStructuralGroup(row.taxonomia))
  );
}

function structuralMvpMarketReading(entry, taxonomyRows, slideRows) {
  if (entry.group === "Consignado INSS e FGTS") {
    const inss = taxonomyRows.find((row) => normalizedStructuralGroup(row.taxonomia) === "Consignado INSS") || {};
    const fgts = taxonomyRows.find((row) => normalizedStructuralGroup(row.taxonomia) === "Consignado FGTS") || {};
    const inssRows = slideRows.filter((row) => normalizedStructuralGroup(row.grupo_comparacao) === "Consignado INSS");
    const fgtsRows = slideRows.filter((row) => normalizedStructuralGroup(row.grupo_comparacao) === "Consignado FGTS");
    return {
      reference: `INSS carteira ${pct(structuralMvpMedian(inssRows, "sub_pl_atual"), 1)} vs. pares ${pct(inss.flagship_sub_atual_mediana, 1)} | FGTS carteira ${pct(structuralMvpMedian(fgtsRows, "sub_pl_atual"), 1)} vs. pares ${pct(fgts.flagship_sub_atual_mediana, 1)}`,
      conclusion: "≈ Em linha nos dois grupos",
      caveat: "Comparação da Sub/PL atual; mínimos júnior e estrutural permanecem identificados separadamente.",
    };
  }
  const row = taxonomyRows[0] || {};
  const peers = integer(row.flagship_cnpjs_com_subordinacao);
  const portfolioMedian = structuralMvpMedian(slideRows, "sub_pl_atual");
  const marketMedian = structuralNumeric(row.flagship_sub_atual_mediana);
  if (entry.group === "Financeiro") {
    return {
      reference: `Referência ampla · ${peers} pares · med. carteira ${pct(portfolioMedian, 1)} vs. mercado ${pct(marketMedian, 1)}`,
      conclusion: "≈ Em linha na referência ampla*",
      caveat: "O grupo Financeiro reúne estruturas distintas; a leitura relativa é direcional.",
    };
  }
  if (entry.group === "Adquirência") {
    return {
      reference: `${peers} pares · med. agregada carteira ${pct(portfolioMedian, 1)} vs. mercado ${pct(marketMedian, 1)}`,
      conclusion: "N/D · mistura risco emissor e adquirente*",
      caveat: "A mediana agregada muda com o subtipo; o slide preserva a ressalva.",
    };
  }
  if (peers < 5) {
    return {
      reference: peers ? `${peers} pares com Sub/PL atual` : "Sem pares documentais",
      conclusion: "N/D · benchmark insuficiente",
      caveat: "Amostra abaixo do mínimo configurável de cinco pares.",
    };
  }
  return {
    reference: `${peers} pares · med. carteira ${pct(portfolioMedian, 1)} vs. mercado ${pct(marketMedian, 1)}`,
    conclusion: row.posicao_vs_mercado || "N/D",
    caveat: "Comparação da Sub/PL atual por taxonomia.",
  };
}

function structuralMvpTitle(entry, rows) {
  const breaches = rows.filter((row) => normalizeProviderName(row.mvp_situacao_piso).includes("abaixo do piso"));
  const thin = rows.filter((row) => normalizeProviderName(row.mvp_situacao_piso).includes("ate 2 p.p. acima"));
  const incomparable = rows.filter((row) => normalizeProviderName(row.mvp_situacao_piso).includes("incomparavel"));
  if (breaches.length) {
    return `${entry.group} | ${breaches.length} ${breaches.length === 1 ? "veículo comparável está" : "veículos comparáveis estão"} abaixo do mínimo estrutural`;
  }
  if (thin.length) {
    return `${entry.group} | ${thin.length} ${thin.length === 1 ? "veículo comparável está" : "veículos comparáveis estão"} até 2 p.p. acima do mínimo estrutural`;
  }
  if (incomparable.length) {
    return `${entry.group} | Sub atual e mínimos documentais por veículo; ${incomparable.length} ${incomparable.length === 1 ? "estrutura exige" : "estruturas exigem"} leitura separada`;
  }
  return `${entry.group} | Sub atual e mínimos documentais por veículo`;
}

function addStructuralMvpSlides(presentation, payload) {
  const allRows = [...(payload.portfolio_export_carteira_101 || [])];
  if (allRows.length !== 101) {
    throw new Error(`MVP estrutural exige os 101 CNPJs da Carteira I; recebeu ${allRows.length}.`);
  }
  const eligible = allRows.filter((row) => structuralBoolean(row.mvp_elegivel_flag));
  const expectedEligible = Math.round(num(payload.carteira_1_structural_summary?.mvp_cnpjs_elegiveis));
  if (expectedEligible <= 0 || eligible.length !== expectedEligible) {
    throw new Error(`MVP estrutural deveria conter ${expectedEligible || "N/D"} CNPJs elegíveis; recebeu ${eligible.length}.`);
  }
  const eligibleCnpjs = new Set();
  eligible.forEach((row) => {
    const cnpj = cnpjDigits(row.cnpj || row.cnpj_numerico);
    if (!cnpj) throw new Error("MVP estrutural contém CNPJ elegível inválido.");
    if (eligibleCnpjs.has(cnpj)) throw new Error(`MVP estrutural contém CNPJ duplicado: ${cnpj}.`);
    eligibleCnpjs.add(cnpj);
  });
  const shown = new Set();
  STRUCTURAL_MVP_SLIDE_SEQUENCE.forEach((entry) => {
    const rows = eligible
      .filter((row) => row.mvp_slide_categoria === entry.group)
      .sort((a, b) => {
        const severity = (row) => {
          const key = normalizeProviderName(row.mvp_situacao_piso);
          return key.includes("abaixo do piso") ? 0 : key.includes("ate 2 p.p. acima") ? 1 : 2;
        };
        return severity(a) - severity(b)
          || num(b.pl_atual_brl) - num(a.pl_atual_brl)
          || num(a.ordem) - num(b.ordem);
      });
    rows.forEach((row) => shown.add(String(row.cnpj)));
    const taxonomyRows = structuralMvpTaxonomyRows(payload, entry.sourceGroups);
    const market = structuralMvpMarketReading(entry, taxonomyRows, rows);
    const totalRows = allRows.filter((row) => row.mvp_slide_categoria === entry.group);
    const totalPl = totalRows.reduce((sum, row) => sum + num(row.pl_atual_brl), 0);
    const eligiblePl = rows.reduce((sum, row) => sum + num(row.pl_atual_brl), 0);
    const slide = presentation.slides.add();
    addHeader(
      slide,
      `RISCO ESTRUTURAL · CARTEIRA I · ${entry.group}`,
      structuralMvpTitle(entry, rows),
      `CVM, Informe Mensal, ${competenceShortPt(payload.latest_complete).toLowerCase()}; pisos em regulamentos FundosNet/B3. Lacunas ficam fora do slide e permanecem no workbook/explorador.`,
      0,
    );

    const summaryCards = [
      {
        label: "COBERTURA DO SLIDE",
        value: `${integer(rows.length)}/${integer(totalRows.length)} CNPJs · ${moneyScale(eligiblePl)} de ${moneyScale(totalPl)}`,
        fill: "#EAF0F7",
        color: "#002B5C",
      },
      {
        label: "REFERÊNCIA DE MERCADO · SUB/PL ATUAL",
        value: market.reference,
        fill: C.white,
        color: C.charcoal,
      },
      {
        label: "LEITURA RELATIVA",
        value: market.conclusion,
        fill: "#FFF1E6",
        color: "#7A1F3D",
      },
    ];
    const cardWidths = [330, 505, 305];
    let cardLeft = 60;
    summaryCards.forEach((card, index) => {
      addText(
        slide,
        `${card.label}\n${card.value}`,
        { left: cardLeft, top: 121, width: cardWidths[index], height: 64 },
        {
          name: `mvp-summary-${entry.id}-${index + 1}`,
          fontSize: 13.333333,
          bold: true,
          color: card.color,
          fill: card.fill,
          lineFill: index === 1 ? "#AFC5DD" : card.fill,
          lineWidth: index === 1 ? 1 : 0,
          verticalAlignment: "middle",
          insets: { top: 7, right: 10, bottom: 7, left: 10 },
        },
      );
      cardLeft += cardWidths[index] + 10;
    });

    const columnGap = 8;
    const columnWidth = (1160 - columnGap * 5) / 6;
    STRUCTURAL_MVP_BANDS.forEach((band, bandIndex) => {
      const left = 60 + bandIndex * (columnWidth + columnGap);
      addText(
        slide,
        band,
        { left, top: 198, width: columnWidth, height: 24 },
        {
          name: `mvp-band-${entry.id}-${bandIndex + 1}`,
          fontSize: 14,
          bold: true,
          color: "#002B5C",
          alignment: "center",
          verticalAlignment: "middle",
          wrap: "none",
        },
      );
      addRule(slide, left, 222, columnWidth, "#002B5C", 2);
      const bandRows = rows.filter((row) => row.mvp_faixa_sub_atual === band);
      if (bandRows.length > 12) {
        throw new Error(`${entry.group} tem ${bandRows.length} cartões na faixa ${band}; revise a paginação do capítulo.`);
      }
      const rowGap = 2;
      const cardHeight = bandRows.length
        ? Math.min(46, Math.max(29, Math.floor((392 - rowGap * (bandRows.length - 1)) / bandRows.length)))
        : 46;
      const cardFontSize = bandRows.length <= 8 ? 13.333333 : bandRows.length <= 10 ? 11.5 : 10;
      bandRows.forEach((row, rowIndex) => {
        const style = structuralMvpCardStyle(row.mvp_situacao_piso);
        const cnpj = String(row.cnpj || row.cnpj_numerico || "nd").replace(/\D/g, "");
        addText(
          slide,
          `${structuralFundName(row, 21)}\n${moneyScale(row.pl_atual_brl)} · Sub atual ${pct(row.sub_pl_atual, 1)}\n${structuralMvpMinima(row)}`,
          {
            left,
            top: 229 + rowIndex * (cardHeight + rowGap),
            width: columnWidth,
            height: cardHeight,
          },
          {
            name: `mvp-card-${entry.id}-${cnpj}`,
            fontSize: cardFontSize,
            bold: true,
            color: style.color,
            fill: style.fill,
            lineFill: style.line,
            lineWidth: 1,
            verticalAlignment: "middle",
            wrap: "none",
            lineSpacing: 0.95,
            insets: { top: 3, right: 5, bottom: 3, left: 5 },
          },
        );
      });
    });
    addText(
      slide,
      `Vinho = abaixo do mínimo estrutural · âmbar = até 2 p.p. acima · azul = mais de 2 p.p. acima · cinza = estrutura incomparável. * Categoria editorial ou piso total, combinado, calculado, ajustado ou sem equivalência direta.`,
      { left: 60, top: 628, width: 1160, height: 31 },
      { fontSize: 13.333333, color: C.note, alignment: "right", verticalAlignment: "middle", wrap: "none" },
    );
    addSourceNotes(slide, [
      "Unidade: um cartão por CNPJ elegível da Carteira I; cada cartão é uma única caixa de texto nomeada pelo CNPJ para reorganização manual.",
      "Elegibilidade do MVP: Sub/PL atual, piso documental e PL do veículo disponíveis. Casos excluídos permanecem integralmente no workbook e no explorador.",
      "O sinal vinho, âmbar ou azul compara Sub/PL atual ao mínimo estrutural somente quando numerador, denominador e tranche são equivalentes; cinza preserva o índice documental sem concluir folga.",
      "O asterisco marca categoria editorial, piso total, combinado, calculado, ajustado ou sem equivalência direta; natureza, fórmula, documento e cláusula permanecem por CNPJ no workbook.",
      `Benchmark: ${market.caveat}`,
    ]);
  });
  if (shown.size !== eligible.length) {
    throw new Error(`Slides MVP exibiram ${shown.size}/${eligible.length} CNPJs elegíveis.`);
  }
}

function addFlagshipCurationSlide(presentation, payload) {
  const rows = [...(payload.carteira_1_structural_taxonomy || [])]
    .sort((a, b) => num(a.ordem) - num(b.ordem));
  const summary = payload.carteira_1_structural_summary || {};
  if (rows.length !== 7 || num(summary.cnpjs) !== 101) {
    throw new Error("Risco estrutural deveria reconciliar sete taxonomias e 101 CNPJs.");
  }
  const vehicle = rows.find((row) => row.taxonomia === "Veículos") || {};
  const slide = presentation.slides.add();
  addHeader(
    slide,
    "RISCO ESTRUTURAL · COBERTURA POR TAXONOMIA",
    `Veículos tem ${integer(vehicle.flagship_cnpjs_com_subordinacao)} pares com subordinação e permanece sem PL mensurável na Carteira I`,
    `CVM, Informe Mensal, ${competenceShortPt(payload.latest_complete).toLowerCase()}; regulamentos FundosNet/B3 lidos por CNPJ. Lacunas permanecem N/D.`,
    0,
  );
  const metrics = [
    ["MÍNIMO JÚNIOR", `${integer(summary.cnpjs_com_minimo_junior)}/101 · ${pct(summary.cobertura_minimo_junior_pct, 1)}`],
    ["MÍNIMO ESTRUTURAL", `${integer(summary.cnpjs_com_minimo_estrutural)}/101 · ${pct(summary.cobertura_minimo_estrutural_pct, 1)}`],
    ["FOLGA COMPARÁVEL", `${integer(summary.cnpjs_com_folga_comparavel)}/101 CNPJs`],
  ];
  metrics.forEach(([label, value], index) => {
    const left = 60 + index * 390;
    addRect(slide, { left, top: 132, width: 370, height: 54 }, index === 1 ? "#FFF1E6" : C.pale);
    addText(slide, label, { left: left + 12, top: 139, width: 150, height: 14 }, { fontSize: 7.8, bold: true, color: C.mid, wrap: "none" });
    addText(slide, value, { left: left + 160, top: 137, width: 195, height: 28 }, { fontSize: 15, bold: true, color: index === 1 ? C.orange : C.charcoal, alignment: "right", verticalAlignment: "middle", wrap: "none" });
  });
  const tableTop = 204;
  const tableHeight = 390;
  addNativeEditorialTable(slide, {
    left: 65,
    top: tableTop,
    width: 1155,
    height: tableHeight,
    headers: ["Taxonomia", "Carteira · CNPJs", "PL dos veículos", "47 flagships · CNPJs", "Presença", "Mín. Jr localizado", "Mín. estrutural"],
    rows: rows.map((row) => [
      row.taxonomia,
      `${integer(row.carteira_cnpjs_com_pl)}/${integer(row.carteira_cnpjs)}`,
      row.carteira_pl_brl == null ? "N/D" : moneyScale(row.carteira_pl_brl),
      `${integer(row.flagship_cnpjs_com_subordinacao)}/${integer(row.flagship_cnpjs)}`,
      row.presenca_carteira,
      `${integer(row.carteira_minimo_junior_cnpjs)}/${integer(row.carteira_cnpjs)}`,
      `${integer(row.carteira_minimo_estrutural_cnpjs)}/${integer(row.carteira_cnpjs)}`,
    ]),
    columnWidths: [175, 125, 145, 145, 220, 165, 180],
    aligns: ["left", "right", "right", "right", "left", "right", "right"],
    fontSize: 9.4,
    headerFontSize: 8.2,
    headerHeight: 27,
  });
  addStructuralRowStrips(slide, rows, { left: 60, top: tableTop, height: tableHeight, headerHeight: 27 });
  addText(slide, `${summary.asterisco} ${summary.nota_pl}`, { left: 60, top: 607, width: 1160, height: 38 }, { fontSize: 8.2, color: C.note, verticalAlignment: "middle" });
  addSourceNotes(slide, [
    "Unidade: CNPJ. A presença compara os sete tipos já usados na curadoria flagship; N/D não é convertido em zero.",
    "Mínimo estrutural inclui mínimo júnior e, com asterisco, suporte total/combinado documentado.",
    "Documento, página, fórmula, natureza e motivo de comparabilidade constam na aba Risco estrutural ativos.",
  ]);
}

function addCarteira1CurationSlide(presentation, payload) {
  const carteira = payload.portfolio_export_carteira_101 || [];
  const flagships = payload.portfolio_export_flagships || [];
  if (carteira.length !== 101 || flagships.length !== 47) {
    throw new Error(
      `Detalhe estrutural exige 101 CNPJs da Carteira I e 47 flagships; recebeu ${carteira.length} + ${flagships.length}.`,
    );
  }
  const allRows = [...carteira, ...flagships].map((row) => ({
    ...row,
    _grupo: normalizedStructuralGroup(row.grupo_comparacao || row.taxonomia_estrutural),
  }));
  const lineKeys = allRows.map((row) => `${row.coorte || "N/D"}::${String(row.cnpj || "")}`);
  if (new Set(lineKeys).size !== allRows.length) {
    throw new Error("Detalhe estrutural contém CNPJ duplicado dentro da mesma base.");
  }
  const pagesByGroup = new Map();
  STRUCTURAL_DETAIL_SLIDE_SEQUENCE.forEach((entry) => {
    const current = pagesByGroup.get(entry.group) || [];
    current.push(entry);
    pagesByGroup.set(entry.group, current);
  });
  const rowsByGroup = new Map();
  for (const [group, entries] of pagesByGroup.entries()) {
    const rows = allRows
      .filter((row) => row._grupo === group)
      .sort((a, b) => {
        const baseA = a.coorte === "Carteira 101" ? 0 : 1;
        const baseB = b.coorte === "Carteira 101" ? 0 : 1;
        return baseA - baseB
          || num(a.ordem, Number.MAX_SAFE_INTEGER) - num(b.ordem, Number.MAX_SAFE_INTEGER)
          || String(a.nome_oficial_cvm || a.nome_referencia || "").localeCompare(
            String(b.nome_oficial_cvm || b.nome_referencia || ""),
            "pt-BR",
          );
      });
    const rowsPerPage = STRUCTURAL_ROWS_PER_SLIDE[group] || 10;
    if (Math.ceil(rows.length / rowsPerPage) !== entries.length) {
      throw new Error(
        `Paginação estrutural de ${group} exige ${entries.length} páginas de até ${rowsPerPage} linhas; recebeu ${rows.length} CNPJs.`,
      );
    }
    rowsByGroup.set(group, rows);
  }
  const coveredRows = [...rowsByGroup.values()].reduce((sum, rows) => sum + rows.length, 0);
  if (coveredRows !== allRows.length) {
    throw new Error(`Paginação estrutural cobriu ${coveredRows}/${allRows.length} linhas.`);
  }

  let emittedRows = 0;
  STRUCTURAL_DETAIL_SLIDE_SEQUENCE.forEach((entry) => {
    const groupRows = rowsByGroup.get(entry.group) || [];
    const rowsPerPage = STRUCTURAL_ROWS_PER_SLIDE[entry.group] || 10;
    const pageRows = groupRows.slice(
      (entry.page - 1) * rowsPerPage,
      entry.page * rowsPerPage,
    );
    emittedRows += pageRows.length;
    const slide = presentation.slides.add();
    addHeader(
      slide,
      `RISCO ESTRUTURAL · ${entry.group}`,
      `${entry.group}: ${integer(groupRows.length)} CNPJs da Carteira I e dos flagships · ${entry.page}/${entry.pages}`,
      `CVM, Informe Mensal, ${competenceShortPt(payload.latest_complete).toLowerCase()}; mesma base normalizada do workbook. N/D permanece lacuna.`,
      0,
    );
    addText(
      slide,
      "Cor = situação frente ao piso documental. A seta em texto mostra a posição relativa aos pares; sem benchmark confiável, a posição fica N/D.",
      { left: 60, top: 119, width: 1160, height: 25 },
      { fontSize: TYPOGRAPHY.axis, color: C.charcoal, verticalAlignment: "middle", wrap: "none" },
    );
    const tableTop = 150;
    const tableHeight = Math.min(420, 30 + pageRows.length * 39);
    const table = addNativeEditorialTable(slide, {
      left: 60,
      top: tableTop,
      width: 1160,
      height: tableHeight,
      headers: [
        "Base", "CNPJ", "FIDC", "Originador / cedente", "PL", "Sub atual",
        "Mín. Jr / estrut.", "Folga", "Preço unitário*", "Situação",
      ],
      rows: pageRows.map((row) => {
        const current = structuralNumeric(row.sub_pl_atual);
        const status = isMissingStructuralText(row.situacao_regulatoria)
          ? "não medido"
          : String(row.situacao_regulatoria);
        return [
          row.coorte === "Carteira 101" ? "Carteira I" : "Flagship",
          numericCnpjText(row.cnpj || row.cnpj_numerico),
          structuralFundName(row, 16),
          structuralPartyLabel(row, 17),
          structuralNumeric(row.pl_atual_brl) === null ? "N/D" : moneyScale(row.pl_atual_brl),
          current === null ? "N/D" : pct(current, 1),
          structuralMinimumLabel(row),
          structuralHeadroomLabel(row.folga_pp),
          structuralPriceLabel(row),
          `${structuralSituationLabel(status)} · ${structuralMarketLabel(row.posicao_mercado)}`,
        ];
      }),
      columnWidths: [90, 145, 155, 155, 70, 70, 110, 80, 125, 160],
      aligns: ["left", "left", "left", "left", "right", "right", "right", "right", "left", "left"],
      fontSize: TYPOGRAPHY.tableBody,
      headerFontSize: TYPOGRAPHY.tableHeader,
      headerHeight: 30,
    });
    pageRows.forEach((row, rowIndex) => {
      if (row.coorte === "Carteira 101") {
        table.cells.block({ row: rowIndex + 1, column: 0, rowCount: 1, columnCount: 1 }).textStyle.bold = true;
      }
      const style = structuralSituationStyle(row.situacao_regulatoria);
      const situation = table.cells.block({
        row: rowIndex + 1,
        column: 9,
        rowCount: 1,
        columnCount: 1,
      });
      situation.assign({ fill: style.fill });
      situation.textStyle.bold = true;
      situation.textStyle.color = style.color;
    });
    if (entry.page === entry.pages) {
      addRect(slide, { left: 60, top: 584, width: 1160, height: 43 }, C.pale);
      addText(
        slide,
        structuralReferenceText(entry.group, payload),
        { left: 73, top: 590, width: 1134, height: 31 },
        { fontSize: TYPOGRAPHY.axis, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle" },
      );
    }
    addText(
      slide,
      "* Mínimo não júnior ou preço/classe excepcional; detalhes e fontes no workbook. Preço = valor unitário por cota.",
      { left: 60, top: 634, width: 1160, height: 25 },
      { fontSize: TYPOGRAPHY.axis, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
    addSourceNotes(slide, [
      "Unidade: uma linha por CNPJ e base; Carteira I e flagships permanecem identificados na primeira coluna.",
      "Mínimo estrutural preserva a natureza documental: júnior, total, combinado, calculado ou ajustado; estruturas não comparáveis ficam sem folga.",
      "Preço unitário: VNU, preço de emissão, subscrição ou integralização por classe/série; quantidade, taxa, spread e remuneração não são exibidos.",
      "Cor codifica somente a situação regulatória. Posição relativa ao mercado usa seta textual neutra e exige pelo menos cinco pares.",
    ]);
  });
  if (emittedRows !== allRows.length) {
    throw new Error(`Slides estruturais emitiram ${emittedRows}/${allRows.length} linhas.`);
  }
}

function addCarteira1TaxonomySlide(presentation, payload) {
  const allRows = [...(payload.carteira_1_structural_watchlist || [])];
  const rows = allRows.slice(0, 8);
  const summary = payload.carteira_1_structural_summary || {};
  const slide = presentation.slides.add();
  addHeader(
    slide,
    "RISCO ESTRUTURAL · ATIVOS",
    `${integer(summary.cnpjs_com_folga_comparavel)} CNPJs têm folga calculável; estes 8 casos priorizam menor absorção e maior PL do veículo`,
    `CVM, Informe Mensal, ${competenceShortPt(payload.latest_complete).toLowerCase()}; regulamentos FundosNet/B3. Folga e absorção ficam N/D quando a tranche ou o denominador não são comparáveis.`,
    0,
  );
  const highlights = new Set(rows.map((row, index) => ["abaixo do mínimo", "folga estreita"].includes(String(row.situacao_regulatoria)) ? index : null).filter((index) => index != null));
  addNativeEditorialTable(slide, {
    left: 60,
    top: 138,
    width: 1160,
    height: 414,
    headers: ["Ativo", "Taxonomia", "PL veículo", "Sub. atual", "Mínimo", "Métrica", "Folga", "Absorção", "Situação"],
    rows: rows.map((row) => [
      truncateWords(row.ativo, 34),
      row.categoria,
      row.pl_atual == null ? "N/D" : moneyScale(row.pl_atual),
      row.sub_pl_atual == null ? "N/D" : pct(row.sub_pl_atual, 1),
      row.minimo_estrutural_display || "N/D",
      structuralNatureLabel(row.minimo_estrutural_natureza),
      row.folga_pp == null ? "N/D" : `${num(row.folga_pp) >= 0 ? "+" : ""}${(num(row.folga_pp) * 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} p.p.`,
      row.perda_ate_gatilho == null ? "N/D" : pct(row.perda_ate_gatilho, 1),
      row.situacao_regulatoria,
    ]),
    columnWidths: [250, 125, 110, 105, 110, 100, 100, 105, 155],
    aligns: ["left", "left", "right", "right", "right", "left", "right", "right", "left"],
    fontSize: TYPOGRAPHY.tableBody,
    headerFontSize: TYPOGRAPHY.tableHeader,
    headerHeight: 27,
    rowHighlights: highlights,
    emphasizeHighlightedRows: true,
  });
  addText(
    slide,
    `* Mínimo estrutural pode ser total/combinado. Lista executiva: 8 de ${integer(allRows.length)} casos; os 101 CNPJs e as fontes estão no workbook.`,
    { left: 60, top: 578, width: 1160, height: 42 },
    { fontSize: TYPOGRAPHY.axis, color: C.note, alignment: "right", verticalAlignment: "middle" },
  );
  addSourceNotes(slide, [
    "Capacidade de absorção até o gatilho = (subordinação atual − mínimo) / (1 − mínimo).",
    "Realce laranja identifica situação regulatória abaixo do mínimo ou em folga estreita. A posição relativa ao mercado usa setas no slide anterior.",
    "A lista mostra oito casos mensuráveis; a aba Risco estrutural ativos preserva os 101 CNPJs e todas as lacunas.",
  ]);
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
  const presentation = installPresentationTypography(Presentation.create({ slideSize: SLIDE }));
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
    addText(slide, `Dados de referência: jun-26 · fechamento em ${stockLong}`, { left: 60, top: 555, width: 720, height: 28 }, {
      fontSize: 16,
      color: C.white,
    });
    addText(slide, "Ofertas CVM e comparativo ANBIMA até 30 de junho de 2026", { left: 60, top: 589, width: 720, height: 28 }, {
      fontSize: 16,
      color: C.light,
    });
    addText(slide, "Itaú BBA · Agosto de 2026", { left: 60, top: 657, width: 500, height: 22 }, {
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
      `Fonte: CVM, ANBIMA e FundosNet; ${stockShortLower}. Ofertas CVM e ANBIMA até jun/26.`,
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
      "ANBIMA — Coletiva de Mercado de Capitais 1S26, valor encerrado até jun/26: https://www.anbima.com.br/data/files/8E/86/DB/07/325AF91098D078F9692BA2A8/Apresentacao%20_%20coletiva%20Mercado%20de%20Capitais%20_%201S26.pdf",
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
      String(row.competencia) === latestCompetence ? stockShortLower : String(row.year),
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
        showValue: idx === expandedCredit.length - 1 && [0, 2].includes(seriesIndex),
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
      // Native PowerPoint labels are clipped to narrow stacked columns. Wider
      // columns keep the exact 7.666 label legible at the 10 pt typography floor.
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 10, overlap: 100 },
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
    });
    const latestCredit = expandedCredit.at(-1) || {};
    addLegend(slide, [
      { label: "Empréstimos", color: C.charcoal },
      { label: "Tít. privados", color: C.note },
      { label: "FIDCs", color: C.orange },
      { label: "Outras securit.", color: C.line },
      { label: "Dív. externa", color: C.light },
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
    const anbimaPeriods = [...new Map(
      marketReconciliation.map((row) => [
        row.period_label,
        { label: row.period_label, order: num(row.period_order) },
      ]),
    ).values()]
      .sort((a, b) => a.order - b.order)
      .map((row) => row.label);
    const latestAnbimaPeriod = anbimaPeriods.at(-1);
    const latestAnbimaSource = marketReconciliation.find(
      (row) => row.period_label === latestAnbimaPeriod,
    ) || {};
    if (latestAnbimaPeriod !== "2026 jan-jun" || latestAnbimaSource.anbima_source_snapshot !== "jun/26") {
      throw new Error("Slide 3 exige reconciliação ANBIMA 2026 jan-jun com snapshot jun/26.");
    }
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
    const latestCvmFidcBrl = num(comparison.find(
      (row) => row.view === viewA
        && row.series_label === "FIDCs"
        && row.period_label === "2026 jan-jun",
    )?.registered_volume_brl);
    const latestAnbimaFidcBrl = num(marketReconciliation.find(
      (row) => row.period_label === latestAnbimaPeriod && row.instrument_label === "FIDCs",
    )?.anbima_closed_volume_brl);
    if (latestCvmFidcBrl <= 0 || latestAnbimaFidcBrl <= 0) {
      throw new Error("Slide 3 sem valores positivos de FIDC para reconciliar CVM e ANBIMA em jan-jun/26.");
    }
    if (taxonomy.length !== 4 || taxonomyLong.length !== 20 || reconciliation.length !== 5) {
      throw new Error("Tabela Emissões por Categoria ANBIMA não fecha 4 categorias × 5 períodos.");
    }
    addHeader(
      slide,
      "OFERTAS ENCERRADAS · CVM E ANBIMA",
      "Emissões | FIDCs seguem ganhando escala nas emissões",
      `CVM/SRE: ${bn(latestCvmFidcBrl, 1)} registrado primário; ANBIMA: ${bn(latestAnbimaFidcBrl, 1)} encerrado. Perímetros distintos; jan–jun/26, snapshot jun/26.`,
      4,
    );
    addSectionLabel(slide, "FIDCs E DEMAIS INSTRUMENTOS ELEGÍVEIS · R$ BI", {
      left: 60,
      top: 132,
      width: 550,
      height: 24,
    });
    slide.charts.add("bar", {
      ...chartBase({ left: 60, top: 160, width: 550, height: 245 }),
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
      ...chartBase({ left: 670, top: 160, width: 550, height: 245 }),
      categories: anbimaPeriods.map((period) => period.replace("2026 jan-jun", "2026 jan–jun")),
      series: instruments.map(([instrument, color]) => ({
        name: instrument,
        values: anbimaPeriods.map((period) => marketValue(period, instrument)),
        valuesFormatCode: "0.0",
        fill: color,
        dataLabels: {
          showValue: ["Debêntures", "FIDCs"].includes(instrument),
          position: "outEnd",
          textStyle: { fill: C.black, fontSize: TYPOGRAPHY.dataLabel, bold: true },
        },
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
    });

    const growthRow = (label, sourceLabel, view) => {
      const row2025 = comparison.find(
        (row) => row.view === view && row.series_label === sourceLabel && row.period_label === "2025 FY",
      ) || {};
      const row2026 = comparison.find(
        (row) => row.view === view && row.series_label === sourceLabel && row.period_label === "2026 jan-jun",
      ) || {};
      const growthLabel = (value) => {
        const parsed = num(value);
        const rendered = pct(parsed, 1);
        return parsed > 0 ? `+${rendered}` : rendered;
      };
      return [label, growthLabel(row2025.yoy_growth), growthLabel(row2026.yoy_growth)];
    };
    const growthRows = [
      growthRow("FIDC", "FIDCs", viewA),
      growthRow("Demais Instr.", "Demais elegíveis", viewA),
      growthRow("Debêntures", "Debêntures", "FIDCs vs instrumentos materiais de 2025"),
      growthRow("CRI", "CRI", "FIDCs vs instrumentos materiais de 2025"),
      growthRow("Notas comerciais", "Notas comerciais", "FIDCs vs instrumentos materiais de 2025"),
      growthRow("CRA", "CRA", "FIDCs vs instrumentos materiais de 2025"),
    ];
    addSectionLabel(slide, "CRESCIMENTO POR INSTRUMENTO", {
      left: 300, top: 425, width: 680, height: 20,
    });
    const growthTable = addNativeEditorialTable(slide, {
      left: 300,
      top: 450,
      width: 680,
      height: 183,
      headers: ["Emissões por instrumento", "2025 YoY %", "1S26 YTD YoY"],
      rows: growthRows,
      columnWidths: [360, 160, 160],
      aligns: ["left", "right", "right"],
      fontSize: 10.2,
      headerFontSize: 10.0,
      headerHeight: 28,
      rowHighlights: new Set([0, 1]),
    });
    [[1, 1, "#007A3D"], [1, 2, "#007A3D"], [2, 2, "#7A1F3D"], [6, 2, "#7A1F3D"]]
      .forEach(([row, column, color]) => {
        const cell = growthTable.cells.block({ row, column, rowCount: 1, columnCount: 1 });
        cell.textStyle.bold = true;
        cell.textStyle.color = color;
      });
    [1, 2].forEach((row) => {
      growthTable.cells.block({ row, column: 0, rowCount: 1, columnCount: 1 }).textStyle.bold = true;
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
      `${latestAnbimaSource.anbima_source_name}, snapshot ${latestAnbimaSource.anbima_source_snapshot}, ${latestAnbimaSource.anbima_source_sheet}, ${latestAnbimaSource.anbima_source_range}: ${latestAnbimaSource.anbima_source_url}`,
      `Perímetros: CVM/SRE mede valor registrado de ofertas primárias encerradas (${bn(latestCvmFidcBrl, 1)} em FIDCs); ANBIMA mede valor encerrado (${bn(latestAnbimaFidcBrl, 1)}). Ambos cobrem jan–jun/26.`,
      "FIDCs 2023 no gráfico CVM: valor encerrado ANBIMA; a correção é idempotente e preserva bundles anteriores à republicação.",
    ]);
  }

  // 4B. Série ampla de mercado ANBIMA; preserva a ordem editorial anterior.
  {
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
    const taxonomyByKey = new Map(
      taxonomy.map((row) => [`${row.period_key}::${row.categoria}`, row]),
    );
    taxonomyPeriods.forEach(([periodKey]) => {
      taxonomyCategories.forEach((category) => {
        if (!taxonomyByKey.has(`${periodKey}::${category}`)) {
          throw new Error(`Taxonomia de emissões sem ${periodKey} × ${category}; zero não é imputado.`);
        }
      });
    });
    const taxonomyRow = (periodKey, category) => taxonomyByKey.get(`${periodKey}::${category}`);
    const periodOrder = [...new Map(
      reconciliation.map((row) => [
        row.period_label,
        { label: row.period_label, order: num(row.period_order) },
      ]),
    ).values()]
      .sort((a, b) => a.order - b.order)
      .map((row) => row.label);
    const latestMarketPeriod = periodOrder.at(-1);
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
    const deb2026 = rowFor(latestMarketPeriod, "Debêntures");
    const fidc2025 = rowFor("2025 FY", "FIDCs");
    const cri2025 = rowFor("2025 FY", "CRI");
    const cri2026 = rowFor(latestMarketPeriod, "CRI");
    const note2026 = rowFor(latestMarketPeriod, "Notas comerciais");
    const cra2023 = rowFor("2023 FY", "CRA");

    // 4. Síntese de estoque e emissões, com Outros aberto no estoque e
    // preservado como categoria positiva no fluxo de novas emissões.
    {
      const summarySlide = presentation.slides.add();
      const stockHistory = [...(payload.type_mix_history || [])].sort(
        (a, b) => num(a.period_order) - num(b.period_order) || num(a.category_order) - num(b.category_order),
      );
      const stockMeta = payload.type_mix_meta || {};
      const stockPeriods = (stockMeta.periods || [])
        .map((row) => ({ competencia: row.competencia, label: row.label }))
        .filter((row) => row.competencia && row.label);
      const stockBroad = ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro"];
      const outrosParts = ["Poder Público", "Multicedente/Multissacado", "Recuperação", "N/D"];
      const outrosSources = {
        "Poder Público": ["Poder Público"],
        "Multicedente/Multissacado": ["Multicarteira Outros", "Multicedente/Multissacado"],
        "Recuperação": ["Recuperação"],
        "N/D": ["N/D"],
      };
      const stockCategories = [...stockBroad, ...outrosParts];
      const display = {
        "Poder Público": "Precatórios / ações",
        "Multicedente/Multissacado": "Multicedente / multisacado",
        "Recuperação": "Recuperação / NP",
      };
      const colors = {
        "Fomento Mercantil": C.mid,
        "Agro, Indústria e Comércio": C.charcoal,
        "Financeiro": C.orange,
        "Poder Público": C.black,
        "Multicedente/Multissacado": C.note,
        "Recuperação": C.light,
        "N/D": C.line,
      };
      const stockByKey = new Map(stockHistory.map((row) => [`${row.competencia}::${row.anbima_tipo}`, row]));
      const outrosByKey = new Map(
        (payload.taxonomy_level_history || [])
          .filter((row) => row.nivel === "foco_analitico" && row.tipo_exibicao === "Outros")
          .map((row) => [`${row.competencia}::${row.categoria}`, row]),
      );
      const stockValue = (period, category, field) => {
        if (stockBroad.includes(category)) return num(stockByKey.get(`${period.competencia}::${category}`)?.[field]);
        return (outrosSources[category] || [category]).reduce((sum, sourceCategory) => {
          const row = outrosByKey.get(`${period.competencia}::${sourceCategory}`) || {};
          return sum + num(row[field === "pl" ? "pl_brl" : "share_total"]);
        }, 0);
      };
      stockPeriods.forEach((period) => {
        const broadOutros = num(stockByKey.get(`${period.competencia}::Outros`)?.pl);
        const openedOutros = outrosParts.reduce(
          (sum, category) => sum + stockValue(period, category, "pl"),
          0,
        );
        if (Math.abs(broadOutros - openedOutros) > 0.01) {
          throw new Error(`Abertura de Outros não reconcilia em ${period.competencia}; zero não é imputado.`);
        }
      });
      const stockSeries = (field, percent = false) => stockCategories.map((category, seriesIndex) => {
        const values = stockPeriods.map((period) => percent
          ? stockValue(period, category, field)
          : stockValue(period, category, field) / 1e9);
        return {
          name: display[category] || category,
          values,
          valuesFormatCode: percent ? "0.0%" : "0.0",
          fill: colors[category],
          dataLabelOverrides: values.map((value, idx) => ({
            idx,
            showValue: percent ? value >= 0.035 : value >= 15,
            position: "center",
            textStyle: { fill: seriesIndex <= 4 ? C.white : C.black, fontSize: TYPOGRAPHY.dataLabel, bold: true },
          })),
        };
      });
      const latestIssuanceOutros = taxonomyRow("jun26", "Outros");
      addHeader(
        summarySlide,
        "SALDO E TIPOS DE FIDCS",
        "Saldo e Tipos de FIDCs | Financeiros dominam saldo e novas emissões",
        `Fontes: CVM, Informe Mensal (${stockShortLower}) e CVM/SRE, ofertas encerradas jan–jun/26. Outros emitidos: ${bn(latestIssuanceOutros.volume_brl, 1)} (${pct(latestIssuanceOutros.share, 1)}).`,
        4,
      );
      addSectionLabel(summarySlide, "SALDO EX-FIC · R$ BI", { left: 60, top: 132, width: 550, height: 20 });
      summarySlide.charts.add("bar", {
        ...chartBase({ left: 60, top: 157, width: 550, height: 205 }),
        categories: stockPeriods.map((row) => row.label),
        series: stockSeries("pl"),
        barOptions: { direction: "column", grouping: "stacked", gapWidth: 48, overlap: 100 },
        hasLegend: false,
        xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 8 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
        yAxis: { ...chartAxis(7.5, "0"), min: 0 },
        dataLabels: { showValue: true, position: "center" },
      });
      addSectionLabel(summarySlide, "PARTICIPAÇÃO NO SALDO", { left: 670, top: 132, width: 550, height: 20 });
      summarySlide.charts.add("bar", {
        ...chartBase({ left: 670, top: 157, width: 550, height: 205 }),
        categories: stockPeriods.map((row) => row.label),
        series: stockSeries("share", true),
        barOptions: { direction: "column", grouping: "percentStacked", gapWidth: 48, overlap: 100 },
        hasLegend: false,
        xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 8 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
        yAxis: { ...chartAxis(7.5, "0%"), min: 0, max: 1, majorUnit: 0.25 },
        dataLabels: { showValue: true, position: "center" },
      });
      addShapeLegend(
        summarySlide,
        stockCategories.map((category) => ({ label: display[category] || category, color: colors[category] })),
        { left: 80, top: 365, width: 1120, height: 28 },
        4,
        { fontSize: 6.7, swatchSize: 7 },
      );
      addSectionLabel(summarySlide, "NOVAS EMISSÕES POR SETOR · R$ BI", { left: 60, top: 402, width: 550, height: 20 });
      summarySlide.charts.add("bar", {
        ...chartBase({ left: 60, top: 427, width: 550, height: 190 }),
        categories: taxonomyPeriods.map(([, label]) => label),
        series: taxonomyCategories.map((category) => ({
          name: category,
          values: taxonomyPeriods.map(([periodKey]) => num(taxonomyRow(periodKey, category).volume_brl) / 1e9),
          valuesFormatCode: "0.0",
          fill: taxonomyColors[category],
        })),
        barOptions: { direction: "column", grouping: "stacked", gapWidth: 45, overlap: 100 },
        hasLegend: true,
        legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 7 } },
        xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 7.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
        yAxis: { ...chartAxis(7.2, "0"), min: 0 },
        dataLabels: { showValue: true, position: "center", textStyle: { fill: C.black, fontSize: 5.2 } },
      });
      addSectionLabel(summarySlide, "NOVAS EMISSÕES POR SETOR · %", { left: 670, top: 402, width: 550, height: 20 });
      summarySlide.charts.add("bar", {
        ...chartBase({ left: 670, top: 427, width: 550, height: 190 }),
        categories: taxonomyPeriods.map(([, label]) => label),
        series: taxonomyCategories.map((category) => ({
          name: category,
          values: taxonomyPeriods.map(([periodKey]) => num(taxonomyRow(periodKey, category).share)),
          valuesFormatCode: "0.0%",
          fill: taxonomyColors[category],
        })),
        barOptions: { direction: "column", grouping: "percentStacked", gapWidth: 45, overlap: 100 },
        hasLegend: true,
        legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 7 } },
        xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 7.5 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
        yAxis: { ...chartAxis(7.2, "0%"), min: 0, max: 1, majorUnit: 0.25 },
        dataLabels: { showValue: true, position: "center", textStyle: { fill: C.black, fontSize: 5.0 } },
      });
      addSourceNotes(summarySlide, [
        "Saldo: classificação analítica por CNPJ; Outros é aberto em Precatórios/Ações, Multicedente/Multisacado, Recuperação/NP e N/D.",
        "Emissões: quatro tipos ANBIMA reconciliados com FIC-FIDC e total emitido; ausência permanece N/D e não vira zero.",
      ]);
    }

    // 5. Detalhamento das emissões por setor.
    const slide = presentation.slides.add();
    addHeader(
      slide,
      "EMISSÕES POR CATEGORIA ANBIMA",
      `Emissões por setor | Financeiro respondeu por ${pct(taxonomyRow("jun26", "Financeiro").share, 1)} do volume no 1S26`,
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
        `2025: CVM ${bn(deb2025.cvm_registered_volume_brl, 1)} + ${bn(deb2025.cvm_harmonization_volume_brl, 1)} em Outros títulos de securitização = ${bn(deb2025.cvm_harmonized_volume_brl, 1)}, ante ${bn(deb2025.anbima_closed_volume_brl, 1)} na ANBIMA. Jan–jun/26: ${bn(deb2026.cvm_harmonized_volume_brl, 1)} ante ${bn(deb2026.anbima_closed_volume_brl, 1)}.`,
      ],
      [
        "FIDCS · MÉTRICA E COBERTURA",
        `Em 2025, a CVM registra ${bn(fidc2025.cvm_registered_volume_brl, 1)} e a ANBIMA encerra ${bn(fidc2025.anbima_closed_volume_brl, 1)}. A diferença combina valor registrado versus encerrado, cobertura e presença de ofertas secundárias na ANBIMA; a causa individual exige reconciliação por oferta.`,
      ],
      [
        "CRI E NOTAS COMERCIAIS",
        `CRI: CVM ${pct(cri2025.raw_gap_pct, 1)} em 2025 e ${pct(cri2026.raw_gap_pct, 1)} em jan–jun/26 versus ANBIMA. Notas comerciais: ${pct(note2026.raw_gap_pct, 1)} em jan–jun/26. O residual pode refletir métrica, rito, retificações e data do snapshot.`,
      ],
      [
        "CRA · PONTO PENDENTE",
        `A CVM ficou ${pct(cra2023.raw_gap_pct, 1)} acima da ANBIMA em 2023. De 2024 a jan–jun/26, o desvio ficou em até 2,7%. A causa de 2023 permanece sem comprovação oferta a oferta.`,
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
      "2023\nR$ bi",
      "2024\nR$ bi",
      "2025\nR$ bi",
      "1S25\nR$ bi",
      "1S26\nR$ bi",
      "1S26\n%",
      "1S26 YoY",
    ];
    const byTaxonomyPeriod = Object.fromEntries(
      taxonomyReconciliation.map((row) => [row.period_key, row]),
    );
    const growthLabel = (current, prior) => {
      if (!num(prior)) return "N/D";
      const change = num(current) / num(prior) - 1;
      return `${change > 0 ? "+" : ""}${pct(change, 1)}`;
    };
    const categoryRows = taxonomyCategories.map((category) => {
      const row = (periodKey) => taxonomyRow(periodKey, category);
      return [
        category,
        biCell(num(row("2023").volume_brl) / 1e9),
        biCell(num(row("2024").volume_brl) / 1e9),
        biCell(num(row("2025").volume_brl) / 1e9),
        biCell(num(row("jun25").volume_brl) / 1e9),
        biCell(num(row("jun26").volume_brl) / 1e9),
        pct(row("jun26").share, 1),
        growthLabel(row("jun26").volume_brl, row("jun25").volume_brl),
      ];
    });
    const totalRow = (periodKey) => num(byTaxonomyPeriod[periodKey]?.emitted_volume_brl);
    const tableRows = [
      ...categoryRows,
      [
        "Total emitido",
        biCell(totalRow("2023") / 1e9),
        biCell(totalRow("2024") / 1e9),
        biCell(totalRow("2025") / 1e9),
        biCell(totalRow("jun25") / 1e9),
        biCell(totalRow("jun26") / 1e9),
        "100,0%",
        growthLabel(totalRow("jun26"), totalRow("jun25")),
      ],
    ];
    addSectionLabel(slide, "EMISSÕES POR CATEGORIA ANBIMA", {
      left: 60, top: 374, width: 1160, height: 18,
    });
    const taxonomyTable = addNativeEditorialTable(slide, {
      left: 60,
      top: 400,
      width: 1160,
      height: 214,
      headers: tableHeaders,
      rows: tableRows,
      columnWidths: [230, 105, 105, 105, 105, 105, 160, 245],
      aligns: ["left", "right", "right", "right", "right", "right", "right", "right"],
      fontSize: TYPOGRAPHY.tableBody,
      headerFontSize: TYPOGRAPHY.tableHeader,
      headerHeight: 30,
      rowHighlights: new Set([4]),
    });
    taxonomyCategories.forEach((category, rowIndex) => {
      const current = num(taxonomyRow("jun26", category).volume_brl);
      const prior = num(taxonomyRow("jun25", category).volume_brl);
      if (!prior) return;
      const change = current / prior - 1;
      const cell = taxonomyTable.cells.block({ row: rowIndex + 1, column: 7, rowCount: 1, columnCount: 1 });
      cell.textStyle.bold = true;
      cell.textStyle.color = change >= 0 ? "#007A3D" : "#7A1F3D";
    });
    const officialPortfolioOutros = (payload.carteira_1_curation || []).filter(
      (row) => row.anbima_tipo === "Outros" && num(row.pl_atual_brl) > 0,
    );
    const analyticalPortfolioOutros = (payload.carteira_1_taxonomy_history || []).find(
      (row) => row.competencia === payload.latest_complete && row.anbima_tipo === "Outros",
    ) || {};
    addRect(slide, { left: 60, top: 620, width: 1160, height: 36 }, C.pale);
    addText(
      slide,
      `CARTEIRA I · ${integer(officialPortfolioOutros.length)} CNPJs oficiais em Outros somam ${bn(officialPortfolioOutros.reduce((sum, row) => sum + num(row.pl_atual_brl), 0), 1)}; o ledger os redistribui em 5 Agro e 1 Financeiro. Nas emissões, Outros permanece positivo: ${bn(taxonomyRow("jun26", "Outros").volume_brl, 1)} no 1S26.`,
      { left: 74, top: 626, width: 1132, height: 24 },
      { fontSize: 9.1, bold: true, color: C.charcoal, alignment: "center", verticalAlignment: "middle", wrap: "none" },
    );
    addSourceNotes(slide, [
      "CVM/SRE — oferta_resolucao_160.csv e oferta_distribuicao.csv: https://dados.cvm.gov.br/dataset/oferta-distrib",
      "FIDCs 2023: valor encerrado ANBIMA, preservado da série histórica; composição não observada escalada pela composição CVM. Snapshot vigente: jun/26.",
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
          dataLabels: {
            showValue: true,
            position: "center",
            textStyle: { fill: C.white, fontSize: TYPOGRAPHY.dataLabel, bold: true },
          },
        },
        {
          name: "Qualificado",
          values: targetPeriods.map((period) => targetValue(period, "Qualificado")),
          valuesFormatCode: "0.0%",
          fill: C.charcoal,
          dataLabels: { showValue: false },
        },
        {
          name: "Geral",
          values: targetPeriods.map((period) => targetValue(period, "Público Geral")),
          valuesFormatCode: "0.0%",
          fill: C.mid,
          dataLabels: { showValue: false },
        },
        {
          name: "N/D",
          values: targetPeriods.map((period) => targetValue(period, "N/D")),
          valuesFormatCode: "0.0%",
          fill: C.light,
          dataLabels: { showValue: false },
        },
      ],
      barOptions: { direction: "column", grouping: "stacked", gapWidth: 45, overlap: 100 },
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fill: C.mid, fontSize: 8.5 } },
      xAxis: { visible: true, textStyle: { fill: C.mid, fontSize: 9 }, line: { style: "solid", fill: C.line, width: 1 }, majorGridlines: null },
      yAxis: { ...chartAxis(8.5, "0%"), min: 0, max: 1, majorUnit: 0.25 },
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
      "Multicedente/Multissacado": "Multicedente/Multisacado",
      "Recuperação": "Recuperação / FIDCs NP",
      "N/D": "N/D",
    };
    const outrosSources = {
      "Poder Público": ["Poder Público"],
      "Multicedente/Multissacado": ["Multicarteira Outros", "Multicedente/Multissacado"],
      "Recuperação": ["Recuperação"],
      "N/D": ["N/D"],
    };
    const outrosCategories = ["Poder Público", "Multicedente/Multissacado", "Recuperação", "N/D"];
    const categories = [...broadCategories, ...outrosCategories];
    const colors = {
      "Fomento Mercantil": C.mid,
      "Agro, Indústria e Comércio": C.charcoal,
      "Financeiro": C.orange,
      "Poder Público": C.black,
      "Multicedente/Multissacado": C.note,
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
      return (outrosSources[category] || [category]).reduce((sum, sourceCategory) => {
        const outrosRow = outrosByKey.get(`${period.competencia}::${sourceCategory}`);
        return sum + num(outrosRow?.[field === "pl" ? "pl_brl" : "share_total"]);
      }, 0);
    };
    const volumeSeries = categories.map((category, seriesIndex) => ({
      name: outrosDisplay[category] || category,
      values: periods.map((period) => valueFor(period, category, "pl") / 1e9),
      valuesFormatCode: "0.0",
      fill: colors[category],
      dataLabelOverrides: periods.map((_, idx) => ({
        idx,
        showValue: !["Recuperação", "N/D"].includes(category),
        position: "center",
        textStyle: {
          fill: [0, 1, 2, 3, 4].includes(seriesIndex) ? C.white : C.black,
          fontSize: TYPOGRAPHY.dataLabel,
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
        showValue: !["Recuperação", "N/D"].includes(category),
        position: "center",
        textStyle: {
          fill: [0, 1, 2, 3, 4].includes(seriesIndex) ? C.white : C.black,
          fontSize: TYPOGRAPHY.dataLabel,
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
      `Rótulos de exibição: Poder Público → Precatórios e/ou Ações Judiciais; Multicarteira Outros e Multicedente/Multissacado → Multicedente/Multisacado; Recuperação → Recuperação / FIDCs NP. Recuperação e N/D ficam detalhados no workbook para evitar sobreposição.`,
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

  // Prestadores e concentração: materializado perto dos demais slides de
  // administração, gestão e custódia no fim do capítulo executivo.
  const addProviderConcentrationSlide = () => {
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
    addShapeLegend(slide, [
      { label: "Dez/25", color: C.mid },
      { label: stockShort, color: C.orange },
    ], { left: 970, top: 128, width: 250, height: 22 }, 2, { fontSize: 8.5 });
  };

  // Market shares detalhados passam ao apêndice.
  const materialFocus = payload.material_focus_top6;

  const providerInsightOffset = 0;

  // 18. Top 20 FIDCs
  {
    const slide = presentation.slides.add();
    const top20 = payload.top20_fidcs;
    const partyLabel = top20PartyLookup(payload);
    const totalPl = top20.reduce((sum, row) => sum + num(row.pl), 0);
    const share = top20.reduce((sum, row) => sum + num(row.market_share_ex_fic), 0);
    const topTwo = (num(top20[0]?.pl) + num(top20[1]?.pl)) / totalPl;
    addHeader(
      slide,
      "RANKING · TOP 20 FIDCs",
      `Top 20 somam ${pct(share, 1)} do PL ex-FIC; Petrobras e TAPSO são ${pct(topTwo, 1)} do bloco`,
      `Fonte: CVM, ANBIMA, ledger analítico e base Carteira 101, ${stockShortLower}. * = foto manual confirmada; N/D = originador/cedente não localizado.`,
      15 + providerInsightOffset,
    );
    const tableRows = top20.map((row) => [
      String(row.rank),
      row.nome_curto,
      bn(row.pl, 1).replace("R$ ", ""),
      pct(row.market_share_ex_fic, 1),
      partyLabel(row),
    ]);
    [0, 1].forEach((block) => {
      addNativeEditorialTable(slide, {
        left: block === 0 ? 60 : 650,
        top: 150,
        width: 570,
        height: 465,
        headers: ["#", "Fundo", "PL bi", "Share", "Originador / cedente"],
        rows: tableRows.slice(block * 10, block * 10 + 10),
        columnWidths: [30, 215, 70, 65, 190],
        aligns: ["right", "left", "right", "right", "left"],
        fontSize: 10.7,
        headerFontSize: 10,
        rowHighlights: new Set(block === 0 ? [0, 1] : []),
      });
    });
    addText(
      slide,
      "* Fonte manual confirmada nas imagens da Carteira 101; o dado documental permanece prioritário. N/D não é inferido pelo nome do fundo.",
      { left: 60, top: 625, width: 1160, height: 24 },
      { fontSize: 9.2, color: C.note, alignment: "right", verticalAlignment: "middle" },
    );
  }

  ["Fomento Mercantil", "Agro, Indústria e Comércio", "Financeiro", "Outros"]
    .forEach((typeName) => {
      [payload.latest_complete, "2025-12"].forEach((competencia) => {
        addTop20ByAnbimaTypeSlide(presentation, payload, typeName, competencia);
      });
    });
  addStructuralMvpSlides(presentation, payload);

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
      top: 450,
      width: 1160,
      height: 170,
      headers: ["Ano", "Ofertas encerradas", "Volume registrado", "Ticket médio", "Ticket mediano", "PF no volume colocado", "Público profissional"],
      rows: annual.map((row) => [
        num(row.year) === currentOfferYear ? `${row.year} YTD` : `${row.year} FY`,
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
      headerHeight: 32,
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
    const compactBuckets = buckets.map((bucket) => String(bucket)
      .replace(/R\$\s*/g, "")
      .replace(/\s*mi\b/gi, "")
      .replace(/\s+/g, ""))
      .map((bucket) => bucket.replace(/^(50|100|200)–/, "$1–\n"));
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
          dataLabels: {
            showValue: index === periodLabels.length - 1,
            position: "outEnd",
            textStyle: { fill: C.black, fontSize: TYPOGRAPHY.dataLabel, bold: true },
          },
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
      "Faixas do eixo em R$ mi; fecham no limite inferior. “> R$ 100 mi” é estrito e exclui ofertas exatamente iguais a R$ 100 mi.",
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
    const currentGuarantee = rowFor("2026 jan-jun", "Garantia firme");
    const guaranteeGrowth = num(currentGuarantee.registered_volume_yoy_ytd);
    const guaranteeDirection = guaranteeGrowth >= 0 ? "cresceu" : "caiu";
    addHeader(
      slide,
      "OFERTAS · VOLUME E REGIME",
      `Emissões | Garantia firme ${guaranteeDirection} ${pct(Math.abs(guaranteeGrowth), 0)} YoY YTD, de ${bn(currentGuarantee.comparison_registered_volume_brl, 1)} para ${bn(currentGuarantee.registered_volume_brl, 1)}`,
      "Fonte: CVM/SRE, dois arquivos de ofertas, snapshot 24/jul/26. Regime declarado; campo ausente = Não informado.",
      30,
    );
    addText(
      slide,
      "Melhores esforços repr. 70% do volume em 2026",
      { left: 60, top: 113, width: 1160, height: 20 },
      { fontSize: 11.5, color: C.mid, verticalAlignment: "middle" },
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
          ...chartAxis(8, xAxisFormat),
          visible: true,
          textStyle: { fill: C.mid, fontSize: 7.6 },
          line: { style: "solid", fill: C.line, width: 0.6 },
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
      `Comparação YTD: garantia firme ${bn(currentGuarantee.comparison_registered_volume_brl, 1)} em jan–jun/25 e ${bn(currentGuarantee.registered_volume_brl, 1)} em jan–jun/26; variação ${pct(guaranteeGrowth, 1)}. Melhores esforços representam ${pct(currentBestEfforts.registered_volume_share, 1)} do volume atual.`,
      "Limitação: volume registrado pode diferir do valor encerrado informado à ANBIMA.",
    ]);
  }

  addCurrentTop15Slide(presentation, payload, "2026 jan-jun", 0);
  addCurrentTop15Slide(presentation, payload, "2025 FY", 0);
  addHistoricalTop15Slide(presentation, payload, "2024 FY", 1, 2, 0);
  addHistoricalTop15Slide(presentation, payload, "2024 FY", 2, 2, 0);
  addHistoricalTop15Slide(presentation, payload, "2023 FY", 1, 2, 0);
  addHistoricalTop15Slide(presentation, payload, "2023 FY", 2, 2, 0);

  addConclusionsSlide(presentation, payload, 32);

  // Prestadores permanecem contíguos; market shares seguem no workbook e no explorador.
  addCombinedProviderRankingSlide(presentation, payload, 0);
  if (SLIDE_CONTRACT_V1.includes("bank_cohort")) {
    addBankFidcEvolutionSlide(presentation, payload, 0);
  }
  addProviderConcentrationSlide();
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

async function addStructuralRiskSheets(workbook, payload) {
  const summary = payload.carteira_1_structural_summary || {};
  const assetColumns = [
    ["#", "ordem"],
    ["CNPJ", "cnpj_formatado"],
    ["Ativo", "ativo"],
    ["Taxonomia", "categoria"],
    ["Categoria MVP", "mvp_slide_categoria"],
    ["Faixa de Sub atual", "mvp_faixa_sub_atual"],
    ["Elegível no MVP", "mvp_elegivel_flag", (value) => value ? "Sim" : "Não"],
    ["Sinal vs. mínimo estrutural", "mvp_situacao_piso"],
    ["Tipo", "tipo_exibicao"],
    ["Foco", "foco_exibicao"],
    ["PL do veículo", "pl_atual"],
    ["Subordinação atual", "sub_pl_atual"],
    ["Mínimo júnior documental", "sub_jr_min_documental"],
    ["Suporte total/combinado", "suporte_total_min_documental"],
    ["Mínimo estrutural · leitura", "minimo_estrutural_display"],
    ["Natureza", "minimo_estrutural_natureza"],
    ["Cláusula / leitura", "minimo_estrutural_texto"],
    ["Fórmula", "minimo_estrutural_formula"],
    ["Exceção *", "excecao_asterisco_flag", (value) => value ? "Sim" : "Não"],
    ["Comparável", "comparacao_estrutural_completa_flag", (value) => value ? "Sim" : "Não"],
    ["Motivo comparabilidade", "comparacao_estrutural_motivo"],
    ["Folga", "folga_pp"],
    ["Capacidade até gatilho", "perda_ate_gatilho"],
    ["Situação regulatória", "situacao_regulatoria"],
    ["Mediana pares", "mercado_categoria_mediana_sub"],
    ["Pares com dado", "n_comparaveis_categoria"],
    ["Excesso vs. pares", "excesso_vs_mercado"],
    ["Posição vs. mercado", "posicao_mercado"],
    ["Documento", "documento_id_regulamento"],
    ["Página / cláusula", "pagina_clausula"],
    ["Fonte documental", "fonte_documental"],
    ["Status curadoria", "status_curadoria_documental"],
  ];
  const assetHeaders = assetColumns.map(([header]) => header);
  const assetRows = worksheetRowsFromPayload(payload.carteira_1_structural_assets || [], assetColumns);
  if (assetRows.length !== 101) {
    throw new Error(`Risco estrutural ativos deveria conter 101 linhas; contém ${assetRows.length}.`);
  }
  const assetSheet = resetSheet(workbook, "Risco estrutural ativos");
  setHeaderBand(
    assetSheet,
    "Carteira 1 · risco estrutural por CNPJ",
    `${integer(summary.cnpjs_com_minimo_junior)}/101 com mínimo júnior; ${integer(summary.cnpjs_com_minimo_estrutural)}/101 com mínimo estrutural. ${summary.asterisco || ""} ${summary.nota_pl || ""}`,
    assetHeaders,
    assetRows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.2 },
  );
  await writeRowsInChunks(assetSheet, 4, assetHeaders, assetRows);
  applyColumnWidths(assetSheet, [45, 125, 390, 150, 180, 120, 105, 180, 160, 190, 125, 115, 125, 135, 145, 135, 500, 240, 80, 90, 420, 95, 115, 135, 110, 90, 105, 160, 100, 145, 420, 220], assetRows.length);
  applyFormatsByHeader(assetSheet, assetHeaders, assetRows.length);
  assetSheet.getRange(`K5:K${assetRows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"';
  ["L", "M", "N", "V", "W", "Y", "AA"].forEach((letter) => {
    assetSheet.getRange(`${letter}5:${letter}${assetRows.length + 4}`).format.numberFormat = "0.0%";
  });
  assetSheet.getRange(`A5:AF${assetRows.length + 4}`).format.rowHeightPx = 62;

  const taxonomyColumns = [
    ["Ordem", "ordem"], ["Taxonomia", "taxonomia"], ["Presença", "presenca_carteira"],
    ["Carteira · CNPJs", "carteira_cnpjs"], ["Carteira · CNPJs com PL", "carteira_cnpjs_com_pl"],
    ["Carteira · PL", "carteira_pl_brl"], ["Carteira · sub mediana", "carteira_sub_atual_mediana"],
    ["Carteira · sub ponderada", "carteira_sub_atual_ponderada"], ["Mínimo júnior · CNPJs", "carteira_minimo_junior_cnpjs"],
    ["Mínimo estrutural · CNPJs", "carteira_minimo_estrutural_cnpjs"], ["Folga comparável · CNPJs", "carteira_folga_comparavel_cnpjs"],
    ["Flagships · CNPJs", "flagship_cnpjs"], ["Flagships · CNPJs com sub", "flagship_cnpjs_com_subordinacao"],
    ["Flagships · PL", "flagship_pl_brl"], ["Flagships · sub mediana", "flagship_sub_atual_mediana"],
    ["Delta vs. flagships", "delta_sub_atual_vs_flagship"], ["Posição", "posicao_vs_mercado"],
  ];
  const taxonomyHeaders = taxonomyColumns.map(([header]) => header);
  const taxonomyRows = worksheetRowsFromPayload(payload.carteira_1_structural_taxonomy || [], taxonomyColumns);
  const taxonomySheet = resetSheet(workbook, "Risco estrutural taxonomia");
  setHeaderBand(
    taxonomySheet,
    "Carteira 1 · risco estrutural por taxonomia",
    "As sete taxonomias alimentam o capítulo estrutural; cinco aparecem no MVP executivo. Mediana e ponderada por PL permanecem lado a lado; grupos com poucos pares mantêm a lacuna.",
    taxonomyHeaders,
    taxonomyRows.length,
    { freezeColumns: 3, wrapText: true, bodyFontSize: 9 },
  );
  await writeRowsInChunks(taxonomySheet, 4, taxonomyHeaders, taxonomyRows);
  applyColumnWidths(taxonomySheet, [60, 180, 180, 105, 130, 125, 135, 145, 140, 155, 155, 115, 155, 125, 145, 125, 190], taxonomyRows.length);
  applyFormatsByHeader(taxonomySheet, taxonomyHeaders, taxonomyRows.length);
  ["F", "N"].forEach((letter) => taxonomySheet.getRange(`${letter}5:${letter}${taxonomyRows.length + 4}`).format.numberFormat = 'R$ #,##0.0,,, "bi"');
  ["G", "H", "O", "P"].forEach((letter) => taxonomySheet.getRange(`${letter}5:${letter}${taxonomyRows.length + 4}`).format.numberFormat = "0.0%");
  taxonomySheet.getRange(`A5:Q${taxonomyRows.length + 4}`).format.rowHeightPx = 42;
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
    ["Slides no contrato ordinal", EXPECTED_SLIDES, SLIDE_CONTRACT_V1.length, '=IF(B9=C9,"OK","ERRO")'],
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
    "CVM: ofertas públicas primárias encerradas, todos os ritos disponíveis, valor registrado. ANBIMA: ofertas públicas encerradas, Valor Encerrado; 2026 = jan–jun. A ponte taxonômica soma Outros títulos de securitização somente a debêntures.",
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
  const rows = materialized;
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
    ["Preço unitário por tipo de cota", "preco_por_tipo_cota"],
    [
      "Remuneração-alvo por tipo de cota",
      "remuneracao_por_tipo_cota",
      (value) => String(value || "").trim() || "N/D",
    ],
    ["Cedente", "cedente"],
    ["Sacado", "sacado"],
    [
      "Cedente / originador · exibição",
      "cedente",
      (_value, row) => combinedPartyField(row, 80),
    ],
    [
      "Sacado · exibição",
      "sacado_exibicao",
      (value) => String(value || "").trim() || "N/D",
    ],
    [
      "Regra exibição sacado",
      "regra_exibicao_sacado",
      (value) => String(value || "").trim() || "N/D",
    ],
    ["Cedente / Originador literal*", "cedente_originador_literal"],
    ["Tipo de recebível literal*", "tipo_recebivel_literal"],
    ["Fonte enriquecimento manual", "fonte_enriquecimento_manual"],
    ["Fonte originador", "fonte_originador"],
    ["Fonte cedente", "fonte_cedente"],
    ["Fonte originador / cedente", "fonte_originador_cedente"],
    ["Natureza do mínimo", "tipo_subordinacao_minima"],
    ["Fonte subordinação", "fonte_subordinacao"],
    ["Fonte preço", "fonte_preco"],
    [
      "Fonte remuneração",
      "fonte_remuneracao",
      (value) => String(value || "").trim() || "N/D",
    ],
    ["Fonte sacado", "fonte_sacado"],
    ["Motivo N/D", "motivo_nd"],
    ["Status", "status"],
  ];
  const headers = columns.map(([header]) => header);
  const invalidPrices = (payload.emission_field_audit || []).filter((row) => {
    const raw = String(row.preco_por_tipo_cota || "").trim();
    if (!raw || /^N\/D(?:\b|\s|—|-)/i.test(raw)) return false;
    const normalized = normalizeProviderName(row.preco_por_tipo_cota);
    return ["quantidade", "spread", "remuneracao", "taxa da cota"]
      .some((token) => normalized.includes(token));
  });
  if (invalidPrices.length) {
    throw new Error(
      `Auditoria emissões contém ${invalidPrices.length} preços incompatíveis com o contrato unitário por cota.`,
    );
  }
  const top15AuditRows = (payload.emission_field_audit || []).filter(
    (row) => row.bloco === "slides 10–17",
  );
  const invalidRemunerations = top15AuditRows.filter((row) => {
    const raw = String(row.remuneracao_por_tipo_cota || "").trim();
    if (!raw || /^N\/D(?:\b|\s|—|-)/i.test(raw)) return false;
    return !targetRemunerationIsValid(raw);
  });
  if (invalidRemunerations.length) {
    throw new Error(
      `Auditoria emissões contém ${invalidRemunerations.length} remunerações-alvo sem benchmark e taxa numérica válidos.`,
    );
  }
  const remunerationsWithoutSource = top15AuditRows.filter((row) => {
    const raw = String(row.remuneracao_por_tipo_cota || "").trim();
    if (!raw || /^N\/D(?:\b|\s|—|-)/i.test(raw)) return false;
    const source = String(row.fonte_remuneracao || "").trim();
    return !source || /^N\/D(?:\b|\s|—|-)/i.test(source);
  });
  if (remunerationsWithoutSource.length) {
    throw new Error(
      `Auditoria emissões contém ${remunerationsWithoutSource.length} remunerações-alvo sem fonte documental identificada.`,
    );
  }
  const rows = worksheetRowsFromPayload(payload.emission_field_audit || [], columns);
  if (rows.length !== 180) {
    throw new Error(`Auditoria emissões deveria conter 180 linhas; contém ${rows.length}.`);
  }
  const sheet = resetSheet(workbook, "Auditoria emissões");
  setHeaderBand(
    sheet,
    "Auditoria dos campos documentais exibidos nos slides 10–17 e 21–22",
    "Uma linha por fundo/período nos slides 10–17 e por emissão nos slides 21–22. Remuneração-alvo registra benchmark + spread da cota/série; preço unitário/VNU permanece em coluna própria para o contrato legado. Originador, cedente e sacado brutos permanecem separados. As colunas de exibição registram a compactação usada no deck, sem substituir o dado integral. Cedente usa a Tabela I da CVM quando declarado; o Informe Mensal não identifica sacado. * = complemento manual. Múltiplas séries e a natureza do mínimo são descritas na própria célula.",
    headers,
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 7.5 },
  );
  await writeRowsInChunks(sheet, 4, headers, rows);
  applyColumnWidths(
    sheet,
    [110, 180, 105, 95, 300, 180, 150, 190, 160, 210, 180, 240, 180, 300, 220, 260, 330, 330, 330, 360, 150, 360, 420, 420, 300, 430, 330],
    rows.length,
  );
  sheet.getRange(`A5:AA${rows.length + 4}`).format.rowHeightPx = 66;
}

const EMISSION_FIELD_COVERAGE_COLUMNS = Object.freeze([
  { header: "Tabela / período", key: "tabela", width: 220 },
  { header: "Tipo ANBIMA", key: "tipo", width: 190 },
  { header: "Competência", key: "competencia", width: 105 },
  {
    header: "Campo",
    key: "campo",
    width: 155,
    transform: (value) => ({
      originador: "Originador",
      cedente: "Cedente",
      subordinacao_minima: "Subordinação mínima",
      remuneracao_por_tipo_cota: "Remuneração-alvo",
      preco_por_tipo_cota: "Preço unitário / VNU",
      sacado: "Sacado",
    }[String(value || "")] || value),
  },
  { header: "Linhas", key: "linhas_total", width: 75, format: "#,##0" },
  { header: "Antes · com dado", key: "antes_com_dado", width: 105, format: "#,##0" },
  { header: "Antes · cobertura", key: "antes_cobertura_pct", width: 110, format: "0.0%" },
  { header: "Antes · PL coberto", key: "antes_pl_coberto_brl", width: 135, format: "R$ #,##0.00" },
  { header: "Antes · cobertura PL", key: "antes_cobertura_pl_pct", width: 125, format: "0.0%" },
  { header: "Depois · com dado", key: "depois_com_dado", width: 110, format: "#,##0" },
  { header: "Depois · cobertura", key: "depois_cobertura_pct", width: 115, format: "0.0%" },
  { header: "Depois · PL coberto", key: "depois_pl_coberto_brl", width: 140, format: "R$ #,##0.00" },
  { header: "Depois · cobertura PL", key: "depois_cobertura_pl_pct", width: 130, format: "0.0%" },
  { header: "N/D depois", key: "nd_depois", width: 90, format: "#,##0" },
  { header: "Piso de publicação", key: "piso_publicacao_pct", width: 120, format: "0.0%" },
  { header: "Piso atendido?", key: "piso_atendido", width: 105, transform: ptYesNo },
]);

const EMISSION_FIELD_PROFILE_COLUMNS = Object.freeze([
  { header: "CNPJ", key: "cnpj", width: 125, format: "00000000000000" },
  { header: "Fundo", key: "fundo", width: 340 },
  { header: "Texto cedente / originador", key: "cedente_originador_texto", width: 390 },
  { header: "Classificação do texto", key: "classificacao_cedente_originador", width: 220 },
  { header: "Aplicação como Cedente", key: "aplicacao_como_cedente", width: 190 },
  { header: "Valor aplicado como Cedente", key: "valor_aplicado_como_cedente", width: 220 },
  { header: "Aplicação como Originador", key: "aplicacao_como_originador", width: 190 },
  { header: "Valor aplicado como Originador", key: "valor_aplicado_como_originador", width: 220 },
  { header: "Texto sacado / devedor", key: "sacado_devedor_texto", width: 390 },
  { header: "Classificação do sacado", key: "classificacao_sacado_devedor", width: 210 },
  { header: "Natureza dos recebíveis", key: "natureza_recebiveis", width: 440 },
  { header: "Documentos primários · IDs", key: "documentos_primarios_ids", width: 300 },
  { header: "Data da consulta", key: "data_consulta", width: 105 },
]);

const EMISSION_REMUNERATION_EVIDENCE_COLUMNS = Object.freeze([
  {
    header: "CNPJ",
    key: "cnpj",
    width: 125,
    format: "00000000000000",
    transform: (value) => numericCnpjText(value),
  },
  {
    header: "CNPJ formatado",
    key: "cnpj_formatado",
    sourceKey: "cnpj",
    width: 145,
    transform: (value) => formatCnpj(value),
  },
  {
    header: "Classe / série",
    key: "classe_serie",
    sourceKey: "value",
    width: 185,
    transform: remunerationClassSeries,
  },
  { header: "Remuneração-alvo literal", key: "value", width: 310 },
  {
    header: "Benchmark compacto",
    key: "benchmark_compacto",
    sourceKey: "value",
    width: 170,
    transform: (value) => auditTargetRemuneration(value, 42),
  },
  { header: "Natureza", key: "nature", width: 250 },
  { header: "Data do documento", key: "document_date", width: 120 },
  { header: "Tipo de fonte", key: "source_kind", width: 165 },
  { header: "Classe documental", key: "document_class", width: 190 },
  { header: "Documento / ID", key: "source_id", width: 230 },
  { header: "Página", key: "page", width: 80 },
  { header: "Status da evidência", key: "status", width: 170 },
  { header: "Confiança", key: "confidence", width: 95, format: "0.00%" },
  { header: "Caminho da fonte", key: "source_path", width: 390 },
  { header: "Link da fonte", key: "source_url", width: 390 },
  { header: "Trecho documental", key: "excerpt", width: 640 },
]);

async function addEmissionRemunerationEvidenceSheet(workbook, payload) {
  const evidence = (payload.emission_field_remuneration_evidence || []).filter(
    (row) => String(row.field || "") === "remuneracao_alvo",
  );
  await addAuditablePayloadSheet(workbook, {
    name: "Remuneração-alvo",
    title: "Remuneração-alvo por CNPJ, cota / série e documento",
    subtitle: "Trilha normalizada das evidências de benchmark + spread. O status documental e a data de corte governam a seleção do valor exibido nos slides 10–17; VNU, quantidade, taxa da carteira e preço unitário permanecem fora desta aba.",
    columns: EMISSION_REMUNERATION_EVIDENCE_COLUMNS,
    rows: evidence,
    freezeColumns: 5,
    bodyFontSize: 8,
    rowHeight: 58,
  });
}

async function addEmissionFieldCoverageSheets(workbook, payload) {
  const coverage = payload.emission_field_coverage || [];
  const profiles = payload.emission_field_profile_mapping || [];
  const coverageSheet = await addAuditablePayloadSheet(workbook, {
    name: "Cobertura emissões",
    title: "Cobertura dos campos dos slides 10–17",
    subtitle: "Cobertura por página e campo, antes e depois do encadeamento documental. Os percentuais de PL usam o PL das 15 linhas de cada página; o piso é o bloqueio mínimo de publicação, não uma meta de completude.",
    columns: EMISSION_FIELD_COVERAGE_COLUMNS,
    rows: coverage,
    freezeColumns: 4,
    bodyFontSize: 8,
    rowHeight: 30,
  });
  if (coverage.length) {
    coverageSheet.getRange(`P5:P${coverage.length + 4}`).conditionalFormats.add("containsText", {
      text: "Não",
      format: { fill: "#F8D7DA", font: { bold: true, color: "#7A1F3D" } },
    });
    coverageSheet.getRange(`P5:P${coverage.length + 4}`).conditionalFormats.add("containsText", {
      text: "Sim",
      format: { fill: "#DCEFE2", font: { bold: true, color: "#006B3C" } },
    });
  }
  await addAuditablePayloadSheet(workbook, {
    name: "Curadoria perfis",
    title: "Classificação funcional da curadoria Top 20",
    subtitle: "A frase é classificada pelo papel que sustenta. Entidade ou ecossistema nomeado pode preencher a parte correspondente; descrição genérica permanece como natureza do recebível; ausência documental permanece N/D. A Tabela I da CVM prevalece para o cedente legal.",
    columns: EMISSION_FIELD_PROFILE_COLUMNS,
    rows: profiles,
    freezeColumns: 2,
    bodyFontSize: 8,
    rowHeight: 58,
  });
}

const PORTFOLIO_EXPORT_COLUMNS = Object.freeze([
  { header: "Ordem", key: "ordem", width: 65 },
  { header: "CNPJ", key: "cnpj_numerico", width: 125, format: "00000000000000" },
  { header: "CNPJ formatado", key: "cnpj_formatado", width: 135 },
  { header: "Nome completo do fundo (CVM)", key: "nome_oficial_cvm", width: 360 },
  { header: "Nome de referência", key: "nome_referencia", width: 260 },
  { header: "Coorte", key: "coorte", width: 105 },
  { header: "Data de referência", key: "data_ref", width: 105 },
  { header: "Status da identidade", key: "status_identidade", width: 155 },
  { header: "PL atual", key: "pl_atual_brl", width: 130, format: 'R$ #,##0.00' },
  { header: "PL das classes reportadas", key: "pl_classes_reportadas_brl", width: 145, format: 'R$ #,##0.00' },
  { header: "PL subordinado atual", key: "pl_subordinado_atual_brl", width: 145, format: 'R$ #,##0.00' },
  { header: "Sub / PL atual", key: "sub_pl_atual", width: 105, format: "0.00%" },
  { header: "Status do Sub / PL", key: "status_sub_pl_atual", width: 260 },
  { header: "Mínimo Jr literal", key: "minimo_junior_literal", width: 110, format: "0.00%" },
  { header: "Mínimo Jr calculado*", key: "minimo_junior_calculado", width: 125, format: "0.00%" },
  { header: "Mínimo Jr ajustado*", key: "minimo_junior_ajustado", width: 120, format: "0.00%" },
  { header: "Suporte total*", key: "suporte_total", width: 105, format: "0.00%" },
  { header: "Suporte Jr + Mezanino*", key: "suporte_combinado_junior_mezanino", width: 140, format: "0.00%" },
  { header: "Índice estrutural usado", key: "minimo_estrutural_usado", width: 135, format: "0.00%" },
  { header: "Índice estrutural exibido", key: "minimo_estrutural_display", width: 155 },
  { header: "Natureza do índice", key: "minimo_estrutural_natureza", width: 170 },
  { header: "Fórmula / regra", key: "minimo_estrutural_formula", width: 210 },
  { header: "Comparável?", key: "comparavel_flag", width: 90 },
  { header: "Motivo da comparabilidade", key: "comparabilidade_motivo", width: 420 },
  { header: "Exceção*", key: "excecao_asterisco_flag", width: 82 },
  { header: "Folga / falta", key: "folga_pp", width: 105, format: "0.00%" },
  { header: "Capacidade até o gatilho", key: "capacidade_ate_gatilho", width: 135, format: "0.00%" },
  { header: "Situação regulatória", key: "situacao_regulatoria", width: 145 },
  { header: "Tipo", key: "tipo_exibicao", width: 150 },
  { header: "Foco", key: "foco_exibicao", width: 190 },
  { header: "Taxonomia estrutural", key: "taxonomia_estrutural", width: 180 },
  { header: "Grupo de comparação", key: "grupo_comparacao", width: 180 },
  { header: "Categoria de risco atual", key: "categoria_risco_atual", width: 185 },
  { header: "Categoria de risco proposta", key: "categoria_risco_proposta", width: 190 },
  { header: "Subtipo de risco diagnosticado", key: "subtipo_risco_diagnosticado", width: 230 },
  { header: "Reclassificação proposta?", key: "reclassificacao_proposta_flag", width: 125 },
  { header: "Status da avaliação", key: "status_avaliacao_reclassificacao", width: 260 },
  { header: "Fundamento da avaliação", key: "fundamento_avaliacao_reclassificacao", width: 430 },
  { header: "Fonte da avaliação", key: "fonte_avaliacao_reclassificacao", width: 390 },
  { header: "Middle Market · status", key: "middle_market_status", width: 260 },
  { header: "Middle Market · evidência", key: "middle_market_evidencia", width: 380 },
  { header: "Porte documentado?", key: "middle_market_porte_documentado_flag", width: 120 },
  { header: "Categoria MVP", key: "mvp_slide_categoria", width: 185 },
  { header: "Categoria MVP original", key: "mvp_slide_categoria_original", width: 185 },
  { header: "Override editorial?", key: "mvp_slide_categoria_override_flag", width: 105 },
  { header: "Fonte do override MVP", key: "mvp_slide_categoria_fonte", width: 390 },
  { header: "Motivo do override MVP", key: "mvp_slide_categoria_motivo", width: 420 },
  { header: "Faixa de Sub atual · MVP", key: "mvp_faixa_sub_atual", width: 125 },
  { header: "Elegível nos 6 slides?", key: "mvp_elegivel_flag", width: 115 },
  { header: "Sinal vs. mínimo estrutural", key: "mvp_situacao_piso", width: 175 },
  { header: "Posição vs. mercado", key: "posicao_mercado", width: 190 },
  { header: "Excesso vs. mediana", key: "excesso_vs_mercado", width: 120, format: "0.00%" },
  { header: "Benchmark confiável?", key: "benchmark_confiavel", width: 115 },
  { header: "Nº de comparáveis", key: "n_comparaveis_categoria", width: 105, format: "#,##0" },
  { header: "Preço unitário numérico", key: "preco_cota_brl", width: 145, format: 'R$ #,##0.00' },
  { header: "Preço por cota · leitura", key: "preco_cota_display", width: 260 },
  { header: "Natureza do preço", key: "preco_cota_natureza", width: 190 },
  { header: "Classe / série do preço", key: "preco_cota_classe_serie", width: 220 },
  { header: "Data do documento de preço", key: "preco_cota_documento_data", width: 130 },
  { header: "Documento do preço", key: "preco_cota_documento_id", width: 145 },
  { header: "Fonte do preço", key: "preco_cota_fonte", width: 420 },
  { header: "Status do preço", key: "preco_cota_status", width: 240 },
  { header: "Exceção de preço*", key: "preco_cota_excecao_asterisco_flag", width: 105 },
  { header: "Cedente / Originador literal*", key: "cedente_originador_literal", width: 250 },
  { header: "Papel literal*", key: "papel_literal", width: 150 },
  { header: "Originador*", key: "originador", width: 210 },
  { header: "Cedente*", key: "cedente", width: 210 },
  { header: "Sacado / devedor*", key: "sacado_devedor", width: 220 },
  { header: "Tipo de recebível*", key: "tipo_recebivel_literal", width: 330 },
  { header: "Fonte das partes / recebível", key: "fonte_partes_recebivel", width: 300 },
  { header: "Status do complemento manual", key: "status_complemento_manual", width: 175 },
  { header: "Observação do complemento manual", key: "observacao_complemento_manual", width: 360 },
  { header: "Documento", key: "documento_id", width: 130 },
  { header: "Data do documento", key: "documento_data", width: 115 },
  { header: "Página / cláusula", key: "pagina_clausula", width: 140 },
  { header: "Status da curadoria", key: "status_curadoria_documental", width: 235 },
  { header: "Fonte documental", key: "fonte_documental", width: 420 },
  { header: "Texto do mínimo", key: "texto_minimo", width: 460 },
  { header: "Campos não preenchidos", key: "campos_nao_preenchidos", width: 320 },
  { header: "Status do preenchimento", key: "status_preenchimento", width: 190 },
]);

const PORTFOLIO_EXPORT_GROUPS = Object.freeze([
  { label: "IDENTIFICAÇÃO", startKey: "ordem", endKey: "status_identidade", fill: C.black },
  { label: "PORTE E SUBORDINAÇÃO ATUAL", startKey: "pl_atual_brl", endKey: "status_sub_pl_atual", fill: C.charcoal },
  { label: "ÍNDICES DOCUMENTAIS", startKey: "minimo_junior_literal", endKey: "minimo_estrutural_formula", fill: C.orange },
  { label: "COMPARABILIDADE E FOLGA", startKey: "comparavel_flag", endKey: "situacao_regulatoria", fill: "#7A1F3D" },
  { label: "TAXONOMIA E REVISÃO DE RISCO", startKey: "tipo_exibicao", endKey: "middle_market_porte_documentado_flag", fill: "#2456D6" },
  { label: "MVP · 6 SLIDES", startKey: "mvp_slide_categoria", endKey: "mvp_situacao_piso", fill: "#002B5C" },
  { label: "BENCHMARK DE MERCADO", startKey: "posicao_mercado", endKey: "n_comparaveis_categoria", fill: C.charcoal },
  { label: "PREÇO UNITÁRIO POR COTA", startKey: "preco_cota_brl", endKey: "preco_cota_excecao_asterisco_flag", fill: "#006B3C" },
  { label: "PARTES E RECEBÍVEL", startKey: "cedente_originador_literal", endKey: "observacao_complemento_manual", fill: "#A65A00" },
  { label: "RASTREABILIDADE", startKey: "documento_id", endKey: "texto_minimo", fill: C.mid },
  { label: "LACUNAS", startKey: "campos_nao_preenchidos", endKey: "status_preenchimento", fill: C.black },
]);

function portfolioExportCell(value, column) {
  if (value === null || value === undefined || value === "") return "N/D";
  if (Array.isArray(value)) return value.length ? value.join("; ") : "N/D";
  if (typeof value === "object") return JSON.stringify(value);
  if (column.key === "cnpj_numerico" || column.format === "00000000000000") {
    const digits = cnpjDigits(value);
    if (!digits) return "N/D";
    return Number(digits);
  }
  if (typeof value === "boolean") return value;
  if (column.format && column.format !== "00000000000000") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : "N/D";
  }
  return value;
}

function portfolioExportRows(payloadRows, columns = PORTFOLIO_EXPORT_COLUMNS) {
  return (payloadRows || []).map((row) => Object.fromEntries(
    columns.map((column) => [
      column.header,
      portfolioExportCell(row[column.key], column),
    ]),
  ));
}

async function writePortfolioRows(sheet, startRowZeroBased, columns, sourceRows, chunkSize = 500) {
  for (let offset = 0; offset < sourceRows.length; offset += chunkSize) {
    const chunk = sourceRows.slice(offset, offset + chunkSize).map((row) =>
      columns.map((column) => portfolioExportCell(row[column.key], column)),
    );
    sheet.getRangeByIndexes(
      startRowZeroBased + offset,
      0,
      chunk.length,
      columns.length,
    ).values = chunk;
  }
}

function addPortfolioGroupBands(sheet) {
  const indexByKey = Object.fromEntries(
    PORTFOLIO_EXPORT_COLUMNS.map((column, index) => [column.key, index]),
  );
  for (const group of PORTFOLIO_EXPORT_GROUPS) {
    const startIndex = indexByKey[group.startKey];
    const endIndex = indexByKey[group.endKey];
    if (!Number.isInteger(startIndex) || !Number.isInteger(endIndex) || startIndex > endIndex) {
      throw new Error(`Faixa de colunas inválida no export: ${group.label}.`);
    }
    const start = columnLetter(startIndex);
    const end = columnLetter(endIndex);
    const range = sheet.getRange(`${start}3:${end}3`);
    range.merge();
    range.values = [[group.label]];
    range.format.fill = group.fill;
    range.format.font = { name: "Arial", size: 8, bold: true, color: C.white };
    range.format.horizontalAlignment = "center";
    range.format.verticalAlignment = "center";
    range.format.rowHeightPx = 22;
  }
}

function addPortfolioConditionalFormatting(sheet, rowCount) {
  if (!rowCount) return;
  const bodyEnd = rowCount + 4;
  const columnIndex = Object.fromEntries(
    PORTFOLIO_EXPORT_COLUMNS.map((column, index) => [column.key, index]),
  );
  const situation = columnLetter(columnIndex.situacao_regulatoria);
  const situationRange = sheet.getRange(`${situation}5:${situation}${bodyEnd}`);
  situationRange.conditionalFormats.add("containsText", {
    text: "abaixo do mínimo",
    format: { fill: "#F8D7DA", font: { bold: true, color: "#7A1F3D" } },
  });
  situationRange.conditionalFormats.add("containsText", {
    text: "folga estreita",
    format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
  });
  situationRange.conditionalFormats.add("containsText", {
    text: "acima do mínimo",
    format: { fill: "#DCEFE2", font: { bold: true, color: "#006B3C" } },
  });
  situationRange.conditionalFormats.add("containsText", {
    text: "não medido",
    format: { fill: C.pale, font: { color: C.mid } },
  });

  const taxonomy = columnLetter(columnIndex.taxonomia_estrutural);
  const taxonomyRange = sheet.getRange(`${taxonomy}5:${taxonomy}${bodyEnd}`);
  Object.entries(FLAGSHIP_TYPE_STYLES).forEach(([label, style]) => {
    taxonomyRange.conditionalFormats.add("containsText", {
      text: label,
      format: { fill: style.fill, font: { bold: true, color: C.charcoal } },
    });
  });
  const manualStatus = columnLetter(columnIndex.status_complemento_manual);
  sheet.getRange(`${manualStatus}5:${manualStatus}${bodyEnd}`).conditionalFormats.add(
    "containsText",
    {
      text: "manual_aplicado",
      format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
    },
  );
}

async function addPortfolioDataSheet(workbook, name, sourceRows, subtitle) {
  const columns = PORTFOLIO_EXPORT_COLUMNS;
  const headers = columns.map((column) => column.header);
  const sheet = workbook.worksheets.add(name);
  setHeaderBand(
    sheet,
    `${name} · base manipulável de risco estrutural`,
    subtitle,
    headers,
    sourceRows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8 },
  );
  addPortfolioGroupBands(sheet);
  await writePortfolioRows(sheet, 4, columns, sourceRows);
  applyColumnWidths(sheet, columns.map((column) => column.width), sourceRows.length);
  columns.forEach((column, index) => {
    if (!column.format || !sourceRows.length) return;
    const letter = columnLetter(index);
    sheet.getRange(`${letter}5:${letter}${sourceRows.length + 4}`).format.numberFormat = column.format;
    sheet.getRange(`${letter}5:${letter}${sourceRows.length + 4}`).format.horizontalAlignment = "right";
  });
  if (sourceRows.length) {
    sheet.getRange(`A5:${columnLetter(columns.length - 1)}${sourceRows.length + 4}`).format.rowHeightPx = 42;
  }
  addPortfolioConditionalFormatting(sheet, sourceRows.length);
  return sheet;
}

function coverageLookup(payload, cohort, field) {
  return (payload.portfolio_export_coverage || []).find(
    (row) => row.coorte === cohort && row.campo === field,
  ) || {};
}

function addPortfolioReadmeSheet(workbook, payload) {
  const sheet = workbook.worksheets.add("Leia-me");
  sheet.showGridLines = false;
  sheet.getRange("A1:H1").merge();
  sheet.getRange("A1").values = [["Carteira 101 + Flagships · base analítica manipulável"]];
  sheet.getRange("A1:H1").format.fill = C.black;
  sheet.getRange("A1:H1").format.font = { name: "Arial", size: 18, bold: true, color: C.white };
  sheet.getRange("A1:H1").format.rowHeightPx = 40;
  sheet.getRange("A2:H2").merge();
  sheet.getRange("A2").values = [[
    `Competência ${payload.latest_complete || "N/D"}. Uma linha por CNPJ, com PL e Sub/PL do Informe Mensal, índices da curadoria documental e métricas do dataframe estrutural compartilhado.`,
  ]];
  sheet.getRange("A2:H2").format.font = { name: "Arial", size: 10, color: C.mid };
  sheet.getRange("A2:H2").format.wrapText = true;
  sheet.getRange("A2:H2").format.rowHeightPx = 38;

  const portfolioCount = (payload.portfolio_export_carteira_101 || []).length;
  const flagshipCount = (payload.portfolio_export_flagships || []).length;
  const junior = coverageLookup(payload, "Carteira 101", "indice_minimo_junior");
  const headroom = coverageLookup(payload, "Carteira 101", "folga_pp");
  const cards = [
    ["Carteira 101", portfolioCount],
    ["Flagships", flagshipCount],
    ["Mínimo júnior identificado", `${junior.linhas_com_dado || 0}/${junior.linhas_total || portfolioCount}`],
    ["Folga comparável", `${headroom.linhas_com_dado || 0}/${headroom.linhas_total || portfolioCount}`],
  ];
  cards.forEach(([label, value], index) => {
    const start = columnLetter(index * 2);
    const end = columnLetter(index * 2 + 1);
    sheet.getRange(`${start}4:${end}4`).merge();
    sheet.getRange(`${start}4`).values = [[label]];
    sheet.getRange(`${start}5:${end}6`).merge();
    sheet.getRange(`${start}5`).values = [[value]];
    sheet.getRange(`${start}4:${end}4`).format.fill = index === 2 ? C.orange : C.charcoal;
    sheet.getRange(`${start}4:${end}4`).format.font = { name: "Arial", size: 9, bold: true, color: C.white };
    sheet.getRange(`${start}5:${end}6`).format.fill = C.pale;
    sheet.getRange(`${start}5:${end}6`).format.font = { name: "Arial", size: 18, bold: true, color: C.black };
    sheet.getRange(`${start}4:${end}6`).format.horizontalAlignment = "center";
    sheet.getRange(`${start}4:${end}6`).format.verticalAlignment = "center";
  });

  const guidance = [
    ["Como usar", "Filtre Carteira 101 ou Flagships por taxonomia, porte, situação regulatória, folga e campos manuais. Todos os percentuais são valores numéricos formatados como %."],
    ["CNPJ", "A coluna CNPJ é numérica e usa o formato 00000000000000. A coluna seguinte preserva a apresentação pontuada."],
    ["Folga / falta", "Sub/PL atual menos o índice estrutural usado. O campo permanece N/D quando a equivalência de tranche não está comprovada."],
    ["Capacidade até o gatilho", "Fração de perda absorvível antes do piso: (Sub/PL atual − mínimo) / (1 − mínimo). Calculada somente em estruturas comparáveis."],
    ["Asterisco (*)", "Indica mínimo calculado ou ajustado, suporte total/combinado, exceção de comparabilidade ou transcrição das fotos fornecidas pelo usuário. A natureza e a fonte permanecem na mesma linha."],
    ["Lacunas", "N/D identifica informação não localizada ou não comparável. N/D não representa zero, média ou estimativa."],
    ["Precedência", "Documento primário preservado; o complemento manual ocupa somente lacunas e aparece em colunas próprias."],
    ["Escopo econômico", "PL representa o patrimônio do veículo. O valor efetivamente encarteirado por posição não está disponível nesta base."],
  ];
  sheet.getRange("A9:B9").values = [["Tema", "Orientação"]];
  sheet.getRange("A9:B9").format.fill = C.black;
  sheet.getRange("A9:B9").format.font = { name: "Arial", size: 10, bold: true, color: C.white };
  sheet.getRange(`A10:B${9 + guidance.length}`).values = guidance;
  sheet.getRange(`A10:B${9 + guidance.length}`).format.font = { name: "Arial", size: 10, color: C.charcoal };
  sheet.getRange(`A10:B${9 + guidance.length}`).format.wrapText = true;
  sheet.getRange(`A10:B${9 + guidance.length}`).format.rowHeightPx = 48;
  sheet.getRange(`A10:A${9 + guidance.length}`).format.font = { name: "Arial", size: 10, bold: true, color: C.charcoal };
  sheet.getRange(`A10:A${9 + guidance.length}`).format.fill = C.pale;
  sheet.getRange(`A9:B${9 + guidance.length}`).format.borders = {
    insideHorizontal: { style: "thin", color: C.line },
    bottom: { style: "thin", color: C.line },
  };
  sheet.getRange("A1:A20").format.columnWidthPx = 190;
  sheet.getRange("B1:B20").format.columnWidthPx = 760;
  ["C", "D", "E", "F", "G", "H"].forEach((letter) => {
    sheet.getRange(`${letter}1:${letter}20`).format.columnWidthPx = 130;
  });
  sheet.freezePanes.freezeRows(2);
}

async function addPortfolioCoverageAndGapsSheet(workbook, payload) {
  const coverageColumns = [
    { header: "Coorte", key: "coorte", width: 120 },
    { header: "Campo", key: "campo", width: 210 },
    { header: "Linhas com dado", key: "linhas_com_dado", width: 105 },
    { header: "Linhas totais", key: "linhas_total", width: 95 },
    { header: "Cobertura por quantidade", key: "cobertura_contagem_pct", width: 145, format: "0.00%" },
    { header: "PL com dado", key: "pl_com_dado_brl", width: 135, format: 'R$ #,##0.00' },
    { header: "PL total", key: "pl_total_brl", width: 135, format: 'R$ #,##0.00' },
    { header: "Cobertura por PL", key: "cobertura_pl_pct", width: 125, format: "0.00%" },
  ];
  const coverage = payload.portfolio_export_coverage || [];
  const sheet = workbook.worksheets.add("Cobertura e lacunas");
  setHeaderBand(
    sheet,
    "Cobertura e lacunas · Carteira 101 + Flagships",
    "Cobertura por quantidade e PL. O denominador de cada percentual permanece explícito.",
    coverageColumns.map((column) => column.header),
    coverage.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 9 },
  );
  await writePortfolioRows(sheet, 4, coverageColumns, coverage);
  applyColumnWidths(sheet, coverageColumns.map((column) => column.width), coverage.length);
  coverageColumns.forEach((column, index) => {
    if (!column.format || !coverage.length) return;
    const letter = columnLetter(index);
    sheet.getRange(`${letter}5:${letter}${coverage.length + 4}`).format.numberFormat = column.format;
  });

  const gaps = payload.portfolio_export_gaps || [];
  const gapColumns = [
    { header: "Coorte", key: "coorte", width: 120 },
    { header: "CNPJ", key: "cnpj", width: 125 },
    { header: "Nome de referência", key: "nome_referencia", width: 300 },
    { header: "Status do preenchimento", key: "status_preenchimento", width: 190 },
    { header: "Campos não preenchidos", key: "campos_nao_preenchidos", width: 360 },
    { header: "Motivo da comparabilidade", key: "comparabilidade_motivo", width: 460 },
    { header: "Status da curadoria", key: "status_curadoria_documental", width: 280 },
  ];
  const sectionRow = coverage.length + 7;
  const gapHeaderRow = sectionRow + 1;
  sheet.getRange(`A${sectionRow}:G${sectionRow}`).merge();
  sheet.getRange(`A${sectionRow}`).values = [["LACUNAS POR CNPJ"]];
  sheet.getRange(`A${sectionRow}:G${sectionRow}`).format.fill = C.orange;
  sheet.getRange(`A${sectionRow}:G${sectionRow}`).format.font = { name: "Arial", size: 11, bold: true, color: C.white };
  sheet.getRange(`A${gapHeaderRow}:G${gapHeaderRow}`).values = [gapColumns.map((column) => column.header)];
  sheet.getRange(`A${gapHeaderRow}:G${gapHeaderRow}`).format.fill = C.black;
  sheet.getRange(`A${gapHeaderRow}:G${gapHeaderRow}`).format.font = { name: "Arial", size: 9, bold: true, color: C.white };
  await writePortfolioRows(sheet, gapHeaderRow, gapColumns, gaps);
  if (gaps.length) {
    const bodyStart = gapHeaderRow + 1;
    const bodyEnd = gapHeaderRow + gaps.length;
    sheet.getRange(`A${bodyStart}:G${bodyEnd}`).format.font = { name: "Arial", size: 8, color: C.charcoal };
    sheet.getRange(`A${bodyStart}:G${bodyEnd}`).format.wrapText = true;
    sheet.getRange(`A${bodyStart}:G${bodyEnd}`).format.rowHeightPx = 46;
    sheet.getRange(`B${bodyStart}:B${bodyEnd}`).format.numberFormat = "@";
  }
}

const PORTFOLIO_FIELD_DEFINITIONS = Object.freeze({
  cnpj_numerico: "CNPJ com 14 dígitos, gravado como número e exibido sem separadores.",
  nome_oficial_cvm: "Denominação completa observada no cadastro/base CVM.",
  pl_atual_brl: "Patrimônio líquido do veículo na competência de referência.",
  pl_classes_reportadas_brl: "Soma das classes de cotas reportadas no Informe Mensal.",
  pl_subordinado_atual_brl: "Soma das classes subordinadas reportadas.",
  sub_pl_atual: "PL subordinado atual dividido pelo PL oficial reconciliado.",
  minimo_junior_literal: "Mínimo júnior lido diretamente no documento, sobre PL.",
  minimo_junior_calculado: "Mínimo júnior convertido de razão/fator documental; linha marcada com *.",
  minimo_junior_ajustado: "Mínimo júnior sobre denominador ajustado; linha marcada com *.",
  suporte_total: "Piso de suporte subordinado total; métrica distinta do júnior isolado.",
  suporte_combinado_junior_mezanino: "Piso combinado de cotas júnior e mezanino.",
  minimo_estrutural_usado: "Piso usado no cálculo somente quando comparável ao Sub/PL atual.",
  comparavel_flag: "Confirma equivalência suficiente entre numerador, denominador e tranche.",
  folga_pp: "Sub/PL atual menos o piso estrutural comparável.",
  capacidade_ate_gatilho: "(Sub/PL atual − piso) / (1 − piso), somente em linhas comparáveis.",
  situacao_regulatoria: "Banda de situação frente ao piso documental.",
  grupo_comparacao: "Grupo comparável da taxonomia estrutural compartilhada entre Carteira I e flagships.",
  posicao_mercado: "Posição relativa à mediana dos pares quando o benchmark cumpre o limiar mínimo.",
  excesso_vs_mercado: "Sub/PL atual menos a mediana dos pares comparáveis; permanece ausente sem benchmark confiável.",
  benchmark_confiavel: "Indica que a categoria tem pelo menos o número mínimo configurado de comparáveis.",
  n_comparaveis_categoria: "Quantidade de pares com subordinação atual utilizável na categoria.",
  preco_cota_brl: "Preço unitário numérico quando uma única leitura documental é aplicável.",
  preco_cota_display: "Preço unitário preservado por classe ou série; não inclui quantidade, taxa, spread ou remuneração.",
  preco_cota_natureza: "Natureza documental do preço: VNU, emissão, subscrição ou integralização.",
  preco_cota_classe_serie: "Classe ou série à qual o preço unitário se refere.",
  preco_cota_documento_data: "Data do documento que sustenta o preço unitário.",
  preco_cota_documento_id: "Identificador do documento que sustenta o preço unitário.",
  preco_cota_fonte: "Caminho ou URL da evidência documental do preço unitário.",
  preco_cota_status: "Status de localização e revisão do preço unitário.",
  preco_cota_excecao_asterisco_flag: "Marca múltiplos valores/classes ou natureza que exige leitura do documento.",
  cedente_originador_literal: "Transcrição literal da coluna combinada Cedente/Originador.",
  papel_literal: "Papel indicado literalmente na fonte manual.",
  fonte_partes_recebivel: "Documento ou foto que sustenta partes e tipo de recebível.",
  fonte_documental: "Referência do regulamento, assembleia ou documento primário.",
  campos_nao_preenchidos: "Lista didática dos campos que permanecem ausentes.",
});

function portfolioFieldType(column) {
  if (column.key === "cnpj_numerico") return "Identificador numérico";
  if (column.format === "0.00%") return "Percentual";
  if (column.format?.startsWith("R$")) return "Moeda (R$)";
  if (/flag$/.test(column.key) || column.key === "benchmark_confiavel") return "Booleano";
  if (column.format === "#,##0") return "Inteiro";
  if (column.key === "ordem") return "Inteiro";
  return "Texto";
}

function portfolioFieldOrigin(column) {
  if (/^(cnpj|nome_|status_identidade|pl_|sub_pl_atual|status_sub_pl)/.test(column.key)) return "CVM / Informe Mensal";
  if (/^preco_cota_/.test(column.key)) return "Curadoria documental de VNU/preço unitário";
  if (/^(minimo_|suporte_|documento_|pagina_|status_curadoria|fonte_documental|texto_minimo)/.test(column.key)) return "Curadoria documental";
  if (/^(comparavel|comparabilidade|excecao|folga|capacidade|situacao|posicao_|excesso_|benchmark_|n_comparaveis)/.test(column.key)) return "Pacote estrutural existente";
  if (/^(tipo_|foco_|taxonomia_|grupo_)/.test(column.key)) return "Taxonomia analítica / oficial preservada";
  if (/^(cedente|papel|originador|sacado|fonte_partes|status_complemento|observacao_complemento)/.test(column.key)) return "Documento ou overlay manual auditado";
  return "Normalização do export";
}

async function addPortfolioDictionarySheet(workbook) {
  const columns = [
    { header: "Campo no Excel", key: "header", width: 235 },
    { header: "Campo no payload", key: "key", width: 245 },
    { header: "Tipo", key: "type", width: 145 },
    { header: "Origem", key: "origin", width: 260 },
    { header: "Definição", key: "definition", width: 620 },
    { header: "Regra de lacuna", key: "missing", width: 260 },
  ];
  const rows = PORTFOLIO_EXPORT_COLUMNS.map((column) => ({
    header: column.header,
    key: column.key,
    type: portfolioFieldType(column),
    origin: portfolioFieldOrigin(column),
    definition: PORTFOLIO_FIELD_DEFINITIONS[column.key]
      || `Campo ${column.header.toLowerCase()} preservado na granularidade de um CNPJ.`,
    missing: "N/D identifica ausência; nenhum valor é imputado como zero.",
  }));
  const sheet = workbook.worksheets.add("Dicionário");
  setHeaderBand(
    sheet,
    "Dicionário da base Carteira 101 + Flagships",
    "Definições, tipos, origem e tratamento de lacunas das colunas manipuláveis.",
    columns.map((column) => column.header),
    rows.length,
    { freezeColumns: 2, wrapText: true, bodyFontSize: 8.5 },
  );
  await writePortfolioRows(sheet, 4, columns, rows);
  applyColumnWidths(sheet, columns.map((column) => column.width), rows.length);
  sheet.getRange(`A5:F${rows.length + 4}`).format.rowHeightPx = 44;
}

async function addPortfolioManualSourcesSheet(workbook, payload) {
  const auditRows = payload.portfolio_export_manual_audit || [];
  const rows = auditRows.length ? auditRows : (payload.manual_cnpj_enrichment || []);
  const columns = [
    { header: "Raiz do CNPJ na foto", key: "raiz_cnpj_foto", width: 110 },
    { header: "CNPJ resolvido", key: "cnpj", width: 125, format: "00000000000000" },
    { header: "Status da resolução", key: "status_resolucao_cnpj", width: 165 },
    { header: "Denominação de referência", key: "denominacao_referencia", width: 330 },
    { header: "Cedente / Originador literal*", key: "cedente_originador_literal", width: 260 },
    { header: "Papel literal*", key: "papel_literal", width: 150 },
    { header: "Originador*", key: "originador", width: 210 },
    { header: "Cedente*", key: "cedente", width: 210 },
    { header: "Sacado / devedor*", key: "sacado_devedor", width: 220 },
    { header: "Tipo de recebível*", key: "tipo_recebivel_literal", width: 330 },
    { header: "Imagem", key: "fonte_manual", width: 145 },
    { header: "Localização na imagem", key: "localizacao_imagem", width: 300 },
    { header: "Status da transcrição", key: "status_transcricao", width: 150 },
    { header: "Confiança", key: "confianca", width: 95 },
    { header: "Observação", key: "observacao", width: 520 },
    { header: "Coortes encontradas", key: "coortes_encontradas", width: 170 },
    { header: "Campos aplicados", key: "campos_aplicados", width: 320 },
    { header: "Aplicado?", key: "aplicado_flag", width: 85 },
    { header: "Motivo da aplicação", key: "motivo_aplicacao", width: 320 },
  ];
  const sheet = workbook.worksheets.add("Fontes manuais");
  setHeaderBand(
    sheet,
    "Fontes manuais · transcrição das fotos fornecidas pelo usuário",
    "* = informação manual separada da evidência documental. Somente status confirmado_legivel é elegível; o overlay preenche lacunas e preserva o valor documental existente.",
    columns.map((column) => column.header),
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8 },
  );
  await writePortfolioRows(sheet, 4, columns, rows);
  applyColumnWidths(sheet, columns.map((column) => column.width), rows.length);
  if (rows.length) {
    sheet.getRange(`A5:S${rows.length + 4}`).format.rowHeightPx = 48;
    sheet.getRange(`A5:A${rows.length + 4}`).format.numberFormat = "00000000";
    sheet.getRange(`B5:B${rows.length + 4}`).format.numberFormat = "00000000000000";
    sheet.getRange(`M5:M${rows.length + 4}`).conditionalFormats.add("containsText", {
      text: "confirmado_legivel",
      format: { fill: "#DCEFE2", font: { bold: true, color: "#006B3C" } },
    });
    sheet.getRange(`M5:M${rows.length + 4}`).conditionalFormats.add("containsText", {
      text: "revisao",
      format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
    });
  }
}

function portfolioRowsWithFormattedCnpj(rows) {
  return (rows || []).map((row) => {
    const digits = numericCnpjText(row.cnpj || row.cnpj_numerico);
    const formatted = digits !== "N/D"
      ? `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`
      : "N/D";
    return { ...row, cnpj: digits, cnpj_formatado: formatted };
  });
}

async function addPortfolioAuxiliarySheet(workbook, {
  name,
  title,
  subtitle,
  columns,
  rows,
  freezeColumns = 2,
  bodyFontSize = 8,
  rowHeight = 46,
}) {
  const sourceRows = portfolioRowsWithFormattedCnpj(rows);
  const sheet = workbook.worksheets.add(name);
  setHeaderBand(
    sheet,
    title,
    subtitle,
    columns.map((column) => column.header),
    sourceRows.length,
    { freezeColumns, wrapText: true, bodyFontSize },
  );
  sheet.getRange(`A2:${columnLetter(columns.length - 1)}2`).format.rowHeightPx = 44;
  await writePortfolioRows(sheet, 4, columns, sourceRows);
  applyColumnWidths(sheet, columns.map((column) => column.width), sourceRows.length);
  columns.forEach((column, index) => {
    if (!column.format || !sourceRows.length) return;
    const letter = columnLetter(index);
    const range = sheet.getRange(`${letter}5:${letter}${sourceRows.length + 4}`);
    range.format.numberFormat = column.format;
    if (column.format !== "@") range.format.horizontalAlignment = "right";
  });
  if (sourceRows.length) {
    sheet.getRange(`A5:${columnLetter(columns.length - 1)}${sourceRows.length + 4}`).format.rowHeightPx = rowHeight;
  }
  return sheet;
}

function ptYesNo(value) {
  if (value === true || String(value).toLowerCase() === "true") return "Sim";
  if (value === false || String(value).toLowerCase() === "false") return "Não";
  return "N/D";
}

function explicitCedenteValue(value, row) {
  if (value !== null && value !== undefined && String(value).trim() !== "") return value;
  return row.cedente_declarado_flag
    ? "N/D — não localizado na consolidação"
    : "N/D — Tabela I sem cedente";
}

function auditPayloadRows(rows, columns) {
  return (rows || []).map((row) => Object.fromEntries(
    columns.map((column) => {
      const sourceKey = column.sourceKey || column.key;
      const value = row[sourceKey];
      return [
        column.key,
        column.transform ? column.transform(value, row) : value,
      ];
    }),
  ));
}

async function addAuditablePayloadSheet(workbook, {
  name,
  title,
  subtitle,
  columns,
  rows,
  freezeColumns = 3,
  bodyFontSize = 8.5,
  rowHeight = 42,
}) {
  const sourceRows = auditPayloadRows(rows, columns);
  const sheet = resetSheet(workbook, name);
  setHeaderBand(
    sheet,
    title,
    subtitle,
    columns.map((column) => column.header),
    sourceRows.length,
    { freezeColumns, wrapText: true, bodyFontSize },
  );
  await writePortfolioRows(sheet, 4, columns, sourceRows);
  applyColumnWidths(sheet, columns.map((column) => column.width), sourceRows.length);
  columns.forEach((column, index) => {
    if (!column.format || !sourceRows.length) return;
    const letter = columnLetter(index);
    const range = sheet.getRange(`${letter}5:${letter}${sourceRows.length + 4}`);
    range.format.numberFormat = column.format;
    if (column.format !== "@") range.format.horizontalAlignment = "right";
  });
  if (sourceRows.length) {
    sheet
      .getRange(`A5:${columnLetter(columns.length - 1)}${sourceRows.length + 4}`)
      .format.rowHeightPx = rowHeight;
  }
  return sheet;
}

const CEDENTE_TOP437_COLUMNS = Object.freeze([
  { header: "Rank por PL", key: "rank_pl_fundo", width: 90, format: "#,##0" },
  { header: "CNPJ do fundo", key: "cnpj_fundo", width: 125, format: "00000000000000" },
  { header: "CNPJ do fundo · fonte", key: "cnpj_fundo_raw", width: 145 },
  { header: "FIDC", key: "fundo", width: 370 },
  { header: "PL do fundo · R$", key: "pl_fundo_reais", width: 145, format: "R$ #,##0.00" },
  { header: "% PL da indústria", key: "pl_fundo_pct_industria_origem", width: 115, format: "0.00%" },
  { header: "% PL acumulado", key: "pl_acumulado_pct_origem", width: 115, format: "0.00%" },
  { header: "PL negativo?", key: "pl_negativo_flag", width: 95, transform: ptYesNo },
  { header: "Administrador", key: "administrador", width: 290 },
  { header: "Cedentes declarados no fundo", key: "cedentes_declarados_fundo", width: 125, format: "#,##0" },
  { header: "Cedente declarado?", key: "cedente_declarado_flag", width: 110, transform: ptYesNo },
  { header: "Documento do cedente · coluna H", key: "cedente_doc_raw", width: 165, transform: explicitCedenteValue },
  { header: "Chave normalizada do documento", key: "cedente_doc_key", width: 190, transform: explicitCedenteValue },
  { header: "Tipo de documento", key: "cedente_tipo", width: 105, transform: explicitCedenteValue },
  { header: "Status do documento", key: "cedente_documento_status", width: 170 },
  { header: "Razão social · coluna K", key: "cedente_razao_social_coluna_k", width: 300, transform: explicitCedenteValue },
  { header: "Razões sociais · coluna K · JSON", key: "cedente_razoes_coluna_k_json", width: 360 },
  { header: "Razão social consolidada", key: "cedente_razao_social_consolidada", width: 300, transform: explicitCedenteValue },
  { header: "Razão social reconciliada?", key: "razao_social_match_flag", width: 125, transform: ptYesNo },
  { header: "CNAE principal", key: "cedente_cnae_principal", width: 190, transform: explicitCedenteValue },
  { header: "Porte da Receita", key: "cedente_porte_receita", width: 125, transform: explicitCedenteValue },
  { header: "Capital social · R$", key: "cedente_capital_social_reais", width: 145, format: "R$ #,##0.00" },
  { header: "Optante Simples", key: "cedente_optante_simples", width: 105, transform: ptYesNo },
  { header: "MEI", key: "cedente_mei", width: 80, transform: ptYesNo },
  { header: "UF", key: "cedente_uf", width: 70, transform: explicitCedenteValue },
  { header: "Fundos em que aparece", key: "fundos_em_que_aparece", width: 115, format: "#,##0" },
  { header: "PL alcançado · R$*", key: "pl_alcancado_reais", width: 145, format: "R$ #,##0.00" },
  { header: "Maior % em um fundo", key: "maior_pct_em_um_fundo", width: 120, format: "0.00%" },
  { header: "Fundos em que aparece · lista", key: "fundos_lista", width: 410 },
  { header: "Linhas na fonte", key: "linhas_declaracao_origem", width: 100, format: "#,##0" },
  { header: "Blocos declarados", key: "blocos_declarados", width: 220 },
  { header: "Ordens declaradas · JSON", key: "ordens_declaradas_json", width: 180 },
  { header: "Percentuais declarados · JSON", key: "percentuais_declarados_json", width: 220 },
  { header: "Declarações preservadas · JSON", key: "declaracoes_json", width: 520 },
  { header: "Duplicidade fundo-cedente?", key: "duplicidade_fundo_cedente_flag", width: 125, transform: ptYesNo },
  { header: "Duplicidade cruza blocos?", key: "duplicidade_cruza_blocos_flag", width: 125, transform: ptYesNo },
  { header: "Duplicidade no mesmo bloco?", key: "duplicidade_mesmo_bloco_flag", width: 135, transform: ptYesNo },
  { header: "Percentual ausente?", key: "percentual_ausente_flag", width: 115, transform: ptYesNo },
  { header: "Percentual não positivo?", key: "percentual_nao_positivo_flag", width: 125, transform: ptYesNo },
  { header: "Percentual acima de 100%?", key: "percentual_acima_100_flag", width: 135, transform: ptYesNo },
  { header: "Percentual inválido?", key: "percentual_invalido_flag", width: 115, transform: ptYesNo },
  { header: "Soma dos percentuais declarados", key: "soma_percentuais_declarados", width: 135, format: "0.00%" },
  { header: "Exclusão ME/EPP/Simples?", key: "filtro_exclusao_me_epp_simples_flag", width: 135, transform: ptYesNo },
  { header: "Triagem Middle Market · status", key: "middle_market_triage_status", width: 210 },
  { header: "Triagem Middle Market · limitação", key: "middle_market_limitation", width: 430 },
]);

const CEDENTE_COVERAGE_COLUMNS = Object.freeze([
  { header: "Rank por PL", key: "rank_pl_fundo", width: 90, format: "#,##0" },
  { header: "CNPJ do fundo", key: "cnpj_fundo", width: 125, format: "00000000000000" },
  { header: "CNPJ do fundo · fonte", key: "cnpj_fundo_raw", width: 145 },
  { header: "FIDC", key: "fundo", width: 370 },
  { header: "PL do fundo · R$", key: "pl_fundo_reais", width: 145, format: "R$ #,##0.00" },
  { header: "% PL da indústria", key: "pl_fundo_pct_industria_origem", width: 115, format: "0.00%" },
  { header: "% PL acumulado · fonte", key: "pl_acumulado_pct_origem", width: 125, format: "0.00%" },
  { header: "Cedentes declarados", key: "cedentes_declarados_fundo", width: 110, format: "#,##0" },
  { header: "Administrador", key: "administrador", width: 290 },
  { header: "PL negativo?", key: "pl_negativo_flag", width: 95, transform: ptYesNo },
  { header: "Cedente declarado?", key: "cedente_declarado_flag", width: 110, transform: ptYesNo },
  { header: "PL com cedente · R$", key: "pl_com_cedente_reais", width: 140, format: "R$ #,##0.00" },
  { header: "PL sem cedente · R$", key: "pl_sem_cedente_reais", width: 140, format: "R$ #,##0.00" },
  { header: "PL acumulado · R$", key: "pl_total_acumulado_reais", width: 145, format: "R$ #,##0.00" },
  { header: "% PL acumulado", key: "pl_total_acumulado_pct", width: 115, format: "0.00%" },
  { header: "Fundos com cedente · acum.", key: "fundos_com_cedente_acumulado", width: 125, format: "#,##0" },
  { header: "Fundos sem cedente · acum.", key: "fundos_sem_cedente_acumulado", width: 125, format: "#,##0" },
  { header: "PL com cedente · acum. R$", key: "pl_com_cedente_acumulado_reais", width: 150, format: "R$ #,##0.00" },
  { header: "PL sem cedente · acum. R$", key: "pl_sem_cedente_acumulado_reais", width: 150, format: "R$ #,##0.00" },
  { header: "% indústria · com cedente", key: "pl_com_cedente_acumulado_pct_industria", width: 125, format: "0.00%" },
  { header: "% indústria · sem cedente", key: "pl_sem_cedente_acumulado_pct_industria", width: 125, format: "0.00%" },
  { header: "% com cedente dentro do corte", key: "pl_com_cedente_pct_dentro_corte", width: 140, format: "0.00%" },
  { header: "Dentro do corte recomendado?", key: "dentro_corte_recomendado_flag", width: 145, transform: ptYesNo },
  { header: "Linha do corte recomendado?", key: "corte_recomendado_flag", width: 145, transform: ptYesNo },
  { header: "Marco de cobertura", key: "marco_cobertura", width: 135 },
]);

const TAXONOMY_DEPARA_COLUMNS = Object.freeze([
  { header: "CNPJ", key: "cnpj_fundo", width: 125, format: "00000000000000" },
  { header: "FIDC", key: "denominacao_referencia", width: 390 },
  { header: "PL · R$", key: "pl_brl", width: 145, format: "R$ #,##0.00" },
  { header: "Tipo anterior", key: "tipo_atual", width: 185 },
  { header: "Foco anterior", key: "foco_atual", width: 210 },
  { header: "Tipo final", key: "tipo_proposto", width: 185 },
  { header: "Foco final", key: "foco_proposto", width: 210 },
  { header: "Efeito", key: "efeito", width: 120 },
  { header: "Competência de referência", key: "competencia_referencia", width: 135 },
  { header: "Arquivo-fonte", key: "fonte_arquivo", width: 240 },
  { header: "SHA-256 da fonte", key: "fonte_sha256", width: 420 },
  { header: "Status da nota do manifest", key: "status_nota_manifest", width: 180 },
  { header: "Nota do manifest", key: "nota_manifest", width: 520 },
]);

const TAXONOMY_OUTROS_COLUMNS = Object.freeze([
  { header: "Rank por PL", key: "Rank PL", width: 90, format: "#,##0" },
  { header: "CNPJ", key: "cnpj_fundo", width: 125, format: "00000000000000" },
  { header: "CNPJ · fonte", key: "CNPJ", width: 145 },
  { header: "FIDC", key: "FIDC", width: 390 },
  { header: "PL · R$", key: "PL (R$)", width: 145, format: "R$ #,##0.00" },
  { header: "Foco publicado", key: "Foco publicado hoje", width: 210 },
  { header: "Balde proposto", key: "Balde proposto", width: 210 },
  { header: "Base da alocação", key: "Base da alocação", width: 520 },
  { header: "Sacado / cedente relevante · fonte", key: "Sacado / cedente relevante (Tabela I + Receita)", width: 330 },
  { header: "Informe jun/26?", key: "Tem informe jun/26?", width: 105 },
  { header: "Observação", key: "Observação", width: 520 },
  { header: "Competência de referência", key: "competencia_referencia", width: 135 },
  { header: "Arquivo-fonte", key: "fonte_arquivo", width: 240 },
  { header: "SHA-256 da fonte", key: "fonte_sha256", width: 420 },
  { header: "Status da nota do manifest", key: "status_nota_manifest", width: 180 },
  { header: "Nota do manifest", key: "nota_manifest", width: 520 },
]);

const TAXONOMY_IMPACT_SUMMARY_COLUMNS = Object.freeze([
  { header: "Visão", key: "view", width: 190 },
  { header: "Competência", key: "competence", width: 105 },
  { header: "Universo / perímetro", key: "universe", width: 360 },
  { header: "Dimensão", key: "dimension", width: 180 },
  { header: "Categoria", key: "category", width: 210 },
  { header: "Decisões", key: "decision_count", width: 85, format: "#,##0" },
  { header: "PL impactado · R$ bi", key: "impacted_pl_brl", width: 145, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Antes · R$ bi", key: "before_brl", width: 135, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Depois · R$ bi", key: "after_brl", width: 135, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Variação · R$ bi", key: "delta_brl", width: 145, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Denominador · R$ bi", key: "denominator_brl", width: 155, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Antes · %", key: "before_share", width: 95, format: "0.00%" },
  { header: "Depois · %", key: "after_share", width: 95, format: "0.00%" },
  { header: "Variação · p.p.", key: "delta_pp", width: 110, format: '0.000 "p.p."' },
  { header: "Fonte", key: "source", width: 480 },
  { header: "Nota de perímetro", key: "note", width: 540 },
]);

const TAXONOMY_ISSUANCE_IMPACT_COLUMNS = Object.freeze([
  { header: "Chave do período", key: "period_key", width: 110 },
  { header: "Período", key: "period_label", width: 115 },
  { header: "Categoria", key: "categoria", width: 210 },
  { header: "Antes · R$ bi", key: "before_volume_brl", width: 135, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Depois · R$ bi", key: "after_volume_brl", width: 135, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Variação · R$ bi", key: "delta_brl", width: 145, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Antes · %", key: "before_share", width: 95, format: "0.00%" },
  { header: "Depois · %", key: "after_share", width: 95, format: "0.00%" },
  { header: "Variação · p.p.", key: "delta_pp", width: 110, format: '0.000 "p.p."' },
  { header: "Total antes · R$ bi", key: "period_total_before_brl", width: 150, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Total depois · R$ bi", key: "period_total_after_brl", width: 155, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Fonte anterior", key: "source_before", width: 440 },
  { header: "Fonte atual", key: "source_after", width: 440 },
  { header: "Nota de reconciliação", key: "note", width: 540 },
]);

const TAXONOMY_MARKET_SHARE_IMPACT_COLUMNS = Object.freeze([
  { header: "Competência", key: "competence", width: 105 },
  { header: "Tipo ANBIMA", key: "tipo_anbima", width: 210 },
  { header: "Foco ANBIMA", key: "foco_anbima", width: 220 },
  { header: "Denominador antes · R$ bi", key: "before_denominator_brl", width: 170, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Denominador depois · R$ bi", key: "after_denominator_brl", width: 175, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Variação do denominador · R$ bi", key: "delta_denominator_brl", width: 190, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Positivo antes · R$ bi", key: "before_positive_denominator_brl", width: 160, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Positivo depois · R$ bi", key: "after_positive_denominator_brl", width: 165, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Fundos antes", key: "before_funds", width: 105, format: "#,##0" },
  { header: "Fundos depois", key: "after_funds", width: 110, format: "#,##0" },
  { header: "Escopo antes · R$ bi", key: "scope_total_before_brl", width: 155, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Escopo depois · R$ bi", key: "scope_total_after_brl", width: 160, format: 'R$ #,##0.0,,, "bi"' },
  { header: "Share antes", key: "before_share_scope", width: 100, format: "0.00%" },
  { header: "Share depois", key: "after_share_scope", width: 105, format: "0.00%" },
  { header: "Variação · p.p.", key: "delta_pp", width: 110, format: '0.000 "p.p."' },
  { header: "Papéis reconciliados", key: "roles_reconciled", width: 125, format: "#,##0" },
  { header: "Fonte", key: "source", width: 520 },
  { header: "Nota de perímetro", key: "note", width: 560 },
]);

function addCedenteReadmeSheet(workbook, payload) {
  const manifest = payload.cedente_middle_market_manifest || {};
  const coverage = manifest.coverage || {};
  const cutoff = manifest.cutoff || {};
  const queue = cutoff.top_queue || {};
  const recommended = (cutoff.snapshots || []).find(
    (row) => Number(row.rank) === Number(cutoff.recommended_rank),
  ) || {};
  const source = manifest.source || {};
  const sheet = resetSheet(workbook, "Cedentes · Leia-me");
  sheet.getRange("A1:H1").merge();
  sheet.getRange("A1").values = [["Triagem de cedentes · Middle Market"]];
  sheet.getRange("A1:H1").format.fill = C.black;
  sheet.getRange("A1:H1").format.font = { name: "Arial", size: 16, bold: true, color: C.white };
  sheet.getRange("A1:H1").format.rowHeightPx = 34;
  sheet.getRange("A2:H2").merge();
  sheet.getRange("A2").values = [[
    `Competência jun/26. Fonte ${source.file || "N/D"}; SHA-256 ${source.sha256 || "N/D"}. Fila recomendada: Top ${cutoff.recommended_rank || "N/D"} por PL.`,
  ]];
  sheet.getRange("A2:H2").format.font = { name: "Arial", size: 10, color: C.mid };
  sheet.getRange("A2:H2").format.wrapText = true;
  sheet.getRange("A2:H2").format.rowHeightPx = 34;

  const summaryRows = [
    ["Universo", coverage.fundos_total, coverage.pl_total_reais, 1, "4.311 fundos da fonte CVM/Tabela I"],
    ["Com cedente declarado", coverage.fundos_com_cedente, coverage.pl_com_cedente_reais, coverage.pl_com_cedente_pct, "Cedente declarado na Tabela I"],
    ["Sem cedente declarado", coverage.fundos_sem_cedente, coverage.pl_sem_cedente_reais, coverage.pl_sem_cedente_pct, "Requer leitura documental"],
    [`Top ${cutoff.recommended_rank || "N/D"}`, queue.fundos, recommended.pl_acumulado_reais, recommended.pl_acumulado_pct, "Corte recomendado para revisão em duas ondas"],
    ["No corte · com cedente", recommended.fundos_com_cedente, recommended.pl_com_cedente_reais, recommended.pl_com_cedente_pct_industria, `${queue.pares_fundo_cedente || 0} pares fundo-cedente`],
    ["No corte · sem cedente", recommended.fundos_sem_cedente, recommended.pl_sem_cedente_reais, num(recommended.pl_sem_cedente_reais) / num(coverage.pl_total_reais), "PL sem cedente identificado permanece explícito"],
  ];
  sheet.getRange("A4:E4").values = [["Métrica", "Fundos", "PL · R$", "% PL da indústria", "Leitura"]];
  sheet.getRange("A4:E4").format.fill = C.black;
  sheet.getRange("A4:E4").format.font = { name: "Arial", size: 10, bold: true, color: C.white };
  sheet.getRange("A5:E10").values = summaryRows;
  sheet.getRange("A5:E10").format.font = { name: "Arial", size: 10, color: C.charcoal };
  sheet.getRange("A5:E10").format.borders = { insideHorizontal: { style: "thin", color: C.line } };
  sheet.getRange("A5:E10").format.rowHeightPx = 30;
  sheet.getRange("B5:B10").format.numberFormat = "#,##0";
  sheet.getRange("C5:C10").format.numberFormat = "R$ #,##0.00";
  sheet.getRange("D5:D10").format.numberFormat = "0.00%";
  sheet.getRange("B5:D10").format.horizontalAlignment = "right";
  sheet.getRange("E5:E10").format.wrapText = true;

  sheet.getRange("A12:H12").merge();
  sheet.getRange("A12").values = [["Limitações e regras de uso"]];
  sheet.getRange("A12:H12").format.fill = C.orange;
  sheet.getRange("A12:H12").format.font = { name: "Arial", size: 11, bold: true, color: C.white };
  const limitations = manifest.limitations || [];
  const requiredLimitations = [
    "Fundo x Cedente: a coluna H fornece o documento do cedente e a coluna K fornece a razão social declarada.",
    "Cedentes consolidados: a chave da coluna A reconcilia razão social e atributos cadastrais das colunas E/F e adjacentes.",
    "A Tabela I identifica cedente; não identifica sacado ou devedor nomeado.",
    "Porte da Receita e capital social não confirmam faturamento entre R$ 30 mi e R$ 500 mi.",
    "Percentuais inválidos permanecem como declarados e recebem flags; não são corrigidos automaticamente.",
  ];
  const notes = [...requiredLimitations, ...limitations]
    .filter((value, index, values) => values.indexOf(value) === index);
  notes.forEach((note, index) => {
    const row = 13 + index;
    sheet.getRange(`A${row}:H${row}`).merge();
    sheet.getRange(`A${row}`).values = [[`• ${note}`]];
    sheet.getRange(`A${row}:H${row}`).format.font = { name: "Arial", size: 10, color: C.charcoal };
    sheet.getRange(`A${row}:H${row}`).format.wrapText = true;
    sheet.getRange(`A${row}:H${row}`).format.rowHeightPx = 30;
  });
  applyColumnWidths(sheet, [220, 105, 150, 125, 470, 80, 80, 80], 12 + notes.length);
  sheet.freezePanes.freezeRows(4);
  return sheet;
}

async function addCedenteAuditSheets(workbook, payload) {
  addCedenteReadmeSheet(workbook, payload);
  const topSheet = await addAuditablePayloadSheet(workbook, {
    name: "Cedentes · Top 437",
    title: "Cedentes · fila priorizada Top 437",
    subtitle: "510 linhas: 214 pares fundo-cedente e 296 fundos sem cedente na Tabela I. PL alcançado soma o PL integral dos fundos citantes e não mede exposição econômica. Percentuais inválidos permanecem declarados e sinalizados.",
    columns: CEDENTE_TOP437_COLUMNS,
    rows: payload.cedente_middle_market_top437 || [],
    freezeColumns: 4,
    bodyFontSize: 8.5,
    rowHeight: 46,
  });
  if ((payload.cedente_middle_market_top437 || []).length) {
    const statusColumn = columnLetter(CEDENTE_TOP437_COLUMNS.findIndex((column) => column.key === "middle_market_triage_status"));
    const invalidColumn = columnLetter(CEDENTE_TOP437_COLUMNS.findIndex((column) => column.key === "percentual_invalido_flag"));
    topSheet.getRange(`${statusColumn}5:${statusColumn}${(payload.cedente_middle_market_top437 || []).length + 4}`).conditionalFormats.add("containsText", {
      text: "sem_cedente_tabela_i",
      format: { fill: C.pale, font: { color: C.mid } },
    });
    topSheet.getRange(`${invalidColumn}5:${invalidColumn}${(payload.cedente_middle_market_top437 || []).length + 4}`).conditionalFormats.add("containsText", {
      text: "Sim",
      format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
    });
  }

  const curveSheet = await addAuditablePayloadSheet(workbook, {
    name: "Cedentes · Cobertura",
    title: "Cedentes · curva acumulada de cobertura",
    subtitle: "4.311 fundos do maior para o menor PL. A aba separa PL com e sem cedente declarado na Tabela I; vazio na fonte permanece ausência, sem imputação.",
    columns: CEDENTE_COVERAGE_COLUMNS,
    rows: payload.cedente_middle_market_coverage_curve || [],
    freezeColumns: 4,
    bodyFontSize: 8.5,
    rowHeight: 34,
  });
  if ((payload.cedente_middle_market_coverage_curve || []).length) {
    const cutoffColumn = columnLetter(CEDENTE_COVERAGE_COLUMNS.findIndex((column) => column.key === "corte_recomendado_flag"));
    curveSheet.getRange(`${cutoffColumn}5:${cutoffColumn}${(payload.cedente_middle_market_coverage_curve || []).length + 4}`).conditionalFormats.add("containsText", {
      text: "Sim",
      format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
    });
  }
}

async function addTaxonomyAuditSheets(workbook, payload) {
  const manifest = payload.taxonomy_audit_manifest || {};
  const source = manifest.source || {};
  const rules = manifest.rules || [];
  const sourceLabel = `${source.filename || "N/D"}; SHA-256 ${source.sha256 || "N/D"}`;
  const rulesLabel = rules.slice(0, 2).join(" · ");
  const decisions = payload.taxonomy_audit_decisions || [];
  const deparaSheet = await addAuditablePayloadSheet(workbook, {
    name: "Taxonomia · de-para",
    title: "Taxonomia auditada · de-para por CNPJ",
    subtitle: `${decisions.length} decisões; ${rulesLabel}. Fonte ${sourceLabel}. Campos oficiais ANBIMA/CVM permanecem preservados.`,
    columns: TAXONOMY_DEPARA_COLUMNS,
    rows: decisions,
    freezeColumns: 3,
    bodyFontSize: 9,
    rowHeight: 48,
  });
  if (decisions.length) {
    const effectColumn = columnLetter(TAXONOMY_DEPARA_COLUMNS.findIndex((column) => column.key === "efeito"));
    deparaSheet.getRange(`${effectColumn}5:${effectColumn}${decisions.length + 4}`).conditionalFormats.add("containsText", {
      text: "Migra de Tipo",
      format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
    });
  }

  const outros = payload.taxonomy_audit_outros_three_buckets || [];
  const outrosSheet = await addAuditablePayloadSheet(workbook, {
    name: "Taxonomia · Outros",
    title: "Taxonomia auditada · abertura de Outros em três baldes",
    subtitle: `${outros.length} linhas. Fundos sem informe em jun/26 permanecem no denominador; o residual F8 não determina classificação analítica. Fonte ${sourceLabel}.`,
    columns: TAXONOMY_OUTROS_COLUMNS,
    rows: outros,
    freezeColumns: 4,
    bodyFontSize: 8.5,
    rowHeight: 58,
  });
  if (outros.length) {
    const bucketColumn = columnLetter(TAXONOMY_OUTROS_COLUMNS.findIndex((column) => column.key === "Balde proposto"));
    outrosSheet.getRange(`${bucketColumn}5:${bucketColumn}${outros.length + 4}`).conditionalFormats.add("containsText", {
      text: "Sai do balde Outros",
      format: { fill: "#FFF0D6", font: { bold: true, color: "#A65A00" } },
    });
  }
}

async function addTaxonomyImpactBlock(sheet, titleRow, title, columns, sourceRows) {
  const rows = auditPayloadRows(sourceRows, columns);
  const lastColumn = columnLetter(columns.length - 1);
  const headerRow = titleRow + 1;
  const dataStartRow = titleRow + 2;
  const dataEndRow = dataStartRow + rows.length - 1;

  sheet.getRange(`A${titleRow}:${lastColumn}${titleRow}`).merge();
  sheet.getRange(`A${titleRow}`).values = [[title]];
  sheet.getRange(`A${titleRow}:${lastColumn}${titleRow}`).format.fill = C.orange;
  sheet.getRange(`A${titleRow}:${lastColumn}${titleRow}`).format.font = {
    name: "Arial",
    size: 11,
    bold: true,
    color: C.white,
  };
  sheet.getRange(`A${titleRow}:${lastColumn}${titleRow}`).format.rowHeightPx = 28;

  sheet.getRange(`A${headerRow}:${lastColumn}${headerRow}`).values = [
    columns.map((column) => column.header),
  ];
  sheet.getRange(`A${headerRow}:${lastColumn}${headerRow}`).format.fill = C.black;
  sheet.getRange(`A${headerRow}:${lastColumn}${headerRow}`).format.font = {
    name: "Arial",
    size: 10,
    bold: true,
    color: C.white,
  };
  sheet.getRange(`A${headerRow}:${lastColumn}${headerRow}`).format.wrapText = true;
  sheet.getRange(`A${headerRow}:${lastColumn}${headerRow}`).format.rowHeightPx = 42;

  if (rows.length) {
    await writePortfolioRows(sheet, dataStartRow - 1, columns, rows);
    const body = sheet.getRange(`A${dataStartRow}:${lastColumn}${dataEndRow}`);
    body.format.font = { name: "Arial", size: 9, color: C.charcoal };
    body.format.verticalAlignment = "center";
    body.format.wrapText = true;
    body.format.rowHeightPx = 46;
    body.format.borders = {
      insideHorizontal: { style: "thin", color: C.line },
      bottom: { style: "thin", color: C.line },
    };
    rows.forEach((_, index) => {
      if (index % 2 === 1) {
        sheet
          .getRange(`A${dataStartRow + index}:${lastColumn}${dataStartRow + index}`)
          .format.fill = C.pale;
      }
    });
    columns.forEach((column, index) => {
      if (!column.format) return;
      const letter = columnLetter(index);
      const range = sheet.getRange(`${letter}${dataStartRow}:${letter}${dataEndRow}`);
      range.format.numberFormat = column.format;
      range.format.horizontalAlignment = "right";
    });
  }
  return dataEndRow + 2;
}

async function addTaxonomyImpactSheet(workbook, payload) {
  const sheet = resetSheet(workbook, "Taxonomia · impacto");
  const blocks = [
    {
      title: "Estoque · fonte bruta e efeito incremental na base corrente",
      columns: TAXONOMY_IMPACT_SUMMARY_COLUMNS,
      rows: payload.taxonomy_audit_impact_summary || [],
    },
    {
      title: "Emissões · impacto por período e Tipo ANBIMA",
      columns: TAXONOMY_ISSUANCE_IMPACT_COLUMNS,
      rows: payload.taxonomy_audit_issuance_impact || [],
    },
    {
      title: "Market share · impacto nos denominadores por subtipo",
      columns: TAXONOMY_MARKET_SHARE_IMPACT_COLUMNS,
      rows: payload.taxonomy_audit_market_share_impact || [],
    },
  ];
  const maxColumns = Math.max(...blocks.map((block) => block.columns.length));
  const lastColumn = columnLetter(maxColumns - 1);
  sheet.getRange(`A1:${lastColumn}1`).merge();
  sheet.getRange("A1").values = [["Taxonomia auditada · impacto reconciliado"]];
  sheet.getRange(`A1:${lastColumn}1`).format.fill = C.black;
  sheet.getRange(`A1:${lastColumn}1`).format.font = {
    name: "Arial",
    size: 16,
    bold: true,
    color: C.white,
  };
  sheet.getRange(`A1:${lastColumn}1`).format.rowHeightPx = 34;
  sheet.getRange(`A2:${lastColumn}2`).merge();
  sheet.getRange("A2").values = [[
    "As tabelas preservam três perímetros: estoque bruto do workbook auditado, efeito incremental na base corrente e emissões/denominadores materializados. Variações em R$ bi e p.p. não são somadas entre perímetros.",
  ]];
  sheet.getRange(`A2:${lastColumn}2`).format.font = {
    name: "Arial",
    size: 10,
    color: C.mid,
  };
  sheet.getRange(`A2:${lastColumn}2`).format.wrapText = true;
  sheet.getRange(`A2:${lastColumn}2`).format.rowHeightPx = 44;

  let nextTitleRow = 4;
  for (const block of blocks) {
    nextTitleRow = await addTaxonomyImpactBlock(
      sheet,
      nextTitleRow,
      block.title,
      block.columns,
      block.rows,
    );
  }

  const widths = Array.from({ length: maxColumns }, (_, index) =>
    Math.max(...blocks.map((block) => block.columns[index]?.width || 80)),
  );
  applyColumnWidths(sheet, widths, nextTitleRow);
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(3);
  return sheet;
}

const PORTFOLIO_PRICE_SHEET_COLUMNS = Object.freeze([
  { header: "CNPJ", key: "cnpj", width: 125, format: "00000000000000" },
  { header: "CNPJ formatado", key: "cnpj_formatado", width: 145 },
  { header: "Classe / série", key: "class_series", width: 230 },
  { header: "Preço unitário · leitura", key: "price_display", width: 180 },
  { header: "Preço unitário · R$", key: "price_brl", width: 155, format: 'R$ #,##0.00' },
  { header: "Natureza", key: "price_nature", width: 190 },
  { header: "Exceção*", key: "excecao_asterisco_flag", width: 95 },
  { header: "Tipo de fonte", key: "source_kind", width: 135 },
  { header: "Documento", key: "source_id", width: 140 },
  { header: "Classe documental", key: "document_class", width: 150 },
  { header: "Data do documento", key: "document_date", width: 125 },
  { header: "Página", key: "page", width: 80 },
  { header: "Status", key: "status", width: 170 },
  { header: "Aprovado para export?", key: "aprovado_para_export_flag", width: 140 },
  { header: "Caminho da fonte", key: "source_path", width: 390 },
  { header: "Link da fonte", key: "source_url", width: 390 },
  { header: "Trecho documental", key: "excerpt", width: 620 },
]);

const DOCUMENT_AUDIT_FIELD_LABELS = Object.freeze([
  ["originador", "Originador"],
  ["cedente", "Cedente"],
  ["sacado_devedor", "Sacado / devedor"],
  ["tipo_recebivel", "Tipo de recebível"],
  ["minimo_junior", "Mínimo júnior"],
  ["minimo_estrutural_total", "Mínimo estrutural total"],
  ["natureza_indice", "Natureza do índice"],
]);

const DOCUMENT_AUDIT_COLUMNS = Object.freeze([
  { header: "Ordem", key: "ordem", width: 70, format: "#,##0" },
  { header: "CNPJ", key: "cnpj", width: 125, format: "00000000000000" },
  { header: "CNPJ formatado", key: "cnpj_formatado", width: 145 },
  { header: "Nome do fundo", key: "nome_fundo", width: 390 },
  { header: "Status do scan", key: "status_scan", width: 140 },
  { header: "Fontes consultadas", key: "fontes_consultadas", width: 115, format: "#,##0" },
  { header: "Status online", key: "status_online", width: 140 },
  { header: "Erros do scan", key: "erros_scan", width: 360 },
  ...DOCUMENT_AUDIT_FIELD_LABELS.flatMap(([key, label]) => [
    { header: `${label} · valor`, key, width: 360 },
    { header: `${label} · status`, key: `${key}_status`, width: 160 },
    { header: `${label} · natureza`, key: `${key}_natureza`, width: 170 },
    { header: `${label} · documento`, key: `${key}_fonte`, width: 180 },
    { header: `${label} · data`, key: `${key}_data`, width: 115 },
    { header: `${label} · página`, key: `${key}_pagina`, width: 85 },
    { header: `${label} · link`, key: `${key}_link`, width: 390 },
    { header: `${label} · camada`, key: `${key}_camada`, width: 150 },
  ]),
]);

const DOCUMENT_EVIDENCE_COLUMNS = Object.freeze([
  { header: "CNPJ", key: "cnpj", width: 125, format: "00000000000000" },
  { header: "CNPJ formatado", key: "cnpj_formatado", width: 145 },
  { header: "Campo", key: "field", width: 170 },
  { header: "Valor encontrado", key: "value", width: 480 },
  { header: "Natureza", key: "nature", width: 180 },
  { header: "Tipo de fonte", key: "source_kind", width: 145 },
  { header: "Documento", key: "source_id", width: 160 },
  { header: "Classe documental", key: "document_class", width: 155 },
  { header: "Data do documento", key: "document_date", width: 125 },
  { header: "Página", key: "page", width: 80 },
  { header: "Status", key: "status", width: 160 },
  { header: "Confiança", key: "confidence", width: 100, format: "0.00%" },
  { header: "Caminho da fonte", key: "source_path", width: 390 },
  { header: "Link da fonte", key: "source_url", width: 390 },
  { header: "Trecho documental", key: "excerpt", width: 640 },
]);

const DOCUMENT_COVERAGE_COLUMNS = Object.freeze([
  { header: "Campo", key: "campo", width: 220 },
  { header: "CNPJ total", key: "linhas_total", width: 100, format: "#,##0" },
  { header: "Antes · com dado", key: "antes_com_dado", width: 115, format: "#,##0" },
  { header: "Antes · cobertura", key: "antes_cobertura_pct", width: 125, format: "0.00%" },
  { header: "Depois · com dado", key: "depois_com_dado", width: 120, format: "#,##0" },
  { header: "Depois · cobertura", key: "depois_cobertura_pct", width: 130, format: "0.00%" },
  { header: "Ganho · linhas", key: "ganho_linhas", width: 110, format: "#,##0" },
]);

const DOCUMENT_CHECKPOINT_COLUMNS = Object.freeze([
  { header: "CNPJ", key: "cnpj", width: 125, format: "00000000000000" },
  { header: "CNPJ formatado", key: "cnpj_formatado", width: 145 },
  { header: "Nome do fundo", key: "nome_fundo", width: 390 },
  { header: "Status", key: "status", width: 130 },
  { header: "Fontes consultadas", key: "sources_consulted", width: 110, format: "#,##0" },
  { header: "Fontes locais", key: "local_inventory_sources", width: 100, format: "#,##0" },
  { header: "Fontes no cache Director", key: "director_cache_sources", width: 125, format: "#,##0" },
  { header: "Status online", key: "online_status", width: 130 },
  { header: "Documentos online", key: "online_inventory_documents", width: 120, format: "#,##0" },
  { header: "Concluído em UTC", key: "completed_at_utc", width: 170 },
  { header: "Erros", key: "errors", width: 420 },
  { header: "Schema", key: "schema_version", width: 220 },
]);

async function addPortfolioPriceSheet(workbook, payload) {
  const rows = payload.portfolio_export_price_evidence || [];
  return addPortfolioAuxiliarySheet(workbook, {
    name: "Preços por cota",
    title: "Preços por cota · VNU, emissão, subscrição ou integralização",
    subtitle: "Uma linha por CNPJ e classe/série documentada. Quantidade, remuneração, taxa e spread não compõem o campo de preço; o trecho-fonte permanece integral. * identifica leitura excepcional.",
    columns: PORTFOLIO_PRICE_SHEET_COLUMNS,
    rows,
    freezeColumns: 3,
    bodyFontSize: 8,
    rowHeight: 54,
  });
}

async function addPortfolioDocumentAuditSheet(workbook, payload) {
  return addPortfolioAuxiliarySheet(workbook, {
    name: "Auditoria documental",
    title: "Auditoria documental · 101 CNPJs da Carteira I",
    subtitle: "Valor escolhido, status, natureza, documento, data, página, link e camada de evidência por campo. Candidato automático não aceito permanece apenas na aba de evidências.",
    columns: DOCUMENT_AUDIT_COLUMNS,
    rows: payload.carteira_101_document_audit || [],
    freezeColumns: 4,
    bodyFontSize: 8,
    rowHeight: 56,
  });
}

async function addPortfolioDocumentEvidenceSheet(workbook, payload) {
  return addPortfolioAuxiliarySheet(workbook, {
    name: "Evidências documentais",
    title: "Evidências documentais · trilha completa por CNPJ",
    subtitle: "Cada trecho localizado preserva campo, valor, natureza, fonte, página, status e confiança. Evidência não equivale automaticamente a campo aceito.",
    columns: DOCUMENT_EVIDENCE_COLUMNS,
    rows: payload.carteira_101_document_evidence || [],
    freezeColumns: 4,
    bodyFontSize: 8,
    rowHeight: 58,
  });
}

async function addPortfolioDocumentCoverageSheet(workbook, payload) {
  const coverage = payload.carteira_101_document_coverage || [];
  const checkpoint = portfolioRowsWithFormattedCnpj(
    payload.carteira_101_document_checkpoint || [],
  );
  const maxColumns = Math.max(
    DOCUMENT_COVERAGE_COLUMNS.length,
    DOCUMENT_CHECKPOINT_COLUMNS.length,
  );
  const lastColumn = columnLetter(maxColumns - 1);
  const sheet = workbook.worksheets.add("Cobertura varredura");
  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastColumn}1`).merge();
  sheet.getRange("A1").values = [["Cobertura da varredura documental · antes, depois e checkpoint"]];
  sheet.getRange(`A1:${lastColumn}1`).format.fill = C.black;
  sheet.getRange(`A1:${lastColumn}1`).format.font = { name: "Arial", size: 16, bold: true, color: C.white };
  sheet.getRange(`A1:${lastColumn}1`).format.rowHeightPx = 34;
  sheet.getRange(`A2:${lastColumn}2`).merge();
  sheet.getRange("A2").values = [["Denominadores explícitos por campo e uma linha de checkpoint para cada CNPJ. Ausência permanece N/D; consulta sem achado continua registrada."]];
  sheet.getRange(`A2:${lastColumn}2`).format.font = { name: "Arial", size: 10, color: C.mid };
  sheet.getRange(`A2:${lastColumn}2`).format.rowHeightPx = 30;

  sheet.getRange(`A4:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}4`).merge();
  sheet.getRange("A4").values = [["COBERTURA POR CAMPO"]];
  sheet.getRange(`A4:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}4`).format.fill = C.orange;
  sheet.getRange(`A4:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}4`).format.font = { name: "Arial", size: 11, bold: true, color: C.white };
  sheet.getRange(`A5:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}5`).values = [DOCUMENT_COVERAGE_COLUMNS.map((column) => column.header)];
  sheet.getRange(`A5:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}5`).format.fill = C.black;
  sheet.getRange(`A5:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}5`).format.font = { name: "Arial", size: 9, bold: true, color: C.white };
  await writePortfolioRows(sheet, 5, DOCUMENT_COVERAGE_COLUMNS, coverage);

  const checkpointSectionRow = 7 + coverage.length;
  const checkpointHeaderRow = checkpointSectionRow + 1;
  sheet.getRange(`A${checkpointSectionRow}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${checkpointSectionRow}`).merge();
  sheet.getRange(`A${checkpointSectionRow}`).values = [["CHECKPOINT POR CNPJ"]];
  sheet.getRange(`A${checkpointSectionRow}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${checkpointSectionRow}`).format.fill = C.orange;
  sheet.getRange(`A${checkpointSectionRow}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${checkpointSectionRow}`).format.font = { name: "Arial", size: 11, bold: true, color: C.white };
  sheet.getRange(`A${checkpointHeaderRow}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${checkpointHeaderRow}`).values = [DOCUMENT_CHECKPOINT_COLUMNS.map((column) => column.header)];
  sheet.getRange(`A${checkpointHeaderRow}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${checkpointHeaderRow}`).format.fill = C.black;
  sheet.getRange(`A${checkpointHeaderRow}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${checkpointHeaderRow}`).format.font = { name: "Arial", size: 9, bold: true, color: C.white };
  await writePortfolioRows(sheet, checkpointHeaderRow, DOCUMENT_CHECKPOINT_COLUMNS, checkpoint);

  const totalRows = checkpointHeaderRow + checkpoint.length;
  sheet.getRange(`A6:${columnLetter(DOCUMENT_COVERAGE_COLUMNS.length - 1)}${5 + coverage.length}`).format.font = { name: "Arial", size: 9, color: C.charcoal };
  sheet.getRange(`A${checkpointHeaderRow + 1}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${totalRows}`).format.font = { name: "Arial", size: 8, color: C.charcoal };
  sheet.getRange(`A${checkpointHeaderRow + 1}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${totalRows}`).format.wrapText = true;
  sheet.getRange(`A${checkpointHeaderRow + 1}:${columnLetter(DOCUMENT_CHECKPOINT_COLUMNS.length - 1)}${totalRows}`).format.rowHeightPx = 46;
  const widths = DOCUMENT_CHECKPOINT_COLUMNS.map((column, index) => Math.max(
    column.width,
    DOCUMENT_COVERAGE_COLUMNS[index]?.width || 0,
  ));
  applyColumnWidths(sheet, widths, totalRows);
  [
    [DOCUMENT_COVERAGE_COLUMNS, 6, 5 + coverage.length],
    [DOCUMENT_CHECKPOINT_COLUMNS, checkpointHeaderRow + 1, totalRows],
  ].forEach(([columns, start, end]) => {
    columns.forEach((column, index) => {
      if (!column.format || end < start) return;
      const range = sheet.getRange(`${columnLetter(index)}${start}:${columnLetter(index)}${end}`);
      range.format.numberFormat = column.format;
      range.format.horizontalAlignment = "right";
    });
  });
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}

async function addPortfolioPayloadDictionarySheet(workbook, payload) {
  const columns = [
    { header: "Campo no payload", key: "campo", width: 250 },
    { header: "Tipo de dado", key: "tipo_dado", width: 135 },
    { header: "Definição", key: "descricao", width: 620 },
    { header: "Origem / regra", key: "origem_regra", width: 420 },
    { header: "Tratamento da lacuna", key: "tratamento_lacuna", width: 300 },
  ];
  return addPortfolioAuxiliarySheet(workbook, {
    name: "Dicionário de campos",
    title: "Dicionário de campos · contrato normalizado do payload",
    subtitle: "Definições materializadas pelo produtor Python. Percentuais são frações; moeda e preço unitário permanecem numéricos quando há leitura única.",
    columns,
    rows: payload.portfolio_export_dictionary || [],
    freezeColumns: 2,
    bodyFontSize: 8.5,
    rowHeight: 50,
  });
}

async function addPortfolioEditableNamesSheet(workbook, cases) {
  const columns = [
    { header: "Ordem", key: "ordem", width: 70 },
    { header: "CNPJ", key: "cnpj_numerico", width: 125, format: "00000000000000" },
    { header: "Nome completo CVM", key: "nome_oficial_cvm", width: 430 },
    { header: "Nome editável para gráfico", key: "nome_editavel", width: 260 },
    { header: "Categoria proposta", key: "categoria_risco_proposta", width: 185 },
    { header: "Subtipo", key: "subtipo_risco_diagnosticado", width: 240 },
  ];
  const rows = cases.map((row) => ({
    ...row,
    nome_editavel: row.nome_referencia && row.nome_referencia !== "N/D"
      ? row.nome_referencia
      : row.nome_oficial_cvm,
  }));
  return addPortfolioAuxiliarySheet(workbook, {
    name: "Nomes editáveis",
    title: "Nomes editáveis · rótulos dos gráficos nativos",
    subtitle: "Edite somente a coluna Nome editável para gráfico. As séries dos gráficos apontam para estas células; CNPJ, nome CVM, categoria e subtipo permanecem como referência.",
    columns,
    rows,
    freezeColumns: 3,
    bodyFontSize: 9,
    rowHeight: 34,
  });
}

const TOP100_EXPORT_COLUMNS = Object.freeze([
  { header: "Ordem do export", key: "ordem_exportacao", width: 90, format: "#,##0" },
  { header: "Rank geral por PL", key: "rank_geral", width: 95, format: "#,##0" },
  { header: "Critério de inclusão", key: "inclusao_criterio", width: 210 },
  { header: "CNPJ", key: "cnpj", width: 125, format: "00000000000000" },
  { header: "CNPJ formatado", key: "cnpj_formatado", width: 135 },
  { header: "Nome completo do fundo (CVM)", key: "nome_fundo", width: 390 },
  { header: "PL", key: "pl_brl", width: 135, format: 'R$ #,##0.00' },
  { header: "% do PL ex-FIC", key: "share_pl_ex_fic", width: 110, format: "0.00%" },
  { header: "Sub / PL atual", key: "subordinacao_atual_pl", width: 120, format: "0.00%" },
  { header: "Mínimo de Sub Jr", key: "minimo_subordinacao_junior", width: 125, format: "0.00%" },
  { header: "Mínimo estrutural", key: "minimo_subordinacao_estrutural", width: 125, format: "0.00%" },
  { header: "Natureza do mínimo", key: "natureza_minimo", width: 310 },
  { header: "Preço inicial por cota", key: "preco_cota_emissao_brl", width: 145, format: 'R$ #,##0.00' },
  { header: "Oferta CVM", key: "oferta_id", width: 100 },
  { header: "Processo CVM", key: "processo_cvm", width: 135 },
  { header: "Data de registro", key: "data_registro", width: 120 },
  { header: "Data de encerramento", key: "data_encerramento", width: 135 },
  { header: "Volume registrado", key: "volume_registrado_brl", width: 145, format: 'R$ #,##0.00' },
  { header: "Cotas registradas", key: "quantidade_registrada", width: 120, format: "#,##0" },
  { header: "Cotas colocadas", key: "quantidade_colocada", width: 115, format: "#,##0" },
  { header: "Montante encerrado", key: "montante_encerrado_brl", width: 145, format: 'R$ #,##0.00' },
  { header: "Cedente / originador", key: "cedente_originador", width: 260 },
  { header: "Sacado / devedor", key: "sacado_devedor", width: 250 },
  { header: "Tipo de recebível", key: "tipo_recebivel", width: 320 },
  { header: "Tipo ANBIMA oficial", key: "tipo_anbima_oficial", width: 180 },
  { header: "Foco ANBIMA oficial", key: "foco_anbima_oficial", width: 200 },
  { header: "Tipo analítico", key: "tipo_analitico", width: 180 },
  { header: "Foco analítico", key: "foco_analitico", width: 210 },
  { header: "Taxonomia funcional N1", key: "taxonomia_funcional_n1", width: 210 },
  { header: "Taxonomia funcional N2", key: "taxonomia_funcional_n2", width: 240 },
  { header: "Middle Market?", key: "middle_market_flag", width: 110 },
  { header: "Middle Market · status", key: "middle_market_status", width: 280 },
  { header: "Middle Market · justificativa", key: "middle_market_justificativa", width: 430 },
  { header: "Evidência", key: "evidencia", width: 500 },
  { header: "Fonte", key: "fonte", width: 440 },
  { header: "Documento", key: "documento_id", width: 170 },
  { header: "Documento da emissão", key: "documento_emissao_id", width: 170 },
  { header: "Página / cláusula", key: "pagina_clausula", width: 150 },
  { header: "Fonte do regulamento", key: "fonte_regulamento", width: 430 },
  { header: "Fonte da emissão", key: "fonte_emissao", width: 430 },
  { header: "Status da cobertura", key: "status_cobertura", width: 230 },
]);

async function buildTop100Workbook(payload) {
  const rows = payload.top100_fidcs_middle_market || [];
  if (rows.length !== 102) {
    throw new Error(`Top 100 + 2 deveria conter 102 linhas; contém ${rows.length}.`);
  }
  const workbook = Workbook.create();
  const readme = workbook.worksheets.add("Leia-me");
  readme.showGridLines = false;
  readme.getRange("A1:H1").merge();
  readme.getRange("A1").values = [["Top 100 + 2 FIDCs · crédito corporativo e Middle Market"]];
  readme.getRange("A1:H1").format.fill = C.black;
  readme.getRange("A1:H1").format.font = { name: "Arial", size: 18, bold: true, color: C.white };
  readme.getRange("A2:H2").merge();
  readme.getRange("A2").values = [[
    `Competência ${payload.latest_complete || "N/D"}. Ranking global por PL ex-FIC, uma linha por CNPJ. O Top 100 recebe duas inclusões documentais de ofertas encerradas em 2026: Citi-Bayer Farmtech e Lavoro Farmtech.`,
  ]];
  readme.getRange("A2:H2").format.font = { name: "Arial", size: 10, color: C.mid };
  readme.getRange("A2:H2").format.wrapText = true;
  readme.getRange("A2:H2").format.rowHeightPx = 42;
  const summary = payload.top100_fidcs_middle_market_summary || {};
  const notes = [
    ["Universo", "100 maiores FIDCs ex-FIC por PL, mais Citi-Bayer Farmtech e Lavoro Farmtech por critério explícito de emissão encerrada em 2026."],
    ["PL do Top 100", moneyScale(summary.top100_pl_brl)],
    ["Participação no PL ex-FIC", pct(summary.top100_share_pl_ex_fic, 1)],
    ["PL do Top 100 + 2", moneyScale(summary.top100_plus2_pl_brl)],
    ["Participação do Top 100 + 2", pct(summary.top100_plus2_share_pl_ex_fic, 1)],
    ["Middle Market", "O status confirmado exige porte documentado. Menção PME/Middle Market aparece como rótulo documental com porte N/D."],
    ["Indício corporativo", "CCB, capital de giro, nota comercial, recebível comercial, risco sacado ou fornecedor; porte do tomador permanece N/D."],
    ["Hipótese de substituição bancária", "A base mostra diversificação de canais. A substituição de crédito bancário exige série casada por devedor e não é concluída neste arquivo."],
  ];
  readme.getRange("A4:B11").values = notes;
  readme.getRange("A4:A11").format.font = { name: "Arial", size: 10, bold: true, color: C.charcoal };
  readme.getRange("B4:B11").format.font = { name: "Arial", size: 10, color: C.charcoal };
  readme.getRange("A4:B11").format.wrapText = true;
  readme.getRange("A4:B11").format.rowHeightPx = 48;
  applyColumnWidths(readme, [180, 720, 80, 80, 80, 80, 80, 80], 9);

  const sheet = workbook.worksheets.add("Top 100 FIDCs");
  setHeaderBand(
    sheet,
    "Top 100 + 2 FIDCs · partes, lastro, estrutura e taxonomias",
    "Ranking por PL ex-FIC em jun/26, com duas inclusões 2026 explicitamente identificadas. Lacunas permanecem N/D; perfis de devedor não são convertidos em nomes de sacados.",
    TOP100_EXPORT_COLUMNS.map((column) => column.header),
    rows.length,
    { freezeColumns: 4, wrapText: true, bodyFontSize: 8.5 },
  );
  await writePortfolioRows(sheet, 4, TOP100_EXPORT_COLUMNS, rows);
  applyColumnWidths(sheet, TOP100_EXPORT_COLUMNS.map((column) => column.width), rows.length);
  TOP100_EXPORT_COLUMNS.forEach((column, index) => {
    if (!column.format) return;
    const letter = columnLetter(index);
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.numberFormat = column.format;
    sheet.getRange(`${letter}5:${letter}${rows.length + 4}`).format.horizontalAlignment = "right";
  });
  sheet.getRange(`A5:${columnLetter(TOP100_EXPORT_COLUMNS.length - 1)}${rows.length + 4}`).format.rowHeightPx = 48;
  return workbook;
}

async function buildPortfolioWorkbook(payload) {
  const carteira = payload.portfolio_export_carteira_101 || [];
  const cases = payload.portfolio_export_cases_99 || [];
  const flagships = payload.portfolio_export_flagships || [];
  const coverage = payload.portfolio_export_coverage || [];
  const gaps = payload.portfolio_export_gaps || [];
  const priceEvidence = payload.portfolio_export_price_evidence || [];
  const documentAudit = payload.carteira_101_document_audit || [];
  const documentCoverage = payload.carteira_101_document_coverage || [];
  const documentEvidence = payload.carteira_101_document_evidence || [];
  const documentCheckpoint = payload.carteira_101_document_checkpoint || [];
  const payloadDictionary = payload.portfolio_export_dictionary || [];
  if (carteira.length !== 101) {
    throw new Error(`Export Carteira 101 deveria conter 101 linhas; contém ${carteira.length}.`);
  }
  if (cases.length !== 99) {
    throw new Error(`Export dos casos deveria conter 99 linhas; contém ${cases.length}.`);
  }
  if (flagships.length !== 47) {
    throw new Error(`Export Flagships deveria conter 47 linhas; contém ${flagships.length}.`);
  }
  if (!coverage.length || !gaps.length) {
    throw new Error("Export Carteira 101 + Flagships sem cobertura ou tabela de lacunas.");
  }
  if (!priceEvidence.length) {
    throw new Error("Export Carteira 101 + Flagships sem evidência de preço unitário por cota.");
  }
  if (documentAudit.length !== 101 || documentCheckpoint.length !== 101) {
    throw new Error(
      `Varredura documental deveria conter 101 CNPJs no audit e no checkpoint; contém ${documentAudit.length} e ${documentCheckpoint.length}.`,
    );
  }
  if (!documentCoverage.length || !documentEvidence.length || !payloadDictionary.length) {
    throw new Error("Export Carteira 101 + Flagships sem cobertura, evidências documentais ou dicionário do payload.");
  }
  const workbook = Workbook.create();
  addPortfolioReadmeSheet(workbook, payload);
  await addPortfolioDataSheet(
    workbook,
    "Carteira 101",
    carteira,
    "101 CNPJs na ordem da base fornecida. Campos estruturais usam a curadoria documental e o dataframe compartilhado; exceções levam * e descrição por linha.",
  );
  await addPortfolioDataSheet(
    workbook,
    "Casos 99",
    cases,
    "99 CNPJs no universo operacional validável. Os dois CNPJs fora desta visão permanecem na aba Carteira 101, com identidade/perímetro N/D documentados.",
  );
  await addPortfolioEditableNamesSheet(workbook, cases);
  await addPortfolioDataSheet(
    workbook,
    "Flagships",
    flagships,
    "47 CNPJs flagship. Folga e capacidade aparecem somente quando a ausência de mezanino ou equivalência de tranche está comprovada.",
  );
  await addPortfolioCoverageAndGapsSheet(workbook, payload);
  await addPortfolioDictionarySheet(workbook);
  await addPortfolioManualSourcesSheet(workbook, payload);
  await addPortfolioPriceSheet(workbook, payload);
  await addPortfolioDocumentAuditSheet(workbook, payload);
  await addPortfolioDocumentEvidenceSheet(workbook, payload);
  await addPortfolioDocumentCoverageSheet(workbook, payload);
  await addPortfolioPayloadDictionarySheet(workbook, payload);
  return workbook;
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
  await addStructuralRiskSheets(workbook, payload);
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
  await addEmissionRemunerationEvidenceSheet(workbook, payload);
  await addEmissionFieldCoverageSheets(workbook, payload);
  await addConclusionsSheet(workbook, payload);
  await addAtlanticoSheet(workbook, payload);
  await addAtlanticoHistorySheet(workbook, payload);
  await addCedenteAuditSheets(workbook, payload);
  await addTaxonomyAuditSheets(workbook, payload);
  await addTaxonomyImpactSheet(workbook, payload);
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
      ["Auditoria emissões", "A1:AA28"],
      ["Remuneração-alvo", "A1:P28"],
      ["Cobertura emissões", "A1:P44"],
      ["Curadoria perfis", "A1:M24"],
      ["Validação emissões", "A1:U25"],
      ["Emissões por categoria", "A1:N12"],
      ["Público-alvo ofertas", "A1:J24"],
      ["Principais conclusões", "A1:E30"],
      ["Curadoria Atlântico", "A1:D36"],
      ["Série Atlântico", "A1:M12"],
      ["Cedentes · Leia-me", "A1:H20"],
      ["Cedentes · Top 437", "A1:AS20"],
      ["Cedentes · Cobertura", "A1:Y20"],
      ["Taxonomia · de-para", "A1:M20"],
      ["Taxonomia · Outros", "A1:P20"],
      ["Taxonomia · impacto", "A1:R64"],
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

async function exportPortfolioWorkbook(workbook) {
  if (!SKIP_QA) {
    const previewSheets = [
      ["Leia-me", "A1:H18"],
      ["Carteira 101", "A1:AV18"],
      ["Flagships", "A1:AV18"],
      ["Cobertura e lacunas", "A1:H34"],
      ["Dicionário", "A1:F24"],
      ["Fontes manuais", "A1:S20"],
    ];
    const workbookQa = path.join(QA_DIR, "carteira_101_flagships");
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
  await fs.mkdir(path.dirname(OUTPUT_PORTFOLIO_XLSX), { recursive: true });
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(OUTPUT_PORTFOLIO_XLSX);
  const patcherName = "patch_portfolio_workbook_charts.py";
  const patcher = [
    process.env.FIDC_PORTFOLIO_CHART_PATCHER,
    path.join(path.dirname(__filename), patcherName),
    path.join(ROOT, "scripts", patcherName),
  ].find((candidate) => candidate && existsSync(candidate));
  if (!patcher) {
    throw new Error(`Patcher dos gráficos da Carteira 101 não localizado: ${patcherName}`);
  }
  const patched = spawnSync(process.env.FIDC_PYTHON || "python3", [patcher, OUTPUT_PORTFOLIO_XLSX], {
    encoding: "utf8",
  });
  if (patched.status !== 0) {
    throw new Error(`Falha ao criar gráficos nativos da Carteira 101: ${patched.stderr || patched.stdout}`);
  }
}

async function exportTop100Workbook(workbook) {
  await fs.mkdir(path.dirname(OUTPUT_TOP100_XLSX), { recursive: true });
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(OUTPUT_TOP100_XLSX);
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
    const portfolioWorkbook = await buildPortfolioWorkbook(payload);
    await exportPortfolioWorkbook(portfolioWorkbook);
    const top100Workbook = await buildTop100Workbook(payload);
    await exportTop100Workbook(top100Workbook);
  }
  if (
    process.env.FIDC_WRITE_MANIFEST === "1" ||
    (process.env.FIDC_SKIP_PRESENTATION !== "1" &&
      process.env.FIDC_SKIP_WORKBOOK !== "1")
  ) {
    await writeExportBundleManifest(payload, payloadRaw);
  }
  process.stdout.write(`${OUTPUT_PPTX}\n${OUTPUT_XLSX}\n${OUTPUT_PORTFOLIO_XLSX}\n${OUTPUT_TOP100_XLSX}\n${OUTPUT_HTML}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
