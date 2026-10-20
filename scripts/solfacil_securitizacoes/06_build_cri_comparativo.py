# -*- coding: utf-8 -*-
import json
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT="/home/user/fidc/outputs/solfacil/Solfacil_CRIs_Comparativo.xlsx"
AR="Arial"; NAVY="1F3864"; BLUE="2E5C8A"; W="FFFFFF"; BL="0000FF"; GREY="F2F2F2"
thin=Side(style="thin",color="BFBFBF"); BOX=Border(left=thin,right=thin,top=thin,bottom=thin)
CDI=13.65

CRIS=["CRI I","CRI II","CRI III","CRI IV","CRI V","CRI VI"]
# serie: (nome, R$ mm, taxa texto, custo a.a. %, vencimento, ISIN, privada?)
SER={
"CRI I":[("Super Sênior",360.0,"Pré 11,51%",11.51,"",  "BRKNSTCRI000",0),
         ("Sênior",90.0,"Pré 12,74%",12.74,"","BRKNSTCRI018",0),
         ("Mezanino",108.0,"Pré 16,48%",16.48,"","BRKNSTCRI026",0),
         ("Subordinado",30.0,"Pré 20,95%",20.95,"","BRKNSTCRI034",0),
         ("Subordinado Jr (privada)",12.0,"9,86% (informe)",9.86,"","",1)],
"CRI II":[("Super Sênior",487.5,"Pré 13,1926%",13.1926,"15/01/2031","BRKNSTCRI059",0),
         ("Sênior",135.0,"Pré 14,5663%",14.5663,"15/01/2031","BRKNSTCRI067",0),
         ("Mezanino",75.0,"CDI + 6,00%",CDI+6.00,"15/01/2034","BRKNSTCRI075",0),
         ("Subordinado",30.0,"CDI + 10,00%",CDI+10.00,"15/01/2034","BRKNSTCRI083",0),
         ("Subordinado Jr (privada)",22.5,"n.d.",None,"15/01/2036","",1)],
"CRI III":[("Super Sênior A",367.5,"Pré 15,50%",15.50,"","BRKNSTCRI0A4",0),
         ("Super Sênior B",120.0,"Pré 15,50%",15.50,"","BRKNSTCRI0B2",0),
         ("Sênior",135.0,"Pré 16,50%",16.50,"","BRKNSTCRI0C0",0),
         ("Mezanino",75.0,"CDI + 5,75%",CDI+5.75,"","BRKNSTCRI0D8",0),
         ("Subordinado",30.0,"CDI + 10,00%",CDI+10.00,"","BRKNSTCRI0E6",0),
         ("Subordinado Jr (privada)",22.5,"n.d.",None,"","",1)],
"CRI IV":[("Super Sênior A",195.0,"Pré 14,2216%",14.2216,"20/09/2030","BRKNSTCRI0G1",0),
         ("Super Sênior B",97.5,"Pré 14,2216%",14.2216,"20/09/2030","BRKNSTCRI0K3",0),
         ("Sênior A",54.0,"Pré 15,3565%",15.3565,"22/09/2033","BRKNSTCRI0H9",0),
         ("Sênior B",27.0,"Pré 15,3565%",15.3565,"22/09/2033","BRKNSTCRI0M9",0),
         ("Mezanino",45.0,"CDI + 5,50%",CDI+5.50,"24/09/2035","BRKNSTCRI0I7",0),
         ("Subordinado",18.0,"CDI + 10,00%",CDI+10.00,"24/09/2035","BRKNSTCRI0J5",0),
         ("Subordinado Jr (privada)",13.5,"CDI + 13,2480%",CDI+13.248,"22/09/2037","BRKNSTCRI0N7",1)],
"CRI V":[("Super Sênior A",103.87,"Pré 14,8064%",14.8064,"20/05/2031","BRVERTCRIDZ7",0),
         ("Super Sênior B",225.55,"104% do CDI",1.04*CDI,"20/05/2031","BRVERTCRIE08",0),
         ("Sênior",70.59,"Pré 15,7760%",15.7760,"22/05/2034","BRVERTCRIE16",0),
         ("Mezanino",37.647,"CDI + 5,50%",CDI+5.50,"20/05/2036","BRVERTCRIE24",0),
         ("Subordinado",18.824,"CDI + 8,00%",CDI+8.00,"20/05/2036","BRVERTCRIE32",0),
         ("Subordinado Jr (privada)",14.118,"Pré 14,06%",14.06,"","",1)],
"CRI VI":[("Sênior A",100.0,"CDI + 1,50%",CDI+1.50,"20/05/2031","BRVERTCRIEC4",0),
         ("Sênior B",282.5,"CDI + 2,00%",CDI+2.00,"21/07/2031","BRVERTCRIED2",0),
         ("Mezanino I",36.0,"CDI + 5,50%",CDI+5.50,"21/07/2036","BRVERTCRIEE0",0),
         ("Mezanino II",18.0,"CDI + 8,00%",CDI+8.00,"21/07/2036","BRVERTCRIEF7",0),
         ("Subordinada (privada)",13.5,"100% do CDI",CDI,"20/07/2038","BRVERTCRIEG5",1)],
}
# nº de séries que formam a camada de topo (Super Sênior, ou Sênior no CRI VI)
TOPO={"CRI I":1,"CRI II":1,"CRI III":2,"CRI IV":2,"CRI V":2,"CRI VI":2}
# nº de séries na camada de topo + segunda camada
TOPO2={"CRI I":2,"CRI II":2,"CRI III":3,"CRI IV":4,"CRI V":3,"CRI VI":3}

