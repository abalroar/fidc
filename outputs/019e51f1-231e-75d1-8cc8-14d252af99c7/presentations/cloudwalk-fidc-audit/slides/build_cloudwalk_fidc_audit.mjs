import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const artifactPath = "/Users/matheusjprates/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";
const art = await import(artifactPath);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const workspace = path.resolve(__dirname, "..");
const outputDir = path.join(workspace, "output");
await fs.mkdir(outputDir, { recursive: true });

const FINAL_PPTX = path.join(outputDir, "cloudwalk-fidcs-auditoria-clean.pptx");
const AUDIT_MD = path.join(outputDir, "cloudwalk-fidcs-audit-ledger.md");

const W = 1600;
const H = 900;

const C = {
  black: "#06080D",
  nearBlack: "#11141A",
  orange: "#F58220",
  orange2: "#FFB366",
  gray900: "#20242A",
  gray700: "#4F5661",
  gray500: "#858B94",
  gray300: "#C9CED6",
  gray200: "#E7E9ED",
  gray100: "#F4F5F7",
  white: "#FFFFFF",
  green: "#2E7D32",
  red: "#A52A2A",
  blue: "#214B7A",
};

function addShape(slide, { left, top, width, height, fill = C.white, line = C.gray300, radius = false }) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left, top, width, height },
    fill,
    line: line ? { fill: line, width: 1 } : { fill: { type: "none" } },
  });
}

function addText(slide, text, { left, top, width, height, size = 22, color = C.black, bold = false, align = "left", valign = "top", fill = { type: "none" }, line = null, italic = false }) {
  const shape = slide.shapes.add({
    geometry: "rect",
    position: { left, top, width, height },
    fill,
    line: line ? { fill: line, width: 1 } : { fill: { type: "none" } },
  });
  shape.text.set(text);
  shape.text.fontSize = size;
  shape.text.color = color;
  shape.text.bold = bold;
  shape.text.italic = italic;
  shape.text.alignment = align;
  shape.text.verticalAlignment = valign;
  return shape;
}

function addHeader(slide, title, kicker = "CloudWalk | FIDCs") {
  addShape(slide, { left: 44, top: 34, width: 66, height: 44, fill: C.black, line: C.black, radius: true });
  addText(slide, "itau", { left: 51, top: 42, width: 35, height: 15, size: 11, color: C.white, bold: true, align: "center", valign: "middle" });
  addText(slide, "BBA", { left: 83, top: 42, width: 25, height: 15, size: 11, color: C.white, bold: true, align: "center", valign: "middle" });
  addText(slide, title, { left: 138, top: 34, width: 1320, height: 48, size: 29, bold: true, valign: "middle" });
  addText(slide, kicker, { left: 138, top: 80, width: 700, height: 28, size: 14, color: C.gray700 });
  slide.shapes.add({
    geometry: "rect",
    position: { left: 44, top: 116, width: 1510, height: 2 },
    fill: C.orange,
    line: { fill: { type: "none" } },
  });
}

function addFooter(slide, page, note = "Fonte: TomaConta FIDCs / IME CVM; regulamentos e termos de emissao locais; deep dive CloudWalk. Valores em R$ nominais.") {
  addText(slide, note, { left: 58, top: 830, width: 1200, height: 24, size: 12, color: C.gray700 });
  slide.shapes.add({ geometry: "rect", position: { left: 44, top: 861, width: 1510, height: 1.5 }, fill: C.orange, line: { fill: { type: "none" } } });
  addText(slide, "CloudWalk |", { left: 58, top: 866, width: 150, height: 24, size: 14, bold: true });
  addText(slide, "Corporativo | Interno", { left: 58, top: 887, width: 180, height: 14, size: 10, color: C.gray700 });
  addShape(slide, { left: 1475, top: 851, width: 48, height: 38, fill: C.black, line: C.black, radius: true });
  addText(slide, "itau", { left: 1481, top: 860, width: 26, height: 12, size: 8, color: C.white, bold: true, align: "center", valign: "middle" });
  addText(slide, "BBA", { left: 1503, top: 860, width: 18, height: 12, size: 8, color: C.white, bold: true, align: "center", valign: "middle" });
  addText(slide, String(page).padStart(2, "0"), { left: 1531, top: 862, width: 28, height: 22, size: 11, color: C.gray700, align: "right" });
}

