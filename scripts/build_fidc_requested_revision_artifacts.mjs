import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';
import os from 'node:os';
import crypto from 'node:crypto';

const parsed=parseArgs({options:{workspace:{type:'string'},data:{type:'string'},output:{type:'string'},full:{type:'boolean'}}});
const args=parsed.values;
for(const key of ['workspace','data','output']) if(!args[key]) throw Error('Missing --'+key);
const runtimeModules=process.env.RUNTIME_NODE_MODULES || path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const require=createRequire(path.join(runtimeModules,'package.json'));
const {FileBlob,Presentation,PresentationFile}=require('@oai/artifact-tool');
const tmp=path.resolve(args.workspace);
const output=path.resolve(args.output);
const data=JSON.parse(await fs.readFile(path.resolve(args.data),'utf8'));
const imported=await PresentationFile.importPptx(await FileBlob.load(path.join(tmp,'template-starter.pptx')));
const model=imported.toProto();
const latest=data.manifest.latest_complete;
const periods=data.manifest.periods;
const scenario=data.manifest.stock_scenario;
const cats=[
 'Fomento Mercantil',
 'Agro, Indústria e Comércio',
 'Financeiro',
 'Multicarteira Pulverizado PF/PJ',
 'Precatórios / ações',
 'Multicedente / multisacado',
 'Recuperação / NP',
 'N/D',
];
const colors={
 'Fomento Mercantil':'73787D',
 'Agro, Indústria e Comércio':'104B08',
 'Financeiro':'F07800',
 'Multicarteira Pulverizado PF/PJ':'4472C4',
 'Precatórios / ações':'151515',
 'Multicedente / multisacado':'7030A0',
 'Recuperação / NP':'D7DADF',
 'N/D':'EEF0F2',
};
const providerColors={
 'Itaú':'FF5500',
 'Kanastra (incl. Limine)':'7030A0',
 'QI Tech':'2456D6',
 'BTG Pactual':'1D4080',
 'Oliveira Trust':'7A1F3D',
 'Bradesco':'73787D',
 'Daycoval':'BEC2C5',
 'Genial':'6EC5E9',
 'Tercon Investimentos':'8D9399',
 'CBSF':'73C6A1',
 'Solis Investimentos':'BEC2C5',
 'Integral Investimentos':'A7ACB0',
 'REAG':'73C6A1',
 'Finaxis':'5B6065',
 'BRL Trust':'454A4F',
 'Hemera':'30353A',
};
const clone=x=>structuredClone(x);
const solid=hex=>({type:1,color:{type:1,value:hex.replace('#','')},gradientStops:[],pictureEffects:[]});
const fmt=v=>Number(v).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1});
const pct=v=>Number(v).toLocaleString('pt-BR',{style:'percent',minimumFractionDigits:1,maximumFractionDigits:1});
const metric=name=>{
 const r=data.metricas_reconciliacao.find(x=>x.metrica===name);
 if(!r) throw Error('Missing metric '+name);
 return r.valor;
};
function element(index,id){
 const e=model.slides[index].elements.find(x=>x.id===id);
 if(!e) throw Error('Missing element slide '+(index+1)+' id '+id);
 return e;
}
function chart(index,id){
 const e=element(index,id);
 const c=model.charts.find(x=>x.id===e.chartReference.id);
 if(!c) throw Error('Missing chart '+id);
 return c;
}
function setText(index,id,value,fontSize){
 const e=element(index,id);
 if(!e.paragraphs || !e.paragraphs.length) throw Error('No text '+index+'/'+id);
 const run=e.paragraphs[0].runs[0];
 e.paragraphs=[clone(e.paragraphs[0])];
 e.paragraphs[0].runs=[clone(run)];
 e.paragraphs[0].runs[0].text=value;
 if(fontSize) e.paragraphs[0].runs[0].textStyle.fontSize=fontSize;
}
function setValues(series,labels,numbers){
 if(numbers.some(v=>!Number.isFinite(v))) throw Error('Nonfinite chart data');
 series.categories=labels;
 series.values=numbers;
 series.valueIndices=numbers.map((_,i)=>i);
 series.categoryIndices=[];
 series.valuePointCount=numbers.length;
 series.formula='';
 series.categoryFormula='';
}
function seriesFor(chartObj,name,index){
 const existing=chartObj.series.find(s=>s.name===name);
 const base=existing || chartObj.series[Math.min(index,chartObj.series.length-1)] || chartObj.series[0];
 if(!base) throw Error('Chart without base series');
 const s=clone(base);
 s.name=name;
 s.fill=solid(colors[name]);
 s.stroke=s.stroke||{};
 s.stroke.fill=solid(colors[name]);
 s.points=[];
 return s;
}
function replaceStackedSeries(chartObj,rows,field,labels,threshold,displayLabels=labels){
 const next=[];
 for(const [idx,name] of cats.entries()){
  const s=seriesFor(chartObj,name,idx);
  const numbers=labels.map(label=>{
   const r=rows.find(x=>(x.competencia||x.period_key)===label && x.categoria===name);
   if(!r) throw Error('Missing '+field+' '+label+'/'+name);
   return field==='pl_brl' || field==='volume_brl' ? Number(r[field])/1e9 : Number(r[field]);
  });
  setValues(s,displayLabels,numbers);
  s.valuesFormatCode=field==='share'?'0.0%':'0.0';
  s.dataLabelOverrides=numbers.map((value,i)=>({
   ...(chartObj.dataLabels?clone(chartObj.dataLabels):{}),
   idx:i,
   showValue:value>=threshold || (name==='Multicarteira Pulverizado PF/PJ' && i===numbers.length-1),
   textStyle:{fontSize:900,fill:solid(['Fomento Mercantil','Agro, Indústria e Comércio','Financeiro','Multicarteira Pulverizado PF/PJ','Precatórios / ações','Multicedente / multisacado'].includes(name)?'FFFFFF':'151515')},
  }));
  next.push(s);
 }
 chartObj.series=next;
 if(chartObj.dataLabels) chartObj.dataLabels.showValue=false;
 if(chartObj.barOptions) chartObj.barOptions.gapWidth=20;
}
function stockRows(){
 return data.saldo_cenarios.filter(r=>r.cenario===scenario);
}
function issuanceRows(){
 return data.emissoes_por_categoria;
}
function editStockCharts(index,ids){
 const stock=stockRows();
 const stockLabels=['dez/23','dez/24','dez/25','jun/26'];
 replaceStackedSeries(chart(index,ids[0]),stock,'pl_brl',periods,15,stockLabels);
 replaceStackedSeries(chart(index,ids[1]),stock,'share',periods,.035,stockLabels);
 const issue=issuanceRows();
 const ip=['2023','2024','2025','jun25','jun26'];
 const issueLabels=['2023','2024','2025','jan–jun/25','jan–jun/26'];
 replaceStackedSeries(chart(index,ids[2]),issue,'volume_brl',ip,5,issueLabels);
 replaceStackedSeries(chart(index,ids[3]),issue,'share',ip,.05,issueLabels);
}
function setLegendSquare(index,id,hex){
 const e=element(index,id);
 e.fill=solid(hex);
 if(e.shape) e.shape.fill=solid(hex);
}
function editStockSlide(index,page){
 editStockCharts(index,['34','35','36','37']);
 setText(index,'2','Saldo e Tipos de FIDCs | Abertura PF/PJ e cenário sem TAPSO/Petrobras');
 setText(index,'5','* PF/PJ: 24 CNPJs; PL dos fundos, Top1 mensal <=1%; Sólido e BizCapital em Financeiro. Emissões por CNPJ; FIC fora; 2023 escalado ANBIMA.',900);
 setText(index,'6',String(page));
 setText(index,'26','PF/PJ*');
 setLegendSquare(index,'25',colors['Multicarteira Pulverizado PF/PJ']);
}
function setCellText(cell,value,fontSize,bold,color){
 const source=(cell.paragraphs && cell.paragraphs[0] && cell.paragraphs[0].runs && cell.paragraphs[0].runs[0]) || {textStyle:{}};
 const lines=String(value).split('\n');
 cell.paragraphs=lines.map(line=>{
  const p=clone(cell.paragraphs[0] || {runs:[source],textStyle:{},inlineNodes:[],paragraphStyle:{bulletCharacter:'',tabStops:[]}});
  const r=clone(source);
  r.text=line;
  r.textStyle=r.textStyle || {};
  r.textStyle.fontSize=fontSize;
  r.textStyle.bold=bold;
  r.textStyle.fill=solid(color);
  p.runs=[r];
  return p;
 });
 cell.text=String(value);
 if(cell.elements && cell.elements[0]) cell.elements[0].paragraphs=clone(cell.paragraphs);
}
function renewRow(row){
 row.id=crypto.randomUUID();
 for(const cell of row.cells){
  cell.id=crypto.randomUUID();
  if(cell.elements && cell.elements[0]) cell.elements[0].id=cell.id+'-text';
 }
 return row;
}
function tableValue(rows,category,key,field){
 const r=rows.find(x=>x.categoria===category && x.period_key===key);
 if(!r) throw Error('Missing table '+category+'/'+key);
 return Number(r[field]);
}
function editIssuanceSlide(index,page){
 const rows=issuanceRows();
 const ip=['2023','2024','2025','jun25','jun26'];
 const issueLabels=['2023','2024','2025','jan–jun/25','jan–jun/26'];
 replaceStackedSeries(chart(index,'19'),rows,'volume_brl',ip,5,issueLabels);
 replaceStackedSeries(chart(index,'20'),rows,'share',ip,.05,issueLabels);
 const e=element(index,'21');
 const header=clone(e.table.rows[0]);
 const bodyStyle=clone(e.table.rows[1]);
 const totalStyle=clone(e.table.rows[e.table.rows.length-1]);
 const display={
  'Multicarteira Pulverizado PF/PJ':'Multicarteira Pulv. PF/PJ',
  'Multicedente / multisacado':'Multicedente/multissacado',
  'Precatórios / ações':'Precatórios/ações',
  'Recuperação / NP':'Recuperação/NP',
 };
 const newRows=[renewRow(header)];
 for(const category of cats){
  const row=renewRow(clone(bodyStyle));
  const values=[
   display[category]||category,
   fmt(tableValue(rows,category,'2023','volume_brl')/1e9),
   fmt(tableValue(rows,category,'2024','volume_brl')/1e9),
   fmt(tableValue(rows,category,'2025','volume_brl')/1e9),
   fmt(tableValue(rows,category,'jun25','volume_brl')/1e9),
   fmt(tableValue(rows,category,'jun26','volume_brl')/1e9),
   pct(tableValue(rows,category,'jun26','share')),
   tableValue(rows,category,'jun25','volume_brl')===0?'N/D':pct(tableValue(rows,category,'jun26','volume_brl')/tableValue(rows,category,'jun25','volume_brl')-1),
  ];
  row.heightEmu=140000;
  row.cells.forEach((cell,i)=>setCellText(cell,values[i],i===0?780:850,false,'30353A'));
  newRows.push(row);
 }
 const total=renewRow(clone(totalStyle));
 const totals=ip.map(key=>rows.filter(x=>x.period_key===key).reduce((a,b)=>a+Number(b.volume_brl),0));
 const totalValues=['Total ex-FIC',...totals.slice(0,5).map(v=>fmt(v/1e9)),'100,0%',pct(totals[4]/totals[3]-1)];
 total.heightEmu=145000;
 total.cells.forEach((cell,i)=>setCellText(cell,totalValues[i],i===0?800:850,false,'30353A'));
 newRows.push(total);
 newRows[0].heightEmu=180000;
 newRows[0].cells.forEach(cell=>{
  const tx=cell.text;
  setCellText(cell,tx,900,true,'FFFFFF');
 });
 e.table.rows=newRows;
 setText(index,'2','Emissões por setor | Financeiro é 60,3% e PF/PJ 4,2% no 1S26');
 setText(index,'13','Emissões por categoria analítica · taxonomia congelada em jun/26');
 setText(index,'17','* Match por CNPJ do fundo e depois da classe; FIC fora; emissor não localizado=N/D; 2023 escalado ao total ANBIMA.',900);
 setText(index,'5','Fonte: CVM/SRE e ANBIMA. Setores ex-FIC; 1S26 totaliza R$ 62,7 bi e reconcilia com R$ 65,5 bi incluindo R$ 2,8 bi de FIC-FIDC.',900);
 setText(index,'6',String(page));
}
function editMethodSlide(index,page){
 const stock=stockRows();
 const stockLabels=['dez/23','dez/24','dez/25','jun/26'];
 replaceStackedSeries(chart(index,'17'),stock,'pl_brl',periods,15,stockLabels);
 replaceStackedSeries(chart(index,'18'),stock,'share',periods,.035,stockLabels);
 const legend=chart(index,'19');
 legend.series=cats.map((name,i)=>{
  const s=seriesFor(legend,name,i);
  setValues(s,[''],[0]);
  return s;
 });
 setText(index,'16','Taxonomia por CNPJ | Critérios aplicados ao saldo e às emissões');
 setText(index,'2','Jun/26 · cenário sem TAPSO/Petrobras · série retroaplicada com taxonomia congelada');
 setText(index,'14','Oito blocos fecham R$ '+fmt(Number(metric('pl_sem_tapso_petrobras_brl'))/1e9)+' bi; PF/PJ soma R$ '+fmt(Number(metric('pfpj_pl_brl'))/1e9)+' bi ('+pct(Number(metric('pfpj_share_sem_tapso_petrobras')))+').');
 setText(index,'15','* PF/PJ: crédito direto confirmado em regulamento + Top1 <=1%; 24 CNPJs; Sólido/BizCapital em Financeiro; PL dos fundos, exposição e devedores N/D.\n* Precatórios: Outros/Poder Público. Multicedente: Outros/Multicarteira Outros ou Multicedente/Multissacado. Recuperação: Outros/Recuperação.\n* Emissões: mesmas listas de CNPJ; fundo > classe > N/D; FIC fora; 2023 escalado ANBIMA.',850);
 const box=element(index,'15');
 box.bbox.yEmu=5740000;
 box.bbox.heightEmu=620000;
 setText(index,'5','Fonte: CVM, ANBIMA, regulamentos integrais e ledgers aprovados. Regras e prompt de atualização no pacote da revisão.',900);
 setText(index,'6',String(page));
}
function editProvider(index,page){
 for(const roleId of [['administrador','24'],['gestor','26'],['custodiante','28']]){
  const role=roleId[0], id=roleId[1];
  const rows=data.prestadores_separados.filter(r=>r.competencia===latest && r.papel===role && r.ordem_slide!=='').sort((a,b)=>Number(a.ordem_slide)-Number(b.ordem_slide)).reverse();
  const c=chart(index,id),s=c.series[0];
  setValues(s,rows.map(r=>r.participante==='Kanastra (incl. Limine)'?'Kanastra / Limine':r.participante),rows.map(r=>Number(r.pl_brl)/1e9));
  s.points=rows.map((r,i)=>({idx:i,fill:solid(providerColors[r.participante] || '8D9399')}));
 }
 setText(index,'22','Volume por prestador | Itaú e Kanastra separados');
 setText(index,'2','Jun/26 · PL ex-FIC, em R$ bilhões · Top 5 + comparadores');
 setText(index,'5','Fonte: CVM, jun/26. Sem Petrobras/TAPSO. Itaú inclui Intrag/Kinea; Kanastra inclui Limine. Independentes: curadoria original.');
 setText(index,'6',String(page));
}
function editAuditSlide(index,page){
 const categories=['Multicarteira Pulverizado PF/PJ','Financeiro','Fomento Mercantil','Multicedente / multisacado'];
 const labels=['PF/PJ*','Financeiro','Fomento','Multicedente'];
 const stock=stockRows().filter(r=>r.competencia===latest);
 for(const pair of [['17','pl_brl'],['18','share']]){
  const id=pair[0], field=pair[1], c=chart(index,id);
  const s=clone(c.series[0]);
  s.name=field==='pl_brl'?'R$ bi':'% do PL ex-FIC';
  const nums=categories.map(name=>{
   const r=stock.find(x=>x.categoria===name);
   return field==='pl_brl'?Number(r.pl_brl)/1e9:Number(r.share);
  });
  setValues(s,labels,nums);
  s.points=categories.map((name,i)=>({idx:i,fill:solid(colors[name])}));
  s.dataLabelOverrides=[];
  c.series=[s];
  c.dataLabels.showValue=true;
  c.dataLabels.textStyle.fill=solid('FFFFFF');
 }
 setText(index,'16','Multicarteira Pulverizado PF/PJ | Decisão final de jun/26');
 setText(index,'2','24 fundos incluídos; Sólido e BizCapital permanecem em Financeiro');
 setText(index,'14','* R$ '+fmt(Number(metric('pfpj_pl_brl'))/1e9)+' bi = PL integral dos 24 fundos ('+pct(Number(metric('pfpj_share_sem_tapso_petrobras')))+' do PL sem TAPSO/Petrobras).');
 setText(index,'15','Regulamentos lidos integralmente; crédito direto PF/PJ confirmado; Top1 mensal <=1% dos DC brutos. Foram reportadas '+metric('pfpj_posicoes_reportadas')+' posições; isso não informa o total de devedores. Exposição efetiva PF/PJ, divisão PF/PJ e total de devedores: N/D. Taxonomia congelada em jun/26 e retroaplicada.',850);
 const box=element(index,'15'); box.bbox.heightEmu=500000;
 setText(index,'5','Fonte: CVM, Informe Mensal jun/26, regulamentos e ledger de 26 decisões. Ver CSV dos 24 incluídos e prompt de atualização.',900);
 setText(index,'6',String(page));
}
if(args.full){
 editStockSlide(3,4);
 editIssuanceSlide(4,5);
 editMethodSlide(5,6);
 editProvider(33,34);
 editStockSlide(37,38);
 editAuditSlide(38,39);
}else{
 editProvider(0,1);
 editStockSlide(1,2);
 editAuditSlide(2,3);
}
const final=Presentation.load(model);
const notes={
 stock:'[Sources]\nCVM Informe Mensal jun/26; bases/saldo_cenarios.csv; bases/emissoes_por_categoria.csv; bases/exclusoes_por_cnpj.csv. PF/PJ via bases/pfpj_24_incluidos.csv. Cenário sem CNPJs 09195235000150 e 26287464000114.',
 issuance:'[Sources]\nCVM/SRE, ofertas encerradas; bases/emissoes_por_cnpj.csv, emissoes_por_categoria.csv e emissoes_auditoria.csv. Match por CNPJ do fundo e depois da classe; FIC fora; sem match=N/D. 2023 escalado ao total encerrado ANBIMA.',
 method:'[Sources]\nCVM/ANBIMA, regulamentos integrais, taxonomy_review_actions.csv, bases/criterios_categorias.csv e categorias_cnpj_jun26.csv. Taxonomia congelada em jun/26 e retroaplicada.',
 providers:'[Sources]\nCVM Informe Mensal jun/26; bases/prestadores_separados.csv e prestadores_linhagem.csv. Itaú/Intrag/Kinea e Kanastra/Limine conforme curadoria documentada.',
 audit:'[Sources]\nCVM Informe Mensal jun/26, Tabelas I, II e VIII; regulamentos integrais; bases/pfpj_26_decisoes.csv e pfpj_24_incluidos.csv. PL dos fundos; exposição efetiva, PF/PJ split e total de devedores=N/D.',
};
if(args.full){
 final.slides.items[3].speakerNotes.textFrame.setText(notes.stock);
 final.slides.items[4].speakerNotes.textFrame.setText(notes.issuance);
 final.slides.items[5].speakerNotes.textFrame.setText(notes.method);
 final.slides.items[33].speakerNotes.textFrame.setText(notes.providers);
 final.slides.items[37].speakerNotes.textFrame.setText(notes.stock);
 final.slides.items[38].speakerNotes.textFrame.setText(notes.audit);
}else{
 final.slides.items[0].speakerNotes.textFrame.setText(notes.providers);
 final.slides.items[1].speakerNotes.textFrame.setText(notes.stock);
 final.slides.items[2].speakerNotes.textFrame.setText(notes.audit);
}
await fs.mkdir(path.dirname(output),{recursive:true});
await (await PresentationFile.exportPptx(final)).save(output);
console.log(output);
