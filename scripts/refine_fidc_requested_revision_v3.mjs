import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, PresentationFile } from '@oai/artifact-tool';
// Authoring inputs are two template-starter.pptx files prepared from the complete and compact source decks.

const textOf = (shape) => {
  try { return String(shape.toSnapshot()?.text ?? '').trim(); } catch { return ''; }
};
const findText = (slide, exact) => slide.shapes.items.find(s => textOf(s) === exact);
const deleteShape = (s) => { if (s) s.delete(); };

const replacements = new Map([
  ['ESCALA DA INDÚSTRIA', 'Escala da indústria'],
  ['SALDO E TIPOS DE FIDCs', 'Saldo e tipos de FIDCs'],
  ['EMISSÕES POR CATEGORIA ANBIMA', 'Emissões por categoria ANBIMA'],
  ['RANKING · TOP 20 FIDCs', 'Ranking · Top 20 FIDCs'],
  ['OFERTAS · VOLUME E REGIME', 'Ofertas · volume e regime'],
  ['RANKING ANBIMA · JUNHO/2026', 'Ranking ANBIMA · junho/2026'],
  ['PRESTADORES · RANKING E CONCENTRAÇÃO', 'Prestadores · ranking e concentração'],
  ['DISTRIBUIÇÃO POR NÚMERO DE COTISTAS', 'Distribuição por número de cotistas'],
  ['VOLUME ORIGINAÇÃO', 'Volume de originação'],
  ['VOLUME DISTRIBUIÇÃO', 'Volume de distribuição'],
  ['VOLUME ORIGINADO', 'Volume originado'],
  ['PARTICIPAÇÃO', 'Participação'],
  ['POSIÇÃO 2026', 'Posição 2026'],
  ['POSIÇÃO 12 MESES', 'Posição 12 meses'],
  ['POSIÇÃO', 'Posição'],
  ['OPERAÇÕES', 'Operações'],
  ['01 · DISTRIBUIÇÃO APÓS A RCVM 175 SEGUE INSTITUCIONAL E CONCENTRADA', '01 · Distribuição após a RCVM 175 segue institucional e concentrada'],
  ['02 · VERTICALIZAÇÃO DEFINE O MODELO OPERACIONAL DA INDÚSTRIA', '02 · Verticalização define o modelo operacional da indústria'],
  ['03 · ESCALA INDEPENDENTE ESTÁ CONCENTRADA EM POUCAS PLATAFORMAS', '03 · Escala independente está concentrada em poucas plataformas'],
  ['04 · MOVIMENTAÇÃO DE ADMINISTRADORES FOI BAIXA E CONCENTRADA', '04 · Movimentação de administradores foi baixa e concentrada'],
  ['05 · GESTÃO É A FUNÇÃO MAIS PULVERIZADA', '05 · Gestão é a função mais pulverizada'],
  ['06 · COORTE BANCÁRIA EXPLICA DOIS TERÇOS DO COMBO COMPLETO DO BTG', '06 · Coorte bancária explica dois terços do combo completo do BTG'],
  ['07 · EMISSÕES ACELERARAM; A MAIOR OFERTA EXPLICA DOIS TERÇOS DO AVANÇO', '07 · Emissões aceleraram; a maior oferta explica dois terços do avanço'],
]);

