#!/usr/bin/env node

import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
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
  (existsSync(path.join(localNodeModules, "sharp/package.json"))
    ? localNodeModules
    : bundledNodeModules);
const require = createRequire(path.join(NODE_MODULES, "package.json"));
const sharp = require("sharp");

const DEFAULT_PAYLOAD = path.join(
  ROOT,
  "data/industry_study/generated_revision/artifact_payload.json",
);
const DEFAULT_OUTPUT_DIR = path.join(ROOT, "outputs/provider_flow_assets");

const COLORS = {
  background: "#FFFFFF",
  foreground: "#151515",
  muted: "#73787D",
  faint: "#D7DADD",
  pale: "#F5F6F7",
  orange: "#EC7000",
  selected: "#FF5500",
  qi: "#2456D6",
  btg: "#1D4080",
  oliveira: "#7A1F3D",
  bb: "#D6A800",
  green: "#73C6A1",
  gray1: "#30353A",
  gray2: "#5B6065",
  gray3: "#8D9399",
  gray4: "#BEC2C5",
};

const GRAYS = [COLORS.gray1, "#454A4F", COLORS.gray2, COLORS.muted, COLORS.gray3, "#A7ACB0", COLORS.gray4];

function argsFrom(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const value = argv[index + 1];
    if (value && !value.startsWith("--")) {
      args[key] = value;
      index += 1;
    } else {
      args[key] = true;
    }
  }
  return args;
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function truthy(value) {
  if (typeof value === "boolean") return value;
  return ["1", "true", "yes", "sim"].includes(String(value || "").trim().toLowerCase());
}

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function compactProvider(value) {
  const text = String(value || "N/D").trim();
  const key = normalize(text);
  if (key.includes("planner")) return "Planner";
  if (key.includes("banco master") || key === "master corretora") return "Banco Master";
  if (key.startsWith("id corretora")) return "ID";
  if (key.includes("oslo")) return "Oslo Capital";
  if (key.includes("limine")) return "Limine Trust";
  if (key.includes("qore")) return "Qore";
  if (key.includes("brl trust")) return "BRL Trust";
  if (key.includes("qi tech")) return "QI Tech";
  if (key.includes("oliveira trust")) return "Oliveira Trust";
  if (key.includes("cbsf") && key.includes("reag")) return "CBSF / Reag Trust";
  if (key.includes("cbsf") || key.includes("reag")) return key.includes("cbsf") ? "CBSF" : "REAG";
  if (key.includes("bradesco") || key.startsWith("bem ")) return "Bradesco";
  if (key.includes("daycoval")) return "Daycoval";
  return text
    .replace(/\bDISTRIBUIDORA DE T[IÍ]TULOS E VALORES MOBILI[AÁ]RIOS\b/gi, "")
    .replace(/\bCORRETORA DE VALORES\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function providerColor(value) {
  const key = normalize(value);
  if (key.includes("qi tech")) return COLORS.qi;
  if (key.includes("btg")) return COLORS.btg;
  if (key.includes("oliveira trust")) return COLORS.oliveira;
  if (key.includes("banco do brasil")) return COLORS.bb;
  if (key.includes("itau")) return COLORS.selected;
  if (key.includes("cbsf") || key.includes("reag")) return COLORS.green;
  if (key.includes("saida") || key.includes("sem reporte")) return COLORS.gray4;
  let hash = 0;
  for (const character of key) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return GRAYS[hash % GRAYS.length];
}

function formatCnpj(value) {
  const digits = String(value || "").replace(/\D/g, "").padStart(14, "0").slice(-14);
  if (!digits.replace(/0/g, "")) return "";
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
}

function compactFund(value) {
  return String(value || "N/D")
    .replace(/FUNDO DE INVESTIMENTO EM DIREITOS CREDIT[ÓO]RIOS/gi, "FIDC")
    .replace(/FUNDO DE INVESTIMENTO EM DIREITO CREDIT[ÓO]RIO/gi, "FIDC")
    .replace(/\s+/g, " ")
    .trim();
}

function viewModels(payload) {
  const adminDetail = (payload.provider_transition_detail || [])
    .filter((row) => truthy(row.mudou_grupo))
    .map((row) => ({
      fund: compactFund(row.denominacao || row.denominacao_destino || row.denominacao_origem),
      cnpj: row.cnpj_fundo_formatado || formatCnpj(row.cnpj_fundo),
      source: compactProvider(row.grupo_origem),
      target: compactProvider(row.grupo_destino),
      pl0: number(row.pl_origem_brl),
      pl1: number(row.pl_destino_brl),
      flow: number(row.pl_comparavel_brl),
      fundosnetUrl: row.fundosnet_url || "",
      sourceUrl: row.fonte_origem_url || "",
      targetUrl: row.fonte_destino_url || "",
    }))
    .sort((a, b) => b.flow - a.flow);
  const adminLinks = (payload.provider_transition_links || [])
    .filter((row) => String(row.papel || "administrador") === "administrador")
    .map((row) => ({
      source: compactProvider(row.grupo_origem),
      target: compactProvider(row.grupo_destino),
      funds: Math.round(number(row.fundos)),
      value: number(row.pl_comparavel_brl || row.pl_flow_brl),
      origin: number(row.pl_origem_brl),
      current: number(row.pl_destino_brl),
      shareUniverse: number(row.share_pl_comparavel),
    }))
    .filter((row) => row.source !== row.target && row.value > 0)
    .sort((a, b) => b.value - a.value);
  const adminSummary = payload.provider_transition_summary || {};

  const reagDetail = (payload.reag_admin_detail || []).map((row) => {
    const status = String(row.status_destino || "");
    const active = status.startsWith("continuante");
    const observed = compactProvider(row.admin_destino_grupo || row.admin_destino_grupo_observado);
    const target = status === "saida_sem_reporte"
      ? "Sem reporte"
      : status === "saida_pl_nao_positivo"
        ? "PL não positivo"
        : observed;
    return {
      fund: compactFund(row.denominacao || row.denominacao_origem),
      cnpj: row.cnpj_fundo_formatado || formatCnpj(row.cnpj_fundo),
      source: "CBSF / Reag Trust",
      target,
      status: active ? "Continuante" : "Saída / sem reporte",
      pl0: number(row.pl_origem_brl),
      pl1: number(row.pl_destino_brl || row.pl_destino_observado_brl),
      flow: number(row.pl_origem_brl),
      manager: compactProvider(row.gestor_destino_grupo_observado || row.gestor_destino_nome_observado),
      custodian: compactProvider(row.custodiante_destino_grupo_observado || row.custodiante_destino_nome_observado),
      fundosnetUrl: row.fundosnet_url || "",
      sourceUrl: row.fonte_origem_url || "",
      targetUrl: row.fonte_destino_url || "",
    };
  }).sort((a, b) => b.flow - a.flow);
  const reagLinkMap = new Map();
  for (const row of reagDetail) {
    const key = `${row.source}|||${row.target}`;
    const item = reagLinkMap.get(key) || {
      source: row.source,
      target: row.target,
      funds: 0,
      value: 0,
      origin: 0,
      current: 0,
    };
    item.funds += 1;
    item.value += row.flow;
    item.origin += row.pl0;
    item.current += row.pl1;
    reagLinkMap.set(key, item);
  }
  const reagLinks = [...reagLinkMap.values()].sort((a, b) => b.value - a.value);
  const reagSummary = payload.reag_admin_summary || {};

  return {
    admin: {
      id: "admin",
      eyebrow: "DEZ/24 → DEZ/25 · ADMINISTRAÇÃO",
      leftLabel: "ADMINISTRADOR · DEZ/24",
      rightLabel: "ADMINISTRADOR · DEZ/25",
      note: "PL comparável = menor PL do fundo entre as duas datas.",
      summary: {
        primary: number(adminSummary.changed_comparable_pl_brl),
        primaryLabel: "PL que mudou de grupo",
        secondary: Math.round(number(adminSummary.changed_funds)),
        secondaryLabel: "FIDCs com troca",
        tertiary: number(adminSummary.changed_share),
        tertiaryLabel: "do estoque comparável",
      },
      links: adminLinks,
      details: adminDetail,
    },
    reag: {
      id: "reag",
      eyebrow: "CBSF / REAG · DEZ/25 → MAI/26",
      leftLabel: "COORTE · DEZ/25",
      rightLabel: "DESTINO · MAI/26",
      note: "Largura = PL de dez/25. Gestão e custódia são fotografia vigente de mai/26, não uma transição histórica.",
      summary: {
        primary: number(reagSummary.pl_origin_brl),
        primaryLabel: "PL inicial da coorte",
        secondary: number(reagSummary.migrated_pl_current_brl),
        secondaryLabel: "PL atual migrado",
        tertiary: number(reagSummary.exited_pl_origin_brl),
        tertiaryLabel: "PL de saídas",
      },
      links: reagLinks,
      details: reagDetail,
    },
  };
}

function assertClose(actual, expected, label, tolerance = 1) {
  if (Math.abs(number(actual) - number(expected)) > tolerance) {
    throw new Error(`${label}: ${actual} != ${expected}`);
  }
}

function validateViews(data) {
  const sum = (rows, key) => rows.reduce((total, row) => total + number(row[key]), 0);
  const unique = (rows) => new Set(rows.map((row) => row.cnpj)).size;
  assertClose(sum(data.admin.links, "value"), data.admin.summary.primary, "PL dos links de administração");
  assertClose(sum(data.admin.details, "flow"), data.admin.summary.primary, "PL do detalhe de administração");
  if (data.admin.details.length !== data.admin.summary.secondary || unique(data.admin.details) !== data.admin.details.length) {
    throw new Error("Contagem/CNPJ do detalhe de administração não reconcilia");
  }
  assertClose(sum(data.reag.links, "value"), data.reag.summary.primary, "PL dos links CBSF/REAG");
  assertClose(sum(data.reag.details, "flow"), data.reag.summary.primary, "PL do detalhe CBSF/REAG");
  if (unique(data.reag.details) !== data.reag.details.length) throw new Error("CNPJ duplicado no detalhe CBSF/REAG");
}

function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function money(value, digits = 1) {
  const amount = number(value);
  if (Math.abs(amount) < 1e8) {
    return `R$ ${(amount / 1e6).toLocaleString("pt-BR", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    })} mi`;
  }
  return `R$ ${(amount / 1e9).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} bi`;
}

function percent(value, digits = 1) {
  return `${(number(value) * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

function fundsLabel(value) {
  const count = Math.round(number(value));
  return `${count.toLocaleString("pt-BR")} ${count === 1 ? "fundo" : "fundos"}`;
}

function nodeOrdering(links) {
  const sourceTotals = new Map();
  const targetTotals = new Map();
  for (const link of links) {
    sourceTotals.set(link.source, (sourceTotals.get(link.source) || 0) + link.value);
    targetTotals.set(link.target, (targetTotals.get(link.target) || 0) + link.value);
  }
  const sources = [...sourceTotals].sort((a, b) => b[1] - a[1]);
  const sourceRank = new Map(sources.map(([name], index) => [name, index]));
  const targetWeight = new Map();
  for (const link of links) {
    const item = targetWeight.get(link.target) || { weighted: 0, total: 0 };
    item.weighted += (sourceRank.get(link.source) || 0) * link.value;
    item.total += link.value;
    targetWeight.set(link.target, item);
  }
  const targets = [...targetTotals].sort((a, b) => {
    const left = targetWeight.get(a[0]);
    const right = targetWeight.get(b[0]);
    const leftRank = left?.total ? left.weighted / left.total : 0;
    const rightRank = right?.total ? right.weighted / right.total : 0;
    return leftRank - rightRank || b[1] - a[1];
  });
  return { sources, targets };
}

function layoutColumn(items, x, top, height, padding) {
  const total = items.reduce((sum, [, value]) => sum + value, 0) || 1;
  const effectivePadding = items.length > 1 ? Math.min(padding, height / (items.length * 2)) : 0;
  const usable = Math.max(40, height - effectivePadding * Math.max(items.length - 1, 0));
  const scale = usable / total;
  const nodes = new Map();
  let cursor = top;
  for (const [name, value] of items) {
    const nodeHeight = Math.max(1.5, value * scale);
    nodes.set(name, { name, value, x, y: cursor, height: nodeHeight, scale });
    cursor += nodeHeight + effectivePadding;
  }
  return { nodes, scale };
}

function layoutSankey(view, topN = 10, width = 1280, height = 620) {
  const links = view.links.slice(0, topN === "all" ? view.links.length : Number(topN));
  const { sources, targets } = nodeOrdering(links);
  const plotTop = 118;
  const plotHeight = height - 158;
  const leftX = 248;
  const rightX = width - 248;
  const left = layoutColumn(sources, leftX, plotTop, plotHeight, view.id === "admin" ? 13 : 18);
  const right = layoutColumn(targets, rightX, plotTop, plotHeight, view.id === "admin" ? 10 : 18);
  const scale = Math.min(left.scale, right.scale);
  for (const node of left.nodes.values()) node.height = Math.max(1.5, node.value * scale);
  for (const node of right.nodes.values()) node.height = Math.max(1.5, node.value * scale);
  const restack = (nodes, order) => {
    const padding = order.length > 1
      ? Math.max(4, (plotHeight - order.reduce((sum, [, value]) => sum + Math.max(1.5, value * scale), 0)) / (order.length - 1))
      : 0;
    let cursor = plotTop;
    for (const [name] of order) {
      const node = nodes.get(name);
      node.y = cursor;
      cursor += node.height + padding;
    }
  };
  restack(left.nodes, sources);
  restack(right.nodes, targets);

  const sourceOffsets = new Map([...left.nodes].map(([name]) => [name, 0]));
  const targetOffsets = new Map([...right.nodes].map(([name]) => [name, 0]));
  const targetOrder = new Map(targets.map(([name], index) => [name, index]));
  const sourceOrder = new Map(sources.map(([name], index) => [name, index]));
  const sourceSorted = [...links].sort((a, b) =>
    (sourceOrder.get(a.source) || 0) - (sourceOrder.get(b.source) || 0) ||
    (targetOrder.get(a.target) || 0) - (targetOrder.get(b.target) || 0) ||
    b.value - a.value
  );
  const targetSorted = [...links].sort((a, b) =>
    (targetOrder.get(a.target) || 0) - (targetOrder.get(b.target) || 0) ||
    (sourceOrder.get(a.source) || 0) - (sourceOrder.get(b.source) || 0) ||
    b.value - a.value
  );
  const startByKey = new Map();
  for (const link of sourceSorted) {
    const key = `${link.source}|||${link.target}`;
    const offset = sourceOffsets.get(link.source) || 0;
    const band = Math.max(1.2, link.value * scale);
    const node = left.nodes.get(link.source);
    startByKey.set(key, { y0: node.y + offset, y1: node.y + offset + band, band });
    sourceOffsets.set(link.source, offset + band);
  }
  const endByKey = new Map();
  for (const link of targetSorted) {
    const key = `${link.source}|||${link.target}`;
    const offset = targetOffsets.get(link.target) || 0;
    const band = Math.max(1.2, link.value * scale);
    const node = right.nodes.get(link.target);
    endByKey.set(key, { y0: node.y + offset, y1: node.y + offset + band, band });
    targetOffsets.set(link.target, offset + band);
  }
  const laidLinks = links.map((link, index) => ({
    ...link,
    index,
    key: `${link.source}|||${link.target}`,
    ...startByKey.get(`${link.source}|||${link.target}`),
    end: endByKey.get(`${link.source}|||${link.target}`),
  }));
  return { links: laidLinks, left: left.nodes, right: right.nodes, leftX, rightX, width, height };
}

function ribbonPath(layout, link) {
  const x0 = layout.leftX + 9;
  const x1 = layout.rightX;
  const curve = (x1 - x0) * 0.47;
  return [
    `M ${x0} ${link.y0}`,
    `C ${x0 + curve} ${link.y0}, ${x1 - curve} ${link.end.y0}, ${x1} ${link.end.y0}`,
    `L ${x1} ${link.end.y1}`,
    `C ${x1 - curve} ${link.end.y1}, ${x0 + curve} ${link.y1}, ${x0} ${link.y1}`,
    "Z",
  ].join(" ");
}

function labelPositions(nodes, minY = 134, maxY = 566, minGap = 37) {
  const items = [...nodes.values()]
    .map((node) => ({ name: node.name, anchor: node.y + node.height / 2, y: node.y + node.height / 2 }))
    .sort((a, b) => a.anchor - b.anchor);
  for (let index = 0; index < items.length; index += 1) {
    items[index].y = Math.max(items[index].anchor, index ? items[index - 1].y + minGap : minY);
  }
  if (items.length && items.at(-1).y > maxY) {
    items.at(-1).y = maxY;
    for (let index = items.length - 2; index >= 0; index -= 1) {
      items[index].y = Math.min(items[index].y, items[index + 1].y - minGap);
    }
  }
  if (items.length && items[0].y < minY) {
    const shift = minY - items[0].y;
    for (const item of items) item.y += shift;
  }
  return new Map(items.map((item) => [item.name, item]));
}

function staticSvg(view, topN, options = {}) {
  const width = options.width || 1280;
  const height = options.height || 620;
  const layout = layoutSankey(view, topN, width, height);
  const shownValue = layout.links.reduce((sum, link) => sum + link.value, 0);
  const changedTotal = view.links.reduce((sum, link) => sum + link.value, 0);
  const metricValue = view.id === "admin" ? money(shownValue) : money(view.summary.primary);
  const metricLabel = view.id === "admin" ? `nos ${topN} maiores fluxos` : view.summary.primaryLabel;
  const secondaryValue = view.id === "admin"
    ? percent(shownValue / Math.max(changedTotal, 1), 1)
    : money(view.summary.secondary);
  const secondaryLabel = view.id === "admin" ? "do PL que migrou" : view.summary.secondaryLabel;
  const tertiaryValue = view.id === "admin"
    ? `${layout.links.reduce((sum, link) => sum + link.funds, 0).toLocaleString("pt-BR")}`
    : money(view.summary.tertiary);
  const tertiaryLabel = view.id === "admin" ? "fundos nesses fluxos" : view.summary.tertiaryLabel;
  const leftLabels = labelPositions(layout.left, 136, height - 53, 37);
  const rightLabels = labelPositions(layout.right, 136, height - 53, 37);
  const remainingLinks = Math.max(0, view.links.length - layout.links.length);
  const remainingValue = Math.max(0, changedTotal - shownValue);
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeXml(view.eyebrow)}">`,
    `<rect width="${width}" height="${height}" fill="${COLORS.background}"/>`,
    `<style>text{font-family:Arial,sans-serif;fill:${COLORS.foreground}}.muted{fill:${COLORS.muted}}.halo{paint-order:stroke;stroke:${COLORS.background};stroke-width:6px;stroke-linejoin:round}</style>`,
    `<text x="40" y="32" font-size="16" font-weight="700" fill="${COLORS.orange}">${escapeXml(view.eyebrow)}</text>`,
    `<text x="40" y="63" font-size="27" font-weight="700">${escapeXml(metricValue)}</text>`,
    `<text x="40" y="85" font-size="13" class="muted">${escapeXml(metricLabel)}</text>`,
    `<text x="390" y="63" font-size="27" font-weight="700">${escapeXml(secondaryValue)}</text>`,
    `<text x="390" y="85" font-size="13" class="muted">${escapeXml(secondaryLabel)}</text>`,
    `<text x="735" y="63" font-size="27" font-weight="700">${escapeXml(tertiaryValue)}</text>`,
    `<text x="735" y="85" font-size="13" class="muted">${escapeXml(tertiaryLabel)}</text>`,
    `<text x="40" y="111" font-size="12" font-weight="700" class="muted">${escapeXml(view.leftLabel)}</text>`,
    `<text x="${width - 40}" y="111" text-anchor="end" font-size="12" font-weight="700" class="muted">${escapeXml(view.rightLabel)}</text>`,
  ];
  for (const link of layout.links) {
    parts.push(`<path d="${ribbonPath(layout, link)}" fill="${providerColor(link.target)}" fill-opacity="0.46"/>`);
  }
  for (const [name, node] of layout.left) {
    const label = leftLabels.get(name);
    parts.push(`<rect x="${layout.leftX}" y="${node.y}" width="9" height="${node.height}" rx="2" fill="${providerColor(name)}"/>`);
    if (Math.abs(label.y - label.anchor) > 3) parts.push(`<path d="M ${layout.leftX} ${label.anchor} L ${layout.leftX - 11} ${label.y}" fill="none" stroke="${COLORS.faint}" stroke-width="1"/>`);
    parts.push(`<text x="${layout.leftX - 15}" y="${label.y - 2}" text-anchor="end" font-size="15" font-weight="700">${escapeXml(compactProvider(name))}</text>`);
    parts.push(`<text x="${layout.leftX - 15}" y="${label.y + 17}" text-anchor="end" font-size="12" class="muted">${escapeXml(money(node.value))}</text>`);
  }
  for (const [name, node] of layout.right) {
    const label = rightLabels.get(name);
    parts.push(`<rect x="${layout.rightX}" y="${node.y}" width="9" height="${node.height}" rx="2" fill="${providerColor(name)}"/>`);
    if (Math.abs(label.y - label.anchor) > 3) parts.push(`<path d="M ${layout.rightX + 9} ${label.anchor} L ${layout.rightX + 11} ${label.y}" fill="none" stroke="${COLORS.faint}" stroke-width="1"/>`);
    parts.push(`<text x="${layout.rightX + 15}" y="${label.y - 2}" font-size="15" font-weight="700">${escapeXml(compactProvider(name))}</text>`);
    parts.push(`<text x="${layout.rightX + 15}" y="${label.y + 17}" font-size="12" class="muted">${escapeXml(money(node.value))}</text>`);
  }
  for (const link of layout.links.slice(0, 1)) {
    const y = ((link.y0 + link.y1) / 2 + (link.end.y0 + link.end.y1) / 2) / 2;
    parts.push(`<text x="${width / 2}" y="${y + 4}" text-anchor="middle" font-size="12" font-weight="700" class="halo">${escapeXml(`${fundsLabel(link.funds)} · ${money(link.value)}`)}</text>`);
  }
  const remainder = view.id === "admin" && remainingLinks
    ? `${view.note} Demais ${remainingLinks} rotas: ${money(remainingValue)}.`
    : view.note;
  parts.push(`<text x="40" y="${height - 14}" font-size="11" class="muted">${escapeXml(remainder)}</text>`);
  parts.push("</svg>");
  return parts.join("");
}

function browserApp(DATA) {
  const root = document.getElementById("provider-flow-explorer");
  const chart = root.querySelector("[data-chart]");
  const tooltip = root.querySelector("[data-tooltip-box]");
  const caption = root.querySelector("[data-detail-caption]");
  const tbody = root.querySelector("tbody");
  const pager = root.querySelector("[data-pager]");
  const search = root.querySelector("input[type=search]");
  const topSelect = root.querySelector("select");
  let state = { view: "admin", topN: 10, selected: null, query: "", page: 0 };
  const n = v => Number.isFinite(Number(v)) ? Number(v) : 0;
  const norm = v => String(v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const money = v => Math.abs(n(v)) < 1e8
    ? "R$ " + (n(v) / 1e6).toLocaleString("pt-BR", {minimumFractionDigits: 0, maximumFractionDigits: 1}) + " mi"
    : "R$ " + (n(v) / 1e9).toLocaleString("pt-BR", {minimumFractionDigits: 1, maximumFractionDigits: 1}) + " bi";
  const pct = v => (n(v) * 100).toLocaleString("pt-BR", {minimumFractionDigits: 1, maximumFractionDigits: 1}) + "%";
  const funds = v => Math.round(n(v)).toLocaleString("pt-BR") + " " + (Math.round(n(v))===1?"fundo":"fundos");
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const color = name => {
    const key = norm(name);
    if (key.includes("qi tech")) return "var(--flow-qi)";
    if (key.includes("btg")) return "var(--flow-btg)";
    if (key.includes("oliveira")) return "var(--flow-oliveira)";
    if (key.includes("cbsf") || key.includes("reag")) return "var(--flow-green)";
    if (key.includes("saida") || key.includes("sem reporte")) return "var(--flow-faint)";
    const palette = ["var(--flow-gray-1)","var(--flow-gray-2)","var(--flow-gray-3)","var(--flow-gray-4)"];
    let hash = 0; for (const c of key) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
    return palette[hash % palette.length];
  };
  const ordering = links => {
    const sm = new Map(), tm = new Map();
    links.forEach(l => { sm.set(l.source,(sm.get(l.source)||0)+l.value); tm.set(l.target,(tm.get(l.target)||0)+l.value); });
    const sources = [...sm].sort((a,b)=>b[1]-a[1]);
    const rank = new Map(sources.map(([x],i)=>[x,i]));
    const w = new Map();
    links.forEach(l => { const x=w.get(l.target)||{w:0,t:0}; x.w+=(rank.get(l.source)||0)*l.value; x.t+=l.value; w.set(l.target,x); });
    const targets=[...tm].sort((a,b)=>{const x=w.get(a[0]),y=w.get(b[0]);return (x.w/x.t)-(y.w/y.t)||b[1]-a[1]});
    return {sources,targets};
  };
  const column = (items,x,top,height,padding) => {
    const total=items.reduce((s,r)=>s+r[1],0)||1; const pad=items.length>1?Math.min(padding,height/(items.length*2)):0;
    const scale=Math.max(40,height-pad*Math.max(items.length-1,0))/total; const nodes=new Map(); let y=top;
    items.forEach(([name,value])=>{const h=Math.max(1.5,value*scale);nodes.set(name,{name,value,x,y,height:h});y+=h+pad}); return {nodes,scale};
  };
  const layout = (view, topN) => {
    const links=topN==="all"?view.links:topN==="250m"?view.links.filter(l=>l.value>=250e6):view.links.slice(0,Number(topN)); const {sources,targets}=ordering(links);
    const W=1280,H=Math.max(620,Math.max(sources.length,targets.length)*39+170),top=118,ph=H-158,lx=248,rx=1032; const L=column(sources,lx,top,ph,view.id==="admin"?13:18); const R=column(targets,rx,top,ph,view.id==="admin"?10:18);
    const scale=Math.min(L.scale,R.scale); const restack=(nodes,items)=>{const total=items.reduce((s,r)=>s+Math.max(1.5,r[1]*scale),0);const pad=items.length>1?Math.max(4,(ph-total)/(items.length-1)):0;let y=top;items.forEach(([name,value])=>{const q=nodes.get(name);q.height=Math.max(1.5,value*scale);q.y=y;y+=q.height+pad})}; restack(L.nodes,sources);restack(R.nodes,targets);
    const sr=new Map(sources.map(([x],i)=>[x,i])),tr=new Map(targets.map(([x],i)=>[x,i])),so=new Map(sources.map(([x])=>[x,0])),to=new Map(targets.map(([x])=>[x,0])),starts=new Map(),ends=new Map();
    [...links].sort((a,b)=>(sr.get(a.source)||0)-(sr.get(b.source)||0)||(tr.get(a.target)||0)-(tr.get(b.target)||0)||b.value-a.value).forEach(l=>{const k=l.source+"|||"+l.target,o=so.get(l.source)||0,band=Math.max(1.2,l.value*scale),q=L.nodes.get(l.source);starts.set(k,{y0:q.y+o,y1:q.y+o+band});so.set(l.source,o+band)});
    [...links].sort((a,b)=>(tr.get(a.target)||0)-(tr.get(b.target)||0)||(sr.get(a.source)||0)-(sr.get(b.source)||0)||b.value-a.value).forEach(l=>{const k=l.source+"|||"+l.target,o=to.get(l.target)||0,band=Math.max(1.2,l.value*scale),q=R.nodes.get(l.target);ends.set(k,{y0:q.y+o,y1:q.y+o+band});to.set(l.target,o+band)});
    return {links:links.map((l,i)=>({...l,index:i,key:l.source+"|||"+l.target,...starts.get(l.source+"|||"+l.target),end:ends.get(l.source+"|||"+l.target)})),left:L.nodes,right:R.nodes,lx,rx,W,H};
  };
  const ribbon = (g,l) => {const x0=g.lx+9,x1=g.rx,c=(x1-x0)*.47;return `M ${x0} ${l.y0} C ${x0+c} ${l.y0}, ${x1-c} ${l.end.y0}, ${x1} ${l.end.y0} L ${x1} ${l.end.y1} C ${x1-c} ${l.end.y1}, ${x0+c} ${l.y1}, ${x0} ${l.y1} Z`};
  const labels = (map,H) => {const rows=[...map.values()].map(q=>({name:q.name,anchor:q.y+q.height/2,y:q.y+q.height/2})).sort((a,b)=>a.anchor-b.anchor),min=136,max=H-53,gap=37;rows.forEach((r,i)=>r.y=Math.max(r.anchor,i?rows[i-1].y+gap:min));if(rows.length&&rows.at(-1).y>max){rows.at(-1).y=max;for(let i=rows.length-2;i>=0;i--)rows[i].y=Math.min(rows[i].y,rows[i+1].y-gap)}if(rows.length&&rows[0].y<min){const d=min-rows[0].y;rows.forEach(r=>r.y+=d)}return new Map(rows.map(r=>[r.name,r]))};
  const relevantKeys = (view,q) => {if(!q)return new Set();const out=new Set();view.details.forEach(r=>{if(norm(Object.values(r).join(" ")).includes(norm(q)))out.add(r.source+"|||"+r.target)});view.links.forEach(l=>{if(norm(l.source+" "+l.target).includes(norm(q)))out.add(l.source+"|||"+l.target)});return out};
  const renderChart = () => {
    const v=DATA[state.view],matches=relevantKeys(v,state.query),scoped=state.query?{...v,links:v.links.filter(l=>matches.has(l.source+"|||"+l.target))}:v,g=layout(scoped,state.query||state.view==="reag"?"all":state.topN); let h="";
    h+=`<svg viewBox="0 0 1280 ${g.H}" role="img" aria-label="${esc(v.eyebrow)}" style="--flow-bg:#fff;--flow-fg:#151515;--flow-muted:#73787D;--flow-border:#D7DADD;--flow-qi:#2456D6;--flow-btg:#1D4080;--flow-oliveira:#7A1F3D;--flow-green:#73C6A1;--flow-gray-1:#30353A;--flow-gray-2:#5B6065;--flow-gray-3:#8D9399;--flow-gray-4:#BEC2C5;--flow-faint:#D7DADD"><title>${esc(v.eyebrow)}</title><desc>${esc(v.note)}</desc><rect width="1280" height="${g.H}" fill="#fff"/><style>text{fill:#151515;font-family:Arial,sans-serif}.metric{font-size:27px;font-weight:700}.metric-label,.node-value,.footnote{font-size:13px;fill:#73787D}.period{font-size:12px;font-weight:700;fill:#73787D}.node-label{font-size:15px;font-weight:700}.link-label{font-size:12px;font-weight:700;paint-order:stroke;stroke:#fff;stroke-width:6px}.leader{fill:none;stroke:#D7DADD;stroke-width:1}</style>`;
    const shown=g.links.reduce((s,l)=>s+l.value,0),total=v.links.reduce((s,l)=>s+l.value,0);
    const scopeLabel=state.query?"nos fluxos encontrados":state.topN==="all"?"em todos os fluxos":state.topN==="250m"?"em rotas ≥ R$ 250 mi":"nos "+state.topN+" maiores";
    const metrics=state.view==="admin"?[[money(shown),scopeLabel],[pct(shown/Math.max(total,1)),"do PL que migrou"],[g.links.reduce((s,l)=>s+l.funds,0).toLocaleString("pt-BR"),"fundos nesses fluxos"]]:[[money(v.summary.primary),v.summary.primaryLabel],[money(v.summary.secondary),v.summary.secondaryLabel],[money(v.summary.tertiary),v.summary.tertiaryLabel]];
    metrics.forEach((m,i)=>{const x=40+i*345;h+=`<text x="${x}" y="61" class="metric">${esc(m[0])}</text><text x="${x}" y="84" class="metric-label">${esc(m[1])}</text>`});
    h+=`<text x="40" y="111" class="period">${esc(v.leftLabel)}</text><text x="1240" y="111" text-anchor="end" class="period">${esc(v.rightLabel)}</text>`;
    g.links.forEach(l=>{const active=!state.query||matches.has(l.key),selected=state.selected===l.key;h+=`<path class="flow-link${selected ? " is-selected" : ""}" data-key="${esc(l.key)}" d="${ribbon(g,l)}" fill="${color(l.target)}" style="opacity:${active?(selected ? .82 : .46):.06}"><title>${esc(l.source+" → "+l.target+" · "+money(l.value)+" · "+funds(l.funds))}</title></path>`});
    const nodes=(map,side)=>{const lm=labels(map,g.H);for(const [name,q] of map){const key=side+"|||"+name,p=lm.get(name),tx=side==="left"?q.x-15:q.x+15,ta=side==="left"?"end":"start";h+=`<g class="flow-node" data-node="${esc(key)}"><rect x="${q.x}" y="${q.y}" width="9" height="${q.height}" rx="2" fill="${color(name)}"/>${Math.abs(p.y-p.anchor)>3?`<path d="M ${side==="left"?q.x:q.x+9} ${p.anchor} L ${side==="left"?q.x-11:q.x+11} ${p.y}" class="leader"/>`:""}<text x="${tx}" y="${p.y-2}" text-anchor="${ta}" class="node-label">${esc(name)}</text><text x="${tx}" y="${p.y+17}" text-anchor="${ta}" class="node-value">${esc(money(q.value))}</text></g>`}};nodes(g.left,"left");nodes(g.right,"right");
    g.links.slice(0,1).forEach(l=>{const y=((l.y0+l.y1)/2+(l.end.y0+l.end.y1)/2)/2;h+=`<text x="640" y="${y+4}" text-anchor="middle" class="link-label">${esc(funds(l.funds)+" · "+money(l.value))}</text>`});
    const remaining=Math.max(0,v.links.length-g.links.length),remainingValue=Math.max(0,total-shown),note=state.query?g.links.length+" rota(s) associada(s) à busca; o valor da fita inclui todos os fundos da rota.":state.view==="admin"&&remaining?v.note+" Demais "+remaining+" rotas: "+money(remainingValue)+".":v.note;
    h+=`<text x="40" y="${g.H-14}" class="footnote">${esc(note)}</text></svg>`;chart.innerHTML=h;bindChart();
  };
  const filteredDetails = () => {
    const v=DATA[state.view],q=norm(state.query);let rows=v.details;
    if(state.selected){const [s,t]=state.selected.split("|||");rows=rows.filter(r=>r.source===s&&r.target===t)}
    if(q)rows=rows.filter(r=>norm(Object.values(r).join(" ")).includes(q));
    return rows;
  };
  const docs = r => `<span class="docs">${r.fundosnetUrl?`<a href="${esc(r.fundosnetUrl)}" target="_blank" rel="noreferrer">FundosNet</a>`:"—"}${r.sourceUrl?`<a href="${esc(r.sourceUrl)}" target="_blank" rel="noreferrer">CVM origem</a>`:""}${r.targetUrl?`<a href="${esc(r.targetUrl)}" target="_blank" rel="noreferrer">CVM destino</a>`:""}</span>`;
  const renderTable = () => {
    const v=DATA[state.view],rows=filteredDetails(),pages=Math.max(1,Math.ceil(rows.length/8));
    state.page=Math.min(state.page,pages-1);
    const selected=v.links.find(l=>l.source+"|||"+l.target===state.selected);
    caption.textContent=selected
      ? `${selected.source} → ${selected.target} · ${funds(selected.funds)} · ${money(selected.value)}${state.view==="admin"?` comparável | ${money(selected.origin)} → ${money(selected.current)}`:` de origem | ${selected.current?money(selected.current):"sem PL atual"}`}`
      : state.query?`${rows.length} fundos encontrados para “${state.query}”`:`${rows.length} fundos na base; selecione um fluxo ou pesquise para filtrar.`;
    const slice=rows.slice(state.page*8,state.page*8+8);
    tbody.innerHTML=slice.map(r=>state.view==="admin"
      ? `<tr><td>${esc(r.fund)}</td><td>${esc(r.cnpj)}</td><td>${esc(r.source)}</td><td>${esc(r.target)}</td><td class="num">${money(r.flow)}</td><td class="num optional">${money(r.pl0)}</td><td class="num optional">${money(r.pl1)}</td><td>${docs(r)}</td></tr>`
      : `<tr><td>${esc(r.fund)}</td><td>${esc(r.cnpj)}</td><td>${esc(r.target)}</td><td class="num">${money(r.pl0)}</td><td class="num optional">${r.pl1?money(r.pl1):"—"}</td><td class="optional">${esc(r.manager||"N/D")}</td><td class="optional">${esc(r.custodian||"N/D")}</td><td>${docs(r)}</td></tr>`
    ).join("")||`<tr><td colspan="8">Nenhum fundo encontrado.</td></tr>`;
    root.querySelector("thead").innerHTML=state.view==="admin"
      ? "<tr><th>Fundo</th><th>CNPJ</th><th>Origem</th><th>Destino</th><th>PL comparável</th><th class='optional'>PL dez/24</th><th class='optional'>PL dez/25</th><th>Fontes</th></tr>"
      : "<tr><th>Fundo</th><th>CNPJ</th><th>Destino</th><th>PL dez/25</th><th class='optional'>PL mai/26</th><th class='optional'>Gestor mai/26</th><th class='optional'>Custodiante mai/26</th><th>Fontes</th></tr>";
    pager.querySelector("span").textContent=`${rows.length?state.page+1:0} / ${rows.length?pages:0}`;
    pager.querySelector("[data-prev]").disabled=state.page<=0;pager.querySelector("[data-next]").disabled=state.page>=pages-1;
  };
  const bindChart = () => {
    chart.querySelectorAll(".flow-link").forEach(el=>{
      el.addEventListener("click",()=>{state.selected=state.selected===el.dataset.key?null:el.dataset.key;state.page=0;render()});
      el.addEventListener("mousemove",e=>{
        const l=DATA[state.view].links.find(x=>x.source+"|||"+x.target===el.dataset.key),total=DATA[state.view].summary.primary;
        tooltip.innerHTML=l?`<strong>${esc(l.source)} → ${esc(l.target)}</strong><br>${funds(l.funds)} · ${money(l.value)}${state.view==="admin"?` comparável<br>${money(l.origin)} → ${money(l.current)} · ${pct(l.value/Math.max(total,1))} do PL migrado`:` de origem<br>${l.current?money(l.current)+" em mai/26":"sem PL positivo em mai/26"}`}`:"";
        tooltip.hidden=false;const r=root.getBoundingClientRect(),t=tooltip.getBoundingClientRect();tooltip.style.left=Math.min(r.width-t.width-8,Math.max(8,e.clientX-r.left+14))+"px";tooltip.style.top=Math.max(8,e.clientY-r.top-t.height-12)+"px";
      });
      el.addEventListener("mouseleave",()=>tooltip.hidden=true)
    });
    chart.querySelectorAll(".flow-node").forEach(el=>el.addEventListener("click",()=>{const [side,name]=el.dataset.node.split("|||");const links=DATA[state.view].links.filter(l=>(side==="left"?l.source:l.target)===name);state.selected=links.length===1?links[0].source+"|||"+links[0].target:null;state.query=name;search.value=name;state.page=0;render()}));
  };
  const fileStem = () => state.view==="admin"?"fluxos_administracao_dez24_dez25":"fluxos_cbsf_reag_dez25_mai26";
  const downloadBlob = (blob,name) => {const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500)};
  const svgBlob = () => new Blob([new XMLSerializer().serializeToString(chart.querySelector("svg"))],{type:"image/svg+xml;charset=utf-8"});
  const pngBlob = () => new Promise((resolve,reject)=>{const svg=chart.querySelector("svg"),box=svg.viewBox.baseVal,url=URL.createObjectURL(svgBlob()),img=new Image();img.onload=()=>{const canvas=document.createElement("canvas"),scale=2;canvas.width=box.width*scale;canvas.height=box.height*scale;const ctx=canvas.getContext("2d");ctx.fillStyle="#fff";ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);URL.revokeObjectURL(url);canvas.toBlob(blob=>blob?resolve(blob):reject(new Error("Falha ao gerar PNG")),"image/png")};img.onerror=reject;img.src=url});
  const csvBlob = () => {const rows=filteredDetails(),headers=state.view==="admin"?["fundo","cnpj","origem","destino","pl_comparavel_brl","pl_dez24_brl","pl_dez25_brl","fundosnet_url","cvm_origem_url","cvm_destino_url"]:["fundo","cnpj","destino","pl_dez25_brl","pl_mai26_brl","gestor_mai26","custodiante_mai26","fundosnet_url","cvm_origem_url","cvm_destino_url"],values=rows.map(r=>state.view==="admin"?[r.fund,r.cnpj,r.source,r.target,r.flow,r.pl0,r.pl1,r.fundosnetUrl,r.sourceUrl,r.targetUrl]:[r.fund,r.cnpj,r.target,r.pl0,r.pl1,r.manager,r.custodian,r.fundosnetUrl,r.sourceUrl,r.targetUrl]),quote=v=>'"'+String(v??"").replaceAll('"','""')+'"',csv=[headers,...values].map(r=>r.map(quote).join(";")).join("\n");return new Blob(["\ufeff"+csv],{type:"text/csv;charset=utf-8"})};
  const render = () => {root.querySelectorAll("[data-view]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.view===state.view)));topSelect.disabled=state.view==="reag";topSelect.value=state.view==="reag"?"all":String(state.topN);renderChart();renderTable()};
  root.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>{state={...state,view:b.dataset.view,selected:null,query:"",page:0};search.value="";render()}));
  topSelect.addEventListener("change",()=>{state.topN=topSelect.value;state.selected=null;state.page=0;render()});
  search.addEventListener("input",()=>{state.query=search.value;state.selected=null;state.page=0;render()});
  pager.querySelector("[data-prev]").addEventListener("click",()=>{state.page=Math.max(0,state.page-1);renderTable()});pager.querySelector("[data-next]").addEventListener("click",()=>{state.page+=1;renderTable()});
  root.querySelector("[data-export-svg]").addEventListener("click",()=>downloadBlob(svgBlob(),fileStem()+".svg"));
  root.querySelector("[data-export-png]").addEventListener("click",async()=>downloadBlob(await pngBlob(),fileStem()+".png"));
  root.querySelector("[data-export-csv]").addEventListener("click",()=>downloadBlob(csvBlob(),fileStem()+"_fundos.csv"));
  root.querySelector("[data-copy]").addEventListener("click",async e=>{const button=e.currentTarget,old=button.textContent;try{const blob=await pngBlob();if(navigator.clipboard&&window.ClipboardItem){await navigator.clipboard.write([new ClipboardItem({"image/png":blob})]);button.textContent="Copiado";setTimeout(()=>button.textContent=old,1400)}else downloadBlob(blob,fileStem()+".png")}catch{button.textContent="Use PNG";setTimeout(()=>button.textContent=old,1400)}});
  render();
}