function addSectionTitle(slide, text, x, y, w) {
  addText(slide, text, { left: x, top: y, width: w, height: 36, size: 25, bold: true });
  slide.shapes.add({ geometry: "rect", position: { left: x, top: y + 38, width: w, height: 1 }, fill: C.gray300, line: { fill: { type: "none" } } });
}

function addCallout(slide, number, label, detail, x, y, w, color = C.orange) {
  addShape(slide, { left: x, top: y, width: w, height: 112, fill: C.white, line: C.gray300, radius: true });
  addText(slide, number, { left: x + 18, top: y + 13, width: 150, height: 42, size: 34, bold: true, color });
  addText(slide, label, { left: x + 18, top: y + 55, width: w - 36, height: 24, size: 16, bold: true });
  addText(slide, detail, { left: x + 18, top: y + 79, width: w - 36, height: 25, size: 11.5, color: C.gray700 });
}

function addMiniTag(slide, text, x, y, w, color = C.orange) {
  addShape(slide, { left: x, top: y, width: w, height: 24, fill: color, line: color, radius: true });
  addText(slide, text, { left: x + 7, top: y + 2, width: w - 14, height: 20, size: 11, color: C.white, bold: true, align: "center", valign: "middle" });
}

function table(slide, { x, y, colWidths, rowHeight = 42, headerHeight = 38, headers, rows, fontSize = 13, headerFontSize = 13, totalRows = [], fills = {} }) {
  let cx = x;
  for (let i = 0; i < headers.length; i++) {
    addShape(slide, { left: cx, top: y, width: colWidths[i], height: headerHeight, fill: C.black, line: C.white });
    addText(slide, headers[i], { left: cx + 8, top: y + 4, width: colWidths[i] - 16, height: headerHeight - 8, size: headerFontSize, color: C.white, bold: true, valign: "middle" });
    cx += colWidths[i];
  }
  for (let r = 0; r < rows.length; r++) {
    const top = y + headerHeight + r * rowHeight;
    const isTotal = totalRows.includes(r);
    cx = x;
    for (let c = 0; c < headers.length; c++) {
      const key = `${r}:${c}`;
      const fill = fills[key] || (isTotal ? C.black : (r % 2 === 0 ? C.white : C.gray100));
      addShape(slide, { left: cx, top, width: colWidths[c], height: rowHeight, fill, line: C.white });
      const color = isTotal ? C.white : (fills[`${r}:${c}:color`] || C.black);
      const bold = isTotal || c === 0 || Boolean(fills[`${r}:${c}:bold`]);
      addText(slide, String(rows[r][c] ?? ""), { left: cx + 8, top: top + 4, width: colWidths[c] - 16, height: rowHeight - 8, size: fontSize, color, bold, valign: "middle" });
      cx += colWidths[c];
    }
  }
}

function bulletList(slide, bullets, x, y, w, size = 17, gap = 36, color = C.black) {
  bullets.forEach((b, i) => {
    addText(slide, "•", { left: x, top: y + i * gap, width: 22, height: 24, size, bold: true, color: C.orange });
    addText(slide, b, { left: x + 28, top: y + i * gap - 1, width: w - 28, height: gap + 4, size, color });
  });
}

function horizFlow(slide, items, x, y, w, h) {
  const boxW = (w - (items.length - 1) * 48) / items.length;
  items.forEach((item, i) => {
    const bx = x + i * (boxW + 48);
    addShape(slide, { left: bx, top: y, width: boxW, height: h, fill: item.fill || C.white, line: C.gray300, radius: true });
    addText(slide, item.title, { left: bx + 14, top: y + 14, width: boxW - 28, height: 24, size: 16, bold: true, color: item.titleColor || C.black, valign: "middle" });
    addText(slide, item.body, { left: bx + 14, top: y + 44, width: boxW - 28, height: h - 54, size: 12.5, color: item.color || C.gray700 });
    if (i < items.length - 1) {
      addText(slide, "→", { left: bx + boxW + 9, top: y + h / 2 - 19, width: 30, height: 30, size: 28, color: C.orange, bold: true, align: "center" });
    }
  });
}

const p = art.Presentation.create();