const mergePairs = [
  ['Originação × Distribuição', 'Originação mede a estruturação e a coordenação da oferta. Distribuição mede o esforço de colocação junto ao investidor.'],
  ['O ranking mede valor', 'A posição vem do volume das operações encerradas no período. Há um ranking separado por número de operações, e ele não é usado nestas lâminas.'],
  ['As duas janelas', '“Acumulado 2026” cobre jan–jun/26. “Últimos 12 meses” cobre jul/25–jun/26 e suaviza o efeito de operações grandes em um único semestre.'],
  ['Uma operação, vários coordenadores', 'O crédito segue os percentuais informados à ANBIMA: proporção da garantia firme, ou proporção do fee em melhores esforços; sem discriminação, rateio igual.'],
  ['O “Percentual Coordenado” define a liderança', 'Na matriz de operações, “Líder” marca a casa com o maior percentual coordenado; “X” marca participação sem liderança.'],
  ['Participação formal sem valor', 'Alguns registros trazem participantes com percentual e valor zerados. Eles constam como participantes, mas não somam volume nem afetam o market share.'],
  ['É um ranking declaratório', 'Operação cujo formulário-padrão não foi enviado à ANBIMA não entra. Parte do mercado liderado por administradores ou estruturadores não associados pode ficar fora.'],
  ['Empresas ligadas saem do Tipo 1', 'Coordenador com 10% ou mais do capital da emissora, cedente ou originadora vai para o Tipo 3, apurado à parte.'],
];

