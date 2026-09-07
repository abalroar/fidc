# -*- coding: utf-8 -*-
"""O LibreOffice não roda neste ambiente, então os valores em cache das fórmulas
são calculados aqui e gravados no arquivo salvo. As fórmulas são preservadas.

O openpyxl grava um <v/> vazio depois de cada <f>; este script SUBSTITUI esse
elemento. Acrescentar um segundo <v> gera um arquivo que o openpyxl lê e o
Excel recusa (CT_Cell admite no máximo um <v>).
"""
import re, shutil, zipfile
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

P = "outputs/solfacil/Solfacil_Securitizacoes_Comparativo.xlsx"

wb = load_workbook(P)
grid = {}
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, (int, float)):
                grid[(ws.title, c.column, c.row)] = float(c.value)

def val(sheet, ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return grid.get((sheet, column_index_from_string(m.group(1)), int(m.group(2))), 0.0)

def evaluate(sheet, f):
    f = f.lstrip("=")
    m = re.match(r"SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)$", f)
    if m:
        c1, r1, c2, r2 = m.groups()
        return sum(grid.get((sheet, ci, ri), 0.0)
                   for ci in range(column_index_from_string(c1), column_index_from_string(c2) + 1)
                   for ri in range(int(r1), int(r2) + 1))
    m = re.match(r"IF\(([A-Z]+\d+)=0,0,\(([A-Z]+\d+)\+([A-Z]+\d+)\)/([A-Z]+\d+)\)$", f)
    if m:
        d = val(sheet, m.group(4))
        return 0.0 if d == 0 else (val(sheet, m.group(2)) + val(sheet, m.group(3))) / d
    m = re.match(r"IF\(([A-Z]+\d+)=0,0,([A-Z]+\d+)/([A-Z]+\d+)\)$", f)
    if m:
        d = val(sheet, m.group(3))
        return 0.0 if d == 0 else val(sheet, m.group(2)) / d
    raise ValueError("padrão de fórmula não previsto: " + f)

cached = {}
for _ in range(2):                      # 1ª passada: totais; 2ª: percentuais
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    v = evaluate(ws.title, c.value)
                    cached[(ws.title, c.coordinate)] = v
                    grid[(ws.title, c.column, c.row)] = v
order = wb.sheetnames
del wb

CELL = r'(<c r="%s"[^>]*>)(<f>[^<]*</f>)(\s*<v\s*/>|\s*<v>[^<]*</v>)?'
tmp = P + ".tmp"
zin, zout = zipfile.ZipFile(P), zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
patched = 0
for item in zin.infolist():
    data = zin.read(item.filename)
    m = re.match(r"xl/worksheets/sheet(\d+)\.xml$", item.filename)
    if m:
        sheet = order[int(m.group(1)) - 1]
        txt = data.decode("utf-8")
        for (sh, coord), v in cached.items():
            if sh != sheet:
                continue
            txt, n = re.subn(CELL % coord,
                             lambda mm: mm.group(1) + mm.group(2) + "<v>%s</v>" % repr(round(v, 10)),
                             txt)
            patched += n
        data = txt.encode("utf-8")
    elif item.filename == "xl/workbook.xml":
        # força o Excel a recalcular ao abrir, para o cache nunca divergir
        txt = data.decode("utf-8")
        txt = re.sub(r"<calcPr[^>]*/>", "", txt)
        txt = txt.replace("</workbook>", '<calcPr calcId="0" fullCalcOnLoad="1"/></workbook>')
        data = txt.encode("utf-8")
    zout.writestr(item.filename, data, zipfile.ZIP_DEFLATED)
zin.close(); zout.close()
shutil.move(tmp, P)

assert patched == len(cached), "células com fórmula não corrigidas: %d de %d" % (patched, len(cached))
print("fórmulas:", len(cached), "| valores em cache gravados:", patched)
