const pptxgen = require("pptxgenjs");

const BG="141A2E", CARD="1D2440", CARD2="242C4D";
const INK="FFFFFF", INK2="C6CEE0", INK3="8E98B4";
const BLUE="3D8FD1", ORA="C87200", GRN="159E78", PUR="9C63C4", RED="D64545";
const F="Calibri", FH="Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";           // 13.333 x 7.5
pres.author = "Análise Setorial de Crédito";
pres.title  = "Securitizações Solfácil — Comitê de Crédito";

const W=13.333, H=7.5, M=0.62;

const OVER=[]; let SLIDE_N=0;
const _addSlide = pres.addSlide.bind(pres);
pres.addSlide = function(...a){
  const s=_addSlide(...a); SLIDE_N++; const n=SLIDE_N;
  const _at = s.addText.bind(s);
  s.addText = function(txt,o){
    try{
      const str = Array.isArray(txt)? txt.map(t=>t.text).join("  ") : String(txt);
      const fs=o.fontSize||12, w=(o.w||1)*72, h=(o.h||1)*72;
      const lines = Math.max(1, Math.ceil((str.length*fs*0.50)/Math.max(w,1)));
      const need = lines*fs*1.22;
      if (need > h+2) OVER.push(`s${n} ALTURA  "${str.slice(0,52)}" precisa ${(need/72).toFixed(2)}in tem ${(h/72).toFixed(2)}in`);
      if ((o.x+o.w) > 13.14 || (o.y+o.h) > 7.42) OVER.push(`s${n} FORA    "${str.slice(0,40)}"`);
    }catch(e){}
    return _at(txt,o);
  };
  return s;
};


function base(title, kicker){
  const s = pres.addSlide();
  s.background = { color: BG };
  if (kicker) s.addText(kicker, {x:M, y:0.34, w:W-2*M, h:0.24, isTextBox:true, margin:0,
    fontFace:F, fontSize:10.5, bold:true, color:ORA, charSpacing:1.4});
  if (title) s.addText(title, {x:M, y:0.60, w:W-2*M, h:0.52, isTextBox:true, margin:0,
    fontFace:FH, fontSize:27, bold:true, color:INK});
  return s;
}
function src(s, t){
  s.addText(t, {x:M, y:H-0.52, w:W-2*M, h:0.3, isTextBox:true, margin:0,
    fontFace:F, fontSize:8.5, italic:true, color:INK3});
}
function card(s,x,y,w,h,fill){
  s.addShape(pres.ShapeType.roundRect, {x,y,w,h, rectRadius:0.06, fill:{color:fill||CARD}, line:{color:fill||CARD}});
}
function stat(s,x,y,w,val,lab,col){
  card(s,x,y,w,1.28,CARD);
  s.addText(val, {x:x+0.18, y:y+0.14, w:w-0.36, h:0.6, isTextBox:true, margin:0,
    fontFace:FH, fontSize:30, bold:true, color:col||INK});
  s.addText(lab, {x:x+0.18, y:y+0.78, w:w-0.36, h:0.42, isTextBox:true, margin:0,
    fontFace:F, fontSize:10, color:INK2});
}
const TBL = {fontFace:F, fontSize:9.5, color:INK2, border:{type:"solid", color:"31395C", pt:0.5}, valign:"middle"};
function hdr(a){ return a.map(t=>({text:t, options:{bold:true, color:INK, fill:{color:CARD2}, fontSize:9.5}})); }

const CH = {
  chartColors:[BLUE,ORA,GRN,PUR],
  showLegend:true, legendPos:"t", legendFontSize:9, legendColor:INK2,
  catAxisLabelColor:INK2, catAxisLabelFontSize:9, catAxisLabelFontFace:F,
  valAxisLabelColor:INK2, valAxisLabelFontSize:9, valAxisLabelFontFace:F,
  valGridLine:{color:"2C3454", size:0.75}, catGridLine:{style:"none"},
  catAxisLineShow:false, valAxisLineShow:false,
  dataLabelColor:INK, dataLabelFontFace:F, dataLabelFontSize:9,
  plotArea:{fill:{color:BG}}, chartArea:{fill:{color:BG}},
};