// Slide 1
{
  const slide = p.slides.add({ width: W, height: H });
  slide.background.fill = C.white;
  addHeader(slide, "Auditoria dos FIDCs | correções antes da versão clean");

  addCallout(slide, "3", "inconsistências materiais de volume", "A.I., PI e Bela exigem separação entre oferta pública e Sub/Jr.", 62, 148, 310, C.orange);
  addCallout(slide, "1", "premissa manual crítica", "Spreads dos Big Pictures não foram localizados nos PDFs baixados.", 395, 148, 310, C.orange);
  addCallout(slide, "0", "uso de dedução linear", "Onde há cronograma, a leitura correta é por série e evento, não rateio linear.", 728, 148, 310, C.green);
  addCallout(slide, "6", "fontes regulatórias-chave", "Regulamentos/termos CVM + deep dive local + inputs manuais documentados.", 1061, 148, 310, C.blue);

  addSectionTitle(slide, "Achados e tratamento no output", 62, 300, 1465);
  const rows = [
    ["A.I.", "Deep dive trazia emissão inicial; slide já refletia lote adicional, mas Sub/Jr em R$108 mm não bate.", "Reg. 993693: Sr R$2.245,6 mm; Mez R$347,5 mm; Jr R$90,0 mm.", "Usar última versão e separar oferta pública de cota subordinada."],
    ["PI", "Slide mostra oferta de R$3.141 mm e Sub de R$108 mm, misturando bases.", "Termo 883040: oferta Sr+Mez R$3.141,6 mm; Jr privado R$97,2 mm.", "Stack completo = R$3.238,8 mm se incluir Jr; oferta pública fica R$3.141,6 mm."],
    ["Bela", "Slide usa PL/stack cheio sem deixar claro que Sub/Jr não é volume da oferta.", "Termos 993253/1166893: ofertas R$4,2 bi e R$5,5 bi; Sub é alvo/derivação por 3%.", "Rotular Sub/Jr como alvo de subordinação, não como dado CVM de oferta."],
    ["Big Pictures", "CDI+ aparece como se estivesse no regulamento baixado.", "Deep dive: benchmark no apêndice; spread não localizado nos PDFs baixados.", "Manter CDI+ informado manualmente pelo usuário, com asterisco."],
    ["Antigos", "Kick Ass II/Multibancos exige distinção entre dado histórico, rerratificação e status.", "Deep dive: alteração para R$1,5 bi e rerratificação de DI+1,37%; slide marcava liquidado.", "Mostrar status e usar última rerratificação quando a análise depender de custo."],
  ];
  table(slide, {
    x: 62, y: 356,
    colWidths: [120, 420, 460, 465],
    headerHeight: 42,
    rowHeight: 78,
    headers: ["Tema", "Risco no slide antigo", "Fonte / achado", "Tratamento no deck clean"],
    rows,
    fontSize: 12.2,
    headerFontSize: 13,
  });
  addFooter(slide, 1);
}

// Slide 2
{
  const slide = p.slides.add({ width: W, height: H });
  slide.background.fill = C.white;
  addHeader(slide, "FIDCs recentes | volumes e custo por tranche");

  addCallout(slide, "R$6,5 bi", "cota sênior 2024-jun/25", "Big Picture I-IV + A.I. + PI, usando A.I. atualizado.", 62, 145, 335, C.orange);
  addCallout(slide, "R$4,2 bi", "Bela I: oferta pública set/25", "Sr R$3.637 mm + Mez R$563 mm; Sub/Jr é alvo, não oferta.", 421, 145, 335, C.blue);
  addCallout(slide, "R$5,5 bi", "Bela II: oferta pública fev/26", "Sr R$4.763 mm + Mez R$737 mm; emissão capturada em 2026.", 780, 145, 335, C.blue);
  addCallout(slide, "CDI+*", "Big Picture é input manual", "1,20% / 1,50% / 1,90% / 3,00% informados pelo usuário.", 1139, 145, 335, C.orange);

  const rows = [
    ["BP I", "Abr/24", "877,5", "-", "n.l.", "1,20%*", "-", "G1 bancos; spread manual"],
    ["BP II", "Abr/24", "291,0", "-", "n.l.", "1,50%*", "-", "Devedores ampliados"],
    ["BP III", "Abr/24", "142,5", "-", "n.l.", "1,90%*", "-", "Lista ampla; alguns caps"],
    ["BP IV", "Abr/24", "240,0", "-", "n.l.", "3,00%*", "-", "Caps por emissor"],
    ["A.I.", "Out/24", "2.245,6", "347,5", "90,0", "0,85%", "3,85%", "Reg. 993693"],
    ["PI", "Abr/25", "2.720,6", "421,0", "97,2", "0,95%", "1,70% / 4,99%", "Termo 883040"],
    ["Bela I", "Set/25", "3.637,1", "562,9", "~130,0*", "0,75%", "1,35% / 4,20%", "Sub alvo 3%"],
    ["Bela II", "Fev/26", "4.762,9", "737,1", "170,1*", "0,75%", "1,35% / 4,20%", "Sub alvo 3%"],
    ["Total 2024-jun/25", "", "6.517,7", "768,5", "187,2", "", "", "Exclui Bela"],
  ];
  table(slide, {
    x: 62, y: 308,
    colWidths: [140, 95, 135, 135, 130, 125, 170, 435],
    headerHeight: 38,
    rowHeight: 49,
    headers: ["FIDC", "Data", "Sr R$mm", "Mez R$mm", "Sub/Jr R$mm", "Sr CDI+", "Mez CDI+", "Observação"],
    rows,
    totalRows: [8],
    fontSize: 12.5,
    headerFontSize: 12.5,
  });
  addText(slide, "* n.l. = não localizado em PDF baixado. Sub/Jr de Bela é derivado por subordinação-alvo, não observado como oferta CVM; Big Picture CDI+ é input manual informado pelo usuário.", {
    left: 70, top: 792, width: 1420, height: 28, size: 12.4, color: C.gray700, italic: true,
  });
  addFooter(slide, 2);
}

