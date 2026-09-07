# -*- coding: utf-8 -*-
import csv, io, os, glob, json, re
BASE = "data/ime_solfacil"
CN = {'36771685000117':'I','42462306000100':'II','49920525000134':'III','44909456000144':'IV',
      '47240785000133':'V','57028406000108':'VI','63505455000189':'VII'}
def norm(s): return re.sub(r'\D','',s or '')

def find(tab, ym):
    for d in (os.path.join(BASE, ym), os.path.join(BASE,'hist2024'), os.path.join(BASE,'hist2023'), os.path.join(BASE,'hist2022'), os.path.join(BASE,'hist2021')):
        p = os.path.join(d, f"inf_mensal_fidc_tab_{tab}_{ym}.csv")
        if os.path.exists(p): return p
    return None

def load(tab, ym):
    p = find(tab, ym)
    if not p: return []
    out = []
    for x in csv.DictReader(io.open(p, encoding='latin1'), delimiter=';'):
        k = norm(x.get('CNPJ_FUNDO_CLASSE'))
        if k in CN:
            x['_f'] = CN[k]; out.append(x)
    return out

def cls(label):
    s = (label or '').lower()
    if 'mezanino' in s: return 'MEZ'
    if 'senior' in s or 'sênior' in s: return 'SR'
    if 'subordinada' in s or 'subordinado' in s or 'junior' in s or 'júnior' in s: return 'JR'
    return 'OUT'

def f(v):
    try: return float((v or '0').replace(',', '.'))
    except Exception: return 0.0

months = []
for y in (2021, 2022, 2023, 2024, 2025, 2026):
    for m in range(1, 13):
        ym = f"{y}{m:02d}"
        if find('I', ym): months.append(ym)
months.sort()

rows = []
for ym in months:
    tabI = {x['_f']: x for x in load('I', ym)}
    tabIV = {x['_f']: x for x in load('IV', ym)}
    bal, amo, cap = {}, {}, {}
    for x in load('X_2', ym):
        c = cls(x['TAB_X_CLASSE_SERIE'])
        bal.setdefault(x['_f'], {}).setdefault(c, 0.0)
        bal[x['_f']][c] += f(x['TAB_X_QT_COTA']) * f(x['TAB_X_VL_COTA'])
    for x in load('X_4', ym):
        c = cls(x['TAB_X_CLASSE_SERIE']); v = f(x['TAB_X_VL_TOTAL'])
        t = x['TAB_X_TP_OPER']
        if t == 'Amortizações':
            amo.setdefault(x['_f'], {}).setdefault(c, 0.0); amo[x['_f']][c] += v
        elif t == 'Captações no Mês':
            cap.setdefault(x['_f'], {}).setdefault(c, 0.0); cap[x['_f']][c] += v
    for fd in CN.values():
        i = tabI.get(fd); iv = tabIV.get(fd)
        if not i and fd not in bal: continue
        g = lambda k: f(i.get(k)) if i else 0.0
        rows.append(dict(
            mes=ym, fundo=fd,
            pl=f(iv.get('TAB_IV_A_VL_PL')) if iv else 0.0,
            ativo=g('TAB_I_VL_ATIVO'),
            dc_risco=g('TAB_I2A_VL_DIRCRED_RISCO'),
            venc_ad=g('TAB_I2A1_VL_CRED_VENC_AD'),
            venc_inad=g('TAB_I2A2_VL_CRED_VENC_INAD'),
            parc_inad=g('TAB_I2A21_VL_TOTAL_PARCELA_INAD'),
            inad=g('TAB_I2A3_VL_CRED_INAD'),
            pdd=g('TAB_I2A11_VL_REDUCAO_RECUP'),
            b_sr=bal.get(fd, {}).get('SR', 0.0), b_mez=bal.get(fd, {}).get('MEZ', 0.0), b_jr=bal.get(fd, {}).get('JR', 0.0),
            a_sr=amo.get(fd, {}).get('SR', 0.0), a_mez=amo.get(fd, {}).get('MEZ', 0.0), a_jr=amo.get(fd, {}).get('JR', 0.0),
            c_sr=cap.get(fd, {}).get('SR', 0.0), c_mez=cap.get(fd, {}).get('MEZ', 0.0), c_jr=cap.get(fd, {}).get('JR', 0.0),
        ))
with open('serie_solfacil.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("meses:", months[0], "->", months[-1], "| linhas:", len(rows))
