#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), "..");

const DEFAULT_PAYLOAD = path.join(
  ROOT,
  "data/industry_study/generated_revision/artifact_payload.json",
);
const FUNDOSNET_CNPJ_BASE =
  "https://fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCVM?cnpjFundo=";
const COMPACT_FIELDS = Object.freeze({
  marketLink: ["source", "target", "funds", "value", "origin", "current", "shareUniverse"],
  cohortLink: ["source", "target", "funds", "value", "origin", "current"],
  marketDetail: ["fund", "cnpj", "source", "target", "pl0", "pl1", "flow"],
  cohortDetail: ["fund", "cnpj", "target", "status", "pl0", "pl1", "flow", "manager", "custodian"],
});

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

function nullableNumber(...values) {
  const value = values.find(
    (candidate) => candidate !== null && candidate !== undefined && candidate !== "",
  );
  if (value === undefined) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Valor numérico inválido no fluxo de prestadores: ${value}`);
  }
  return parsed;
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

const MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function competenceParts(value, fallback = "2026-05") {
  const matches = [...String(value || "").matchAll(/(\d{4})-(\d{2})(?:-\d{2})?/g)];
  const fallbackMatches = [...String(fallback).matchAll(/(\d{4})-(\d{2})(?:-\d{2})?/g)];
  const match = matches.at(-1) || fallbackMatches.at(-1);
  if (!match) throw new Error(`Competencia invalida: ${value}`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) throw new Error(`Competencia invalida: ${value}`);
  const monthLabel = MONTHS_PT[month - 1];
  const yearShort = String(year).slice(-2);
  return {
    competence: `${year}-${String(month).padStart(2, "0")}`,
    label: `${monthLabel}/${yearShort}`,
    slug: `${monthLabel}${yearShort}`,
  };
}

function periodFields(startValue, endValue, filePrefix) {
  const start = competenceParts(startValue, "2024-12");
  const current = competenceParts(endValue, "2026-05");
  return {
    period: `${start.label.toUpperCase()} → ${current.label.toUpperCase()}`,
    startLabel: start.label,
    startSlug: start.slug,
    currentLabel: current.label,
    currentSlug: current.slug,
    fileStem: `${filePrefix}_${start.slug}_${current.slug}`,
  };
}

function periodFieldsFromReference(value, filePrefix) {
  const matches = [...String(value || "").matchAll(/(\d{4})-(\d{2})(?:-\d{2})?/g)];
  const start = matches[0] ? `${matches[0][1]}-${matches[0][2]}` : "2024-12";
  const endMatch = matches.at(-1);
  const end = endMatch ? `${endMatch[1]}-${endMatch[2]}` : "2026-05";
  return periodFields(start, end, filePrefix);
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
      flow: number(row.pl_destino_brl || row.pl_comparavel_brl),
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
  const adminPeriod = periodFields(
    adminSummary.competencia_origem || "2024-12",
    payload.latest_complete || adminSummary.competencia_destino || "2026-05",
    "fluxos_admin",
  );

  const historicalCoverage = payload.provider_history_cvm_coverage || [];
  const historicalDetails = payload.provider_history_cvm_detail || [];
  const historicalLinks = payload.provider_history_cvm_links || [];
  const historicalRoleView = (role, label) => {
    const coverage = historicalCoverage.find(
      (row) => String(row.papel) === role && String(row.data_referencia || "").includes("→"),
    ) || {};
    const rolePeriod = periodFieldsFromReference(
      coverage.data_referencia,
      `fluxos_${role}`,
    );
    const details = historicalDetails
      .filter((row) => String(row.papel) === role && truthy(row.comparavel) && truthy(row.mudou_grupo))
      .map((row) => ({
        fund: compactFund(row.denominacao),
        cnpj: row.cnpj_fundo_formatado || formatCnpj(row.cnpj_fundo),
        source: compactProvider(row.origem_prestador_grupo),
        target: compactProvider(row.destino_prestador_grupo),
        pl0: number(row.pl_mai26_brl),
        pl1: number(row.pl_mai26_brl),
        flow: number(row.pl_mai26_brl),
        fundosnetUrl: "",
        sourceUrl: row.fonte_url || "",
        targetUrl: row.fonte_url || "",
      }))
      .sort((a, b) => b.flow - a.flow);
    const links = historicalLinks
      .filter((row) => String(row.papel) === role && truthy(row.mudou_grupo))
      .map((row) => ({
        source: compactProvider(row.origem_prestador_grupo),
        target: compactProvider(row.destino_prestador_grupo),
        funds: Math.round(number(row.fundos)),
        value: number(row.pl_mai26_brl),
        origin: number(row.pl_mai26_brl),
        current: number(row.pl_mai26_brl),
        shareUniverse: number(row.share_pl_comparavel),
      }))
      .filter((row) => row.source !== row.target && row.value > 0)
      .sort((a, b) => b.value - a.value);
    return {
      id: role,
      kind: "market",
      ...rolePeriod,
      eyebrow: `${rolePeriod.period} · ${label.toUpperCase()} · AMOSTRA ICVM 555`,
      leftLabel: `${label.toUpperCase()} · ${rolePeriod.startLabel.toUpperCase()}`,
      rightLabel: `${label.toUpperCase()} · ${rolePeriod.currentLabel.toUpperCase()}`,
      note: `Largura = PL ${rolePeriod.currentLabel}. Cobertura comparável: ${percent(number(coverage.cobertura_pl_resolvida), 1)} do PL da coorte; amostra ICVM 555, sem extrapolação.`,
      summary: {
        primary: number(coverage.pl_mudou_grupo_mai26_brl),
        primaryLabel: "PL que mudou na amostra",
        secondary: Math.round(number(coverage.fundos_mudaram_grupo)),
        secondaryLabel: "FIDCs com troca na amostra",
        tertiary: number(coverage.cobertura_pl_resolvida),
        tertiaryLabel: "cobertura do PL da coorte",
      },
      links,
      details,
    };
  };

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
      pl1: nullableNumber(row.pl_destino_brl, row.pl_destino_observado_brl),
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
      current: null,
    };
    item.funds += 1;
    item.value += row.flow;
    item.origin += row.pl0;
    if (row.pl1 !== null) {
      item.current = number(item.current) + row.pl1;
    }
    reagLinkMap.set(key, item);
  }
  const reagLinks = [...reagLinkMap.values()].sort((a, b) => b.value - a.value);
  const reagSummary = payload.reag_admin_summary || {};
  const reagPeriod = periodFields(
    reagSummary.competencia_origem || "2025-12",
    reagSummary.competencia_destino || payload.latest_complete || "2026-05",
    "fluxos_cbsf_reag",
  );

  return {
    admin: {
      id: "admin",
      kind: "market",
      ...adminPeriod,
      eyebrow: `${adminPeriod.period} · ADMINISTRAÇÃO`,
      leftLabel: `ADMINISTRADOR · ${adminPeriod.startLabel.toUpperCase()}`,
      rightLabel: `ADMINISTRADOR · ${adminPeriod.currentLabel.toUpperCase()}`,
      note: `Largura = PL ${adminPeriod.currentLabel}. Cobertura: ${percent(number(adminSummary.coverage_pl), 1)} do PL da coorte atual; fundos sem administrador observado em ${adminPeriod.startLabel} ficam fora.`,
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
    gestor: historicalRoleView("gestor", "Gestão"),
    custodiante: historicalRoleView("custodiante", "Custódia"),
    reag: {
      id: "reag",
      kind: "cohort",
      ...reagPeriod,
      eyebrow: `CBSF / REAG · ${reagPeriod.period}`,
      leftLabel: `COORTE · ${reagPeriod.startLabel.toUpperCase()}`,
      rightLabel: `DESTINO · ${reagPeriod.currentLabel.toUpperCase()}`,
      note: `Largura = PL de ${reagPeriod.startLabel}. Gestão e custódia são fotografia vigente de ${reagPeriod.currentLabel}; a série histórica dessas funções não está disponível.`,
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
  for (const role of ["gestor", "custodiante"]) {
    assertClose(sum(data[role].links, "value"), data[role].summary.primary, `PL dos links de ${role}`);
    assertClose(sum(data[role].details, "flow"), data[role].summary.primary, `PL do detalhe de ${role}`);
    if (data[role].details.length !== data[role].summary.secondary || unique(data[role].details) !== data[role].details.length) {
      throw new Error(`Contagem/CNPJ do detalhe de ${role} não reconcilia`);
    }
  }
  assertClose(sum(data.reag.links, "value"), data.reag.summary.primary, "PL dos links CBSF/REAG");
  assertClose(sum(data.reag.details, "flow"), data.reag.summary.primary, "PL do detalhe CBSF/REAG");
  if (unique(data.reag.details) !== data.reag.details.length) throw new Error("CNPJ duplicado no detalhe CBSF/REAG");
}

function constantDetailValue(details, key, viewId) {
  const values = new Set(details.map((row) => String(row[key] ?? "")));
  if (values.size > 1) {
    throw new Error(`${viewId}.${key} deixou de ser constante; atualize o esquema compacto`);
  }
  return values.values().next().value || "";
}

function compactViews(data) {
  const views = {};
  for (const [viewId, view] of Object.entries(data)) {
    const { links, details, ...metadata } = view;
    const linkFields = COMPACT_FIELDS[`${view.kind}Link`];
    const detailFields = COMPACT_FIELDS[`${view.kind}Detail`];
    if (!linkFields || !detailFields) {
      throw new Error(`Tipo de visão sem esquema compacto: ${view.kind}`);
    }
    const fundosnetRows = details.filter((row) => row.fundosnetUrl);
    if (fundosnetRows.length > 0 && fundosnetRows.length !== details.length) {
      throw new Error(`${viewId}.fundosnetUrl deixou de ter cobertura uniforme`);
    }
    const fundosnetFromCnpj = fundosnetRows.length > 0;
    if (
      fundosnetFromCnpj
      && fundosnetRows.some(
        (row) => (
          row.fundosnetUrl
          !== `${FUNDOSNET_CNPJ_BASE}${String(row.cnpj || "").replace(/\D/g, "")}`
        ),
      )
    ) {
      throw new Error(`${viewId}.fundosnetUrl deixou de ser derivável do CNPJ`);
    }
    const documents = {
      fundosnetBase: fundosnetFromCnpj ? FUNDOSNET_CNPJ_BASE : "",
      sourceUrl: constantDetailValue(details, "sourceUrl", viewId),
      targetUrl: constantDetailValue(details, "targetUrl", viewId),
      ...(view.kind === "cohort"
        ? { detailSource: constantDetailValue(details, "source", viewId) }
        : {}),
    };
    views[viewId] = {
      ...metadata,
      documents,
      links: links.map((row) => linkFields.map((field) => row[field])),
      details: details.map((row) => detailFields.map((field) => row[field])),
    };
  }
  return {
    schemaVersion: "provider_flow_compact_v1",
    fields: COMPACT_FIELDS,
    views,
  };
}

function expandCompactViews(compact) {
  if (compact.schemaVersion !== "provider_flow_compact_v1") {
    throw new Error(`Esquema compacto desconhecido: ${compact.schemaVersion}`);
  }
  const rowObject = (fields, values) => Object.fromEntries(
    fields.map((field, index) => [field, values[index]]),
  );
  const views = {};
  for (const [viewId, compactView] of Object.entries(compact.views)) {
    const {
      documents,
      links: compactLinks,
      details: compactDetails,
      ...metadata
    } = compactView;
    const linkFields = compact.fields[`${metadata.kind}Link`];
    const detailFields = compact.fields[`${metadata.kind}Detail`];
    const links = compactLinks.map((row) => rowObject(linkFields, row));
    const details = compactDetails.map((row) => {
      const detail = rowObject(detailFields, row);
      const fundosnetUrl = documents.fundosnetBase
        ? `${documents.fundosnetBase}${String(detail.cnpj || "").replace(/\D/g, "")}`
        : "";
      if (metadata.kind === "market") {
        return {
          ...detail,
          fundosnetUrl,
          sourceUrl: documents.sourceUrl,
          targetUrl: documents.targetUrl,
        };
      }
      return {
        fund: detail.fund,
        cnpj: detail.cnpj,
        source: documents.detailSource,
        target: detail.target,
        status: detail.status,
        pl0: detail.pl0,
        pl1: detail.pl1,
        flow: detail.flow,
        manager: detail.manager,
        custodian: detail.custodian,
        fundosnetUrl,
        sourceUrl: documents.sourceUrl,
        targetUrl: documents.targetUrl,
      };
    });
    views[viewId] = { ...metadata, links, details };
  }
  return views;
}

function flagshipModels(payload) {
  const summary = payload.flagship_curation_summary || {};
  const families = [...(payload.flagship_families || [])]
    .sort((a, b) => number(a.ordem_familia) - number(b.ordem_familia))
    .map((row) => ({
      order: Math.round(number(row.ordem_familia)),
      category: String(row.categoria || "N/D"),
      family: String(row.familia_flagship || "N/D"),
      cnpjs: String(row.cnpjs || ""),
      funds: Math.round(number(row.fundos)),
      pl: nullableNumber(row.pl_atual_brl),
      subordinate: nullableNumber(row.pl_subordinado_atual_brl),
      ratio: nullableNumber(row.subordinacao_atual_pct),
      range: String(row.faixa_subordinacao_atual || "N/D"),
      minJunior: String(row.subordinacao_minima_junior_display || "N/D"),
      price: String(row.preco_emissao_display || "N/D"),
      mezzanine: String(row.cota_mezanino || "N/D"),
      documented: Math.round(number(row.cnpjs_com_pacote_documental)),
      status: String(row.status_curadoria || "N/D"),
    }));
  const details = [...(payload.flagship_curation || [])]
    .sort(
      (a, b) =>
        number(a.ordem_familia) - number(b.ordem_familia)
        || number(b.representante_familia) - number(a.representante_familia)
        || number(b.pl_atual_brl) - number(a.pl_atual_brl),
    )
    .map((row) => ({
      order: Math.round(number(row.ordem_familia)),
      category: String(row.categoria || "N/D"),
      family: String(row.familia_flagship || "N/D"),
      representative: truthy(row.representante_familia),
      fund: compactFund(row.denominacao || "N/D"),
      cnpj: String(row.cnpj_fundo_formatado || formatCnpj(row.cnpj_fundo)),
      pl: nullableNumber(row.pl_atual_brl),
      subordinate: nullableNumber(row.pl_subordinado_atual_brl),
      ratio: nullableNumber(row.subordinacao_atual_pct),
      range: String(row.faixa_subordinacao_atual || "N/D"),
      minJunior: String(row.subordinacao_minima_junior_display || "N/D"),
      threshold: String(row.subordinacao_minima_texto || "N/D"),
      thresholdSource: String(row.subordinacao_minima_fonte || "N/D"),
      price: String(row.preco_emissao_display || "N/D"),
      priceClass: String(row.preco_emissao_classe || "N/D"),
      priceDate: String(row.preco_emissao_data || "N/D"),
      priceSource: String(row.preco_emissao_fonte || "N/D"),
      mezzanine: String(row.cota_mezanino || "N/D"),
      mezzanineSource: String(row.cota_mezanino_fonte || "N/D"),
      acceleration: String(row.vencimento_antecipado || "N/D"),
      accelerationSource: String(row.vencimento_antecipado_fonte || "N/D"),
      packageStatus: String(row.pacote_documental_status || "N/D"),
      packagePath: String(row.pacote_documental_path || "N/D"),
      fundosnetUrl: String(row.fundosnet_url || ""),
      gaps: String(row.lacunas || "N/D"),
    }));
  return {
    summary: {
      competence: String(summary.competencia || payload.latest_complete || "N/D"),
      families: Math.round(number(summary.familias)),
      cnpjs: Math.round(number(summary.cnpjs)),
      current: Math.round(number(summary.cnpjs_com_subordinacao_atual)),
      documented: Math.round(number(summary.cnpjs_com_pacote_documental)),
      minJunior: Math.round(number(summary.cnpjs_com_minimo_junior)),
      price: Math.round(number(summary.cnpjs_com_preco_vnu)),
      mezzanine: Math.round(number(summary.cnpjs_com_mezanino_comprovado)),
      acceleration: Math.round(number(summary.cnpjs_com_evento)),
      currentSource: String(summary.fonte_pl_subordinacao || "N/D"),
      documentarySource: String(summary.fonte_documental || "N/D"),
      methodology: String(summary.metodologia || "N/D"),
    },
    families,
    details,
  };
}

const FLAGSHIP_FIELDS = Object.freeze({
  family: [
    "order", "category", "family", "cnpjs", "funds", "pl", "subordinate",
    "ratio", "range", "minJunior", "price", "mezzanine", "documented", "status",
  ],
  detail: [
    "order", "category", "family", "representative", "fund", "cnpj", "pl",
    "subordinate", "ratio", "range", "minJunior", "threshold",
    "thresholdSource", "price", "priceClass", "priceDate", "priceSource",
    "mezzanine", "mezzanineSource", "acceleration", "accelerationSource",
    "packageStatus", "packagePath", "fundosnetUrl", "gaps",
  ],
});

function compactFlagships(data) {
  return {
    schemaVersion: "flagship_curation_compact_v1",
    fields: FLAGSHIP_FIELDS,
    summary: data.summary,
    families: data.families.map(
      (row) => FLAGSHIP_FIELDS.family.map((field) => row[field]),
    ),
    details: data.details.map(
      (row) => FLAGSHIP_FIELDS.detail.map((field) => row[field]),
    ),
  };
}

function expandCompactFlagships(compact) {
  if (compact.schemaVersion !== "flagship_curation_compact_v1") {
    throw new Error(`Esquema de flagship desconhecido: ${compact.schemaVersion}`);
  }
  const object = (fields, values) => Object.fromEntries(
    fields.map((field, index) => [field, values[index]]),
  );
  return {
    summary: compact.summary,
    families: compact.families.map((values) => object(compact.fields.family, values)),
    details: compact.details.map((values) => object(compact.fields.detail, values)),
  };
}

function validateFlagships(data) {
  if (data.families.length !== 26) {
    throw new Error(`Curadoria flagship deveria conter 26 famílias; contém ${data.families.length}`);
  }
  if (data.details.length !== 47) {
    throw new Error(`Curadoria flagship deveria conter 47 CNPJs; contém ${data.details.length}`);
  }
  if (new Set(data.details.map((row) => row.cnpj)).size !== data.details.length) {
    throw new Error("Curadoria flagship contém CNPJ duplicado");
  }
  if (data.details.some((row) => row.pl === null || row.ratio === null)) {
    throw new Error("Curadoria flagship contém PL ou subordinação atual ausente");
  }
  if (data.families.reduce((total, row) => total + row.funds, 0) !== data.details.length) {
    throw new Error("Curadoria flagship não reconcilia famílias e CNPJs");
  }
  if (
    data.summary.families !== data.families.length
    || data.summary.cnpjs !== data.details.length
    || data.summary.current !== data.details.length
  ) {
    throw new Error("Resumo da curadoria flagship não reconcilia com o detalhe");
  }
}

const TAXONOMY_FIELDS = Object.freeze([
  "competence", "level", "type", "category", "funds", "pl", "typePl", "totalPl",
  "shareType", "shareTotal",
]);

function taxonomyModels(payload) {
  return [...(payload.taxonomy_level_history || [])]
    .map((row) => ({
      competence: String(row.competencia || "N/D"),
      level: String(row.nivel || "N/D"),
      type: String(row.tipo_exibicao || "N/D"),
      category: String(row.categoria || "N/D"),
      funds: Math.round(number(row.fundos)),
      pl: nullableNumber(row.pl_brl),
      typePl: nullableNumber(row.pl_tipo_brl),
      totalPl: nullableNumber(row.pl_total_brl),
      shareType: nullableNumber(row.share_tipo),
      shareTotal: nullableNumber(row.share_total),
    }))
    .sort(
      (a, b) =>
        a.competence.localeCompare(b.competence)
        || a.level.localeCompare(b.level)
        || a.type.localeCompare(b.type)
        || b.pl - a.pl,
    );
}

function compactTaxonomy(rows) {
  return {
    schemaVersion: "taxonomy_levels_compact_v1",
    fields: TAXONOMY_FIELDS,
    rows: rows.map((row) => TAXONOMY_FIELDS.map((field) => row[field])),
  };
}

function expandCompactTaxonomy(compact) {
  if (compact.schemaVersion !== "taxonomy_levels_compact_v1") {
    throw new Error(`Esquema de taxonomia desconhecido: ${compact.schemaVersion}`);
  }
  return compact.rows.map((values) => Object.fromEntries(
    compact.fields.map((field, index) => [field, values[index]]),
  ));
}

function validateTaxonomy(rows) {
  const expectedLevels = new Set([
    "foco_analitico",
    "tabela_ii_analitica",
    "taxonomia_funcional_n1",
    "taxonomia_funcional_n2",
  ]);
  const levels = new Set(rows.map((row) => row.level));
  if (
    rows.length === 0
    || levels.size !== expectedLevels.size
    || [...expectedLevels].some((level) => !levels.has(level))
  ) {
    throw new Error("Explorador não preservou os quatro níveis de taxonomia");
  }
  if (rows.some((row) => row.pl === null || row.typePl === null || row.totalPl === null)) {
    throw new Error("Taxonomia por nível contém PL ausente");
  }
}

function percent(value, digits = 1) {
  return `${(number(value) * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
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
    const W=1280,H=Math.max(620,Math.max(sources.length,targets.length)*39+170),top=118,ph=H-158,lx=248,rx=1032,market=view.kind==="market"; const L=column(sources,lx,top,ph,market?13:18); const R=column(targets,rx,top,ph,market?10:18);
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
    const metrics=v.kind==="market"?[[money(shown),scopeLabel],[pct(shown/Math.max(total,1)),"do PL que migrou"],[g.links.reduce((s,l)=>s+l.funds,0).toLocaleString("pt-BR"),"fundos nesses fluxos"]]:[[money(v.summary.primary),v.summary.primaryLabel],[money(v.summary.secondary),v.summary.secondaryLabel],[money(v.summary.tertiary),v.summary.tertiaryLabel]];
    metrics.forEach((m,i)=>{const x=40+i*345;h+=`<text x="${x}" y="61" class="metric">${esc(m[0])}</text><text x="${x}" y="84" class="metric-label">${esc(m[1])}</text>`});
    h+=`<text x="40" y="111" class="period">${esc(v.leftLabel)}</text><text x="1240" y="111" text-anchor="end" class="period">${esc(v.rightLabel)}</text>`;
    g.links.forEach(l=>{const active=!state.query||matches.has(l.key),selected=state.selected===l.key;h+=`<path class="flow-link${selected ? " is-selected" : ""}" data-key="${esc(l.key)}" d="${ribbon(g,l)}" fill="${color(l.target)}" style="opacity:${active?(selected ? .82 : .46):.06}"><title>${esc(l.source+" → "+l.target+" · "+money(l.value)+" · "+funds(l.funds))}</title></path>`});
    const nodes=(map,side)=>{const lm=labels(map,g.H);for(const [name,q] of map){const key=side+"|||"+name,p=lm.get(name),tx=side==="left"?q.x-15:q.x+15,ta=side==="left"?"end":"start";h+=`<g class="flow-node" data-node="${esc(key)}"><rect x="${q.x}" y="${q.y}" width="9" height="${q.height}" rx="2" fill="${color(name)}"/>${Math.abs(p.y-p.anchor)>3?`<path d="M ${side==="left"?q.x:q.x+9} ${p.anchor} L ${side==="left"?q.x-11:q.x+11} ${p.y}" class="leader"/>`:""}<text x="${tx}" y="${p.y-2}" text-anchor="${ta}" class="node-label">${esc(name)}</text><text x="${tx}" y="${p.y+17}" text-anchor="${ta}" class="node-value">${esc(money(q.value))}</text></g>`}};nodes(g.left,"left");nodes(g.right,"right");
    g.links.slice(0,1).forEach(l=>{const y=((l.y0+l.y1)/2+(l.end.y0+l.end.y1)/2)/2;h+=`<text x="640" y="${y+4}" text-anchor="middle" class="link-label">${esc(funds(l.funds)+" · "+money(l.value))}</text>`});
    const remaining=Math.max(0,v.links.length-g.links.length),remainingValue=Math.max(0,total-shown),note=state.query?g.links.length+" rota(s) associada(s) à busca; o valor da fita inclui todos os fundos da rota.":v.kind==="market"&&remaining?v.note+" Demais "+remaining+" rotas: "+money(remainingValue)+".":v.note;
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
      ? `${selected.source} → ${selected.target} · ${funds(selected.funds)} · ${money(selected.value)}${v.kind==="market"?` de PL ${v.currentLabel}`:` de origem | ${selected.current==null?"sem PL reportado em "+v.currentLabel:money(selected.current)+" em "+v.currentLabel}`}`
      : state.query?`${rows.length} fundos encontrados para “${state.query}”`:`${rows.length} fundos na base; selecione um fluxo ou pesquise para filtrar.`;
    const slice=rows.slice(state.page*8,state.page*8+8);
    tbody.innerHTML=slice.map(r=>v.kind==="market"
      ? `<tr><td>${esc(r.fund)}</td><td>${esc(r.cnpj)}</td><td>${esc(r.source)}</td><td>${esc(r.target)}</td><td class="num">${money(r.flow)}</td><td class="num optional">${money(r.pl0)}</td><td class="num optional">${money(r.pl1)}</td><td>${docs(r)}</td></tr>`
      : `<tr><td>${esc(r.fund)}</td><td>${esc(r.cnpj)}</td><td>${esc(r.target)}</td><td class="num">${money(r.pl0)}</td><td class="num optional">${r.pl1==null?"—":money(r.pl1)}</td><td class="optional">${esc(r.manager||"N/D")}</td><td class="optional">${esc(r.custodian||"N/D")}</td><td>${docs(r)}</td></tr>`
    ).join("")||`<tr><td colspan="8">Nenhum fundo encontrado.</td></tr>`;
    root.querySelector("thead").innerHTML=v.kind==="market"
      ? `<tr><th>Fundo</th><th>CNPJ</th><th>Origem</th><th>Destino</th><th>PL ${esc(v.currentLabel)}</th><th class='optional'>PL origem</th><th class='optional'>PL atual</th><th>Fontes</th></tr>`
      : `<tr><th>Fundo</th><th>CNPJ</th><th>Destino</th><th>PL ${esc(v.startLabel)}</th><th class='optional'>PL ${esc(v.currentLabel)}</th><th class='optional'>Gestor ${esc(v.currentLabel)}</th><th class='optional'>Custodiante ${esc(v.currentLabel)}</th><th>Fontes</th></tr>`;
    pager.querySelector("span").textContent=`${rows.length?state.page+1:0} / ${rows.length?pages:0}`;
    pager.querySelector("[data-prev]").disabled=state.page<=0;pager.querySelector("[data-next]").disabled=state.page>=pages-1;
  };
  const bindChart = () => {
    chart.querySelectorAll(".flow-link").forEach(el=>{
      el.addEventListener("click",()=>{state.selected=state.selected===el.dataset.key?null:el.dataset.key;state.page=0;render()});
      el.addEventListener("mousemove",e=>{
        const v=DATA[state.view],l=v.links.find(x=>x.source+"|||"+x.target===el.dataset.key),total=v.summary.primary;
        tooltip.innerHTML=l?`<strong>${esc(l.source)} → ${esc(l.target)}</strong><br>${funds(l.funds)} · ${money(l.value)}${v.kind==="market"?` de PL ${esc(v.currentLabel)} · ${pct(l.value/Math.max(total,1))} do PL migrado`:` de origem<br>${l.current==null?"sem PL reportado em "+esc(v.currentLabel):money(l.current)+" em "+esc(v.currentLabel)}`}`:"";
        tooltip.hidden=false;const r=root.getBoundingClientRect(),t=tooltip.getBoundingClientRect();tooltip.style.left=Math.min(r.width-t.width-8,Math.max(8,e.clientX-r.left+14))+"px";tooltip.style.top=Math.max(8,e.clientY-r.top-t.height-12)+"px";
      });
      el.addEventListener("mouseleave",()=>tooltip.hidden=true)
    });
    chart.querySelectorAll(".flow-node").forEach(el=>el.addEventListener("click",()=>{const [side,name]=el.dataset.node.split("|||");const links=DATA[state.view].links.filter(l=>(side==="left"?l.source:l.target)===name);state.selected=links.length===1?links[0].source+"|||"+links[0].target:null;state.query=name;search.value=name;state.page=0;render()}));
  };
  const fileStem = () => DATA[state.view].fileStem;
  const downloadBlob = (blob,name) => {const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500)};
  const svgBlob = () => new Blob([new XMLSerializer().serializeToString(chart.querySelector("svg"))],{type:"image/svg+xml;charset=utf-8"});
  const pngBlob = () => new Promise((resolve,reject)=>{const svg=chart.querySelector("svg"),box=svg.viewBox.baseVal,url=URL.createObjectURL(svgBlob()),img=new Image();img.onload=()=>{const canvas=document.createElement("canvas"),scale=2;canvas.width=box.width*scale;canvas.height=box.height*scale;const ctx=canvas.getContext("2d");ctx.fillStyle="#fff";ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);URL.revokeObjectURL(url);canvas.toBlob(blob=>blob?resolve(blob):reject(new Error("Falha ao gerar PNG")),"image/png")};img.onerror=reject;img.src=url});
  const csvBlob = () => {const v=DATA[state.view],rows=filteredDetails(),market=v.kind==="market",headers=market?["fundo","cnpj","origem","destino",`pl_${v.currentSlug}_brl`,"pl_origem_brl","pl_atual_brl","fundosnet_url","cvm_origem_url","cvm_destino_url"]:["fundo","cnpj","destino",`pl_${v.startSlug}_brl`,`pl_${v.currentSlug}_brl`,`gestor_${v.currentSlug}`,`custodiante_${v.currentSlug}`,"fundosnet_url","cvm_origem_url","cvm_destino_url"],values=rows.map(r=>market?[r.fund,r.cnpj,r.source,r.target,r.flow,r.pl0,r.pl1,r.fundosnetUrl,r.sourceUrl,r.targetUrl]:[r.fund,r.cnpj,r.target,r.pl0,r.pl1,r.manager,r.custodian,r.fundosnetUrl,r.sourceUrl,r.targetUrl]),quote=v=>'"'+String(v??"").replaceAll('"','""')+'"',csv=[headers,...values].map(r=>r.map(quote).join(";")).join("\n");return new Blob(["\ufeff"+csv],{type:"text/csv;charset=utf-8"})};
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