// Slide 3
{
  const slide = p.slides.add({ width: W, height: H });
  slide.background.fill = C.white;
  addHeader(slide, "Devedores e IFs permitidas | perfil ficou mais granular");

  addSectionTitle(slide, "Leitura dos regulamentos", 62, 145, 1005);
  const rows = [
    ["BP I", "Itaú, Bradesco, BB, Santander e CEF.", "Não separado como IF de caixa na leitura; regra aparece como devedor/emissor.", "Perfil concentrado em bancos grandes."],
    ["BP II / III", "G1 + Nu, Sicredi, Safra, Citi, CSF, XP, BTG, Pan; BP III adiciona Inter, Portoseg, BV, Banpará, Daycoval, Sofisa, BNB, Modal.", "Não separado como IF de caixa na leitura.", "Ampliação de emissores; alguns nomes condicionados/capados."],
    ["BP IV", "Emissores qualificados e não qualificados; exemplos: C6, Neon, Midway, Realize, Will, Mercado Pago, PEFISA, Original, Credsystem.", "Não separado como IF de caixa na leitura.", "C6/Neon 10%; Midway/Realize 7%; demais qualificados 5%; não qualificados 1% PL."],
    ["A.I. / PI", "G1: Itaú/Bradesco/BB/Santander/CEF. G2: Nu/Sicredi/Safra/Citi. G3/G4: lista ampliada; exclui Credz, Digicash e Zema.", "Bradesco, Santander, BB, CEF, Itaú e BTG; rating >= br.AA.", "Estrutura por grupos, com subordinacões mínimas por classe."],
    ["Bela", "Mantém G1; adiciona Mercado Pago e BTG no G2; C6 no G3; exclui Credz, Master/Will e Zema.", "Bradesco, Santander, BB, CEF, Itaú e BTG; rating >= br.AA.", "Perfil mais amplo, mas regulamento explicita travas e grupos."],
  ];
  table(slide, {
    x: 62, y: 205,
    colWidths: [95, 395, 245, 270],
    headerHeight: 42,
    rowHeight: 89,
    headers: ["FIDC", "Bancos / devedores permitidos", "IFs permitidas", "Leitura de risco"],
    rows,
    fontSize: 10.6,
    headerFontSize: 11.5,
  });

  addSectionTitle(slide, "Implicação executiva", 1114, 145, 380);
  const riskCards = [
    ["2024", "Perfil mais bancário e concentrado em emissores grandes."],
    ["2025", "Aumento de granularidade: grupos, caps e subordinação por tranche."],
    ["2026", "Bela escala o stack; foco migra para caps, duration e caixa."],
  ];
  riskCards.forEach((r, i) => {
    const yy = 205 + i * 92;
    addShape(slide, { left: 1114, top: yy, width: 380, height: 76, fill: i % 2 === 0 ? C.gray100 : C.white, line: C.gray300, radius: true });
    addText(slide, r[0], { left: 1132, top: yy + 11, width: 64, height: 26, size: 17, bold: true, color: C.orange });
    addText(slide, r[1], { left: 1200, top: yy + 10, width: 270, height: 46, size: 12.8, color: C.gray700 });
    if (i < 2) addText(slide, "↓", { left: 1282, top: yy + 71, width: 40, height: 24, size: 18, color: C.orange, bold: true, align: "center" });
  });
  bulletList(slide, [
    "O slide clean separa devedor/emissor de IF autorizada para caixa/conta.",
    "Big Pictures têm menor evidência de custo nos PDFs baixados; os spreads continuam como input manual.",
    "Bela é a principal mudança de perfil: cresce volume, alonga prazo e traz mais grupos/caps explícitos.",
    "Para Comitê, a pergunta-chave é se a diversificação adicional compensa duration e custo de carregamento."
  ], 1118, 502, 360, 14.2, 52);
  addText(slide, "Fontes regulatórias: BP I 1072697; BP II 1072783; BP III 1072799; BP IV 1072746; A.I. 993693; PI 993687; Bela 1117954.", {
    left: 1118, top: 736, width: 360, height: 50, size: 11, color: C.gray700, italic: true,
  });
  addFooter(slide, 3);
}

