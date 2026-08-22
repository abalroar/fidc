import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = process.cwd();
const DATA_DIR = path.join(ROOT, "data", "solfacil");
const OUTPUT_DIR = path.join(ROOT, "outputs", "solfacil");
const PREVIEW_DIR = path.join(ROOT, "tmp", "solfacil_excel_previews");
const OUTPUT = path.join(OUTPUT_DIR, "Solfacil_CRI_FIDC_20260822.xlsx");

const COLORS = {
  black: "#171717",
  dark: "#3C3C3C",
  mid: "#707070",
  line: "#D7D7D7",
  light: "#F2F2F2",
  pale: "#FAFAFA",
  white: "#FFFFFF",
  orange: "#E46C0A",
  orangePale: "#FCE8D5",
};

const SHEETS = [
  ["00_Painel", "00_painel.csv", "O programa reúne originação, warehouses FIDC, take-outs CRI e investidores. Os indicadores abaixo preservam perímetro e data-base."],
  ["01_Veiculos", "01_veiculos.csv", "Cada linha identifica um veículo e sua última competência pública. PL e saldo de CRI aparecem lado a lado sem misturar datas."],
  ["02_Series", "02_series.csv", "A espinha dorsal contém todas as classes FIDC e séries CRI confirmadas nos documentos. Séries privadas permanecem separadas das públicas."],
  ["03_Elegibilidade", "03_elegibilidade.csv", "Os critérios estão na mesma régua para mostrar onde o CRI aperta o pool. Limite contratual e preço efetivo ocupam colunas distintas."],
  ["04_Concentracao", "04_concentracao.csv", "Limites contratuais e concentração observada usam colunas separadas. O cap ANBIMA é classificatório e não substitui o contrato."],
  ["05_Prazos_WAM", "05_prazos_wam.csv", "Teto de WAM, prazo do recebível e prazo legal do veículo aparecem na mesma escala. WAM observado fica n/d quando o tape não é público."],
  ["06_Waterfall", "06_waterfall.csv", "A ordem de caixa mostra quando a estrutura paga por metas e quando vira sequencial. O resumo preserva os gatilhos por veículo."],
  ["06b_Waterfall_Visual", "06b_waterfall_visual.csv", "Os dois regimes ficam lado a lado em blocos de células editáveis. O diagrama é uma síntese; a redação por veículo está na aba anterior."],
  ["07_Subordinada", "07_subordinada.csv", "A saída da subordinada depende de pisos, coberturas, quóruns e ausência de eventos. Pagamentos observados ficam n/d sem histórico público completo por classe."],
  ["08_PDD", "08_pdd.csv", "A matriz separa a grade contratual da PDD observada. A razão PDD sobre saldo acima de 90 dias sinaliza o possível efeito vagão."],
  ["09_Eventos", "09_eventos.csv", "Cada evento liga gatilho, parâmetro, consequência e cura. A existência da cláusula não prova que o evento ocorreu."],
  ["10_Subscritores", "10_subscritores.csv", "Distribuição na emissão e posição corrente seguem perímetros distintos. Zeros de uma oferta ainda aberta não viram ausência de investidores."],
  ["11_Matriz_FIDC_CRI", "11_matriz_fidc_cri.csv", "Cedeu exige evidência documental; Pode ceder resulta do cruzamento de mandato e critérios. O estado inferido não confirma uma fita concreta."],
  ["11b_Cessoes", "11b_cessoes.csv", "A tabela registra apenas cessões documentadas. Preço percentual permanece n/d sem saldo contábil comparável."],
  ["12_Custo_Captacao", "12_custo_captacao.csv", "Taxas contratadas ficam visíveis e o all-in permanece n/d sem curvas datadas e custos completos. A lacuna evita equivalência estimada."],
  ["13_Cronograma_Pagamentos", "13_cronograma_pagamentos.csv", "Realizado vem do Informe Mensal e Projetado identifica a curva contratual não localizada. Os gráficos nativos usam apenas saldos realizados."],
  ["14_Antes_Depois", "14_antes_depois.csv", "A janela t−3 a t+3 acompanha PL, carteira, PDD e atraso em torno da cessão. Sem tape por CCB, seleção do pool e mudança de denominador não se separam."],
  ["15_FIDC_vs_CRI", "15_fidc_vs_cri.csv", "O veredito aponta onde cada instrumento tem vantagem observável e quais dados faltam. Campos n/d não são tratados como evidência favorável."],
  ["16_Conflitos", "16_conflitos.csv", "Toda divergência conserva os dois valores e a decisão adotada. Laranja marca conflitos reconciliados, sem ocultar a fonte descartada."],
  ["17_Fontes", "17_fontes.csv", "O inventário mapeia cada fonte_id para documento, URL, data-base e trecho. Fontes não obtidas continuam registradas como lacuna."],
  ["18_Metodologia", "18_metodologia.csv", "As fórmulas e qualificadores permitem reproduzir cada métrica calculada. Nenhuma fórmula converte n/d em zero."],
  ["19_Glossario", "19_glossario.csv", "Os termos usados no material aparecem em português direto. Cada definição descreve a função econômica do conceito."],
];

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else {
      if (ch === '"') quoted = true;
      else if (ch === ',') { row.push(field); field = ""; }
      else if (ch === '\n') { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
      else field += ch;
    }
  }
  if (field.length || row.length) { row.push(field.replace(/\r$/, "")); rows.push(row); }
  return rows.filter((r) => r.some((v) => v !== ""));
}