function flagshipApp(DATA) {
  const root = document.getElementById("flagship-curation-explorer");
  const category = root.querySelector("[data-flag-category]");
  const search = root.querySelector("[data-flag-search]");
  const grid = root.querySelector("[data-flag-grid]");
  const tbody = root.querySelector("tbody");
  const caption = root.querySelector("[data-flag-caption]");
  const pager = root.querySelector("[data-flag-pager]");
  let state = { category: "all", query: "", page: 0 };
  const n = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const norm = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[character]));
  const money = value => n(value) === null
    ? "N/D"
    : Math.abs(n(value)) < 1e9
      ? "R$ " + (n(value) / 1e6).toLocaleString("pt-BR", {minimumFractionDigits: 0, maximumFractionDigits: 1}) + " mi"
      : "R$ " + (n(value) / 1e9).toLocaleString("pt-BR", {minimumFractionDigits: 1, maximumFractionDigits: 1}) + " bi";
  const pct = value => n(value) === null
    ? "N/D"
    : (n(value) * 100).toLocaleString("pt-BR", {minimumFractionDigits: 1, maximumFractionDigits: 1}) + "%";
  const ranges = [
    ["< 10%", "#ECEEEF"], ["10%–15%", "#D7DADD"], ["15%–20%", "#BEC2C5"],
    ["20%–35%", "#E8BE9D"], ["35%–60%", "#F29A52"], ["≥ 60%", "#EC7000"],
  ];
  const categories = [...new Set(DATA.families.map(row => row.category))];
  category.innerHTML = `<option value="all">Todas as categorias</option>` + categories.map(value => `<option value="${esc(value)}">${esc(value)}</option>`).join("");
  const matches = row => {
    if (state.category !== "all" && row.category !== state.category) return false;
    if (!state.query) return true;
    return norm(Object.values(row).join(" ")).includes(norm(state.query));
  };
  const renderGrid = () => {
    const scoped = DATA.families.filter(matches);
    grid.innerHTML = ranges.map(([range, color]) => {
      const rows = scoped.filter(row => row.range === range);
      return `<section class="flag-range"><h3 style="--range-color:${color}"><span>${esc(range)}</span><b>${rows.length}</b></h3><div>${rows.map(row => `
        <article class="flag-card">
          <strong>${esc(row.family)}</strong>
          <span>${money(row.pl)} · atual ${pct(row.ratio)}</span>
          <small>mín. jr ${esc(row.minJunior)} · VNU ${esc(row.price)}</small>
          <small>${esc(row.documented + "/" + row.funds + " CNPJs com pacote")}</small>
        </article>`).join("") || `<p class="flag-empty">Sem famílias neste filtro.</p>`}</div></section>`;
    }).join("");
  };
  const filteredDetails = () => DATA.details.filter(matches);
  const sourceDetails = row => {
    const links = row.fundosnetUrl
      ? `<a href="${esc(row.fundosnetUrl)}" target="_blank" rel="noreferrer">FundosNet</a>`
      : "";
    return `<details><summary>Fontes</summary><div class="flag-sources">${links}<span>${esc(row.packagePath)}</span><span>Subord.: ${esc(row.thresholdSource)}</span><span>VNU: ${esc(row.priceSource)}</span><span>Eventos: ${esc(row.accelerationSource)}</span></div></details>`;
  };
  const renderTable = () => {
    const rows = filteredDetails();
    const pages = Math.max(1, Math.ceil(rows.length / 10));
    state.page = Math.min(state.page, pages - 1);
    const current = rows.slice(state.page * 10, state.page * 10 + 10);
    caption.textContent = `${rows.length} CNPJs no filtro · competência ${DATA.summary.competence}.`;
    tbody.innerHTML = current.map(row => `<tr>
      <td><strong>${esc(row.fund)}</strong><br><small>${esc(row.family)}</small></td>
      <td>${esc(row.cnpj)}</td>
      <td class="num">${money(row.pl)}</td>
      <td class="num">${pct(row.ratio)}<br><small>${esc(row.range)}</small></td>
      <td>${esc(row.minJunior)}<br><small>${esc(row.threshold)}</small></td>
      <td>${esc(row.price)}<br><small>${esc(row.priceClass)} · ${esc(row.priceDate)}</small></td>
      <td>${esc(row.mezzanine)}</td>
      <td>${esc(row.acceleration)}</td>
      <td>${esc(row.packageStatus)}<br><small>${esc(row.gaps)}</small></td>
      <td>${sourceDetails(row)}</td>
    </tr>`).join("") || `<tr><td colspan="10">Nenhum CNPJ encontrado.</td></tr>`;
    pager.querySelector("span").textContent = `${rows.length ? state.page + 1 : 0} / ${rows.length ? pages : 0}`;
    pager.querySelector("[data-flag-prev]").disabled = state.page <= 0;
    pager.querySelector("[data-flag-next]").disabled = state.page >= pages - 1;
  };
  const render = () => { renderGrid(); renderTable(); };
  const downloadCsv = () => {
    const headers = ["categoria","familia","fundo","cnpj","pl_atual_brl","pl_subordinado_atual_brl","subordinacao_atual_pct","faixa","minimo_junior","preco_vnu","mezanino","vencimento_antecipado","status_pacote","lacunas","fundosnet_url"];
    const rows = filteredDetails().map(row => [row.category,row.family,row.fund,row.cnpj,row.pl,row.subordinate,row.ratio,row.range,row.minJunior,row.price,row.mezzanine,row.acceleration,row.packageStatus,row.gaps,row.fundosnetUrl]);
    const quote = value => '"' + String(value ?? "").replaceAll('"','""') + '"';
    const csv = [headers, ...rows].map(row => row.map(quote).join(";")).join("\n");
    const blob = new Blob(["\ufeff" + csv], {type:"text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob), anchor = document.createElement("a");
    anchor.href = url; anchor.download = "curadoria_flagship.csv"; document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  };
  category.addEventListener("change", () => { state.category = category.value; state.page = 0; render(); });
  search.addEventListener("input", () => { state.query = search.value; state.page = 0; render(); });
  pager.querySelector("[data-flag-prev]").addEventListener("click", () => { state.page = Math.max(0, state.page - 1); renderTable(); });
  pager.querySelector("[data-flag-next]").addEventListener("click", () => { state.page += 1; renderTable(); });
  root.querySelector("[data-flag-csv]").addEventListener("click", downloadCsv);
  render();
}

function taxonomyApp(DATA) {
  const root = document.getElementById("taxonomy-level-explorer");
  const level = root.querySelector("[data-tax-level]");
  const type = root.querySelector("[data-tax-type]");
  const competence = root.querySelector("[data-tax-competence]");
  const chart = root.querySelector("[data-tax-chart]");
  const tbody = root.querySelector("tbody");
  const caption = root.querySelector("[data-tax-caption]");
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[character]));
  const n = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const money = value => n(value) === null
    ? "N/D"
    : Math.abs(n(value)) < 1e9
      ? "R$ " + (n(value) / 1e6).toLocaleString("pt-BR", {minimumFractionDigits: 0, maximumFractionDigits: 1}) + " mi"
      : "R$ " + (n(value) / 1e9).toLocaleString("pt-BR", {minimumFractionDigits: 1, maximumFractionDigits: 1}) + " bi";
  const pct = value => n(value) === null
    ? "N/D"
    : (n(value) * 100).toLocaleString("pt-BR", {minimumFractionDigits: 1, maximumFractionDigits: 1}) + "%";
  const levelLabels = {
    foco_analitico: "Foco analítico",
    tabela_ii_analitica: "Tabela II analítica",
    taxonomia_funcional_n1: "Taxonomia funcional N1",
    taxonomia_funcional_n2: "Taxonomia funcional N2",
  };
  const values = field => [...new Set(DATA.map((row) => row[field]))];
  level.innerHTML = values("level").map((value) => `<option value="${esc(value)}">${esc(levelLabels[value] || value)}</option>`).join("");
  type.innerHTML = values("type").map((value) => `<option value="${esc(value)}">${esc(value)}</option>`).join("");
  competence.innerHTML = values("competence").sort().reverse().map((value) => `<option value="${esc(value)}">${esc(value)}</option>`).join("");
  level.value = values("level").includes("foco_analitico") ? "foco_analitico" : values("level")[0];
  type.value = values("type").includes("Outros") ? "Outros" : values("type")[0];
  const rows = () => DATA
    .filter((row) => row.level === level.value && row.type === type.value && row.competence === competence.value)
    .sort((a, b) => b.pl - a.pl);
  const render = () => {
    const scoped = rows();
    caption.textContent = `${levelLabels[level.value] || level.value} · ${type.value} · ${competence.value} · ${scoped.length} categorias.`;
    chart.innerHTML = scoped.map((row) => `<article class="tax-bar">
      <div><strong>${esc(row.category)}</strong><span>${money(row.pl)} · ${pct(row.shareType)} do tipo</span></div>
      <div class="tax-track" aria-label="${esc(row.category + ": " + pct(row.shareType))}"><i style="width:${Math.max(0, Math.min(100, Number(row.shareType || 0) * 100))}%"></i></div>
    </article>`).join("") || `<p class="tax-empty">Sem categorias para esta combinação.</p>`;
    tbody.innerHTML = scoped.map((row) => `<tr>
      <td>${esc(row.category)}</td><td class="num">${row.funds.toLocaleString("pt-BR")}</td>
      <td class="num">${money(row.pl)}</td><td class="num">${pct(row.shareType)}</td>
      <td class="num">${pct(row.shareTotal)}</td>
    </tr>`).join("") || `<tr><td colspan="5">Sem categorias para esta combinação.</td></tr>`;
  };
  [level, type, competence].forEach((control) => control.addEventListener("change", render));
  render();
}