// Slide 4
{
  const slide = p.slides.add({ width: W, height: H });
  slide.background.fill = C.white;
  addHeader(slide, "FIDCs antigos | condições corrigidas e status");

  addSectionTitle(slide, "Tabela auditada", 62, 145, 1015);
  const rows = [
    ["Kick Ass I / Itaú I", "R$291 mm", "R$15 mm inicial / R$5,6 mm residual", "CDI+1,15%", "Ago/26", "Cartão qualquer bandeira; revolving; prazo máx. 360d."],
    ["Akira I / Itaú II", "R$500 mm", "R$15 mm / 3%", "CDI+1,14%", "Jan/27", "Mantém condição econômica próxima ao slide antigo."],
    ["Kick Ass II / Multibancos I", "R$950 mm no slide; deep dive acha alteração p/ R$1.500 mm", "R$69 mm / 6,8%; R$18 mm residual", "CDI+1,37%*", "Liquidado", "Separar volume histórico da última rerratificação de custo."],
    ["Akira II / Multibancos II", "R$1.500 mm", "R$79 mm / min. 5%", "CDI+1,35%", "Jan/26", "Cronograma explícito: não usar dedução linear."],
  ];
  table(slide, {
    x: 62, y: 205,
    colWidths: [185, 180, 190, 112, 90, 243],
    headerHeight: 42,
    rowHeight: 84,
    headers: ["FIDC antigo", "Sr / volume", "Sub / mínimo", "Remun. Sr", "Status", "Observação"],
    rows,
    fontSize: 10.8,
    headerFontSize: 11.5,
  });

  addSectionTitle(slide, "Akira II: amortização deve ser por evento", 1098, 145, 415);
  addShape(slide, { left: 1098, top: 205, width: 415, height: 390, fill: C.white, line: C.gray300, radius: true });
  addText(slide, "Cronograma da rerratificação 2025", { left: 1120, top: 225, width: 360, height: 26, size: 17, bold: true });
  const sched = [
    ["Fev-Jul/25", "6 x R$240 mm", "principal acelerado"],
    ["Ago-Dez/25", "5 x R$10 mm", "saldo remanescente*"],
    ["Jan/26", "R$10 mm", "amort. final"],
  ];
  table(slide, {
    x: 1120, y: 270,
    colWidths: [120, 120, 120],
    headerHeight: 30,
    rowHeight: 44,
    headers: ["Janela", "Evento", "Leitura"],
    rows: sched,
    fontSize: 10.2,
    headerFontSize: 10.4,
  });
  bulletList(slide, [
    "A leitura correta é o cronograma de quotas/principal indicado no documento.",
    "A tese anterior de amortização linear foi descartada.",
    "Para custo financeiro, o saldo mensal precisa refletir cada queda de principal."
  ], 1120, 452, 360, 13.2, 42);
  addMiniTag(slide, "ponto de auditoria", 1120, 555, 140, C.red);
  addText(slide, "O valor de 2025 depende de incluir ou não as parcelas pequenas de Ago-Dez; o deck marca a fonte e evita média anual fixa.", {
    left: 1275, top: 549, width: 205, height: 55, size: 11.2, color: C.gray700,
  });

  addShape(slide, { left: 62, top: 608, width: 1450, height: 150, fill: C.gray100, line: C.gray300, radius: true });
  addText(slide, "Como fica no slide clean", { left: 88, top: 628, width: 260, height: 25, size: 17, bold: true });
  bulletList(slide, [
    "Não trato os FIDCs antigos como bloco único: Itaú, Multibancos, KA/Akira têm custo, status e amortização distintos.",
    "Onde o documento traz rerratificação, ela prevalece para o custo corrente; onde o slide mostra condição histórica, ela fica identificada como histórica.",
    "Para qualquer cálculo de despesa, o motor deve usar saldos mensais/eventos de amortização, não uma média anual repetida por 12 meses."
  ], 92, 668, 1370, 15.3, 34);
  addFooter(slide, 4);
}