/* ---------------------------------------------------------------- 1 capa */
{
  const s = pres.addSlide(); s.background={color:BG};
  s.addText("COMITÊ DE CRÉDITO  ·  SETEMBRO DE 2026", {x:M, y:1.30, w:W-2*M, h:0.3, isTextBox:true, margin:0,
    fontFace:F, fontSize:11, bold:true, color:ORA, charSpacing:1.6});
  s.addText("Securitizações Solfácil", {x:M, y:1.72, w:W-2*M, h:0.86, isTextBox:true, margin:0,
    fontFace:FH, fontSize:44, bold:true, color:INK});
  s.addText("Sete FIDCs e duas emissões de CRI · estrutura, take-outs e capacidade de saque da cota subordinada",
    {x:M, y:2.58, w:9.6, h:0.4, isTextBox:true, margin:0, fontFace:F, fontSize:13.5, color:INK2});
  const w=2.86, g=0.24; let x=M;
  stat(s,x,3.60,w,"9","operações no perímetro CVM",INK); x+=w+g;
  stat(s,x,3.60,w,"R$ 4,1 bi","ofertas registradas 2023–2026",BLUE); x+=w+g;
  stat(s,x,3.60,w,"R$ 1,17 bi","PL agregado dos FIDCs hoje",ORA); x+=w+g;
  stat(s,x,3.60,w,"R$ 11,9 mm","saque de cota sub disponível hoje",GRN);
  src(s,"Fontes: cadastro e informe mensal FIDC (dados.cvm.gov.br, jul–ago/2026); regulamentos e relatórios de rating no Fundos.NET; registro de ofertas da CVM.");
  s.addNotes('Perimetro: 7 classes de FIDC no cadastro CVM com o nome Solfacil e 2 emissoes de CRI da Vert com lastro declarado da Plataforma Solfacil. O FIDC Solfarma nao integra o grupo.');
}

/* ---------------------------------------------------------------- 2 perímetro */
{
  const s = base("Perímetro e estrutura","01 · MAPA DAS OPERAÇÕES");
  const rows = [
    hdr(["Operação","1ª emissão","PL / volume","Subordinação mínima","Regime de amortização"]),
    ["IS Green Solfácil I","dez/2020","R$ 84 mm","25% do PL (razão de garantia 133%)","Programada linear"],
    ["IS Green Solfácil II","out/2021","R$ 94 mm","20% do PL · júnior 4,5%","Alvo de composição → sequencial no 60º mês"],
    ["Solfácil IV","jun/2022","R$ 18 mm","Não publicada no regulamento","Definida por apêndice · fundo em run-off"],
    ["IS Green Solfácil V","mar/2023","R$ 68 mm","20% do PL · júnior 7%","Programada linear"],
    ["IS Green Solfácil III","jul/2023","R$ 141 mm","25% / 10% / 4% por faixa","Alvo de composição → sequencial no 48º mês"],
    ["IS Green Solfácil VI","nov/2024","R$ 145 mm","Cobertura 133,3% / 111,1% / 104,2%","Bullet · sequencial por gatilho"],
    ["IS Green Solfácil VII","jan/2026","R$ 620 mm","Cobertura 133,3% / 111,1% / 104,2%","Revolvente 12m → pro rata · sequencial por gatilho"],
    ["CRI Vert 174ª","mai/2026","R$ 471 mm","Cobertura 147,1% / 120,5% / 109,9%","Pro rata até o 47º mês → sequencial"],
    ["CRI Vert 177ª","jul/2026","R$ 628 mm","Não divulgada","Não divulgado"],
  ];
  s.addTable(rows, {x:M, y:1.32, w:W-2*M, colW:[2.55,1.15,1.35,3.15,3.89],
    ...TBL, rowH:0.40, autoPage:false});
  src(s,"PL dos FIDCs em jul/2026 (VI em ago/2026); volume dos CRI é o montante emitido, incluindo séries de colocação privada.");
  s.addNotes('Ordem cronologica de primeira emissao. Tres desenhos de amortizacao coexistem: linear programada (I e V), alvo de composicao (II, III e VII) e bullet (VI).');
}