function simplifyDeck(presentation, { compact = false } = {}) {
  const changes = { deletedLines: 0, titleCase: 0, footers: 0, pageNumbers: 0, mergedCards: 0, chartsRefreshed: 0 };
  for (let i = 0; i < presentation.slides.items.length; i++) {
    const slide = presentation.slides.items[i];
    for (const shape of [...slide.shapes.items]) {
      const t = textOf(shape);
      const f = shape.frame;
      if (!t && f && f.width >= 250 && f.height <= 3) {
        shape.delete(); changes.deletedLines++; continue;
      }
      if (replacements.has(t)) {
        shape.text.replace(t, replacements.get(t)); changes.titleCase++;
      }
    }

    // Rodapés de fonte/metodologia: alinhamento à esquerda e uma faixa de texto estável.
    for (const shape of [...slide.shapes.items]) {
      const t = textOf(shape);
      const f = shape.frame;
      if (!t || !f) continue;
      if (f.top >= 610 && !/^\d+$/.test(t)) {
        shape.text.alignment = 'left';
        shape.text.autoFit = 'shrinkText';
        shape.frame = { left: 60, top: f.top, width: 1100, height: f.height };
        changes.footers++;
      }
      if (f.top >= 650 && /^\d+$/.test(t)) {
        shape.text.set(String(i + 1));
        shape.text.alignment = 'right';
        changes.pageNumbers++;
      }
    }
  }

  if (!compact) {
    // Lâmina 14 (fonte 14): uma única caixa de texto, sem o filete/chip laranja.
    const s14 = presentation.slides.items[13];
    for (const shape of [...s14.shapes.items]) {
      const f = shape.frame;
      if (f && f.left <= 1 && f.width <= 25 && f.height >= 700) shape.delete();
    }
    const eyebrow = findText(s14, 'Ranking ANBIMA · junho/2026') || findText(s14, 'RANKING ANBIMA · JUNHO/2026');
    const title = findText(s14, 'Posição competitiva do Itaú BBA em renda fixa e híbridos');
    const subtitle = findText(s14, 'Originação e distribuição · acumulado de 2026 e últimos 12 meses');
    const reference = findText(s14, 'Ranking ANBIMA de Renda Fixa e Híbridos — referência Junho/2026');
    if (!title || !eyebrow || !subtitle || !reference) throw new Error('Não foi possível consolidar a lâmina 14.');
    title.frame = { left: 88.32, top: 215.04, width: 1094.4, height: 238 };
    title.text.set([
      { spaceAfter: 10, runs: [{ run: 'Ranking ANBIMA · junho/2026', textStyle: { fontSize: '14.67px', typeface: 'Arial', color: '#E36C0A', bold: true } }] },
      { spaceAfter: 9, runs: [{ run: 'Posição competitiva do Itaú BBA em renda fixa e híbridos', textStyle: { fontSize: '40px', typeface: 'Arial', color: '#151515', bold: true } }] },
      { spaceAfter: 15, runs: [{ run: 'Originação e distribuição · acumulado de 2026 e últimos 12 meses', textStyle: { fontSize: '18.67px', typeface: 'Arial', color: '#5D6369' } }] },
      { runs: [{ run: 'Ranking ANBIMA de Renda Fixa e Híbridos — referência junho/2026', textStyle: { fontSize: '14.67px', typeface: 'Arial', color: '#8D9399' } }] },
    ]);
    title.text.alignment = 'left'; title.text.verticalAlignment = 'top'; title.text.autoFit = 'shrinkText';
    deleteShape(eyebrow); deleteShape(subtitle); deleteShape(reference);

    // Lâmina-fonte 25 agora é a lâmina 23: remove os chips e une título + explicação por bloco.
    const s23 = presentation.slides.items[22];
    for (const shape of [...s23.shapes.items]) {
      const f = shape.frame;
      if (f && f.width <= 8 && f.height >= 80) shape.delete();
    }
    for (const [heading, expectedBody] of mergePairs) {
      const h = findText(s23, heading);
      const body = findText(s23, expectedBody) || s23.shapes.items.find(s => {
        const t=textOf(s), f=s.frame; return t && t.startsWith(expectedBody.slice(0,45)) && f?.top > (h?.frame?.top ?? 0);
      });
      if (!h || !body) throw new Error(`Par não localizado na lâmina 23: ${heading}`);
      const hf = h.frame, bf = body.frame;
      h.frame = { left: hf.left, top: hf.top, width: hf.width, height: (bf.top + bf.height) - hf.top };
      h.text.set([
        { spaceAfter: 4, runs: [{ run: heading, textStyle: { fontSize: '15.33px', typeface: 'Arial', color: '#151515', bold: true } }] },
        { runs: [{ run: textOf(body), textStyle: { fontSize: '12.67px', typeface: 'Arial', color: '#5D6369' } }] },
      ]);
      h.text.alignment = 'left'; h.text.verticalAlignment = 'top'; h.text.autoFit = 'shrinkText';
      body.delete(); changes.mergedCards++;
    }

    // Substitui os quatro gráficos importados que geravam relações OOXML inválidas no PowerPoint.
    const marketShare = {
      16: [
        { categories: ['6º  UBS BB','5º  XP Investimentos','4º  Santander','3º  BTG Pactual','2º  Itaú BBA','1º  Bradesco BBI'], values: [0.07040879184,0.07825892098,0.09456496776,0.09952460536,0.2286817511,0.27789560251], blue: 4, frame: {left:59.52,top:168.96,width:547.2,height:437.76} },
        { categories: ['6º  UBS BB','5º  Santander','4º  XP Investimentos','3º  BTG Pactual','2º  Bradesco BBI','1º  Itaú BBA'], values: [0.07451209379,0.08883897779,0.09451906615,0.10418540682,0.20545717664,0.25024393331], blue: 5, frame: {left:649.92,top:168.96,width:547.2,height:437.76} },
      ],
      18: [
        { categories: ['6º  UBS BB','5º  Santander','4º  XP Investimentos','3º  BTG Pactual','2º  Bradesco BBI','1º  Itaú BBA'], values: [0.05618662601,0.07146291134,0.07350064594,0.15507438227,0.17869834915,0.26599103078], blue: 5, frame: {left:59.52,top:168.96,width:547.2,height:437.76} },
        { categories: ['6º  UBS BB','5º  Santander','4º  XP Investimentos','3º  BTG Pactual','2º  Bradesco BBI','1º  Itaú BBA'], values: [0.06424275488,0.0789632087,0.08384054545,0.16031117313,0.16255878564,0.24625711518], blue: 5, frame: {left:649.92,top:168.96,width:547.2,height:437.76} },
      ],
    };
    for (const idx of [16, 18]) {
      const slide = presentation.slides.items[idx];
      for (const chart of [...slide.charts.items]) slide.charts.deleteById(chart.id);
      for (const spec of marketShare[idx]) {
        slide.charts.add('bar', {
          position: spec.frame,
          categories: spec.categories,
          series: [{
            name: 'Market share',
            values: spec.values,
            valuesFormatCode: '0.0%',
            fill: '#8D9399',
            points: spec.categories.map((_, pointIdx) => ({ idx: pointIdx, fill: pointIdx === spec.blue ? '#14315C' : '#8D9399' })),
          }],
          barOptions: { direction: 'bar', grouping: 'clustered', gapWidth: 45, varyColors: false },
          hasLegend: false,
          chartFill: { color: '#FFFFFF', transparency: 100000 },
          plotAreaFill: { color: '#FFFFFF', transparency: 100000 },
          chartLine: { width: 0, fill: { color: '#FFFFFF', transparency: 100000 } },
          plotAreaLine: { width: 0, fill: { color: '#FFFFFF', transparency: 100000 } },
          xAxis: { visible: true, min: 0, max: 0.35, majorUnit: 0.05, numberFormatCode: '0%', textStyle: { fill: '#5D6369', fontSize: 9 }, majorGridlines: null, line: { style: 'solid', fill: '#8D9399', width: 1 } },
          yAxis: { visible: true, textStyle: { fill: '#3C4248', fontSize: 13 }, majorGridlines: null, line: { style: 'solid', fill: '#D9DDE1', width: 1 } },
          dataLabels: { showValue: true, position: 'outEnd', textStyle: { fill: '#2F3438', fontSize: 12, bold: true } },
        });
        changes.chartsRefreshed++;
      }
    }
  }
  return changes;
}