INFO={
"CRI I":   dict(emissora="Kanastra",emissao="1ª",demi="15/01/2024",reg="16/02/2024",enc="23/02/2024",
   coord="Itaú BBA",af="Vórtx",rt="AA+sf(bra) / AAsf(bra) (Fitch)",nser=5,
   cob_topo=None,cob_2=None,cob_mez=None,cob_sub=None,txmin=21.5,conc="0,10% do patrimônio separado",
   tkpf=350,tkpj=600,carteira=277.81,pdd=43.62,atraso=22.30,npl90=16.35,dur="4 anos e 5 meses",saldo=226.28),
"CRI II":  dict(emissora="Kanastra",emissao="2ª",demi="25/06/2024",reg="21/06/2024",enc="28/06/2024",
   coord="Itaú BBA",af="Oliveira Trust",rt="AAA (Moody's) / AA+ (Fitch)",nser=5,
   cob_topo=159.00,cob_2=123.00,cob_mez=110.00,cob_sub=105.00,txmin=21.0,conc="0,10% do patrimônio separado",
   tkpf=350,tkpj=600,carteira=389.83,pdd=46.94,atraso=23.75,npl90=15.31,dur="1 ano e 2 meses",saldo=352.73),
"CRI III": dict(emissora="Kanastra",emissao="3ª",demi="28/05/2025",reg="03/06/2025",enc="06/06/2025",
   coord="Itaú BBA",af="Oliveira Trust",rt="AAA (Moody's)",nser=6,
   cob_topo=158.73,cob_2=123.46,cob_mez=109.89,cob_sub=105.26,txmin=22.0,conc="0,10% do patrimônio separado",
   tkpf=350,tkpj=700,carteira=545.06,pdd=26.04,atraso=11.44,npl90=5.09,dur="1 ano e 6 meses",saldo=536.60),
"CRI IV":  dict(emissora="Kanastra",emissao="4ª",demi="28/09/2025",reg="29/09/2025",enc="13/10/2025",
   coord="Itaú BBA",af="Oliveira Trust",rt="AAA (Moody's)",nser=7,
   cob_topo=158.73,cob_2=123.46,cob_mez=109.89,cob_sub=105.26,txmin=21.0,conc="0,25% do patrimônio separado",
   tkpf=350,tkpj=700,carteira=383.01,pdd=15.80,atraso=5.79,npl90=2.64,dur="4 anos",saldo=384.81),
"CRI V":   dict(emissora="Vert",emissao="174ª",demi="20/05/2026",reg="20/05/2026",enc="28/05/2026",
   coord="XP",af="Oliveira Trust",rt="AAA (Moody's)",nser=6,
   cob_topo=147.06,cob_2=120.48,cob_mez=109.89,cob_sub=105.26,txmin=21.0,conc="0,15% caindo a 0,07%",
   tkpf=350,tkpj=700,carteira=443.62,pdd=0.00,atraso=1.56,npl90=0.00,dur="n.d.",saldo=457.91),
"CRI VI":  dict(emissora="Vert",emissao="177ª",demi="21/07/2026",reg="20/07/2026",enc="02/09/2026",
   coord="XP e Bradesco BBI",af="Oliveira Trust",rt="Sem rating",nser=5,
   cob_topo=120.48,cob_2=109.89,cob_mez=105.26,cob_sub=None,txmin=21.5,conc="0,11% do valor da emissão",
   tkpf=350,tkpj=700,carteira=445.88,pdd=0.49,atraso=1.48,npl90=0.00,dur="26,7 meses",saldo=457.21),
}

import re as _re
def cdi_formula(tx):
    m=_re.match(r"CDI \+ ([\d,]+)%$", tx)
    if m: return "=$B$3+%s" % m.group(1).replace(",",".")
    m=_re.match(r"([\d,]+)% do CDI$", tx)
    if m: return "=$B$3*%s" % (float(m.group(1).replace(",","."))/100)
    return None

wb=Workbook(); wb.remove(wb.active)
CACHE={}

# ------------------------------------------------- aba Séries
ss=wb.create_sheet("Séries")
ss["A1"]="Séries por emissão — valores integralizados"
ss["A1"].font=Font(name=AR,size=13,bold=True,color=NAVY)
ss["A2"]="Valores em R$ milhões, em azul as entradas. Custo a.a. converte as séries pós-fixadas ao CDI da célula B3."
ss["A2"].font=Font(name=AR,size=9,italic=True,color="595959")
ss["A3"]="CDI de referência (% a.a.)"; ss["A3"].font=Font(name=AR,size=10,bold=True,color=NAVY)
ss["B3"]=CDI; ss["B3"].font=Font(name=AR,size=10,bold=True,color=BL); ss["B3"].number_format='0.00'
ss["B3"].fill=PatternFill("solid",fgColor="FFFF00")
hdr=["Emissão","Série","Camada","R$ mm","% do total","Remuneração","Custo a.a. (%)","Vencimento","ISIN","Colocação"]
for j,h in enumerate(hdr,start=1):
    c=ss.cell(row=5,column=j,value=h)
    c.font=Font(name=AR,size=10,bold=True,color=W); c.fill=PatternFill("solid",fgColor=NAVY)
    c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=BOX