function clientRuntime(data) {
  const serialized = JSON.stringify(data).replace(/</g, "\\u003c");
  return `<script type="application/json" id="provider-flow-data">${serialized}<\/script>
<script>(()=>{const compact=JSON.parse(document.getElementById("provider-flow-data").textContent);const expanded=(${expandCompactViews.toString()})(compact);const taxonomy=(${expandCompactTaxonomy.toString()})(compact.taxonomy);const flagships=(${expandCompactFlagships.toString()})(compact.flagships);(${browserApp.toString()})(expanded);(${taxonomyApp.toString()})(taxonomy);(${flagshipApp.toString()})(flagships)})();<\/script>`;
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
    #taxonomy-level-explorer,#flagship-curation-explorer{--flag-bg:var(--background,#FFFFFF);--flag-fg:var(--foreground,#151515);--flag-muted:var(--muted-foreground,#73787D);--flag-border:var(--border,#D7DADD);--flag-pale:var(--accent,#F5F6F7);margin-top:54px;padding-top:28px;border-top:2px solid var(--flag-fg);color:var(--flag-fg);font-family:Arial,sans-serif}
    #taxonomy-level-explorer .tax-heading h2{font-size:22px;line-height:1.15;margin:0 0 5px;letter-spacing:-.02em}
    #taxonomy-level-explorer .tax-heading p{margin:0;color:var(--flag-muted);font-size:14px}
    #taxonomy-level-explorer .tax-controls{display:flex;gap:12px;align-items:end;margin:18px 0 14px;flex-wrap:wrap}
    #taxonomy-level-explorer label{display:grid;gap:4px;color:var(--flag-muted)}
    #taxonomy-level-explorer select{font:inherit;border:1px solid var(--flag-border);background:var(--flag-bg);color:var(--flag-fg);border-radius:4px;padding:7px 9px}
    #taxonomy-level-explorer .tax-caption{color:var(--flag-muted);font-size:13px;margin-bottom:12px}
    #taxonomy-level-explorer .tax-chart{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px 20px}
    #taxonomy-level-explorer .tax-bar{display:grid;gap:5px}
    #taxonomy-level-explorer .tax-bar>div:first-child{display:flex;justify-content:space-between;gap:12px;font-size:12px}
    #taxonomy-level-explorer .tax-bar span{color:var(--flag-muted);white-space:nowrap}
    #taxonomy-level-explorer .tax-track{height:8px;background:var(--flag-pale);overflow:hidden}
    #taxonomy-level-explorer .tax-track i{display:block;height:100%;background:#EC7000}
    #taxonomy-level-explorer table{border-collapse:collapse;width:100%;margin-top:20px;font-size:12px}
    #taxonomy-level-explorer th,#taxonomy-level-explorer td{text-align:left;padding:8px 7px;border-bottom:1px solid var(--flag-border)}
    #taxonomy-level-explorer th{color:var(--flag-muted)}
    #taxonomy-level-explorer td.num,#taxonomy-level-explorer th.num{text-align:right;white-space:nowrap}
    #flagship-curation-explorer .flag-heading h2{font-size:22px;line-height:1.15;margin:0 0 5px;letter-spacing:-.02em}
    #flagship-curation-explorer .flag-heading p{margin:0;color:var(--flag-muted);font-size:14px}
    #flagship-curation-explorer .flag-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:18px 0}
    #flagship-curation-explorer .flag-metric{border:1px solid var(--flag-border);padding:12px 13px}
    #flagship-curation-explorer .flag-metric strong{display:block;font-size:24px;line-height:1}
    #flagship-curation-explorer .flag-metric span{display:block;color:var(--flag-muted);font-size:12px;margin-top:6px}
    #flagship-curation-explorer .flag-controls{display:flex;gap:12px;align-items:end;margin:0 0 14px;flex-wrap:wrap}
    #flagship-curation-explorer label{display:grid;gap:4px;color:var(--flag-muted)}
    #flagship-curation-explorer input,#flagship-curation-explorer select,#flagship-curation-explorer button{font:inherit;border:1px solid var(--flag-border);background:var(--flag-bg);color:var(--flag-fg);border-radius:4px;padding:7px 9px}
    #flagship-curation-explorer .flag-search{flex:1;min-width:240px}
    #flagship-curation-explorer button{cursor:pointer;margin-left:auto}
    #flagship-curation-explorer .flag-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px;align-items:start}
    #flagship-curation-explorer .flag-range{min-width:0}
    #flagship-curation-explorer .flag-range h3{display:flex;justify-content:space-between;align-items:center;margin:0;padding:8px 9px;background:var(--range-color);font-size:12px}
    #flagship-curation-explorer .flag-range h3 b{font-size:11px}
    #flagship-curation-explorer .flag-card{border:1px solid var(--flag-border);border-top:0;padding:9px;min-height:82px;display:grid;gap:4px;background:var(--flag-bg)}
    #flagship-curation-explorer .flag-card:nth-child(even){background:var(--flag-pale)}
    #flagship-curation-explorer .flag-card strong{font-size:12px;line-height:1.2}
    #flagship-curation-explorer .flag-card span{font-size:11px;font-weight:700}
    #flagship-curation-explorer .flag-card small{color:var(--flag-muted);font-size:10px;line-height:1.2}
    #flagship-curation-explorer .flag-empty{font-size:11px;color:var(--flag-muted);padding:8px;margin:0;border:1px solid var(--flag-border);border-top:0}
    #flagship-curation-explorer .flag-caption{margin-top:22px;color:var(--flag-muted);font-size:13px}
    #flagship-curation-explorer table{border-collapse:collapse;width:100%;margin-top:8px;font-size:12px}
    #flagship-curation-explorer th,#flagship-curation-explorer td{text-align:left;padding:8px 7px;border-bottom:1px solid var(--flag-border);vertical-align:top}
    #flagship-curation-explorer th{color:var(--flag-muted)}
    #flagship-curation-explorer td.num,#flagship-curation-explorer th.num{text-align:right;white-space:nowrap}
    #flagship-curation-explorer td small{color:var(--flag-muted)}
    #flagship-curation-explorer details summary{cursor:pointer;color:var(--flag-fg)}
    #flagship-curation-explorer .flag-sources{display:grid;gap:4px;margin-top:6px;min-width:220px;color:var(--flag-muted)}
    #flagship-curation-explorer .flag-sources a{color:var(--flag-fg)}
    #flagship-curation-explorer .flag-pager{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-top:10px;color:var(--flag-muted)}
    @media(max-width:720px){#provider-flow-explorer .optional{display:none}#provider-flow-explorer [data-chart]{min-height:260px}#provider-flow-explorer .metric{font-size:22px}#provider-flow-explorer .node-label{font-size:13px}#provider-flow-explorer th,#provider-flow-explorer td{padding:7px 4px}}
    @media(max-width:980px){#flagship-curation-explorer .flag-grid{grid-template-columns:repeat(3,minmax(0,1fr))}#flagship-curation-explorer .flag-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:620px){#taxonomy-level-explorer .tax-chart{grid-template-columns:1fr}#flagship-curation-explorer .flag-grid{grid-template-columns:1fr}#flagship-curation-explorer .flag-metrics{grid-template-columns:1fr}#flagship-curation-explorer table{font-size:11px}}
    @media(prefers-reduced-motion:reduce){#provider-flow-explorer .flow-link{transition:none}}
  </style>
  <header class="flow-heading"><h2>Movimentação de prestadores da indústria de FIDCs</h2><p>Selecione um fluxo para abrir os fundos, compare o PL nas duas datas e copie a visão para o Office.</p></header>
  <div class="flow-controls" aria-label="Controles da visualização">
    <div class="view-switch" aria-label="Visão">
      <button type="button" data-view="admin" aria-pressed="true">Administração</button>
      <button type="button" data-view="gestor" aria-pressed="false">Gestão</button>
      <button type="button" data-view="custodiante" aria-pressed="false">Custódia</button>
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
<section id="taxonomy-level-explorer" aria-labelledby="taxonomy-level-title">
  <header class="tax-heading"><h2 id="taxonomy-level-title">Taxonomia reclassificada por nível</h2><p>Os quatro níveis analíticos permanecem disponíveis para comparar composição, PL e participação dentro de cada tipo.</p></header>
  <div class="tax-controls">
    <label>Nível<select data-tax-level aria-label="Nível de taxonomia"></select></label>
    <label>Tipo<select data-tax-type aria-label="Tipo ANBIMA reclassificado"></select></label>
    <label>Competência<select data-tax-competence aria-label="Competência"></select></label>
  </div>
  <div class="tax-caption" data-tax-caption aria-live="polite"></div>
  <div class="tax-chart" data-tax-chart></div>
  <table aria-label="Categorias do nível de taxonomia selecionado">
    <thead><tr><th>Categoria</th><th class="num">Fundos</th><th class="num">PL</th><th class="num">% do tipo</th><th class="num">% da indústria</th></tr></thead>
    <tbody></tbody>
  </table>
</section>
<section id="flagship-curation-explorer" aria-labelledby="flagship-curation-title">
  <header class="flag-heading"><h2 id="flagship-curation-title">Curadoria comparável dos fundos flagship</h2><p>PL e subordinação atual são calculados por CNPJ. Mínimos, VNUs, mezanino e eventos reproduzem somente os documentos curados.</p></header>
  <div class="flag-metrics">
    <div class="flag-metric"><strong>${data.flagships.summary.families}</strong><span>famílias flagship</span></div>
    <div class="flag-metric"><strong>${data.flagships.summary.current}/${data.flagships.summary.cnpjs}</strong><span>CNPJs com subordinação atual</span></div>
    <div class="flag-metric"><strong>${data.flagships.summary.minJunior}</strong><span>mínimos júnior localizados</span></div>
    <div class="flag-metric"><strong>${data.flagships.summary.price}</strong><span>preços/VNUs localizados</span></div>
  </div>
  <div class="flag-controls">
    <label>Categoria<select data-flag-category aria-label="Categoria flagship"></select></label>
    <label class="flag-search">Buscar fundo, família ou CNPJ<input data-flag-search type="search" placeholder="Ex.: Cloudwalk Bela, Veículos, 62.393.679/0001-83"></label>
    <button type="button" data-flag-csv>Exportar CSV</button>
  </div>
  <div class="flag-grid" data-flag-grid aria-label="Famílias por faixa de subordinação atual"></div>
  <div class="flag-caption" data-flag-caption aria-live="polite"></div>
  <table aria-label="Curadoria documental dos CNPJs flagship">
    <thead><tr><th>Fundo / família</th><th>CNPJ</th><th class="num">PL atual</th><th class="num">Subord. atual</th><th>Mínimo júnior</th><th>Preço/VNU</th><th>Mezanino</th><th>Vencimento antecipado / avaliação</th><th>Status e lacunas</th><th>Rastreabilidade</th></tr></thead>
    <tbody></tbody>
  </table>
  <div class="flag-pager" data-flag-pager><button type="button" data-flag-prev>Anterior</button><span>0 / 0</span><button type="button" data-flag-next>Próxima</button></div>
</section>
${clientRuntime(data)}`;
}

function standaloneHtml(data) {
  return `<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"><title>Explorador da indústria de FIDCs</title></head>
<body style="margin:0;padding:24px;background:#FFFFFF">${fragmentHtml(data, true)}</body>
</html>`;
}

async function main() {
  const args = argsFrom(process.argv.slice(2));
  const payloadPath = path.resolve(String(args.payload || DEFAULT_PAYLOAD));
  const htmlPath = path.resolve(
    String(args.html || path.join(ROOT, "outputs/provider_flows_explorer.html")),
  );
  const fragmentPath = args.fragment ? path.resolve(String(args.fragment)) : "";
  const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
  const data = viewModels(payload);
  const taxonomy = taxonomyModels(payload);
  const flagships = flagshipModels(payload);
  validateViews(data);
  validateTaxonomy(taxonomy);
  validateFlagships(flagships);
  const compact = {
    ...compactViews(data),
    taxonomy: compactTaxonomy(taxonomy),
    flagships: compactFlagships(flagships),
  };
  const expanded = expandCompactViews(compact);
  const expandedTaxonomy = expandCompactTaxonomy(compact.taxonomy);
  const expandedFlagships = expandCompactFlagships(compact.flagships);
  if (!isDeepStrictEqual(expanded, data)) {
    throw new Error("O esquema compacto não preservou integralmente o view-model");
  }
  if (!isDeepStrictEqual(expandedTaxonomy, taxonomy)) {
    throw new Error("O esquema compacto não preservou integralmente a taxonomia");
  }
  if (!isDeepStrictEqual(expandedFlagships, flagships)) {
    throw new Error("O esquema compacto não preservou integralmente a curadoria flagship");
  }
  validateViews(expanded);
  validateTaxonomy(expandedTaxonomy);
  validateFlagships(expandedFlagships);
  await fs.mkdir(path.dirname(htmlPath), { recursive: true });
  await fs.writeFile(htmlPath, standaloneHtml(compact), "utf8");
  if (fragmentPath) {
    await fs.mkdir(path.dirname(fragmentPath), { recursive: true });
    await fs.writeFile(fragmentPath, fragmentHtml(compact, false), "utf8");
  }
  process.stdout.write(`${htmlPath}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