async function writeBlob(file, blob) { await fs.writeFile(file, new Uint8Array(await blob.arrayBuffer())); }

async function renderAll(presentation, dir, prefix) {
  await fs.mkdir(dir, { recursive: true });
  const layouts = path.join(dir, 'layouts');
  const previews = path.join(dir, 'slides');
  await fs.mkdir(layouts, { recursive: true });
  await fs.mkdir(previews, { recursive: true });
  for (let i = 0; i < presentation.slides.items.length; i++) {
    const slide = presentation.slides.items[i];
    const stem = `${prefix}-slide-${String(i + 1).padStart(2, '0')}`;
    const png = await presentation.export({ slide, format: 'png', scale: 1 });
    await writeBlob(path.join(previews, `${stem}.png`), png);
    const layout = await slide.export({ format: 'layout', scale: 1 });
    await writeBlob(path.join(layouts, `${stem}.layout.json`), layout);
  }
  const montage = await presentation.export({ format: 'webp', montage: true, scale: 1 });
  await writeBlob(path.join(dir, `${prefix}-montage.webp`), montage);
}

async function main() {
  const [fullIn, compactIn, outDir] = process.argv.slice(2);
  if (!fullIn || !compactIn || !outDir) throw new Error('Uso: edit_v3.mjs full compact outDir');
  await fs.mkdir(outDir, { recursive: true });
  const full = await PresentationFile.importPptx(await FileBlob.load(fullIn));
  const compact = await PresentationFile.importPptx(await FileBlob.load(compactIn));
  const fullChanges = simplifyDeck(full, { compact: false });
  const compactChanges = simplifyDeck(compact, { compact: true });
  const fullOut = path.join(outDir, 'Industria_FIDC_Completa_Revisada_20260901_v3.pptx');
  const compactOut = path.join(outDir, 'FIDC_Revisao_Diretoria_20260901_v3.pptx');
  await (await PresentationFile.exportPptx(full)).save(fullOut);
  await (await PresentationFile.exportPptx(compact)).save(compactOut);
  await renderAll(full, path.join(outDir, 'full-render'), 'full');
  await renderAll(compact, path.join(outDir, 'compact-render'), 'compact');
  console.log(JSON.stringify({ fullOut, compactOut, fullSlides: full.slides.items.length, compactSlides: compact.slides.items.length, fullChanges, compactChanges }, null, 2));
}

main().catch(e => { console.error(e); process.exitCode = 1; });