function clientRuntime(data) {
  const serialized = JSON.stringify(data).replace(/</g, "\\u003c");
  return `<script>(${browserApp.toString()})(${serialized});<\/script>`;
}

function fragmentHtml(data, standalone = false) {
  const theme = standalone
    ? `:root{--background:#FFFFFF;--foreground:#151515;--muted-foreground:#73787D;--border:#D7DADD;--accent:#F5F6F7;--primary:#151515;--primary-foreground:#FFFFFF;--viz-series-1:#EC7000;--viz-series-2:#2456D6;--viz-series-3:#1D4080;--viz-series-4:#7A1F3D;--viz-series-5:#73C6A1;--viz-series-6:#8D9399;font-family:Arial,sans-serif}`
    : "";
  return `<div id="provider-flow-explorer" class="provider-flow-explorer">
  <style>
    ${theme}
    #provider-flow-explorer{--flow-bg:var(--background,#FFFFFF);--flow-fg:var(--foreground,#151515);--flow-muted:var(--muted-foreground,#73787D);--flow-border:var(--border,#D7DADD);--flow-pale:var(--accent,#F5F6F7);--flow-orange:var(--viz-series-1,#EC7000);--flow-qi:var(--viz-series-2,#2456D6);--flow-btg:var(--viz-series-3,#1D4080);--flow-oliveira:var(--viz-series-4,#7A1F3D);--flow-green:var(--viz-series-5,#73C6A1);--flow-gray-1:var(--foreground,#30353A);--flow-gray-2:color-mix(in srgb,var(--foreground,#30353A) 78%,var(--background,#FFFFFF));--flow-gray-3:color-mix(in srgb,var(--foreground,#30353A) 58%,var(--background,#FFFFFF));--flow-gray-4:color-mix(in srgb,var(--foreground,#30353A) 38%,var(--background,#FFFFFF));--flow-faint:color-mix(in srgb,var(--foreground,#30353A) 24%,var(--background,#FFFFFF));position:relative;color:var(--flow-fg);font-family:Arial,sans-serif;max-width:100%;}
    #provider-flow-explorer .flow-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-bottom:12px}
    #provider-flow-explorer .flow-heading{margin:0 0 16px}
    #provider-flow-explorer .flow-heading h2{font-size:22px;line-height:1.15;margin:0 0 5px;letter-spacing:-.02em}
    #provider-flow-explorer .flow-heading p{margin:0;color:var(--flow-muted);font-size:14px}
    #provider-flow-explorer .view-switch{display:flex;gap:6px}
    #provider-flow-explorer button,#provider-flow-explorer input,#provider-flow-explorer select{font:inherit}
    #provider-flow-explorer button{border:1px solid var(--flow-border);background:transparent;color:var(--flow-fg);padding:7px 11px;border-radius:4px;cursor:pointer}
    #provider-flow-explorer button[aria-pressed="true"]{background:var(--primary,#151515);color:var(--primary-foreground,#FFFFFF);border-color:var(--primary,#151515)}
    #provider-flow-explorer button:disabled{opacity:.35;cursor:default}
    #provider-flow-explorer label{display:grid;gap:4px;color:var(--flow-muted)}
    #provider-flow-explorer input,#provider-flow-explorer select{border:1px solid var(--flow-border);background:var(--flow-bg);color:var(--flow-fg);border-radius:4px;padding:7px 9px;min-width:150px}
    #provider-flow-explorer .search{flex:1;min-width:210px}
    #provider-flow-explorer .exports{display:flex;flex-wrap:wrap;gap:6px;margin-left:auto}
    #provider-flow-explorer [data-chart]{width:100%;min-height:360px}
    #provider-flow-explorer svg{display:block;width:100%;height:auto;background:var(--flow-bg)}
    #provider-flow-explorer svg text{fill:var(--flow-fg);font-family:Arial,sans-serif}
    #provider-flow-explorer .metric{font-size:27px;font-weight:700}
    #provider-flow-explorer .metric-label,#provider-flow-explorer .node-value,#provider-flow-explorer .footnote{font-size:13px;fill:var(--flow-muted)}
    #provider-flow-explorer .period{font-size:12px;font-weight:700;fill:var(--flow-muted)}
    #provider-flow-explorer .node-label{font-size:15px;font-weight:700}
    #provider-flow-explorer .link-label{font-size:12px;font-weight:700;paint-order:stroke;stroke:var(--flow-bg);stroke-width:6px;stroke-linejoin:round;pointer-events:none}
    #provider-flow-explorer .flow-link{cursor:pointer;transition:opacity .18s ease,filter .18s ease}
    #provider-flow-explorer .flow-link:hover,#provider-flow-explorer .flow-link.is-selected{opacity:.82!important;filter:saturate(1.1)}
    #provider-flow-explorer .flow-node{cursor:pointer}
    #provider-flow-explorer .leader{fill:none;stroke:var(--flow-border);stroke-width:1}
    #provider-flow-explorer .detail-caption{border-top:1px solid var(--flow-border);padding-top:10px;margin-top:4px;min-height:24px;color:var(--flow-muted)}
    #provider-flow-explorer table{border-collapse:collapse;width:100%;margin-top:8px}
    #provider-flow-explorer th,#provider-flow-explorer td{text-align:left;padding:8px 7px;border-bottom:1px solid var(--flow-border);vertical-align:top}
    #provider-flow-explorer th{font-weight:700;color:var(--flow-muted)}
    #provider-flow-explorer a{color:var(--flow-fg);text-decoration-color:var(--flow-border);text-underline-offset:2px}
    #provider-flow-explorer .docs{display:grid;gap:3px;white-space:nowrap}
    #provider-flow-explorer td.num,#provider-flow-explorer th.num{text-align:right;white-space:nowrap}
    #provider-flow-explorer .pager{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-top:10px;color:var(--flow-muted)}
    #provider-flow-explorer .flow-tooltip{position:absolute;z-index:2;max-width:320px;padding:8px 10px;background:var(--flow-fg);color:var(--flow-bg);border-radius:4px;pointer-events:none}
    @media(max-width:720px){#provider-flow-explorer .optional{display:none}#provider-flow-explorer [data-chart]{min-height:260px}#provider-flow-explorer .metric{font-size:22px}#provider-flow-explorer .node-label{font-size:13px}#provider-flow-explorer th,#provider-flow-explorer td{padding:7px 4px}}
    @media(prefers-reduced-motion:reduce){#provider-flow-explorer .flow-link{transition:none}}
  </style>
  <header class="flow-heading"><h2>Movimentação de prestadores da indústria de FIDCs</h2><p>Selecione um fluxo para abrir os fundos, compare o PL nas duas datas e copie a visão para o Office.</p></header>
  <div class="flow-controls" aria-label="Controles da visualização">
    <div class="view-switch" aria-label="Visão">
      <button type="button" data-view="admin" aria-pressed="true">Mercado</button>
      <button type="button" data-view="reag" aria-pressed="false">CBSF / REAG</button>
    </div>
    <label>Fluxos visíveis<select aria-label="Quantidade de fluxos"><option value="10">Top 10</option><option value="25">Top 25</option><option value="250m">≥ R$ 250 mi</option><option value="all">Todos</option></select></label>
    <label class="search">Buscar fundo, CNPJ ou prestador<input type="search" placeholder="Ex.: Cielo, 26.286.939/0001-58, QI Tech"></label>
    <div class="exports" aria-label="Exportar visão"><button type="button" data-copy>Copiar para Office</button><button type="button" data-export-svg>SVG</button><button type="button" data-export-png>PNG</button><button type="button" data-export-csv>CSV</button></div>
  </div>
  <div data-chart></div>
  <div class="detail-caption" data-detail-caption aria-live="polite"></div>
  <table aria-label="Fundos do fluxo selecionado"><thead></thead><tbody></tbody></table>
  <div class="pager" data-pager><button type="button" data-prev aria-label="Página anterior">Anterior</button><span>0 / 0</span><button type="button" data-next aria-label="Próxima página">Próxima</button></div>
  <div class="flow-tooltip" data-tooltip-box hidden></div>
</div>
${clientRuntime(data)}`;
}