/* ---------------------------------------------------------------- 3 subordinação */
{
  const s = base("Subordinação atual contra o piso contratual","02 · ESTRUTURA DE CAPITAL");
  const cats=["I","II","III","IV","V","VI","VII"];
  s.addChart(pres.ChartType.bar, [
    {name:"Subordinação atual", labels:cats, values:[36.4,27.1,33.2,0.0,20.9,25.2,26.0]},
    {name:"Piso contratual",    labels:cats, values:[25.0,20.0,25.0,0.0,20.0,25.0,25.0]},
  ], {x:M, y:1.30, w:7.55, h:4.35, barDir:"col", barGapWidthPct:60,
      ...CH, showValue:true, dataLabelPosition:"outEnd", dataLabelFormatCode:'0.0"%"',
      valAxisMaxVal:40, valAxisMajorUnit:10, valAxisLabelFormatCode:'0"%"'});
  card(s,8.45,1.30,W-M-8.45,4.35);
  const bl=[
    ["FIDC V","folga de 0,9 p.p. sobre o piso de 20%; abaixo dos 22% exigidos para amortizar a júnior"],
    ["FIDC VI","piso atendido, mas a razão de cobertura sênior está em 134,8% contra gatilho de 133,3%"],
    ["FIDC IV","sem cota subordinada em circulação; cobertura da sênior em 90,8%"],
    ["FIDC I e III","maiores colchões do grupo, 11,4 e 8,2 p.p. acima do piso"],
  ];
  let y=1.50;
  bl.forEach(([k,v])=>{
    s.addText(k, {x:8.66, y:y, w:3.9, h:0.24, isTextBox:true, margin:0, fontFace:F, fontSize:11, bold:true, color:ORA});
    s.addText(v, {x:8.66, y:y+0.24, w:3.9, h:0.70, isTextBox:true, margin:0, fontFace:F, fontSize:10, color:INK2});
    y+=1.02;
  });
  src(s,"Subordinação = (mezanino + júnior) ÷ PL, informe mensal FIDC jul/2026 (VI em ago/2026). Piso conforme regulamento vigente de cada classe.");
  s.addNotes('A subordinacao atual esta acima do piso em todos os fundos com cota subordinada em circulacao. A folga do V e do VI e menor do que a leitura do piso sugere, porque as travas de amortizacao e a razao de cobertura mordem antes.');
}