ss.row_dimensions[5].height=24
BLOCK={}
r=6
for k in CRIS:
    r0=r
    tot=sum(s[1] for s in SER[k])
    for i,(nome,vl,tx,cst,venc,isin,priv) in enumerate(SER[k],start=1):
        ss.cell(row=r,column=1,value=k).font=Font(name=AR,size=9,bold=True,color=NAVY)
        ss.cell(row=r,column=2,value="%dª"%i).font=Font(name=AR,size=9)
        ss.cell(row=r,column=3,value=nome).font=Font(name=AR,size=9)
        c=ss.cell(row=r,column=4,value=vl); c.number_format='#,##0.000'; c.font=Font(name=AR,size=9,color=BL)
        f="=D%d/SUM($D$%d:$D$%d)"%(r,r0,r0+len(SER[k])-1)
        c=ss.cell(row=r,column=5,value=f); c.number_format='0.0%'; c.font=Font(name=AR,size=9)
        CACHE[("Séries","E%d"%r)]=vl/tot
        ss.cell(row=r,column=6,value=tx).font=Font(name=AR,size=9)
        gf=cdi_formula(tx)
        if gf:
            c=ss.cell(row=r,column=7,value=gf); CACHE[("Séries","G%d"%r)]=cst
        else:
            c=ss.cell(row=r,column=7,value=cst if cst is not None else "n.d.")
        c.number_format='0.00'
        c.font=Font(name=AR,size=9,color=BL if cst is not None else "808080")
        ss.cell(row=r,column=8,value=venc or "–").font=Font(name=AR,size=9)
        ss.cell(row=r,column=9,value=isin or "–").font=Font(name=AR,size=9)
        ss.cell(row=r,column=10,value="Privada" if priv else "Pública").font=Font(name=AR,size=9)
        for j in range(1,11):
            ss.cell(row=r,column=j).border=BOX
            if j in (4,5,7): ss.cell(row=r,column=j).alignment=Alignment(horizontal="right")
        pub = (not priv) and cst is not None
        c=ss.cell(row=r,column=11,value="=IF($J%d=\"Pública\",IFERROR($D%d*$G%d,0),0)"%(r,r,r))
        CACHE[("Séries","K%d"%r)]= vl*cst if pub else 0.0
        c.number_format='#,##0.00'; c.font=Font(name=AR,size=8,color="BFBFBF")
        c=ss.cell(row=r,column=12,value="=IF(AND($J%d=\"Pública\",ISNUMBER($G%d)),$D%d,0)"%(r,r,r))
        CACHE[("Séries","L%d"%r)]= vl if pub else 0.0
        c.number_format='#,##0.000'; c.font=Font(name=AR,size=8,color="BFBFBF")
        r+=1
    BLOCK[k]=(r0,r-1)
    r+=1
ss.cell(row=5,column=11,value="aux: R$ x custo").font=Font(name=AR,size=8,bold=True,color=W)
ss.cell(row=5,column=11).fill=PatternFill("solid",fgColor=NAVY)
ss.cell(row=5,column=12,value="aux: R$ público").font=Font(name=AR,size=8,bold=True,color=W)
ss.cell(row=5,column=12).fill=PatternFill("solid",fgColor=NAVY)
for j,wd in enumerate([10,6,24,11,11,20,13,13,15,11,14,14],start=1):
    ss.column_dimensions[get_column_letter(j)].width=wd
ss.sheet_view.showGridLines=False

# ------------------------------------------------- dados de 31/08/2026 (informe mensal de CRI, Fundos.NET)
# carteira = a vencer sem atraso + a vencer com atraso + vencidos nao pagos
IME={
#        carteira    PDD      arrasto  faixas   npl90    ativofin  saldo_series
"CRI I":  (277.7655, 43.6175, 22.2968, 22.2968, 16.3547, 13.9352, 226.28),
"CRI II": (389.8072, 46.9353, 23.7481, 23.7481, 15.3112, 17.2181, 352.73),
"CRI III":(545.0604, 26.0372, 11.4449, 11.4449,  5.0924, 24.0119, 536.60),
"CRI IV": (382.9950, 15.8003,  5.7914,  5.7914,  2.6360, 14.1357, 384.81),
"CRI V":  (443.6201,  0.0000, 42.4165,  1.5582,  0.0000, 16.6805, 457.91),
"CRI VI": (445.8813,  0.4938, 44.7006,  1.4806,  0.0000, 11.8817, 457.21),
}
# saldo acumulado da camada de topo em 31/08/2026 (R$ mm)
TOPO_SALDO={"CRI I":160.6046,"CRI II":221.3604,"CRI III":338.6900,"CRI IV":235.7000,
            "CRI V":310.0500,"CRI VI":388.4400}
# base de medicao do atraso no informe: faixas de aging
BASE_AGING={"CRI I":"Saldo de arrasto","CRI II":"Saldo de arrasto","CRI III":"Saldo de arrasto",
            "CRI IV":"Saldo de arrasto","CRI V":"Parcelas em atraso","CRI VI":"Parcelas em atraso"}
# razao de cobertura: minimo do TS e nivel em 31/08/2026 (em %)
COB={
"CRI I":  dict(mn=[None,None,None,None], at=[154.47,115.80,109.63,None], org="Calculado"),
"CRI II": dict(mn=[159.00,123.00,110.00,105.00], at=[162.75,126.43,112.44,107.67], org="Informe"),
"CRI III":dict(mn=[158.73,123.46,109.89,105.26], at=[159.72,124.22,110.54,105.04], org="Informe"),
"CRI IV": dict(mn=[158.73,123.46,109.89,105.26], at=[160.83,123.51,108.00,102.73], org="Informe"),
"CRI V":  dict(mn=[147.06,120.48,109.89,105.26], at=[148.46,119.99,108.74,103.85], org="Calculado"),
"CRI VI": dict(mn=[120.48,109.89,105.26,None],   at=[117.72,107.56,103.10,None],   org="Calculado"),
}
# preco de aquisicao: teto do FIDC cedente sobre o saldo contabil da CCB
CED={
"CRI I":  ("FIDC Solfácil II","n.d. no regulamento vigente"),
"CRI II": ("FIDC Solfácil II e IV","100,5% (FIDC II)"),
"CRI III":("FIDC Solfácil II, IV e VI","100,5% (II) / 101,0% (VI)"),
"CRI IV": ("FIDC Solfácil II, IV e VI, e Solfácil","100,5% (II) / 101,0% (VI)"),
"CRI V":  ("FIDC Solfácil VI e Solfácil","101,0% (FIDC VI)"),
"CRI VI": ("FIDC Solfácil VI e VII, e Solfácil","101,0% (VI) / 104,0% (VII)"),
}
MESES={"CRI I":31,"CRI II":26,"CRI III":15,"CRI IV":11,"CRI V":3,"CRI VI":1}