function colName(index) {
  let n = index + 1, name = "";
  while (n > 0) { const rem = (n - 1) % 26; name = String.fromCharCode(65 + rem) + name; n = Math.floor((n - 1) / 26); }
  return name;
}

function typedValue(value, header) {
  if (value === "n/d" || value === "") return value || "n/d";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value) && /(data|competencia|vencimento|inicio|ocorrencia|base)/i.test(header)) {
    return new Date(`${value}T00:00:00Z`);
  }
  const textColumns = /(cnpj|isin|fonte|status|nota|nome|serie|camada|tipo|indexador|taxa_|rating|situacao|descricao|redacao|regime|ordem_|prioridade|reserva|evento|quorum|formula|unidade|documento|url|caminho|sha|observacao|leitura|definicao|metrica|indicador_ou_etapa|data_base_[AB]|valor_fonte|valor_adotado|parametro|prazo_de_cura|quem_|restricao|vedacoes|ativo|colocacao|retida|saque|testes|pisos|indices|trava|tratamento|base_de_incidencia|efeito_vagao|titulares|coordenadores|fonte_da_posicao|fidc$|cri_evento|evidencia|vantagem_real|o_que_falta)/i;
  if (!textColumns.test(header) && /^-?\d+(?:\.\d+)?$/.test(value)) return Number(value);
  return value;
}

function widthFor(header, values) {
  if (/fonte_id/i.test(header)) return 34;
  if (/(nota|descricao|redacao|literal|vedacoes|testes|leitura|definicao|qualificador|formula|como_funciona|evidencia|falta|justificativa|observacao|url_ou_caminho)/i.test(header)) return 42;
  if (/(nome|administrador|gestor|custodiante|agente|auditor|securitizadora|documento)/i.test(header)) return 28;
  if (/(data|competencia|vencimento)/i.test(header)) return 13;
  if (/(status|tipo|camada|serie|indexador|rating|colocacao)/i.test(header)) return 19;
  const longest = Math.max(header.length, ...values.slice(0, 40).map((v) => String(v ?? "").length));
  return Math.max(11, Math.min(24, longest + 2));
}

function formatColumn(sheet, header, col, rowCount) {
  const range = sheet.getRange(`${colName(col)}6:${colName(col)}${rowCount + 5}`);
  if (/(data|competencia|vencimento|inicio|ocorrencia)/i.test(header)) range.setNumberFormat("yyyy-mm-dd");
  else if (/(pct|concentracao|subordinacao|pdd_|razao_|folga_vs_limite|cap_|preco_max|preco_efetivo|retorno)/i.test(header)) range.setNumberFormat("0.0%");
  else if (/R\$mi/i.test(header)) range.setNumberFormat('"R$" #,##0.0');
  else if (/R\$/i.test(header) || /(saldo_inicial|saldo_final|juros_programados|amortizacao_programada|juros_pagos|amortizacao_paga)/i.test(header)) range.setNumberFormat('"R$" #,##0');
  else if (/(bps|qtd_|quantidade|ordem|mob)/i.test(header)) range.setNumberFormat("#,##0");
  else if (/(dias|meses|duration|wam|prazo)/i.test(header)) range.setNumberFormat("#,##0.0");
}