/* ---------------------------------------------------------------- 4 take-outs */
{
  const s = base("Take-outs: três eventos concentram a saída de carteira","03 · MOVIMENTO DE CARTEIRA");
  const labs=["jan/24","","mar","","mai","","jul","","set","","nov","","jan/25","","mar","","mai","","jul","","set","","nov","","jan/26","","mar","","mai","","jul","ago"];
  const IV=[1124.8,1167.6,1169.4,1164.7,1198.8,1203.7,1004.6,1005.6,1020.6,1024.1,1216.8,1214.2,1238.5,1231.1,1030.7,1037.2,939.8,141.3,90.9,64.4,47.0,38.3,30.5,28.5,25.8,22.1,19.2,18.0,18.8,20.0,17.5,null];
  const VI=[null,null,null,null,null,null,null,null,null,null,60.2,121.6,174.3,289.6,370.7,432.0,495.6,557.2,681.9,772.6,895.1,897.7,902.0,943.2,944.0,942.1,942.9,941.9,466.8,437.4,211.1,145.2];
  const II=[535.8,374.9,358.8,351.0,339.7,330.3,217.2,208.2,190.5,182.1,176.1,173.3,168.8,163.9,161.9,153.8,150.5,145.5,142.3,137.8,134.4,129.0,124.4,122.1,117.9,113.2,108.6,103.6,100.1,96.1,94.1,null];
  s.addChart(pres.ChartType.line, [
    {name:"FIDC IV", labels:labs, values:IV},
    {name:"FIDC VI", labels:labs, values:VI},
    {name:"FIDC II", labels:labs, values:II},
  ], {x:M, y:1.30, w:8.15, h:4.25, ...CH, lineSize:2.25, lineSmooth:false, showValue:false,
      valAxisTitle:"PL, R$ mm", showValAxisTitle:true, valAxisTitleColor:INK2, valAxisTitleFontSize:9,
      valAxisMaxVal:1300, valAxisMajorUnit:250});
  card(s,9.05,1.30,W-M-9.05,4.25);
  const ev=[
    ["fev e jul/2024 · FIDC II","−30% e −34% do PL. Sênior amortizada em R$ 135 mm e R$ 97 mm."],
    ["jun/2025 · FIDC IV","−85% do PL em um mês. Sênior R$ 570 mm, mezanino R$ 151 mm, júnior R$ 87 mm."],
    ["mai a ago/2026 · FIDC VI","−85% acumulado. Carteira cedida ao CRI Vert 174ª; FIDC VI é cedente no termo de securitização."],
  ];
  let y=1.50;
  ev.forEach(([k,v])=>{
    s.addText(k, {x:9.26, y:y, w:3.45, h:0.26, isTextBox:true, margin:0, fontFace:F, fontSize:11, bold:true, color:ORA});
    s.addText(v, {x:9.26, y:y+0.27, w:3.45, h:0.95, isTextBox:true, margin:0, fontFace:F, fontSize:10, color:INK2});
    y+=1.30;
  });
  src(s,"PL mensal, informe mensal FIDC. FIDC IV sem informe em ago/2026; FIDC II idem.");
  s.addNotes('Take-out = cessao de carteira a outro veiculo, com amortizacao simultanea das cotas. Os tres eventos estruturais somam cerca de R$ 1,9 bi de reducao de PL.');
}

/* ---------------------------------------------------------------- 5 qualidade */
{
  const s = base("Qualidade da carteira remanescente após o take-out","04 · A PERGUNTA CENTRAL");
  s.addChart(pres.ChartType.bar, [
    {name:"Inadimplência ≥ 90d / carteira", labels:["FIDC IV\nmai/25","FIDC IV\nset/25","FIDC VI\nabr/26","FIDC VI\nago/26"], values:[2.5,16.6,1.9,11.5]},
    {name:"PDD / carteira",                 labels:["FIDC IV\nmai/25","FIDC IV\nset/25","FIDC VI\nabr/26","FIDC VI\nago/26"], values:[7.5,59.7,5.5,35.2]},
  ], {x:M, y:1.32, w:7.35, h:4.30, barDir:"col", barGapWidthPct:55, ...CH,
      showValue:true, dataLabelPosition:"outEnd", dataLabelFormatCode:'0.0"%"',
      valAxisMaxVal:70, valAxisMajorUnit:20, valAxisLabelFormatCode:'0"%"'});
  card(s,8.25,1.32,W-M-8.25,2.02);
  s.addText("Take-out estrutural (> 50% do PL)", {x:8.46, y:1.50, w:4.2, h:0.26, isTextBox:true, margin:0, fontFace:F, fontSize:11, bold:true, color:ORA});
  s.addText([
    {text:"Inadimplência ≥ 90d multiplicada por 6,0 a 6,6 em três meses", options:{bullet:true, breakLine:true}},
    {text:"PDD multiplicada por 6,3 a 7,9 no mesmo intervalo", options:{bullet:true, breakLine:true}},
    {text:"Efeito medido no FIDC IV (jun/25) e no FIDC VI (mai/26)", options:{bullet:true}},
  ], {x:8.46, y:1.82, w:4.2, h:1.40, isTextBox:true, margin:0, fontFace:F, fontSize:10, color:INK2, paraSpaceAfter:5});
  card(s,8.25,3.50,W-M-8.25,2.12);
  s.addText("Take-out parcial (15% a 35% do PL)", {x:8.46, y:3.68, w:4.2, h:0.26, isTextBox:true, margin:0, fontFace:F, fontSize:11, bold:true, color:BLUE});
  s.addText([
    {text:"FIDC II jul/24: inadimplência de 2,2% para 3,7%, PDD de 10,3% para 13,1%", options:{bullet:true, breakLine:true}},
    {text:"FIDC IV mar/25: inadimplência de 2,3% para 2,5%, PDD de 7,0% para 7,5%", options:{bullet:true, breakLine:true}},
    {text:"Deterioração de 1,1x a 1,7x — ordem de grandeza distinta", options:{bullet:true}},
  ], {x:8.46, y:4.00, w:4.2, h:1.50, isTextBox:true, margin:0, fontFace:F, fontSize:10, color:INK2, paraSpaceAfter:5});
  src(s,"Inadimplência = (créditos vencidos inadimplentes + créditos inadimplidos) ÷ carteira de direitos creditórios; PDD = provisão ÷ carteira. Informe mensal FIDC.");
  s.addNotes('Resposta direta a pergunta do comite: take-out estrutural multiplica inadimplencia e PDD do residuo por aproximadamente 6 em tres meses. Take-out parcial nao produz o mesmo efeito.');
}