def carteira(k): return IME[k][0]
def pdd(k):      return IME[k][1]
def arrasto(k):  return IME[k][2]
def npl90(k):    return IME[k][4]
def ativofin(k): return IME[k][5]
def num_cob(k):  return carteira(k)-pdd(k)+ativofin(k)
def protecao(k): return num_cob(k)-TOPO_SALDO[k]

# ------------------------------------------------- aba CRIs
cs=wb.create_sheet("CRIs",0)
cs["A1"]="CRIs Solfácil — comparativo das seis emissões"
cs["A1"].font=Font(name=AR,size=14,bold=True,color=NAVY)
cs["A2"]=("Estrutura conforme termos de securitização e prospectos definitivos registrados na CVM. "
          "Carteira, PDD, atraso e razões de cobertura na data-base de 31/08/2026, do informe mensal de CRI entregue no Fundos.NET. "
          "A coluna Fonte indica, linha a linha, de onde vem o dado.")
cs["A2"].font=Font(name=AR,size=9,italic=True,color="595959")
cs.merge_cells("A2:H2")
NC=len(CRIS)+2          # coluna da Fonte
HR=4
cs.cell(row=HR,column=1,value="Indicador")
for j,k in enumerate(CRIS,start=2): cs.cell(row=HR,column=j,value=k)
cs.cell(row=HR,column=NC,value="Fonte")
for j in range(1,NC+1):
    c=cs.cell(row=HR,column=j)
    c.font=Font(name=AR,size=10,bold=True,color=W); c.fill=PatternFill("solid",fgColor=NAVY)
    c.alignment=Alignment(horizontal="center",vertical="center"); c.border=BOX
cs.row_dimensions[HR].height=22

def sec(r,t):
    cs.cell(row=r,column=1,value=t)
    for j in range(1,NC+1):
        c=cs.cell(row=r,column=j); c.fill=PatternFill("solid",fgColor=BLUE)
        c.font=Font(name=AR,size=9,bold=True,color=W); c.border=BOX
    cs.row_dimensions[r].height=16
def line(r,label,fn,fmt=None,bold=False,fonte="",h=18):
    cs.cell(row=r,column=1,value=label).font=Font(name=AR,size=9,bold=True,color=NAVY)
    cs.cell(row=r,column=1).border=BOX
    cs.cell(row=r,column=1).alignment=Alignment(vertical="center",wrap_text=True)
    for j,k in enumerate(CRIS,start=2):
        v=fn(k)
        c=cs.cell(row=r,column=j)
        if isinstance(v,tuple):
            c.value=v[0]; CACHE[("CRIs",c.coordinate)]=v[1]
        else:
            c.value=v if v is not None else "–"
        if fmt and not isinstance(v,str): c.number_format=fmt
        c.font=Font(name=AR,size=9,bold=bold)
        c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=BOX
    f=cs.cell(row=r,column=NC,value=fonte)
    f.font=Font(name=AR,size=8,color="404040"); f.border=BOX
    f.alignment=Alignment(vertical="center",wrap_text=True,horizontal="left")
    cs.row_dimensions[r].height=h

def blk(k): return BLOCK[k]
def rngD(k,a,b):
    r0,_=blk(k); return "'Séries'!D%d:D%d"%(r0+a,r0+b)
def tot(k): return sum(s[1] for s in SER[k])
def topo_val(k): return sum(s[1] for s in SER[k][:TOPO[k]])
def topo2_val(k): return sum(s[1] for s in SER[k][:TOPO2[k]])
def custo_pub(k):
    rows=[s for s in SER[k] if not s[6] and s[3] is not None]
    return sum(s[1]*s[3] for s in rows)/sum(s[1] for s in rows)

FP="Prospecto definitivo / termo de securitização (CVM)"
FI="Informe mensal de CRI 08/2026 (Fundos.NET)"

r=HR+1
sec(r,"IDENTIFICAÇÃO"); r+=1
for lab,key,fo in [("Securitizadora","emissora","Prospecto definitivo, capa"),
                   ("Nº da emissão","emissao","Prospecto definitivo, capa"),
                   ("Data de emissão","demi","Termo de securitização, preâmbulo"),
                   ("Registro CVM","reg","CVM/SRE, ato de registro da oferta"),
                   ("Encerramento da oferta","enc","Anúncio de encerramento (CVM/SRE)"),
                   ("Coordenador líder","coord","Prospecto definitivo, capa"),
                   ("Agente fiduciário","af","Prospecto definitivo, capa"),
                   ("Rating da camada de topo","rt","Relatório de rating da agência")]:
    line(r,lab,lambda k,key=key: INFO[k][key],fonte=fo); r+=1
line(r,"Volume total emitido (R$ mm)",
     lambda k: ("=SUM(%s)"%rngD(k,0,len(SER[k])-1), tot(k)), fmt='#,##0.0', bold=True,
     fonte="Soma da aba Séries; quadro de séries do TS"); r+=1
line(r,"Nº de séries", lambda k: INFO[k]["nser"], fmt='0', fonte="TS, quadro de séries"); r+=1

sec(r,"SUBORDINAÇÃO NA EMISSÃO"); r+=1
line(r,"Camada de topo", lambda k: "Super Sênior" if "Super" in SER[k][0][0] else "Sênior A e B",
     fonte="TS, classe de cada série"); r+=1
line(r,"Peso da camada de topo",
     lambda k: ("=SUM(%s)/SUM(%s)"%(rngD(k,0,TOPO[k]-1), rngD(k,0,len(SER[k])-1)), topo_val(k)/tot(k)),
     fmt='0.0%', fonte="Cálculo sobre a aba Séries"); r+=1