function uniqueDates(rows, vehicle = null) {
  const realized = rows.filter((r) => r.status === "Realizado");
  const expected = new Map();
  for (const row of realized) {
    if (!expected.has(row.veiculo_id)) expected.set(row.veiculo_id, new Set());
    expected.get(row.veiculo_id).add(row.serie);
  }
  const byDate = new Map();
  for (const row of realized) {
    if (vehicle && row.veiculo_id !== vehicle) continue;
    if (!byDate.has(row.competencia)) byDate.set(row.competencia, new Map());
    const byVehicle = byDate.get(row.competencia);
    if (!byVehicle.has(row.veiculo_id)) byVehicle.set(row.veiculo_id, []);
    byVehicle.get(row.veiculo_id).push(row);
  }
  return [...byDate.entries()]
    .filter(([, byVehicle]) => [...byVehicle.entries()].every(([vehicleId, group]) => {
      const present = new Set(group.map((row) => row.serie));
      return present.size === expected.get(vehicleId).size && group.every((row) => row.saldo_final !== "n/d");
    }))
    .map(([date]) => date)
    .sort();
}

function recordDateRange(records) {
  const dates = records
    .flatMap((row) => String(row.data_base || row.competencia || row.data_acesso || "").match(/\d{4}-\d{2}-\d{2}/g) || [])
    .filter((value, index, values) => values.indexOf(value) === index)
    .sort();
  if (!dates.length) return "por linha";
  return dates.length === 1 ? dates[0] : `${dates[0]} a ${dates[dates.length - 1]}`;
}