/* ---------------------------------------------------------------- 6 mecanica */
{
  const s = base("O take-out é seleção positiva por construção","05 · MECÂNICA");
  const w=(W-2*M-0.5)/3;
  const bx=[
    ["Critério do comprador","O recebível não pode estar em atraso e o devedor não pode ter operação inadimplente na data de oferta. Prazo, ticket e prazo médio ponderado também limitam a seleção."],
    ["Efeito na carteira cedida","Sai o crédito adimplente, dentro de prazo e ticket. A carteira cedida chega ao veículo comprador limpa."],
    ["Efeito na carteira residual","Fica o atrasado, o de prazo longo e o de ticket fora de faixa. O denominador encolhe e o estoque provisionado passa a dominar."],
  ];
  bx.forEach(([t,d],i)=>{
    const x=M+i*(w+0.25);
    card(s,x,1.35,w,3.05,CARD);
    s.addText(String(i+1), {x:x+0.22, y:1.52, w:0.6, h:0.5, isTextBox:true, margin:0, fontFace:FH, fontSize:26, bold:true, color:ORA});
    s.addText(t, {x:x+0.22, y:2.08, w:w-0.44, h:0.52, isTextBox:true, margin:0, fontFace:F, fontSize:13, bold:true, color:INK});
    s.addText(d, {x:x+0.22, y:2.66, w:w-0.44, h:1.55, isTextBox:true, margin:0, fontFace:F, fontSize:10.5, color:INK2});
  });
  card(s,M,4.62,W-2*M,1.30,CARD2);
  s.addText("Evidência: no FIDC VI a carteira caiu de R$ 928 mm (abr/26) para R$ 218 mm (ago/26) e a PDD subiu de 5,5% para 35,2%. A provisão em reais subiu de R$ 51 mm para R$ 77 mm com a carteira caindo 76%: o estoque provisionado não foi cedido.",
    {x:M+0.24, y:4.86, w:W-2*M-0.48, h:0.85, isTextBox:true, margin:0, fontFace:F, fontSize:11.5, color:INK});
  src(s,"Critérios de elegibilidade dos FIDC VI e VII e do termo de securitização da 174ª emissão da Vert.");
  s.addNotes('O efeito nao depende de intencao: os criterios de elegibilidade do veiculo comprador excluem credito em atraso, o que torna a cessao uma selecao positiva.');
}