line(r,"Subordinação abaixo do topo",
     lambda k: ("=1-SUM(%s)/SUM(%s)"%(rngD(k,0,TOPO[k]-1), rngD(k,0,len(SER[k])-1)), 1-topo_val(k)/tot(k)),
     fmt='0.0%', bold=True, fonte="Cálculo sobre a aba Séries"); r+=1
line(r,"Subordinação abaixo da 2ª camada",
     lambda k: ("=1-SUM(%s)/SUM(%s)"%(rngD(k,0,TOPO2[k]-1), rngD(k,0,len(SER[k])-1)), 1-topo2_val(k)/tot(k)),
     fmt='0.0%', fonte="Cálculo sobre a aba Séries"); r+=1

sec(r,"RAZÃO DE COBERTURA — MÍNIMO DO COVENANT vs 31/08/2026"); r+=1
LAB=["camada de topo","2ª camada","3ª camada","4ª camada"]
for i,lb in enumerate(LAB):
    line(r,"Mínimo — %s"%lb, lambda k,i=i: COB[k]["mn"][i]/100 if COB[k]["mn"][i] else None,
         fmt='0.00%', fonte="TS, definição de Razão de Cobertura"); r+=1
    line(r,"Em 31/08/2026 — %s"%lb, lambda k,i=i: COB[k]["at"][i]/100 if COB[k]["at"][i] else None,
         fmt='0.00%', fonte="Informe 08/2026 (CRI II a IV) ou cálculo sobre o informe (CRI I, V, VI)"); r+=1
    line(r,"Folga — %s (p.p.)"%lb,
         lambda k,i=i: (COB[k]["at"][i]-COB[k]["mn"][i]) if (COB[k]["at"][i] and COB[k]["mn"][i]) else None,
         fmt='+0.00;-0.00', bold=True, fonte="Linha anterior menos o mínimo"); r+=1
line(r,"Origem do nível em 31/08/2026", lambda k: COB[k]["org"],
     fonte="Informe = campo IndiceSubordinacaoDataBase; Calculado = (carteira − PDD + ativo financeiro) ÷ saldo acumulado das séries", h=28); r+=1

sec(r,"RETORNO E EXCESSO DE SPREAD"); r+=1
line(r,"Taxa média mínima de retorno da carteira", lambda k: INFO[k]["txmin"]/100, fmt='0.00%',
     fonte='TS, definição "Taxa Média Mínima de Retorno" (critério de elegibilidade, verificado pro forma a cada cessão)', h=30); r+=1
def f_custo(k):
    r0,r1=BLOCK[k]
    return ("=SUM('Séries'!K%d:K%d)/SUM('Séries'!L%d:L%d)/100"%(r0,r1,r0,r1), custo_pub(k)/100)
def f_spread(k):
    r0,r1=BLOCK[k]
    return ("=%s/100-SUM('Séries'!K%d:K%d)/SUM('Séries'!L%d:L%d)/100"%(INFO[k]["txmin"],r0,r1,r0,r1),
            (INFO[k]["txmin"]-custo_pub(k))/100)
line(r,"Custo médio ponderado das séries públicas", f_custo, fmt='0.00%',
     fonte="Cálculo próprio: média das remunerações das séries públicas do TS ponderada pelo volume; pós-fixadas convertidas ao CDI da célula B3 da aba Séries (13,65% a.a.)", h=34); r+=1
line(r,"Excesso de spread bruto (p.p.)", f_spread, fmt='0.00%', bold=True,
     fonte="Cálculo próprio: as duas linhas acima. Piso estático: usa o mínimo de elegibilidade, não o retorno efetivo, e não desconta taxas, despesas nem perdas", h=34); r+=1

sec(r,"COMPRA DA CARTEIRA PELA SECURITIZADORA"); r+=1
line(r,"Cedente", lambda k: CED[k][0],
     fonte='TS, definição "Cedentes"', h=26); r+=1
line(r,"Preço de aquisição", lambda k: "Valor presente das parcelas vincendas descontadas pela Taxa de Retorno da própria CCB, no máximo",
     fonte='TS, definição "Preço de Aquisição"', h=30); r+=1
line(r,"Teto do FIDC cedente na compra da CCB (% do saldo contábil)", lambda k: CED[k][1],
     fonte="Regulamento do FIDC cedente, Critérios de Elegibilidade (FIDC II 100,5%; FIDC VI 101,0%; FIDC VII 104,0%)", h=34); r+=1
AGIO={"CRI I":"Regulamento do FIDC II não prevê essa destinação",
      "CRI II":"Regulamentos dos FIDC II e IV não preveem essa destinação",
      "CRI III":"FIDC VI: vai à cota júnior. FIDC II e IV não preveem",
      "CRI IV":"FIDC VI: vai à cota júnior. FIDC II e IV não preveem",
      "CRI V":"Vai integralmente à cota subordinada júnior, se subordinação e cobertura ficarem enquadradas pro forma",
      "CRI VI":"Vai integralmente à cota subordinada júnior, se subordinação e cobertura ficarem enquadradas pro forma"}
line(r,"Ágio apurado na venda pelo FIDC", lambda k: AGIO[k],
     fonte="Regulamentos FIDC VI e VII, ordem de alocação do Evento de Venda: ágio = valor que exceder o valor presente da carteira, nunca o valor de face", h=40); r+=1
line(r,"Preço de recompra (hipóteses de recompra)", lambda k: "Valor presente do direito creditório na data da recompra",
     fonte='TS, definição "Preço de Recompra"', h=26); r+=1