function addPaymentCharts(sheet, records, headers, dataEndRow) {
  const vehicles = ["CRI_K1", "CRI_K2", "CRI_K3", "CRI_K4", "CRI_V174", "CRI_V177", "Consolidado"];
  const layers = ["Super Sênior", "Sênior", "Mezanino", "Subordinada/Júnior"];
  const canonicalLayer = (value) => {
    const s = String(value).toLowerCase();
    if (s.includes("super")) return "Super Sênior";
    if (s.includes("sênior") || s.includes("senior")) return "Sênior";
    if (s.includes("mezan")) return "Mezanino";
    return "Subordinada/Júnior";
  };
  const startCol = 15;
  const chartCols = [[15, 25], [27, 37]];
  vehicles.forEach((vehicle, idx) => {
    const dates = uniqueDates(records, vehicle === "Consolidado" ? null : vehicle);
    const blockRow = 4 + idx * 35;
    const startCell = sheet.getCell(blockRow, startCol);
    const matrix = [["competencia", ...layers]];
    for (const d of dates) {
      matrix.push([new Date(`${d}T00:00:00Z`), ...layers.map((layer) => {
        const total = records.filter((r) => r.status === "Realizado" && r.competencia === d && (vehicle === "Consolidado" || r.veiculo_id === vehicle) && canonicalLayer(r.camada) === layer && r.saldo_final !== "n/d").reduce((a, r) => a + Number(r.saldo_final || 0), 0);
        return total;
      })]);
    }
    const hasDocumentedDates = matrix.length > 1;
    if (!hasDocumentedDates) matrix.push(["n/d", null, null, null, null]);
    const helper = sheet.getRangeByIndexes(blockRow, startCol, matrix.length, matrix[0].length);
    helper.values = matrix;
    if (hasDocumentedDates) helper.getColumn(0).setNumberFormat("yyyy-mm-dd");
    sheet.getRangeByIndexes(blockRow + 1, startCol + 1, Math.max(1, matrix.length - 1), 4).setNumberFormat('"R$" #,##0,, "mi"');
    helper.format.font = { name: "Aptos", size: 8, color: COLORS.mid };
    helper.format.borders = { preset: "all", style: "thin", color: COLORS.line };
    helper.getRow(0).format = { fill: COLORS.black, font: { name: "Aptos", size: 8, bold: true, color: COLORS.white }, rowHeight: 20, wrapText: true };
    helper.getColumn(0).format.columnWidth = 12;
    for (let c = 1; c < matrix[0].length; c++) helper.getColumn(c).format.columnWidth = 15;
    const chart = sheet.charts.add("ColumnStacked", helper);
    chart.title = `${vehicle} — saldo realizado por camada (R$)${hasDocumentedDates ? "" : " — n/d"}`;
    chart.hasLegend = true;
    chart.legend = { position: "bottom", textStyle: { fontSize: 9, color: COLORS.dark } };
    chart.titleTextStyle.fontSize = 11;
    chart.xAxis = hasDocumentedDates
      ? { axisType: "dateAxis", numberFormatCode: "mmm-yy", textStyle: { fontSize: 8 } }
      : { textStyle: { fontSize: 8 } };
    chart.yAxis = { numberFormatCode: '"R$" #,##0,," mi"', majorGridlines: { style: "solid", fill: COLORS.line, width: 1 }, textStyle: { fontSize: 8 } };
    const fills = [COLORS.orange, COLORS.dark, COLORS.mid, "#B8B8B8"];
    if (chart.series?.items) chart.series.items.forEach((series, i) => { series.fill = fills[i % fills.length]; });
    const pos = chartCols[idx % 2];
    const top = 5 + Math.floor(idx / 2) * 22;
    chart.setPosition(`${colName(pos[0])}${top}`, `${colName(pos[1])}${top + 18}`);
  });
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  const workbook = Workbook.create();

  const loaded = {};
  for (const [sheetName, fileName, reading] of SHEETS) {
    const csvText = await fs.readFile(path.join(DATA_DIR, fileName), "utf8");
    const raw = parseCsv(csvText.replace(/^\uFEFF/, ""));
    const headers = raw[0];
    const values = raw.slice(1).map((row) => headers.map((h, i) => typedValue(row[i] ?? "", h)));
    const records = raw.slice(1).map((row) => Object.fromEntries(headers.map((h, i) => [h, row[i] ?? "n/d"])));
    loaded[sheetName] = { headers, values, records };
    const sheet = workbook.worksheets.add(sheetName);
    sheet.showGridLines = false;
    const lastCol = colName(headers.length - 1);
    sheet.mergeCells(`A1:${lastCol}1`);
    sheet.mergeCells(`A2:${lastCol}2`);
    sheet.mergeCells(`A3:${lastCol}3`);
    sheet.getRange("A1").values = [[sheetName.replace(/_/g, " ")]];
    sheet.getRange("A2").values = [[reading]];
    const sources = [...new Set(records.flatMap((r) => String(r.fonte_id || "").split(" | ")).filter(Boolean))];
    sheet.getRange("A3").values = [[`Data-base: ${recordDateRange(records)} | Fontes: ${sources.slice(0, 5).join("; ")}${sources.length > 5 ? "; ver 17_Fontes" : ""}`]];
    sheet.getRange("A1").format = { fill: COLORS.black, font: { name: "Aptos Display", size: 18, bold: true, color: COLORS.white }, rowHeight: 30, verticalAlignment: "center" };
    sheet.getRange("A2").format = { fill: COLORS.white, font: { name: "Aptos", size: 11, color: COLORS.dark }, rowHeight: 34, wrapText: true, verticalAlignment: "center" };
    sheet.getRange("A3").format = { fill: COLORS.light, font: { name: "Aptos", size: 9, color: COLORS.mid }, rowHeight: 24, wrapText: true, verticalAlignment: "center" };
    const tableMatrix = [headers, ...values];
    sheet.getRange(`A5:${lastCol}${values.length + 5}`).values = tableMatrix;
    const table = sheet.tables.add(`A5:${lastCol}${values.length + 5}`, true, `tbl_${sheetName.replace(/[^A-Za-z0-9_]/g, "_")}`);
    table.style = "TableStyleMedium1";
    table.showBandedRows = true;
    table.showFilterButton = true;
    const headerRange = sheet.getRange(`A5:${lastCol}5`);
    headerRange.format = { fill: COLORS.black, font: { name: "Aptos", size: 9, bold: true, color: COLORS.white }, rowHeight: 34, wrapText: true, verticalAlignment: "center", horizontalAlignment: "left", borders: { preset: "all", style: "thin", color: COLORS.dark } };
    const dataRange = sheet.getRange(`A6:${lastCol}${values.length + 5}`);
    dataRange.format.font = { name: "Aptos", size: 9, color: COLORS.black };
    dataRange.format.verticalAlignment = "top";
    dataRange.format.wrapText = true;
    dataRange.format.borders = { preset: "all", style: "thin", color: COLORS.line };
    for (let c = 0; c < headers.length; c++) {
      const colRange = sheet.getRange(`${colName(c)}5:${colName(c)}${values.length + 5}`);
      colRange.format.columnWidth = widthFor(headers[c], values.map((r) => r[c]));
      formatColumn(sheet, headers[c], c, values.length);
    }
    sheet.freezePanes.freezeRows(5);
    sheet.getRange("A4").values = [[sheetName === "16_Conflitos" ? "Legenda: laranja = divergência reconciliada" : sheetName === "17_Fontes" ? "Legenda: laranja = fonte tentada e não localizada" : sheetName === "08_PDD" ? "Legenda: laranja = PDD / saldo >90d acima de 100%" : ""]];
    sheet.getRange(`A4:${lastCol}4`).format = { font: { name: "Aptos", size: 8, italic: true, color: COLORS.mid }, rowHeight: 16 };
  }

  // Clickable index and program map on the panel.
  const panel = workbook.worksheets.getItem("00_Painel");
  panel.getRange("K5:K26").values = [["Índice clicável"], ...SHEETS.slice(1).map(([name]) => [name])];
  panel.getRange("K5").format = { fill: COLORS.black, font: { bold: true, color: COLORS.white, size: 10 } };
  for (let i = 1; i < SHEETS.length; i++) panel.getRange(`K${5 + i}`).formulas = [[`=HYPERLINK("#'${SHEETS[i][0]}'!A1","${SHEETS[i][0]}")`]];
  panel.getRange("K5:K26").format.columnWidth = 28;
  panel.getRange("K30:N34").values = [
    ["Mapa do programa", "", "", ""],
    ["Originação", "Warehouse FIDC", "Take-out CRI", "Investidores"],
    ["CCBs solares", "Acumula e financia", "Compra pool elegível", "Absorvem camadas"],
    ["1", "2", "3", "4"],
    ["Fonte: METH_COMPARACAO_FIDC_CRI", "", "", ""],
  ];
  panel.getRange("K30:N30").merge(); panel.getRange("K34:N34").merge();
  panel.getRange("K30:N30").format = { fill: COLORS.black, font: { bold: true, color: COLORS.white, size: 11 }, horizontalAlignment: "center" };
  panel.getRange("K31:N33").format = { fill: COLORS.light, font: { bold: true, color: COLORS.black, size: 10 }, borders: { preset: "all", style: "thin", color: COLORS.line }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
  panel.getRange("K31:K33").format.fill = COLORS.orangePale;
  panel.getRange("K30:N34").format.columnWidth = 19;

  // Native comparison chart in 05.
  const term = workbook.worksheets.getItem("05_Prazos_WAM");
  const termRows = loaded["05_Prazos_WAM"].values.length + 5;
  const termChart = term.charts.add("bar", { chartType: "bar", title: "Prazo do recebível e do veículo (meses)", hasLegend: true });
  const termS1 = termChart.series.add("Prazo máximo do recebível");
  termS1.categoryFormula = `'05_Prazos_WAM'!$A$6:$A$${termRows}`; termS1.formula = `'05_Prazos_WAM'!$E$6:$E$${termRows}`; termS1.fill = COLORS.orange;
  const termS2 = termChart.series.add("Prazo do veículo / série mais longa");
  termS2.categoryFormula = `'05_Prazos_WAM'!$A$6:$A$${termRows}`; termS2.formula = `'05_Prazos_WAM'!$G$6:$G$${termRows}`; termS2.fill = COLORS.mid;
  termChart.titleTextStyle.fontSize = 12; termChart.hasLegend = true;
  termChart.xAxis = { textStyle: { fontSize: 8 } }; termChart.yAxis = { numberFormatCode: "0", majorGridlines: { style: "solid", fill: COLORS.line, width: 1 }, textStyle: { fontSize: 8 } };
  termChart.setPosition("P5", "AB28");

  // Native PDD comparison.
  const pdd = workbook.worksheets.getItem("08_PDD");
  const pddRows = loaded["08_PDD"].values.length + 5;
  const pddChart = pdd.charts.add("column", { chartType: "column", title: "PDD e saldo acima de 90 dias (% da carteira)", hasLegend: true });
  const p1 = pddChart.series.add("PDD observada"); p1.categoryFormula = `'08_PDD'!$A$6:$A$${pddRows}`; p1.formula = `'08_PDD'!$M$6:$M$${pddRows}`; p1.fill = COLORS.orange;
  const p2 = pddChart.series.add("Saldo >90d"); p2.categoryFormula = `'08_PDD'!$A$6:$A$${pddRows}`; p2.formula = `'08_PDD'!$N$6:$N$${pddRows}`; p2.fill = COLORS.mid;
  pddChart.yAxis = { numberFormatCode: "0.0%", majorGridlines: { style: "solid", fill: COLORS.line, width: 1 }, textStyle: { fontSize: 8 } };
  pddChart.xAxis = { textStyle: { fontSize: 8 } }; pddChart.titleTextStyle.fontSize = 12; pddChart.setPosition("V5", "AJ27");

  // Cell-native waterfall diagrams.
  const wf = workbook.worksheets.getItem("06b_Waterfall_Visual");
  const wfRecords = loaded["06b_Waterfall_Visual"].records;
  const regimes = [...new Set(wfRecords.map((r) => r.regime))];
  regimes.forEach((regime, idx) => {
    const baseCol = idx === 0 ? 9 : 15;
    wf.getRangeByIndexes(4, baseCol, 1, 5).merge();
    wf.getCell(4, baseCol).values = [[regime]];
    wf.getRangeByIndexes(4, baseCol, 1, 5).format = { fill: idx === 0 ? COLORS.orange : COLORS.black, font: { color: COLORS.white, bold: true, size: 11 }, horizontalAlignment: "center", verticalAlignment: "center" };
    wfRecords.filter((r) => r.regime === regime).forEach((r, j) => {
      const block = wf.getRangeByIndexes(6 + j * 3, baseCol, 2, 5); block.merge(); block.values = [[`${r.ordem}. ${r.degrau}`]];
      block.format = { fill: j % 2 === 0 ? COLORS.light : COLORS.white, font: { color: COLORS.black, bold: j === 0, size: 10 }, borders: { preset: "all", style: "thin", color: COLORS.line }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
    });
  });

  // Payment curves: seven native stacked charts driven by the CSV-derived helper grids.
  const schedule = workbook.worksheets.getItem("13_Cronograma_Pagamentos");
  addPaymentCharts(schedule, loaded["13_Cronograma_Pagamentos"].records, loaded["13_Cronograma_Pagamentos"].headers, loaded["13_Cronograma_Pagamentos"].values.length + 5);

  // Before/after native line chart.
  const before = workbook.worksheets.getItem("14_Antes_Depois");
  const beforeRecords = loaded["14_Antes_Depois"].records;
  const groups = [...new Set(beforeRecords.map((r) => `${r.fidc} / ${r.cri_evento}`))];
  const mobs = [-3, -2, -1, 0, 1, 2, 3];
  const beforeMatrix = [["mob", ...groups, "Evento t=0"]];
  const maxPdd = Math.max(...beforeRecords.map((r) => Number(r.pdd_pct_carteira || 0)));
  for (const mob of mobs) {
    beforeMatrix.push([mob, ...groups.map((group) => {
      const [fidc, cri] = group.split(" / ");
      const hit = beforeRecords.find((r) => r.fidc === fidc && r.cri_evento === cri && Number(r.mob) === mob);
      return hit ? Number(hit.pdd_pct_carteira) : null;
    }), mob === 0 ? maxPdd * 1.08 : null]);
  }
  const beforeHelper = before.getRange(`R5:${colName(17 + beforeMatrix[0].length - 1)}${4 + beforeMatrix.length}`);
  beforeHelper.values = beforeMatrix;
  beforeHelper.format = { font: { name: "Aptos", size: 8, color: COLORS.mid }, borders: { preset: "all", style: "thin", color: COLORS.line }, horizontalAlignment: "center", verticalAlignment: "center" };
  beforeHelper.getRow(0).format = { fill: COLORS.black, font: { name: "Aptos", size: 8, bold: true, color: COLORS.white }, rowHeight: 30, wrapText: true };
  beforeHelper.getColumn(0).format.columnWidth = 7;
  for (let c = 1; c < beforeMatrix[0].length; c++) {
    beforeHelper.getColumn(c).format.columnWidth = c === beforeMatrix[0].length - 1 ? 12 : 16;
    before.getRangeByIndexes(5, 17 + c, beforeMatrix.length - 1, 1).setNumberFormat("0.0%");
  }
  const beforeChart = before.charts.add("line", beforeHelper);
  beforeChart.title = "PDD em torno das cessões (t=0)"; beforeChart.hasLegend = true;
  if (beforeChart.series?.items) beforeChart.series.items.forEach((series, i) => { series.fill = i === beforeChart.series.items.length - 1 ? COLORS.black : [COLORS.orange, "#F2A15B", COLORS.dark, COLORS.mid][i % 4]; });
  beforeChart.yAxis = { numberFormatCode: "0.0%", majorGridlines: { style: "solid", fill: COLORS.line, width: 1 }, textStyle: { fontSize: 8 } };
  beforeChart.xAxis = { textStyle: { fontSize: 8 } }; beforeChart.titleTextStyle.fontSize = 12; beforeChart.setPosition("Y5", "AM28");

  // Three conditional formats, each with a visible legend in row 4.
  const conflicts = workbook.worksheets.getItem("16_Conflitos");
  const conflictCol = loaded["16_Conflitos"].headers.indexOf("conflito");
  conflicts.getRange(`${colName(conflictCol)}6:${colName(conflictCol)}${loaded["16_Conflitos"].values.length + 5}`).conditionalFormats.add("containsText", { text: "sim", format: { fill: COLORS.orangePale, font: { bold: true, color: COLORS.black } } });
  const sources = workbook.worksheets.getItem("17_Fontes");
  const sourceStatusCol = loaded["17_Fontes"].headers.indexOf("status_obtencao");
  sources.getRange(`${colName(sourceStatusCol)}6:${colName(sourceStatusCol)}${loaded["17_Fontes"].values.length + 5}`).conditionalFormats.add("containsText", { text: "não localizado", format: { fill: COLORS.orangePale, font: { bold: true, color: COLORS.black } } });
  const ratioCol = loaded["08_PDD"].headers.indexOf("razao_pdd_sobre_90d");
  pdd.getRange(`${colName(ratioCol)}6:${colName(ratioCol)}${loaded["08_PDD"].values.length + 5}`).conditionalFormats.add("cellIs", { operator: "greaterThan", formula: 1, format: { fill: COLORS.orangePale, font: { bold: true, color: COLORS.black } } });

  // Compact verification before export.
  const inspection = await workbook.inspect({ kind: "sheet,table,drawing", maxChars: 12000, tableMaxRows: 3, tableMaxCols: 5 });
  await fs.writeFile(path.join(PREVIEW_DIR, "inspection.ndjson"), inspection.ndjson, "utf8");
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "formula error scan" });
  await fs.writeFile(path.join(PREVIEW_DIR, "formula-errors.ndjson"), errors.ndjson, "utf8");

  for (const [sheetName] of SHEETS) {
    const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.7, format: "png" });
    await fs.writeFile(path.join(PREVIEW_DIR, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
  }
  const scheduleCharts = await workbook.render({ sheetName: "13_Cronograma_Pagamentos", range: "P1:AL90", scale: 1, format: "png" });
  await fs.writeFile(path.join(PREVIEW_DIR, "13_Cronograma_Pagamentos_charts.png"), new Uint8Array(await scheduleCharts.arrayBuffer()));
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(OUTPUT);
  console.log(JSON.stringify({ output: OUTPUT, sheets: SHEETS.length, tables: SHEETS.length }));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