/* ---------------------------------------------------------------- 7 saques */
{
  const s = base("Cota subordinada júnior: quanto já saiu","06 · SAQUE DE SUBORDINADA");
  const rows=[
    hdr(["Fundo","Sacado","Aportado","Líquido","Maior evento","Saldo atual"]),
    ["IS Green Solfácil I","R$ 10,1 mm","—","R$ 10,1 mm","ago/24 · R$ 1,2 mm","R$ 3,3 mm"],
    ["IS Green Solfácil II","R$ 13,6 mm","—","R$ 13,6 mm","set/24 · R$ 6,2 mm","R$ 11,5 mm"],
    ["IS Green Solfácil III","R$ 26,0 mm","—","R$ 26,0 mm","set/25 · R$ 3,2 mm","R$ 17,2 mm"],
    ["Solfácil IV","R$ 214,6 mm","R$ 96,4 mm","R$ 118,2 mm","jun/25 · R$ 86,7 mm","zero"],
    ["IS Green Solfácil V","R$ 7,1 mm","—","R$ 7,1 mm","set/25 · R$ 3,4 mm","R$ 5,0 mm"],
    ["IS Green Solfácil VI","R$ 55,5 mm","R$ 41,2 mm","R$ 14,3 mm","jun/26 · R$ 29,0 mm","R$ 6,1 mm"],
    ["IS Green Solfácil VII","R$ 7,7 mm","R$ 25,5 mm","−R$ 17,8 mm","jul/26 · R$ 7,7 mm","R$ 32,4 mm"],
  ];
  s.addTable(rows, {x:M, y:1.32, w:7.85, colW:[2.10,1.05,1.05,1.10,1.60,0.95], ...TBL, rowH:0.40});
  card(s,8.70,1.32,W-M-8.70,3.30);
  s.addText("Padrão observado", {x:8.92, y:1.52, w:3.7, h:0.28, isTextBox:true, margin:0, fontFace:F, fontSize:12, bold:true, color:ORA});
  s.addText([
    {text:"Os maiores saques acompanham take-outs: FIDC IV em jun/25 (R$ 86,7 mm) e FIDC VI em jun e ago/26 (R$ 49,3 mm).", options:{bullet:true, breakLine:true}},
    {text:"Nos fundos maduros o saque é mensal e pequeno — o excesso sobre o alvo de composição.", options:{bullet:true, breakLine:true}},
    {text:"FIDC VII é o único com aporte líquido: R$ 25,5 mm entrando contra R$ 7,7 mm saindo.", options:{bullet:true, breakLine:true}},
    {text:"FIDC IV devolveu R$ 118 mm líquidos e hoje não tem subordinada em circulação.", options:{bullet:true}},
  ], {x:8.92, y:1.90, w:3.7, h:2.55, isTextBox:true, margin:0, fontFace:F, fontSize:10, color:INK2, paraSpaceAfter:7});
  card(s,8.70,4.78,W-M-8.70,0.86,CARD2);
  s.addText("Total sacado no período: R$ 334,6 mm · aportado R$ 163,1 mm", {x:8.92, y:4.98, w:3.7, h:0.5, isTextBox:true, margin:0, fontFace:F, fontSize:11, bold:true, color:INK});
  src(s,"Amortizações e captações por subclasse, tabela X.4 do informe mensal FIDC, jan/2024 a ago/2026. Antes de 2024 as subclasses não eram identificadas separadamente no informe.");
  s.addNotes('Janela de analise limitada a jan/2024 porque antes disso o informe mensal nao identificava as subclasses separadamente.');
}

/* ---------------------------------------------------------------- 8 regras */
{
  const s = base("As regras que autorizam o saque","07 · TRAVAS CONTRATUAIS");
  const rows=[
    hdr(["Fundo","Condição para amortizar a cota subordinada"]),
    ["IS Green Solfácil I","Pro forma: subordinadas ≥ 26,5% do PL e mezanino B + júnior ≥ 16,5%. Razão de garantia das cotas públicas ≥ 110%. Sem evento de avaliação em curso."],
    ["IS Green Solfácil II","Relações mínimas mantidas (subordinadas ≥ 20%, júnior ≥ 4,5%), índices de atraso enquadrados e rentabilidade da júnior positiva nos últimos 3 meses."],
    ["IS Green Solfácil III","Índices de subordinação enquadrados (25% / 10% / 4%). No regime pro rata, a júnior recebe apenas o excesso sobre o alvo de 12% do PL."],
    ["Solfácil IV","Não publicada no regulamento vigente."],
    ["IS Green Solfácil V","Pro forma: subordinadas ≥ 22% do PL e júnior ≥ 9%. Índice de garantia das cotas públicas ≥ 105%."],
    ["IS Green Solfácil VI e VII","Solicitação de 75% da júnior; amortização pro rata em curso; índices de subordinação enquadrados; razões de cobertura acima do patamar de liberação (136,0% / 113,3% / 106,3%). No VI só a partir do 18º mês, no VII do 24º."],
  ];
  s.addTable(rows, {x:M, y:1.32, w:W-2*M, colW:[2.60,9.49], ...TBL, rowH:0.52, fontSize:10});
  card(s,M,5.40,W-2*M,0.80,CARD2);
  s.addText("Em todos os casos a autorização é pro forma: o teste é feito considerando a amortização já realizada. O regime sequencial suspende integralmente o pagamento à subordinada.",
    {x:M+0.24, y:5.56, w:W-2*M-0.48, h:0.5, isTextBox:true, margin:0, fontFace:F, fontSize:11, color:INK});
  src(s,"Regulamentos vigentes de cada classe, capítulos de amortização e ordem de alocação de recursos.");
  s.addNotes('Todas as travas sao testadas pro forma. Nos fundos VI e VII ha ainda exigencia de deliberacao de 75% da junior e prazo minimo de 18 e 24 meses.');
}