// Slide 5
{
  const slide = p.slides.add({ width: W, height: H });
  slide.background.fill = C.white;
  addHeader(slide, "CloudWalk IP | por que o balanço fica inchado e a DRE não mostra o custo");

  addSectionTitle(slide, "Balanço individual publicado (R$ mm)", 62, 145, 585);
  const rows = [
    ["Ativo total", "7.690", "8.625", "10.512"],
    ["Emissores - a receber", "7.055", "7.424", "9.098"],
    ["Cotas Sub FIDCs", "189", "198", "240"],
    ["Bancos/FIDCs - obrigação repasse", "6.764", "7.156", "8.737"],
    ["Patrimônio líquido", "561", "696", "821"],
    ["Dívida total / PL", "1.206%", "1.029%", "1.064%"],
  ];
  table(slide, {
    x: 62, y: 205,
    colWidths: [250, 105, 105, 105],
    headerHeight: 36,
    rowHeight: 48,
    headers: ["Conta", "dez/22", "dez/23", "jun/24"],
    rows,
    fontSize: 12.5,
    headerFontSize: 12.3,
  });
  addText(slide, "Leitura: a IP mantém o ativo econômico dos recebíveis e registra um passivo espelho de repasse para bancos/FIDCs. A cota subordinada fica em investimento, separada do recebível.", {
    left: 76, top: 544, width: 540, height: 62, size: 14, color: C.gray700,
  });

  addSectionTitle(slide, "Passo a passo contábil", 700, 145, 840);
  const steps = [
    ["1. Originação", "A adquirência gera recebível contra bancos emissores; ele nasce na CloudWalk IP."],
    ["2. Cessão sem true sale", "A companhia/auditoria entende que a IP retém riscos e benefícios relevantes: chargeback, cancelamento, recompra/ajustes e obrigação de repasse."],
    ["3. Ativo e passivo ficam na IP", "O recebível permanece em Emissores a Receber; a obrigação com bancos/FIDCs aparece em Bancos/FIDCs - Obrigações Repasse/Cessão."],
    ["4. Subordinada como investimento", "A CloudWalk IP permanece cotista subordinada/junior; essa exposição fica em Cotas Sub FIDCs, na rubrica de investimentos."],
    ["5. Escrow separa o dinheiro", "A conta Escrow é de titularidade da IP, mas com movimentação restrita: paga primeiro FIDCs/bancos e depois repassa o residual para a IP."],
    ["6. DRE mostra receita líquida", "A tese contábil é que a receita financeira já chega líquida do custo; para análise, fazemos gross-up de receita e despesa implícita."],
  ];
  let sy = 205;
  for (const [num, body] of steps) {
    addShape(slide, { left: 700, top: sy, width: 56, height: 38, fill: C.orange, line: C.orange, radius: true });
    addText(slide, num.split(".")[0], { left: 700, top: sy + 2, width: 56, height: 32, size: 19, color: C.white, bold: true, align: "center", valign: "middle" });
    addText(slide, num, { left: 770, top: sy - 2, width: 250, height: 24, size: 16, bold: true });
    addText(slide, body, { left: 770, top: sy + 22, width: 730, height: 36, size: 13, color: C.gray700 });
    sy += 62;
  }

  addSectionTitle(slide, "Fluxo econômico simplificado", 62, 660, 1475);
  horizFlow(slide, [
    { title: "Recebível R$100", body: "Bancos emissores pagam o fluxo originado na adquirência.", fill: C.gray100 },
    { title: "Conta Escrow BTG", body: "Titularidade da IP, movimentação restrita e waterfall operacional.", fill: C.white },
    { title: "FIDC / cotistas", body: "Recebem principal e remuneração antes do residual da IP.", fill: C.gray100 },
    { title: "CloudWalk IP", body: "Reconhece o residual/fee; despesa financeira fica implícita para fins gerenciais.", fill: C.white },
  ], 70, 710, 1455, 76);

  addText(slide, "Mensagem para diretoria: a contabilização é uma tese de apresentação contábil; a análise de crédito precisa recompor o custo financeiro econômico para medir margem, eficiência de funding e risco de alavancagem.", {
    left: 700, top: 590, width: 790, height: 48, size: 12.8, color: C.black, bold: true,
  });
  addFooter(slide, 5, "Fonte: demonstrações CloudWalk IP publicadas conforme slide-base; TomaConta FIDCs / IME CVM; documentos regulatórios locais. Valores em R$ mm nominais.");
}