sec(r,"CRITÉRIOS DE ELEGIBILIDADE"); r+=1
line(r,"Prazo máximo do recebível", lambda k: "3.845 dias (≈126 meses)", fonte=FP); r+=1
line(r,"Prazo médio ponderado máximo", lambda k: "2.000 dias (≈66 meses)", fonte=FP); r+=1
line(r,"Carência máxima da CCB", lambda k: "185 dias", fonte=FP); r+=1
line(r,"Idade máxima do devedor PF", lambda k: "71 anos", fonte=FP); r+=1
line(r,"Requisito do devedor PJ", lambda k: "Constituído há ≥ 2 anos", fonte=FP); r+=1
line(r,"Teto por devedor PF (R$ mil)", lambda k: INFO[k]["tkpf"], fmt='#,##0', fonte=FP); r+=1
line(r,"Teto por devedor PJ (R$ mil)", lambda k: INFO[k]["tkpj"], fmt='#,##0', fonte=FP); r+=1
line(r,"Concentração máxima por devedor", lambda k: INFO[k]["conc"], fonte=FP, h=26); r+=1
line(r,"Revolvência", lambda k: "Não", fonte=FP); r+=1
line(r,"Regime fiduciário", lambda k: "Sim", fonte=FP); r+=1
line(r,"Lastro", lambda k: "CCB pré-fixada de financiamento de Sistema Solar", fonte=FP, h=26); r+=1

sec(r,"CARTEIRA E INADIMPLÊNCIA EM 31/08/2026"); r+=1
line(r,"Carteira de direitos creditórios (R$ mm)", lambda k: carteira(k), fmt='#,##0.0',
     fonte=FI+": a vencer sem atraso + a vencer com atraso + vencidos não pagos", h=26); r+=1
line(r,"Ativo financeiro (R$ mm)", lambda k: ativofin(k), fmt='#,##0.0',
     fonte=FI+": títulos públicos, compromissadas e cotas de FI de liquidez diária", h=26); r+=1
line(r,"Saldo das séries (R$ mm)", lambda k: IME[k][6], fmt='#,##0.0', fonte=FI+": saldo por série"); r+=1
line(r,"PDD (R$ mm)", lambda k: pdd(k), fmt='#,##0.00', fonte=FI+": provisão para redução ao valor recuperável"); r+=1
line(r,"PDD / carteira", lambda k: pdd(k)/carteira(k), fmt='0.0%', fonte="Cálculo sobre as duas linhas acima"); r+=1
line(r,"Saldo de arrasto (R$ mm)", lambda k: arrasto(k), fmt='#,##0.0',
     fonte=FI+": créditos a vencer com parcelas atrasadas, ou seja, saldo integral dos contratos com ao menos uma parcela em atraso", h=34); r+=1
line(r,"Saldo de arrasto / carteira", lambda k: arrasto(k)/carteira(k), fmt='0.0%', bold=True,
     fonte="Cálculo sobre as duas linhas acima. Única métrica de atraso comparável entre as seis emissões", h=26); r+=1
line(r,"Base das faixas de atraso no informe", lambda k: BASE_AGING[k],
     fonte="Verificado somando as faixas: na Kanastra a soma fecha com o saldo de arrasto; na Vert fecha com as parcelas vencidas apenas", h=34); r+=1
line(r,"Soma das faixas de atraso (R$ mm)", lambda k: IME[k][3], fmt='#,##0.0',
     fonte=FI+": faixas de 1 a 30 até acima de 361 dias", h=26); r+=1
line(r,"Atraso acima de 90 dias / carteira", lambda k: npl90(k)/carteira(k),
     fmt='0.0%', bold=True,
     fonte=FI+": faixas de 91 a 120, 121 a 150, 151 a 180, 181 a 360 e acima de 361 dias. Comparável só dentro da mesma securitizadora", h=40); r+=1
line(r,"Cobertura da PDD sobre o atraso acima de 90 dias (x)",
     lambda k: (pdd(k)/npl90(k)) if npl90(k) else "n.a.", fmt='0.00"x"',
     fonte="Cálculo: PDD ÷ atraso acima de 90 dias"); r+=1
line(r,"Duration reportada no informe", lambda k: INFO[k]["dur"], fonte=FI); r+=1
line(r,"Meses desde a emissão (em ago/26)", lambda k: MESES[k], fmt='0', fonte="Cálculo sobre a data de emissão"); r+=1

sec(r,"SUBORDINAÇÃO CONTRA INADIMPLÊNCIA EM 31/08/2026"); r+=1
line(r,"Proteção abaixo da camada de topo (R$ mm)", lambda k: protecao(k), fmt='#,##0.0',
     fonte="Cálculo: (carteira − PDD + ativo financeiro) menos o saldo acumulado das séries da camada de topo", h=34); r+=1
line(r,"Proteção abaixo do topo / carteira líquida de PDD", lambda k: protecao(k)/num_cob(k), fmt='0.0%', bold=True,
     fonte="Cálculo sobre a linha acima"); r+=1
line(r,"Proteção ÷ saldo de arrasto (x)", lambda k: protecao(k)/arrasto(k), fmt='0.0"x"', bold=True,
     fonte="Cálculo: proteção abaixo do topo ÷ saldo de arrasto. Quantas vezes o atraso teria de virar perda integral para atingir a camada de topo", h=40); r+=1
line(r,"Proteção ÷ atraso acima de 90 dias (x)",
     lambda k: (protecao(k)/npl90(k)) if npl90(k) else "n.a.", fmt='0.0"x"',
     fonte="Cálculo. n.a. nas emissões da Vert, que não reportam atraso acima de 90 dias nas faixas", h=34); r+=1
line(r,"Proteção ÷ PDD (x)", lambda k: (protecao(k)/pdd(k)) if pdd(k) else "n.a.", fmt='0.0"x"',
     fonte="Cálculo. n.a. no CRI V, cuja PDD vem zerada no informe"); r+=1