/* ---------------------------------------------------------------- 9 headroom */
{
  const s = base("Capacidade de saque hoje","08 · QUANTO PODE SAIR");
  const cats=["I","II","III","IV","V","VI","VII"];
  s.addChart(pres.ChartType.bar, [
    {name:"Teto de saque hoje (R$ mm)", labels:cats, values:[3.3,7.7,0.3,0.0,0.0,0.0,0.6]},
    {name:"Saldo da cota júnior (R$ mm)", labels:cats, values:[3.3,11.5,17.2,0.0,5.0,6.1,32.4]},
  ], {x:M, y:1.32, w:7.20, h:4.28, barDir:"col", barGapWidthPct:55, ...CH,
      showValue:true, dataLabelPosition:"outEnd", dataLabelFormatCode:'0.0'});
  const rows=[
    hdr(["Fundo","Teto","Restrição que trava"]),
    ["I","R$ 3,3 mm","Saldo da própria júnior; somando o mezanino B as travas comportariam R$ 10,1 mm"],
    ["II","R$ 7,7 mm","Júnior ≥ 4,5% do PL"],
    ["III","R$ 0,3 mm","Alvo pro rata de 12% do PL; pisos de índice comportariam R$ 12,1 mm"],
    ["IV","zero","Sem cota subordinada em circulação"],
    ["V","zero","Subordinadas em 20,9% contra 22% exigidos"],
    ["VI","zero","Cobertura sênior em 134,8% contra 136,0% de liberação"],
    ["VII","R$ 0,6 mm","Cobertura mezanino B em 106,4% contra 106,3%; pisos comportariam R$ 20,4 mm"],
  ];
  s.addTable(rows, {x:8.10, y:1.32, w:W-M-8.10, colW:[0.55,0.95,3.11], ...TBL, rowH:0.48, fontSize:9});
  src(s,"Estimativa a partir do informe mensal de jul/2026 (VI em ago/2026), aplicando as travas de cada regulamento pro forma à amortização. A razão de cobertura usa a carteira líquida de PDD mais disponibilidades e ativos financeiros, sem o redutor previsto em regulamento.");
  s.addNotes('A trava efetiva raramente e o piso de subordinacao. No III e o alvo de composicao; no VI e VII e a razao de cobertura; no V e a trava especifica de amortizacao da junior.');
}