function standaloneHtml(data) {
  return `<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"><title>Fluxos de prestadores de FIDC</title></head>
<body style="margin:0;padding:24px;background:#FFFFFF">${fragmentHtml(data, true)}</body>
</html>`;
}

async function main() {
  const args = argsFrom(process.argv.slice(2));
  const payloadPath = path.resolve(String(args.payload || DEFAULT_PAYLOAD));
  const outputDir = path.resolve(String(args["output-dir"] || DEFAULT_OUTPUT_DIR));
  const htmlPath = path.resolve(String(args.html || path.join(outputDir, "provider_flows_explorer.html")));
  const fragmentPath = args.fragment ? path.resolve(String(args.fragment)) : "";
  const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
  const data = viewModels(payload);
  validateViews(data);
  await fs.mkdir(outputDir, { recursive: true });
  await fs.mkdir(path.dirname(htmlPath), { recursive: true });
  const adminSvg = staticSvg(data.admin, 10);
  const reagSvg = staticSvg(data.reag, "all");
  await Promise.all([
    sharp(Buffer.from(adminSvg)).resize({ width: 2560 }).png().toFile(path.join(outputDir, "provider_flow_admin.png")),
    sharp(Buffer.from(reagSvg)).resize({ width: 2560 }).png().toFile(path.join(outputDir, "provider_flow_reag.png")),
    fs.writeFile(path.join(outputDir, "provider_flow_admin.svg"), adminSvg, "utf8"),
    fs.writeFile(path.join(outputDir, "provider_flow_reag.svg"), reagSvg, "utf8"),
    fs.writeFile(htmlPath, standaloneHtml(data), "utf8"),
  ]);
  if (fragmentPath) {
    await fs.mkdir(path.dirname(fragmentPath), { recursive: true });
    await fs.writeFile(fragmentPath, fragmentHtml(data, false), "utf8");
  }
  process.stdout.write(`${htmlPath}\n${path.join(outputDir, "provider_flow_admin.png")}\n${path.join(outputDir, "provider_flow_reag.png")}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