const blob = await art.PresentationFile.exportPptx(p);
await blob.save(FINAL_PPTX);

const auditMarkdown = `# CloudWalk FIDCs - ledger de auditoria

## Escopo

Revisão dos slides anexos contra o deep dive local \`data/deep_dives/carteira_cloudwalk_7681d350\`, regulamentos/termos de emissão armazenados em \`data/raw\` e extrações regulatórias locais.

## Achados materiais

1. **A.I.**: o deep dive original trazia a emissão inicial de 14/10/2024 (Sr R$1.680,0 mm; Mez R$260,0 mm). A versão mais recente do regulamento \`993693\` indica Sr R$2.245,6 mm e Mez R$347,5 mm, além de Jr R$90,0 mm. O slide antigo acertava a direção do lote adicional, mas usava Sub/Jr de R$108 mm sem fonte localizada.

2. **PI**: o termo \`883040\` sustenta a oferta pública de R$3.141,6 mm (Sr + Mez). O mesmo pacote indica Jr privado de R$97,2 mm. Portanto, o slide deve separar oferta pública de stack completo; R$108 mm de Sub/Jr não foi suportado na fonte localizada.

3. **Bela**: os termos de emissão sustentam R$4,2 bi em set/25 e R$5,5 bi em fev/26 para oferta pública Sr + Mez. A cota subordinada/junior deve ser apresentada como alvo/derivação por subordinação, salvo fonte de emissão privada específica.

4. **Big Picture I-IV**: volumes foram localizados, mas os spreads CDI+ não foram encontrados nos PDFs baixados pelo deep dive. Foram mantidos como inputs manuais do usuário: CDI+1,20%, CDI+1,50%, CDI+1,90% e CDI+3,00%.

5. **FIDCs antigos**: Kick Ass II / Multibancos I exige distinção entre volume/status histórico e última rerratificação econômica; deep dive aponta CDI+1,37%. Akira II tem cronograma explícito de amortização, não dedução linear.

## Fontes principais citadas no deck

- A.I.: \`data/raw/57609282000146/993693_regulamento_regulamento_993693_2025-09-04.pdf\`
- PI: \`data/raw/60356171000180/883040_regulamento_regulamento_883040_2025-04-11.pdf\` e \`993687_regulamento_regulamento_993687_2025-09-04.pdf\`
- Bela: \`data/raw/62393679000183/993253_emissao_emissao_993253_2025-09-16.pdf\`, \`1117954_regulamento_regulamento_1117954_2026-02-19.pdf\` e \`1166893_emissao_emissao_1166893_2026-04-20.pdf\`
- Big Picture: regulamentos \`1072697\`, \`1072783\`, \`1072799\`, \`1072746\`
- Akira II: \`data/raw/44124617000194/851798_regulamento_regulamento_851798_2025-02-28.pdf\`

## Observação de uso

O PPTX é propositalmente executivo. Para discussão com Comitê, usar o ledger para justificar a origem dos ajustes e o deck para conduzir a narrativa.
`;
await fs.writeFile(AUDIT_MD, auditMarkdown, "utf8");

console.log(JSON.stringify({ FINAL_PPTX, AUDIT_MD }, null, 2));