/* ---------------------------------------------------------------- 10 folga */
{
  const s = base("Distância até o gatilho","09 · MARGEM DE SEGURANÇA");
  const cats=["I","III","II","VII","VI","V","IV"];
  s.addChart(pres.ChartType.bar, [
    {name:"Folga até o gatilho (p.p.)", labels:cats, values:[24.3,8.2,7.1,3.0,1.5,1.4,-42.5]},
  ], {x:M, y:1.32, w:7.20, h:4.28, barDir:"col", barGapWidthPct:65, ...CH, showLegend:false,
      chartColors:[BLUE], showValue:true, dataLabelPosition:"outEnd", dataLabelFormatCode:'0.0'});
  card(s,8.10,1.32,W-M-8.10,4.28);
  s.addText("Leitura", {x:8.32, y:1.52, w:4.2, h:0.28, isTextBox:true, margin:0, fontFace:F, fontSize:12, bold:true, color:ORA});
  s.addText([
    {text:"VI, VII e V operam com margem de 1,4 a 3,0 p.p. Um mês de deterioração leva ao gatilho.", options:{bullet:true, breakLine:true}},
    {text:"No VI a cobertura caiu de 152,4% (jul/26) para 134,8% (ago/26), mês do saque de R$ 20,3 mm da júnior.", options:{bullet:true, breakLine:true}},
    {text:"No VII a cobertura sênior está em 136,3% contra patamar de liberação de 136,0%.", options:{bullet:true, breakLine:true}},
    {text:"O IV está com cobertura da sênior em 90,8%: o patrimônio não cobre a classe.", options:{bullet:true, breakLine:true}},
    {text:"I, II e III mantêm 7 a 24 p.p. de colchão.", options:{bullet:true}},
  ], {x:8.32, y:1.90, w:4.2, h:3.30, isTextBox:true, margin:0, fontFace:F, fontSize:10.5, color:INK2, paraSpaceAfter:8});
  src(s,"Métrica por fundo: razão de cobertura sênior contra o patamar de desalavancagem em VI e VII; razão de garantia contra o mínimo em I, IV e V; índice de subordinação contra o piso em II e III.");
  s.addNotes('Folga medida em pontos percentuais entre a metrica vigente e o gatilho aplicavel a cada fundo. V, VI e VII operam com margem inferior a 3 p.p.');
}

/* ---------------------------------------------------------------- 11 comite */
{
  const s = base("Pontos para o comitê","10 · CONCLUSÕES");
  const pts=[
    ["Take-out estrutural degrada o resíduo em torno de 6x","Inadimplência e PDD da carteira remanescente multiplicam por 6 em três meses. Take-outs parciais até 35% do PL ficam em 1,1x a 1,7x."],
    ["O FIDC VI está no gatilho","Cobertura sênior em 134,8% contra 133,3% de desalavancagem. Nova cessão ao CRI 177ª reduz ainda mais a base."],
    ["O saque da júnior antecede a deterioração","R$ 49,3 mm saíram do VI em jun e ago/26, com a PDD já em 14% e 35%. As travas foram atendidas em cada data."],
    ["Capacidade de saque hoje é residual","R$ 11,9 mm no agregado contra R$ 75,5 mm de saldo júnior. Cinco dos sete fundos não têm folga."],
    ["Solfácil IV sem cobertura","PL de R$ 17,5 mm, só sênior em circulação, cobertura de 90,8% e PDD de 41% da carteira."],
  ];
  let y=1.30;
  pts.forEach(([t,d],i)=>{
    card(s,M,y,W-2*M,0.92,i<2?CARD2:CARD);
    s.addText(String(i+1).padStart(2,"0"), {x:M+0.24, y:y+0.24, w:0.55, h:0.44, isTextBox:true, margin:0, fontFace:FH, fontSize:18, bold:true, color:ORA});
    s.addText(t, {x:M+0.92, y:y+0.13, w:4.55, h:0.66, isTextBox:true, margin:0, fontFace:F, fontSize:12.5, bold:true, color:INK});
    s.addText(d, {x:M+5.60, y:y+0.13, w:6.45, h:0.66, isTextBox:true, margin:0, fontFace:F, fontSize:10.5, color:INK2});
    y+=1.00;
  });
  src(s,"Base: informe mensal FIDC até ago/2026, regulamentos vigentes e documentos das ofertas registradas na CVM.");
  s.addNotes('Pontos para deliberacao. O item 2 e o mais sensivel: o FIDC VI esta a 1,5 p.p. do evento de desalavancagem, que trocaria o regime para sequencial.');
}

pres.writeFile({fileName:"Solfacil_Securitizacoes_Comite.pptx"}).then(f=>{
  console.log("gerado:",f);
  if(OVER.length){ console.log("\nALERTAS DE LAYOUT:"); OVER.forEach(o=>console.log("  "+o)); }
  else console.log("layout: sem alertas");
});
