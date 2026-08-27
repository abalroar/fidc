import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';
import os from 'node:os';
const {values:args}=parseArgs({options:{workspace:{type:'string'},data:{type:'string'},output:{type:'string'},full:{type:'boolean'}}});
for(const key of ['workspace','data','output'])if(!args[key])throw Error(`Missing --${key}`);
const runtimeModules=process.env.RUNTIME_NODE_MODULES || path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const require=createRequire(path.join(runtimeModules,'package.json'));
const {FileBlob,Presentation,PresentationFile}=require('@oai/artifact-tool');
const tmp=path.resolve(args.workspace);
const output=path.resolve(args.output);
const out=path.dirname(output);
const data=JSON.parse(await fs.readFile(path.resolve(args.data),'utf8'));
const imported=await PresentationFile.importPptx(await FileBlob.load(path.join(tmp,'template-starter.pptx')));
const indices=args.full?[33,37,38]:[0,1,2];
const model=imported.toProto();
const latest=data.manifest.latest_complete;
const clone=x=>structuredClone(x);
const solid=hex=>({type:1,color:{type:1,value:hex.replace('#','')},gradientStops:[],pictureEffects:[]});
const fmt=v=>Number(v).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1});
function element(i,id){const e=model.slides[indices[i]].elements.find(e=>e.id===id);if(!e)throw Error(`Missing ${i}/${id}`);return e;}
function chart(i,id){return model.charts.find(c=>c.id===element(i,id).chartReference.id);}
function text(i,id,value){
  const e=element(i,id);
  if(e.paragraphs.length!==1 || e.paragraphs[0].runs.length!==1)throw Error(`Unexpected text structure ${i}/${id}`);
  e.paragraphs[0].runs[0].text=value;
}
function values(s,labels,numbers){
  if(numbers.some(v=>!Number.isFinite(v)))throw Error('Nonfinite chart data');
  s.categories=labels;s.values=numbers;s.valueIndices=numbers.map((_,i)=>i);
  s.categoryIndices=[];s.valuePointCount=numbers.length;s.formula='';s.categoryFormula='';
}
const color=name=>name==='Itaú'?'FF5500':name.includes('Kanastra')?'7030A0':({'QI Tech':'2456D6','BTG Pactual':'1D4080','Oliveira Trust':'7A1F3D','Genial':'67C9E6','Daycoval':'BEC2C5'}[name]||'73787D');

// 1. Keep the original true Top 5, then the two comparators at the bottom.
for(const [role,id] of [['administrador','24'],['gestor','26'],['custodiante','28']]){
 const rows=data.prestadores_separados.filter(r=>r.competencia===latest && r.papel===role && r.ordem_slide!=='').sort((a,b)=>Number(a.ordem_slide)-Number(b.ordem_slide)).reverse();
 const c=chart(0,id),s=c.series[0];
 values(s,rows.map(r=>r.participante==='Kanastra (incl. Limine)'?'Kanastra / Limine':r.participante),rows.map(r=>r.pl_brl/1e9));
 s.points=rows.map((r,idx)=>({idx,fill:solid(color(r.participante))}));
 c.barOptions.gapWidth=20;
 for(const axis of [c.yAxis,...c.axes.filter(a=>a.kind===3)])axis.deleted=true;
}
text(0,'22','Volume por prestador | Itaú e Kanastra separados');
text(0,'2','Jun/26 · PL ex-FIC, em R$ bilhões · Top 5 + comparadores');
text(0,'8','Top 5 + Itaú + Kanastra');
text(0,'5','Fonte: CVM, jun/26. Sem Petrobras/TAPSO. Itaú inclui Intrag/Kinea; Kanastra inclui Limine. Independentes: curadoria original.');
text(0,'6',String(indices[0]+1));

// 2. Recalculate every stock series and percentage; tested zero offer hits.
const stock=data.saldo_cenarios.filter(r=>r.cenario==='sem_tapso_petrobras');
for(const [id,field] of [['34','pl_brl'],['35','share']]){
 const c=chart(1,id);
 for(const s of c.series){
   const numbers=data.manifest.periods.map(period=>{
    const r=stock.find(r=>r.competencia===period && r.categoria===s.name);
    if(!r)throw Error(`Missing stock ${period}/${s.name}`);
    return field==='pl_brl'?r.pl_brl/1e9:r.share;
   });
   values(s,s.categories,numbers);
   s.dataLabelOverrides.forEach((label,i)=>{label.showValue=field==='pl_brl'?numbers[i]>=15:numbers[i]>=.035;});
 }
}
const denominator=stock.find(r=>r.competencia===latest).denominador_pl_brl;
// Improve label contrast in the additional slide; emission values are unchanged.
for(const id of ['36','37']){
 const c=chart(1,id);
 for(const s of c.series){
  s.dataLabelOverrides=s.values.map((value,idx)=>({
   ...clone(c.dataLabels),idx,showValue:id==='37'||value>=8,
   textStyle:{fontSize:1000,fill:solid(['Fomento Mercantil','Agro, Indústria e Comércio'].includes(s.name)?'FFFFFF':'151515')},
  }));
 }
}
text(1,'2','Saldo e Tipos de FIDCs | Sem TAPSO e Sistema Petrobras');
text(1,'5',`Fonte: CVM/ANBIMA. Jun/26: PL de R$ ${fmt(denominator/1e9)} bi. Exclusão em todo o histórico; nenhuma oferta dos dois CNPJs na coorte.`);
text(1,'6',String(indices[1]+1));