sec(r,"DISPONIBILIDADE DA INFORMAÇÃO"); r+=1
line(r,"Informe mensal de CRI", lambda k: "Mensal, público, no Fundos.NET",
     fonte="fnet.bmfbovespa.com.br, gerenciador de documentos de certificados, tipo de fundo CRI", h=26); r+=1
line(r,"Prazo de entrega", lambda k: "Até o 15º dia do mês seguinte à data-base",
     fonte="Resolução CVM 60, art. 42 — informe mensal da securitizadora", h=26); r+=1
line(r,"Relatório do agente fiduciário", lambda k: "Anual, até 30 de abril, no Fundos.NET e no site do AF",
     fonte="Resolução CVM 17, art. 15", h=26); r+=1
line(r,"O que o informe não traz", lambda k: "Safras, curvas de perda, taxa média efetiva da carteira e renegociações",
     fonte="Constatação: campos ausentes do informe mensal de CRI", h=30); r+=1

cs.column_dimensions["A"].width=36
for j in range(2,NC): cs.column_dimensions[get_column_letter(j)].width=17
cs.column_dimensions[get_column_letter(NC)].width=62
cs.freeze_panes="B5"; cs.sheet_view.showGridLines=False

foot=r+1
cs.cell(row=foot,column=1,value=(
 "Leitura das razões de cobertura: todas estão em percentual verdadeiro, 158,73% significa carteira líquida de PDD mais ativo financeiro igual a 1,5873 vez o saldo das séries daquela camada. "
 "O CRI I não traz nível numérico de razão de cobertura: o termo define a fórmula sem fixar patamar, e o informe reporta índice de subordinação (45,9% abaixo da 1ª série) em vez de razão de cobertura. "
 "CRI V e CRI VI: o campo IndiceSubordinacaoDataBase do informe da Vert vem preenchido com o peso de cada série na emissão, não com a razão de cobertura, então o nível foi calculado a partir dos saldos do próprio informe. "
 "A PDD zerada do CRI V é o que consta do informe de 08/2026 e aparenta ser campo não preenchido. "
 "Atraso acima de 90 dias nas emissões da Vert aparece zerado porque as faixas da Vert medem parcelas vencidas, não saldo de arrasto."))
cs.cell(row=foot,column=1).font=Font(name=AR,size=8,italic=True,color="595959")
cs.cell(row=foot,column=1).alignment=Alignment(wrap_text=True,vertical="top")
cs.merge_cells(start_row=foot,start_column=1,end_row=foot,end_column=NC)
cs.row_dimensions[foot].height=78