// 3. Four disjoint screening groups; no claim that PF/PJ is validated as diversified.
const screenKeys=['PF pessoal / estudantil / BNPL (triagem)','PJ / PF-PJ (triagem)','Fomento Mercantil','Multicedente / multisacado'];
const screenRows=screenKeys.map(k=>data.credito_triagem_resumo.find(r=>r.recorte_credito===k));
const labels=['Crédito PF*','PJ / PF-PJ*','Fomento Mercantil','Multicedente / multisacado'];
for(const [id,field,max] of [['17','pl_brl',100],['18','share_total',.12]]){
 const c=chart(2,id),s=clone(c.series[0]);
 s.name=field==='pl_brl'?'PL dos fundos · R$ bi':'Participação no PL ex-FIC';
 s.valuesFormatCode=field==='pl_brl'?'0.0':'0.0%';
 values(s,labels,screenRows.map(r=>field==='pl_brl'?r.pl_brl/1e9:r.share_total));
 s.dataLabelOverrides=[];delete s.dataLabels;
 s.points=labels.map((_,idx)=>({idx,fill:solid(['EC7000','30353A','73787D','7030A0'][idx])}));
 c.series=[s];c.barOptions.grouping=1;c.barOptions.overlap=0;c.barOptions.gapWidth=60;
 c.dataLabels.position=2;c.dataLabels.textStyle.fill=solid('FFFFFF');c.dataLabels.showValue=true;
 for(const a of [c.yAxis,...c.axes.filter(a=>a.kind===3)]){a.max=max;a.numberFormatCode=field==='pl_brl'?'0':'0%';}
}
const deletedLegend=element(2,'19').chartReference.id;
model.slides[indices[2]].elements=model.slides[indices[2]].elements.filter(e=>e.id!=='19');
model.charts=model.charts.filter(c=>c.id!==deletedLegend);
text(2,'16','Crédito pulverizado PF/PJ | Triagem dos fundos candidatos');
text(2,'2','Jun/26 · PL dos fundos por classificação atual; pulverização ainda não validada');
text(2,'7','PL dos fundos · R$ bilhões');
text(2,'10','Participação no PL total ex-FIC');
const screenTotal=screenRows[0].pl_brl+screenRows[1].pl_brl;
text(2,'14',`*PF e PJ: R$ ${fmt(screenTotal/1e9)} bi em candidatos (${fmt((screenRows[0].share_total+screenRows[1].share_total)*100)}% do PL); total pulverizado validado = N/D.`);
text(2,'15','PF*: pessoal, estudantil e BNPL. Recorte não exaustivo; exclui consignado, veículos, imobiliário e meios de pagamento. CCB não comprova PJ nem pulverização; há conflitos documentais.');
text(2,'5',`Fonte: CVM/ANBIMA e ledger vigente. Base total: R$ ${fmt(screenRows[0].denominador_pl_brl/1e9)} bi. Valores de triagem; ver CSV por CNPJ e relatório de evidências.`);
text(2,'6',String(indices[2]+1));

const final=Presentation.load(model);
const sourceNotes=[
 '[Sources]\nCVM Informe Mensal jun/26; bases/prestadores_separados.csv e prestadores_linhagem.csv. Itaú/INTRAG/Kinea conforme curadoria existente. Kanastra/Limine: https://pt.linkedin.com/posts/kanastra_kanastra-compra-limine-dtvm-para-avan%C3%A7ar-activity-7181046721483816960-aUAG . Participação minoritária Itaú: https://www.itau.com.br/media/dam/m/36e80c6030c3408c/original/010425-intrag-volta-ao-negocio-de-fidcs-de-recebiveis-em-parceria-com-a-kanastra.pdf . Gestão/custódia: cadastro vigente; sem soma entre funções.',
 '[Sources]\nCVM Informe Mensal jun/26; bases/saldo_cenarios.csv; bases/exclusoes_por_cnpj.csv; bases/emissoes_cenario.csv. CNPJs 09195235000150 e 26287464000114 excluídos do numerador e denominador em todos os períodos. Coorte de ofertas verificada sem ocorrências dos dois fundos; valores de emissão mantidos. Original preservado.',
 '[Sources]\nCVM/ANBIMA e taxonomy_review_actions.csv congelados no manifesto. bases/credito_triagem_cnpj.csv e credito_triagem_resumo.csv. Nenhuma nova classificação aprovada. Exemplo de conflito: Mercado Crédito (33254370000104), regulamento 1128340, pp. 9 e 94, permite PF e PJ; Mercado Crédito I Brasil (37511828000114), regulamento 1200490, pp. 20 e 143, mandato consumidor/comerciante e limite de 0,5% por devedor nos critérios de enquadramento. Não mede composição efetiva de jun/26. Monee I (42922136000107): o regulamento 1159092, pp.30–33, trata de arranjos de pagamento; revalidar rótulo BNPL da curadoria. URLs: https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1128340 ; https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1200490 ; https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=1159092 .',
];
await fs.mkdir(path.join(tmp,'final-layout'),{recursive:true});
await fs.mkdir(path.join(tmp,'final-render'),{recursive:true});
for(const [i,s] of final.slides.items.entries()){
 if(indices.includes(i))s.speakerNotes.textFrame.setText(sourceNotes[indices.indexOf(i)]);
 const image=await final.export({slide:s,format:'png',scale:1.5});
 await fs.writeFile(path.join(tmp,'final-render',`slide-${i+1}.png`),Buffer.from(await image.arrayBuffer()));
 await fs.writeFile(path.join(tmp,'final-layout',`slide-${String(i+1).padStart(2,'0')}.layout.json`),await (await s.export({format:'layout'})).text());
}
await fs.mkdir(out,{recursive:true});
await (await PresentationFile.exportPptx(final)).save(output);
console.log(output);