# ------------------------------------------------- aba Notas
ns=wb.create_sheet("Notas")
ns["A1"]="Notas, definições e fontes"; ns["A1"].font=Font(name=AR,size=13,bold=True,color=NAVY)
NOT=[
("Perímetro","Seis emissões de CRI com lastro declarado em CCB originadas na Plataforma Solfácil: Kanastra 1ª a 4ª (CNPJ 48.238.484/0001-38) e Vert 174ª e 177ª (CNPJ 25.005.683/0001-09). Identificadas na base de ofertas encerradas sob a Resolução CVM 160 e confirmadas no Fundos.NET."),
("Data-base dos dados atuais","31/08/2026. Vem do informe mensal de CRI de competência 08/2026 entregue por cada securitizadora no Fundos.NET, em XML. Consulta em 20/10/2026. Os seis arquivos são: Kanastra 1ª a 4ª emissão e Vert 174ª e 177ª séries da 1ª emissão. É o documento mais recente disponível: o informe de 09/2026 vence no 15º dia de outubro e ainda não estava publicado para todas."),
("Como chegar ao informe","fnet.bmfbovespa.com.br/fnet/publico/abrirGerenciadorDocumentosCertificadosCVM, tipo de fundo CRI, buscar pela securitizadora, categoria Informe Mensal. Público, sem cadastro."),
("Taxa média mínima de retorno","Definição expressa no termo de securitização, entre os critérios de elegibilidade: 21,5% a.a. no CRI I, 21% no CRI II, 22% no CRI III, 21% no CRI IV, 21% no CRI V e 21,5% no CRI VI. É um mínimo para a média da carteira, verificado pro forma a cada cessão, não um piso por crédito. Não é a taxa efetiva da carteira, que não é divulgada."),
("Custo médio ponderado das séries","Cálculo próprio. Toma a remuneração contratual de cada série pública no termo de securitização e pondera pelo volume integralizado. As séries pós-fixadas em CDI foram convertidas somando o spread ao CDI de 13,65% a.a. (Selic anualizada de setembro de 2026, série 4389 do SGS do Banco Central). A série de colocação privada, subscrita pela Solfácil, fica fora da conta. Trocar o CDI na célula B3 da aba Séries recalcula tudo."),
("Excesso de spread bruto","Cálculo próprio: taxa média mínima de retorno menos o custo médio ponderado das séries públicas. É um piso estático. Usa o mínimo de elegibilidade e não o retorno efetivo da carteira, e não desconta taxa de administração, taxa de gestão, despesas do patrimônio separado nem perda de crédito. O excesso disponível de fato é menor."),
("Razão de cobertura","Valor presente dos direitos creditórios líquido de PDD mais ativo financeiro, dividido pelo saldo devedor acumulado das séries até aquela camada. Apurada pela emissora e informada no campo IndiceSubordinacaoDataBase do informe mensal, com o mínimo no campo IndiceSubordinacaoMinimo."),
("Divergência de preenchimento","CRI II a IV: a Kanastra preenche o campo com a razão de cobertura e o nível confere com o cálculo a partir dos saldos do próprio informe, com diferença de até 0,2 p.p. CRI I: a Kanastra preenche com índice de subordinação (45,85% abaixo da 1ª série, 30,81% abaixo da 2ª). CRI V e VI: a Vert preenche com o peso de cada série na emissão, cujos valores somam 100%, o que não é razão de cobertura nem índice de subordinação; nesses dois a razão foi calculada."),
("Saldo de arrasto e parcelas em atraso","Saldo de arrasto é o saldo devedor integral de todo contrato com ao menos uma parcela em atraso. Parcelas em atraso são só as prestações vencidas e não pagas. O informe tem campos para os dois, mas o preenchimento divide-se por securitizadora: na Kanastra a soma das faixas de aging fecha exatamente com o saldo de arrasto, logo o aging dela é de arrasto; na Vert a soma das faixas fica muito abaixo do saldo de arrasto declarado (1,6 contra 42,4 R$ mm no CRI V; 1,5 contra 44,7 no CRI VI), logo o aging dela é de parcelas. Por isso a comparação de atraso acima de 90 dias entre Kanastra e Vert não é válida, e o saldo de arrasto sobre carteira é a única métrica de atraso comparável entre as seis."),
("Compra da carteira pela securitizadora","O preço de aquisição é definido no termo de securitização como o valor presente das parcelas vincendas descontadas pela Taxa de Retorno da própria CCB, e o termo diz que o preço deve corresponder a no máximo esse valor. Não há ágio contratual sobre o valor presente do crédito nessa ponta. O ágio ou deságio que os prospectos mencionam na integralização é sobre o preço do CRI, definido pelos coordenadores no ato da subscrição e aplicado igualmente a todos os CRI da série."),
("Compra da carteira pelo FIDC","Nessa ponta há ágio contratual sobre o valor contábil. O regulamento define Saldo Contábil da CCB como o valor presente das parcelas descontadas pela taxa de juros da própria CCB, e fixa teto para o preço de aquisição: 100,5% do saldo contábil no FIDC II, 101,0% no FIDC VI e 104,0% no FIDC VII. O FIDC IV, cujo regulamento é anterior à adaptação à Resolução CVM 175, define Preço de Compra sem teto percentual. Do outro lado, o preço fica limitado pela Taxa Mínima de Transferência, piso para a taxa de desconto usada na compra."),
("Ganho do FIDC na venda","Sim, o FIDC apura ganho no take-out e esse ganho é distribuído. Os regulamentos do FIDC VI e do FIDC VII, na ordem de alocação de recursos de um Evento de Venda, mandam pagar aos titulares de cotas subordinadas júnior o valor do ágio na venda dos direitos creditórios, desde que, considerando pro forma o pagamento, os índices de subordinação e as razões de cobertura fiquem enquadrados. O FIDC VII define ágio como exclusivamente o valor que exceder o valor presente da carteira de CCB detida pelo fundo, vedando o uso do valor original, nominal ou de face como base. No FIDC VII o pagamento é líquido da premiação por amortização antecipada e do MtM negativo dos derivativos não coberto pela reserva de MtM. Efeito de crédito: o ágio do take-out sai do fundo para a cota júnior, isto é, para a Solfácil, em vez de ficar retido como colchão, respeitados os covenants."),
("Proteção abaixo da camada de topo","Carteira líquida de PDD mais ativo financeiro, menos o saldo acumulado das séries da camada de topo. É o colchão em reais que teria de ser consumido antes de a camada de topo perder principal."),
("Lastro","Em todas as seis, o critério de elegibilidade exige CCB pré-fixada cujo recurso tenha destinação específica à aquisição de Sistema Solar em imóvel: placas fotovoltaicas, equipamentos e sistemas acessórios para geração, armazenamento e utilização de energia solar, instalados por Integradores Solares. Nenhuma das emissões admite outro tipo de bem financiado."),
("Cadeia de originação","A Solfácil Energia Solar Tecnologia e Serviços Financeiros (31.931.053/0001-50) opera a plataforma, faz a análise de crédito e é agente de cobrança. A CCB é emitida pelo devedor em favor de um endossante inicial — BMP Sociedade de Crédito Direto, depois Solfácil SCD e Solfácil SCFI (48.755.901/0001-10). O equipamento é fornecido e instalado pelo Integrador Solar, empresa terceira aprovada na plataforma, e não pela Solfácil. Há alienação fiduciária dos equipamentos descritos na CCB, sem registro prévio em cartório."),
("Fontes documentais","Prospectos definitivos e termos de securitização registrados na CVM (processos SRE/0104/2024, SRE/1471/2024, SRE/1111/2025, SRE/2711/2025, SRE/1197/2026 e SRE/2316/2026); regulamentos dos FIDC Solfácil II, IV, VI e VII no Fundos.NET; informes mensais de CRI de competência 08/2026 no Fundos.NET; base de ofertas públicas encerradas em dados.cvm.gov.br; série 4389 do SGS do Banco Central. Consulta em 20/10/2026."),
]
r=3
for t,d in NOT:
    ns.cell(row=r,column=1,value=t).font=Font(name=AR,size=10,bold=True,color=NAVY)
    ns.cell(row=r,column=1).alignment=Alignment(vertical="top",wrap_text=True)
    c=ns.cell(row=r,column=2,value=d); c.font=Font(name=AR,size=9)
    c.alignment=Alignment(vertical="top",wrap_text=True)
    ns.row_dimensions[r].height=max(28, 13*(len(d)//110+1))
    r+=1
ns.column_dimensions["A"].width=30; ns.column_dimensions["B"].width=135
ns.sheet_view.showGridLines=False

wb.save(OUT)
json.dump({"%s!%s"%k:v for k,v in CACHE.items()}, open("/tmp/claude-0/-home-user-fidc/27891f9c-8b60-5562-8194-4e25a29cb16e/scratchpad/cache_cri.json","w"))
print("gerado:",OUT,"| formulas com cache:",len(CACHE))
