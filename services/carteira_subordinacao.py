"""Carteira de subordinação — registro do analista, posição atual e gráfico.

Três responsabilidades, deliberadamente no mesmo módulo porque compartilham o
mesmo contrato de dados:

``load_registry`` / ``save_entry``
    O registro em disco onde o mínimo documental de cada FIDC é guardado.  É o
    **único** lugar onde essa informação entra: a Carteira 101 chega ali por
    semeadura (:func:`seed_registry`), e a inclusão manual de um CNPJ pelo
    analista grava exatamente no mesmo arquivo, com as mesmas colunas.  Não há
    caminho privilegiado para os 101.

``resolve_portfolio``
    Junta o registro ao Informe Mensal.  Para cada CNPJ vale **a competência
    mais recente em que aquele fundo reportou** — não a competência mais
    recente da base.  Quando julho chega para parte da carteira e junho é o que
    existe para o resto, cada fundo entra com o seu próprio dado mais novo, e a
    coluna ``competencia`` diz qual é.

``dumbbell_figure``
    O gráfico: um par de pontos por fundo, ligados por uma haste.  Onde o ponto
    do mínimo aparece **acima** do ponto da subordinação atual, o fundo está
    abaixo do que o próprio regulamento exige — a leitura é imediata, sem
    consultar legenda ou tabela.

Unidades: tudo em pontos percentuais.  O Informe Mensal reporta subordinação
como fração (0,2474) e a curadoria documental em pontos percentuais (4,5); a
conversão acontece uma única vez, aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import re

import numpy as np
import pandas as pd


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "industry_study"
REGISTRY_NAME = "carteira_subordinacao_registry.csv"
MONTHLY_NAME = "vehicle_monthly.csv.gz"
CURATION_NAME = "industry_carteira_1_document_curation.csv"
SCOPE_NAME = "industry_carteira_1_scope.csv"
CLASSIFICATION_NAME = "industry_anbima_classification.csv.gz"
TAXONOMY_NAME = "carteira_taxonomia_estrutural.csv"
NAO_CLASSIFICADO = "Não classificado"

REGISTRY_COLUMNS: tuple[str, ...] = (
    "cnpj",
    "apelido",
    "subordinacao_minima_pct",
    "subordinacao_estrutural_pct",
    "inclui_mezanino",
    "origem",
    "fonte",
    "observacao",
    "responsavel",
    "atualizado_em_utc",
)

ORIGEM_CARTEIRA_101 = "carteira_101"
ORIGEM_MANUAL = "manual"

#: Um fundo é considerado ativo quando reportou em alguma das últimas
#: competências da base.  A tolerância existe porque o Informe de um mês chega
#: escalonado: exigir a competência mais recente derrubaria do gráfico fundos
#: vivos que apenas ainda não entregaram.
ACTIVE_TOLERANCE_MONTHS = 3

# Paleta: cinza neutro para o que o fundo tem hoje, vermelho para o que o
# regulamento exige.  O vermelho carrega o alerta; o cinza é a referência.
COLOR_CURRENT = "#8D9399"
COLOR_MINIMUM = "#C8102E"
#: O maior dos dois valores.  Verde puro contra o vermelho é o pior par possível
#: para quem tem deuteranopia (ΔE 6,0); este verde-azulado sobe a separação para
#: ΔE 14,9, bem acima do piso, e continua lendo como verde.  A posição reforça:
#: o ponto verde é sempre o de cima.
COLOR_HIGHER = "#17A398"
COLOR_STEM = "#C9CCCF"
#: A haste de quem está abaixo do mínimo — é o que o olho tem de encontrar.
COLOR_GAP = "#C8102E"
COLOR_INK = "#12151A"
COLOR_MUTED = "#6B7178"
COLOR_GRID = "#E4E6E8"
SURFACE = "#FFFFFF"

#: Fração da altura da figura reservada aos nomes na vertical.
_FAIXA_NOMES = 0.36

SERIE_MAIOR = "O maior dos dois"
SERIE_ATUAL = "Subordinação atual"
SERIE_MINIMO = "Mínimo exigido"


class RegistryError(ValueError):
    """Entrada recusada pelo registro."""


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def normalize_cnpj(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 14:
        raise RegistryError(
            f"CNPJ inválido: {value!r}. Informe os 14 dígitos, com ou sem máscara."
        )
    return digits


def format_cnpj(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or "")).zfill(14)
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _empty_registry() -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in REGISTRY_COLUMNS})


def registry_path(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    return Path(data_dir) / REGISTRY_NAME


def load_registry(data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """O registro em disco, ou um registro vazio com o mesmo formato."""

    path = registry_path(data_dir)
    # O arquivo é criado vazio pelo ``touch`` que antecede a trava de escrita,
    # então "existe" e "tem conteúdo" não são a mesma coisa aqui.
    if not path.exists() or path.stat().st_size == 0:
        return _empty_registry()
    frame = pd.read_csv(path, dtype=str).fillna("")
    for column in REGISTRY_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["cnpj"] = frame["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    for column in ("subordinacao_minima_pct", "subordinacao_estrutural_pct"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["inclui_mezanino"] = frame["inclui_mezanino"].astype(str).str.lower().eq("true")
    return frame[list(REGISTRY_COLUMNS)].drop_duplicates("cnpj", keep="last")


def _check_pct(value: object, label: str) -> float | None:
    if value is None or value == "" or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        number = float(str(value).replace("%", "").replace(",", "."))
    except ValueError as exc:
        raise RegistryError(f"{label} não é um número: {value!r}") from exc
    if not 0 <= number <= 100:
        raise RegistryError(
            f"{label} deve estar entre 0 e 100 pontos percentuais; recebi {number:g}."
        )
    return round(number, 4)


def save_entry(
    *,
    cnpj: str,
    subordinacao_minima_pct: object = None,
    subordinacao_estrutural_pct: object = None,
    inclui_mezanino: bool = False,
    apelido: str = "",
    fonte: str = "",
    observacao: str = "",
    responsavel: str = "",
    origem: str = ORIGEM_MANUAL,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> pd.DataFrame:
    """Grava (ou substitui) a linha de um CNPJ e devolve o registro completo.

    A escrita é serializada por ``flock`` no próprio arquivo, do mesmo modo que
    o resto do repositório trata ledgers editados pela interface: dois
    analistas salvando ao mesmo tempo no mesmo servidor não se sobrescrevem.
    """

    digits = normalize_cnpj(cnpj)
    minima = _check_pct(subordinacao_minima_pct, "Subordinação mínima")
    estrutural = _check_pct(subordinacao_estrutural_pct, "Mínimo estrutural (Sub+Mez)")
    if minima is None and estrutural is None:
        raise RegistryError(
            "Informe ao menos um dos dois mínimos — o júnior isolado ou o "
            "estrutural (Sub+Mez). Sem mínimo não há o que comparar."
        )
    if minima is not None and estrutural is not None and estrutural < minima:
        raise RegistryError(
            f"O mínimo estrutural ({estrutural:g} p.p.) não pode ser menor que o "
            f"mínimo júnior ({minima:g} p.p.): o estrutural soma o mezanino ao júnior."
        )

    path = registry_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            current = load_registry(data_dir)
            current = current[current["cnpj"].ne(digits)]
            row = {
                "cnpj": digits,
                "apelido": str(apelido or "").strip(),
                "subordinacao_minima_pct": minima,
                "subordinacao_estrutural_pct": estrutural,
                "inclui_mezanino": bool(inclui_mezanino or estrutural is not None),
                "origem": str(origem or ORIGEM_MANUAL),
                "fonte": str(fonte or "").strip(),
                "observacao": str(observacao or "").strip(),
                "responsavel": str(responsavel or "").strip(),
                "atualizado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            updated = pd.concat([current, pd.DataFrame([row])], ignore_index=True)
            updated = updated.sort_values("cnpj").reset_index(drop=True)
            handle.seek(0)
            handle.truncate()
            updated.to_csv(handle, index=False)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return updated


def remove_entry(cnpj: str, data_dir: Path = DEFAULT_DATA_DIR) -> pd.DataFrame:
    """Retira um CNPJ do registro."""

    digits = normalize_cnpj(cnpj)
    path = registry_path(data_dir)
    if not path.exists():
        return _empty_registry()
    with path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            updated = load_registry(data_dir)
            updated = updated[updated["cnpj"].ne(digits)].reset_index(drop=True)
            handle.seek(0)
            handle.truncate()
            updated.to_csv(handle, index=False)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return updated


def seed_registry(
    data_dir: Path = DEFAULT_DATA_DIR, *, overwrite: bool = False
) -> pd.DataFrame:
    """Semeia o registro com os mínimos documentais da Carteira 101.

    Os valores são os mesmos da curadoria documental que alimentou a planilha
    entregue — regulamento, página e status vêm junto, no campo ``fonte``.  Uma
    linha já editada por um analista (``origem`` manual) é preservada, salvo
    ``overwrite``.
    """

    curation = pd.read_csv(Path(data_dir) / CURATION_NAME, dtype=str)
    scope = pd.read_csv(Path(data_dir) / SCOPE_NAME, dtype=str)
    names = scope.set_index("cnpj_fundo")["nome_foto"].to_dict()
    existing = load_registry(data_dir)
    manual = set(existing.loc[existing["origem"].eq(ORIGEM_MANUAL), "cnpj"])

    rows: list[dict[str, object]] = []
    for record in curation.itertuples():
        digits = re.sub(r"\D", "", str(record.cnpj_fundo)).zfill(14)
        if digits in manual and not overwrite:
            continue
        minima = pd.to_numeric(record.subordinacao_minima_junior_pct, errors="coerce")
        estrutural = pd.to_numeric(record.suporte_estrutural_minimo_pct, errors="coerce")
        if pd.isna(minima) and pd.isna(estrutural):
            # Sem mínimo documentado não há comparação; o fundo fica de fora do
            # registro em vez de entrar com um número inventado.
            continue
        fonte = " · ".join(
            part
            for part in (
                f"Regulamento {record.documento_id_regulamento}"
                if _filled(record.documento_id_regulamento)
                else "",
                f"p. {record.pagina_clausula}" if _filled(record.pagina_clausula) else "",
                str(record.documento_data_regulamento or "").strip(),
            )
            if part
        )
        rows.append(
            {
                "cnpj": digits,
                "apelido": str(names.get(record.cnpj_fundo, "") or "").strip(),
                "subordinacao_minima_pct": None if pd.isna(minima) else round(float(minima), 4),
                "subordinacao_estrutural_pct": (
                    None if pd.isna(estrutural) else round(float(estrutural), 4)
                ),
                "inclui_mezanino": bool(not pd.isna(estrutural)),
                "origem": ORIGEM_CARTEIRA_101,
                "fonte": fonte,
                "observacao": str(record.status_curadoria_documental or "").strip(),
                "responsavel": "curadoria_documental_carteira_101",
                "atualizado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )

    seeded = pd.DataFrame(rows, columns=list(REGISTRY_COLUMNS))
    keep = existing[~existing["cnpj"].isin(set(seeded["cnpj"]))] if len(existing) else existing
    merged = pd.concat([keep, seeded], ignore_index=True)
    merged = merged.drop_duplicates("cnpj", keep="last").sort_values("cnpj").reset_index(drop=True)
    path = registry_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False)
    return merged


def _filled(value: object) -> bool:
    return value is not None and str(value).strip() not in {"", "nan", "None"}


# ---------------------------------------------------------------------------
# Posição
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PortfolioPosition:
    """A carteira resolvida e o que descreve a resolução."""

    frame: pd.DataFrame
    competencia_base: str
    competencia_corte_ativo: str


def _latest_monthly(data_dir: Path) -> pd.DataFrame:
    monthly = pd.read_csv(
        Path(data_dir) / MONTHLY_NAME,
        dtype={"cnpj": str},
        usecols=[
            "competencia",
            "cnpj",
            "denominacao",
            "pl",
            "subordinacao_pct",
            "vl_cotas_total",
            "vl_cotas_subordinadas",
        ],
        low_memory=False,
    )
    monthly["competencia"] = monthly["competencia"].astype(str)
    monthly["cnpj"] = monthly["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    for column in ("pl", "subordinacao_pct", "vl_cotas_total", "vl_cotas_subordinadas"):
        monthly[column] = pd.to_numeric(monthly[column], errors="coerce")

    # Só uma competência em que o fundo de fato reportou patrimônio conta como
    # "o dado mais recente daquele fundo".
    reported = monthly[monthly["pl"].gt(0)].sort_values("competencia")
    # E o mês só serve para medir subordinação se o fundo tiver reportado o
    # valor das cotas.  Patrimônio positivo com total de cotas zerado não é um
    # fundo sem subordinação: é a quebra do quadro de cotas naquele mês, e ela
    # produziria 0% onde o mês anterior traz o número real.
    integro = reported[reported["vl_cotas_total"].gt(0)]
    escolhido = integro.groupby("cnpj", as_index=False).tail(1).copy()
    escolhido["quadro_de_cotas_integro"] = True

    # Um fundo cujo quadro de cotas nunca fechou continua entrando, com a
    # última competência que reportou patrimônio e a marca de que o quadro veio
    # incompleto — some do gráfico, não da tabela.
    faltantes = reported[~reported["cnpj"].isin(set(escolhido["cnpj"]))]
    if len(faltantes):
        resto = faltantes.groupby("cnpj", as_index=False).tail(1).copy()
        resto["quadro_de_cotas_integro"] = False
        escolhido = pd.concat([escolhido, resto], ignore_index=True)

    # Quantos meses seguidos, até a competência escolhida, o fundo reporta
    # cotas subordinadas zeradas.  Um 0% isolado é ruído; nove meses seguidos
    # descrevem um fundo de classe única, e a tabela precisa distinguir os dois.
    ultimo = escolhido.set_index("cnpj")["competencia"]
    zerado = reported[reported["cnpj"].isin(set(escolhido["cnpj"]))].copy()
    zerado = zerado[zerado["competencia"].le(zerado["cnpj"].map(ultimo))]
    zerado["zerada"] = zerado["vl_cotas_subordinadas"].fillna(0).le(0)
    meses = (
        zerado.sort_values("competencia")
        .groupby("cnpj")["zerada"]
        .apply(lambda flags: _trailing_true(list(flags)))
    )
    escolhido["meses_sem_subordinada"] = escolhido["cnpj"].map(meses).fillna(0).astype(int)
    return escolhido


def _trailing_true(flags: list[bool]) -> int:
    """Quantos ``True`` fecham a sequência."""

    total = 0
    for flag in reversed(flags):
        if not flag:
            break
        total += 1
    return total


def _shift_competence(competencia: str, months: int) -> str:
    year, month = (int(part) for part in competencia.split("-")[:2])
    total = year * 12 + (month - 1) - months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _structural_taxonomy(data_dir: Path) -> dict[str, str]:
    """O mapa CNPJ → categoria dos slides estruturais, se materializado.

    É a mesma classificação que dava nome aos slides 18–23 (Financeiro,
    Adquirência, Agro / Revenda, Risco Corporativo, Consignado INSS e FGTS,
    Factoring), extraída do payload publicado por
    ``scripts/build_carteira_taxonomia_estrutural.py``.
    """

    path = Path(data_dir) / TAXONOMY_NAME
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str)
    frame["cnpj"] = frame["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    return frame.set_index("cnpj")["categoria_estrutural"].to_dict()


def _classification(data_dir: Path) -> pd.DataFrame:
    registry = pd.read_csv(Path(data_dir) / CLASSIFICATION_NAME, dtype=str)
    by_fund = registry.drop_duplicates("cnpj_fundo").set_index("cnpj_fundo")
    by_class = registry.drop_duplicates("cnpj_classe").set_index("cnpj_classe")
    return by_fund, by_class


def resolve_portfolio(
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    somente_ativos: bool = True,
    tolerancia_meses: int = ACTIVE_TOLERANCE_MONTHS,
) -> PortfolioPosition:
    """O registro cruzado com o dado mais recente de cada fundo."""

    registry = load_registry(data_dir)
    latest = _latest_monthly(data_dir)
    competencia_base = str(latest["competencia"].max()) if len(latest) else ""
    corte = _shift_competence(competencia_base, tolerancia_meses) if competencia_base else ""
    by_fund, by_class = _classification(data_dir)

    merged = registry.merge(latest, on="cnpj", how="left")
    merged["fundo"] = (
        merged["denominacao"].fillna("").where(
            merged["denominacao"].notna() & merged["denominacao"].astype(str).str.strip().ne(""),
            merged["apelido"],
        )
    )
    merged.loc[merged["fundo"].astype(str).str.strip().eq(""), "fundo"] = merged["cnpj"].map(
        format_cnpj
    )
    merged["tipo_anbima"] = (
        merged["cnpj"].map(by_fund["tipo_anbima"])
        .fillna(merged["cnpj"].map(by_class["tipo_anbima"]))
        .fillna("Não classificado")
    )
    taxonomia = _structural_taxonomy(data_dir)
    merged["categoria_estrutural"] = (
        merged["cnpj"].map(taxonomia).replace("N/D", NAO_CLASSIFICADO)
        .fillna(NAO_CLASSIFICADO)
    )
    merged["foco_anbima"] = (
        merged["cnpj"].map(by_fund["foco_anbima"])
        .fillna(merged["cnpj"].map(by_class["foco_anbima"]))
        .fillna("")
    )
    merged["pl_mm"] = merged["pl"] / 1e6
    # O Informe traz fração; o registro, pontos percentuais.
    merged["sub_atual_pct"] = merged["subordinacao_pct"] * 100.0
    merged["referencia_pct"] = merged["subordinacao_estrutural_pct"].where(
        merged["subordinacao_estrutural_pct"].notna(),
        merged["subordinacao_minima_pct"],
    )
    merged["referencia_tipo"] = np.where(
        merged["subordinacao_estrutural_pct"].notna(),
        "Estrutural (Sub+Mez)",
        "Júnior",
    )
    merged.loc[merged["referencia_pct"].isna(), "referencia_tipo"] = "N/D"
    merged["folga_pp"] = merged["sub_atual_pct"] - merged["referencia_pct"]
    merged["abaixo_do_minimo"] = merged["folga_pp"].lt(0)
    merged["ativo"] = (
        merged["competencia"].notna() & merged["competencia"].astype(str).ge(corte)
        if corte
        else merged["competencia"].notna()
    )
    merged["quadro_de_cotas_integro"] = merged["quadro_de_cotas_integro"].fillna(False)
    merged["meses_sem_subordinada"] = merged["meses_sem_subordinada"].fillna(0).astype(int)
    merged["comparavel"] = (
        merged["sub_atual_pct"].notna()
        & merged["referencia_pct"].notna()
        & merged["quadro_de_cotas_integro"]
    )

    if somente_ativos:
        merged = merged[merged["ativo"]]
    ordered = merged.sort_values(
        ["comparavel", "sub_atual_pct"], ascending=[False, False]
    ).reset_index(drop=True)
    return PortfolioPosition(
        frame=ordered,
        competencia_base=competencia_base,
        competencia_corte_ativo=corte,
    )


# ---------------------------------------------------------------------------
# Gráfico
# ---------------------------------------------------------------------------

#: A frase registral que separa o nome próprio do fundo do resto.
_BOILERPLATE = re.compile(
    r"\bFUNDOS? DE INVESTIMENTOS? EM DIREITOS CREDIT[ÓO]RIOS?"
    r"(?:\s+N[ÃA]O[- ]PADRONIZADOS?)?\b|\bFIDC(?:\s+NP)?\b",
    flags=re.IGNORECASE,
)
#: O que vem depois do nome próprio e não o identifica: forma de condomínio,
#: responsabilidade, classe.  Corta-se no primeiro que aparecer.
_TRAILING = re.compile(
    r"\b(?:DE\s+)?(?:CLASSE\s+[ÚU]NICA|RESPONSABILIDADE\s+LIMITADA|"
    r"RESP\.?\s*(?:LTDA|LIMITADA)|FECHAD[AO]|ABERT[AO])\b.*$",
    flags=re.IGNORECASE,
)
#: Prefixo registral que às vezes antecede o nome próprio.
_LEADING = re.compile(r"^\s*(?:CLASSE\s+[ÚU]NICA\s+(?:DO|DA|DE)?)\s*", flags=re.IGNORECASE)
_MINUSCULAS = {"de", "do", "da", "dos", "das", "e", "em", "no", "na", "para", "com"}
_ROMANOS = re.compile(r"^[IVX]+$")
_VOGAIS = set("AEIOUÁÉÍÓÚÂÊÔÃÕÀ")


def _e_sigla(palavra: str) -> bool:
    """Sigla, e não palavra: sem vogal, com dígito, ou numeral romano.

    Sem esse teste, manter toda palavra curta em caixa alta transformaria BLUE,
    CASH e CLUB em siglas.  O preço é que MCPO e IBBA saem em caixa de título —
    continuam legíveis, que é o que o rótulo precisa ser.
    """

    if any(caractere.isdigit() for caractere in palavra):
        return True
    if _ROMANOS.fullmatch(palavra):
        return True
    return not (set(palavra) & _VOGAIS)


def _caixa(nome: str) -> str:
    """Caixa de título, preservando siglas e rebaixando conectivos."""

    partes = []
    for indice, palavra in enumerate(nome.split()):
        if palavra.isupper() and _e_sigla(palavra):
            partes.append(palavra)
        elif indice and palavra.lower() in _MINUSCULAS:
            partes.append(palavra.lower())
        else:
            partes.append(palavra.capitalize() if palavra.isupper() else palavra)
    return " ".join(partes)


def short_fund_name(name: str, *, limite: int = 28) -> str:
    """O nome próprio do fundo, sem a boilerplate registral.

    Corta **na** frase registral em vez de subtraí-la: retirar
    "fundo de investimento em direitos creditórios" do meio de
    "COBUCCIO … DE CLASSE ÚNICA FECHADA DE RESPONSABILIDADE LIMITADA" deixaria
    "Cobuccio de Fechada de Re…", que não é nome de nada.  O que interessa é o
    que vem antes; só quando não há nada antes é que se olha o que vem depois.
    """

    bruto = _LEADING.sub("", re.sub(r"\s+", " ", str(name or "")).strip())
    partes = _BOILERPLATE.split(bruto, maxsplit=1)
    nome = partes[0].strip(" -–·,")
    if len(nome) < 3 and len(partes) > 1:
        nome = _TRAILING.sub("", partes[1]).strip(" -–·,")
    if len(nome) < 3:
        nome = _TRAILING.sub("", bruto).strip(" -–·,") or bruto
    nome = _caixa(nome)
    return nome if len(nome) <= limite else nome[: limite - 1].rstrip() + "…"


def dumbbell_figure(
    frame: pd.DataFrame,
    *,
    titulo: str = "",
    subtitulo: str = "",
    rodape: str = "",
    fonte: str = "",
    destaques: int = 3,
    rotulos: list[str] | None = None,
    nomear_todos: bool = False,
    figsize: tuple[float, float] = (11.2, 6.6),
    dpi: int = 200,
):
    """Um par de pontos por fundo, ligados pela haste, ordenados do maior atual.

    Onde o ponto vermelho (mínimo) fica acima do cinza (atual), o fundo está
    abaixo do que o regulamento exige.  Esses fundos ganham rótulo direto,
    porque são o motivo de o gráfico existir.
    """

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    data = frame[frame["comparavel"].fillna(False)].copy() if "comparavel" in frame else frame.copy()
    data = data.sort_values("sub_atual_pct", ascending=False).reset_index(drop=True)

    figure, axes = plt.subplots(figsize=figsize, dpi=dpi)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)

    if data.empty:
        axes.text(
            0.5,
            0.5,
            "Nenhum fundo com subordinação atual e mínimo documentado.",
            ha="center",
            va="center",
            color=COLOR_MUTED,
            fontsize=12,
        )
        axes.set_axis_off()
        figure.tight_layout()
        return figure

    positions = np.arange(len(data))
    atual = data["sub_atual_pct"].to_numpy(dtype=float)
    minimo = data["referencia_pct"].to_numpy(dtype=float)

    # O verde marca o maior dos dois valores; o outro ponto mantém a cor da sua
    # série.  Quando o verde está no mínimo — e não na subordinação atual — o
    # fundo está abaixo do que o regulamento exige, e é ali que a haste fica
    # vermelha e grossa, para o olho cair no buraco antes de ler qualquer
    # rótulo.
    falta = minimo > atual
    axes.vlines(positions[~falta], atual[~falta], minimo[~falta],
                color=COLOR_STEM, linewidth=1.1, zorder=1)
    axes.vlines(positions[falta], atual[falta], minimo[falta],
                color=COLOR_GAP, linewidth=2.6, zorder=2)
    axes.scatter(positions[~falta], minimo[~falta], s=42, color=COLOR_MINIMUM,
                 zorder=3, edgecolors=SURFACE, linewidths=0.6)
    axes.scatter(positions[falta], atual[falta], s=42, color=COLOR_CURRENT,
                 zorder=3, edgecolors=SURFACE, linewidths=0.6)
    axes.scatter(positions, np.maximum(atual, minimo), s=62,
                 color=COLOR_HIGHER, zorder=4, edgecolors=SURFACE, linewidths=1.1)

    top = float(np.nanmax([atual.max(), minimo.max()]))
    axes.set_ylim(0, top * 1.08)
    axes.set_xlim(-1.2, len(data) - 0.2 + len(data) * 0.02)

    axes.yaxis.tick_right()
    axes.yaxis.set_label_position("right")
    axes.grid(axis="y", color=COLOR_GRID, linewidth=0.9, zorder=0)
    axes.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axes.spines[side].set_visible(False)
    axes.spines["bottom"].set_color(COLOR_INK)
    axes.spines["bottom"].set_linewidth(1.3)
    axes.tick_params(axis="y", length=0, labelsize=10, colors=COLOR_INK, pad=4)
    axes.tick_params(axis="x", length=0, labelbottom=False)

    # Rótulo direto onde a leitura importa: quem está abaixo do mínimo primeiro,
    # depois os maiores por PL, para dar escala ao eixo sem poluir.
    breaches = data.index[data["folga_pp"].lt(0)].tolist()
    by_size = (
        data.sort_values("pl_mm", ascending=False).index.tolist()
        if "pl_mm" in data
        else []
    )
    if nomear_todos:
        # Todo veículo nomeado, sem sobreposição: o nome desce para o eixo, na
        # vertical.  É o único arranjo em que vinte e tantos rótulos cabem —
        # anotar cada ponto no plano viraria uma mancha de texto.
        tamanho = 7.4 if len(data) <= 14 else (6.4 if len(data) <= 24 else 5.4)
        # O nome cabe até onde a faixa embaixo do eixo alcança; derivar o
        # truncamento da altura evita rótulo cortado quando a figura encolhe.
        disponivel = figsize[1] * _FAIXA_NOMES - 0.16
        limite = max(10, int(disponivel / (tamanho / 72.0 * 0.62)))
        axes.set_xticks(positions)
        axes.set_xticklabels(
            [short_fund_name(str(nome), limite=limite) for nome in data["fundo"]],
            rotation=90,
            fontsize=tamanho,
            color=COLOR_MUTED,
        )
        axes.tick_params(axis="x", length=0, labelbottom=True, pad=4)
        for indice, marca in enumerate(axes.get_xticklabels()):
            if falta[indice]:
                marca.set_color(COLOR_GAP)
                marca.set_fontweight("bold")
        labelled = []
    elif rotulos is not None:
        # Quando o slide traz a tabela ao lado, quem nomeia é ela; o gráfico
        # rotula apenas os CNPJs pedidos, para não virar parede de texto.
        escolhidos = set(rotulos)
        labelled = [i for i in data.index if data.at[i, "cnpj"] in escolhidos]
    else:
        # Rótulos vizinhos se sobrepõem e viram borrão; exigimos um afastamento
        # mínimo no eixo, o que também impede que a marcação atropele o texto.
        espacamento = max(3, len(data) // 12)
        labelled = []
        for index in breaches + by_size:
            if index in labelled:
                continue
            if any(abs(index - taken) < espacamento for taken in labelled):
                continue
            labelled.append(index)
            if len(labelled) >= max(destaques, len(breaches)):
                break
    limite_direita = len(data) * 0.72
    for index in labelled:
        altura = max(atual[index], minimo[index])
        # Perto da borda direita o rótulo cresce para fora da figura; ali ele
        # passa a sair do ponto para a esquerda.
        a_esquerda = index > limite_direita
        em_falta = bool(falta[index])
        axes.annotate(
            short_fund_name(str(data.at[index, "fundo"])),
            (index, altura),
            textcoords="offset points",
            xytext=(-6 if a_esquerda else 6, 10),
            fontsize=8.8,
            color=COLOR_GAP if em_falta else COLOR_INK,
            fontweight="bold" if em_falta else "normal",
            ha="right" if a_esquerda else "left",
            zorder=5,
        )

    tem_cabecalho = bool(titulo or subtitulo)
    figure.subplots_adjust(
        left=0.03,
        right=0.93,
        top=0.74 if tem_cabecalho else (0.88 if figsize[0] >= 9.5 else 0.84),
        # Nomes na vertical precisam de faixa embaixo; sem eles o gráfico
        # aproveita a lâmina inteira.
        bottom=0.16 if (rodape or fonte) else (_FAIXA_NOMES if nomear_todos else 0.06),
    )
    if tem_cabecalho:
        # Filete vermelho, título e subtítulo — a assinatura visual do formato.
        figure.add_artist(
            Line2D([0.03, 0.09], [0.955, 0.955], color=COLOR_MINIMUM, linewidth=3.6,
                   transform=figure.transFigure)
        )
        figure.text(0.03, 0.895, titulo, fontsize=16.5, fontweight="bold", color=COLOR_INK)
        if subtitulo:
            figure.text(0.03, 0.848, subtitulo, fontsize=11.5, color=COLOR_MUTED)
    figure.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", markersize=8.6,
                   color=COLOR_HIGHER, label="O maior dos dois"),
            Line2D([], [], marker="o", linestyle="none", markersize=7.5,
                   color=COLOR_CURRENT, label="Subordinação atual"),
            Line2D([], [], marker="o", linestyle="none", markersize=7.5,
                   color=COLOR_MINIMUM, label="Mínimo exigido"),
            Line2D([], [], linestyle="-", linewidth=2.6, color=COLOR_GAP,
                   label="Abaixo do mínimo"),
        ],
        loc="upper left",
        bbox_to_anchor=(0.028, 0.815 if tem_cabecalho else 0.995),
        frameon=False,
        # Quatro entradas só cabem em uma linha numa figura larga; abaixo disso
        # a última sai cortada pela borda.
        ncol=4 if figsize[0] >= 9.5 else 2,
        handletextpad=0.4,
        columnspacing=1.5,
        fontsize=10.5 if figsize[0] >= 9.5 else 8.8,
        labelcolor=COLOR_INK,
    )
    if rodape:
        figure.text(0.03, 0.075, rodape, fontsize=8.8, color=COLOR_MUTED, wrap=True)
    if fonte:
        figure.text(0.03, 0.022, fonte, fontsize=8.8, color=COLOR_MUTED)
    return figure


def chart_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """A carteira no formato longo que o gráfico consome.

    Uma linha por fundo com os dois valores e a ordem, mais duas linhas por
    fundo (atual e mínimo) para as camadas de pontos.  Sai daqui pronto tanto
    para o Altair quanto para qualquer outra saída.
    """

    data = frame[frame["comparavel"].fillna(False)] if "comparavel" in frame else frame
    data = data.sort_values("sub_atual_pct", ascending=False).reset_index(drop=True)
    data = data.assign(
        ordem=range(len(data)),
        rotulo=data["fundo"].map(short_fund_name),
        maior=data[["sub_atual_pct", "referencia_pct"]].max(axis=1),
        menor=data[["sub_atual_pct", "referencia_pct"]].min(axis=1),
        falta=data["referencia_pct"].gt(data["sub_atual_pct"]),
    )
    return data


def altair_dumbbell(frame: pd.DataFrame, *, height: int = 420):
    """O mesmo gráfico em Altair — a saída nativa e interativa do dashboard.

    O PNG do matplotlib existe para o PPTX, que precisa de imagem; na página o
    gráfico é vetorial, responsivo e com tooltip por fundo.
    """

    import altair as alt

    data = chart_frame(frame)
    if data.empty:
        return alt.Chart(pd.DataFrame({"x": [0], "y": [0]})).mark_text(
            text="Nenhum fundo com subordinação atual e mínimo documentado.",
            color=COLOR_MUTED,
            size=13,
        ).encode().properties(height=height)

    ordem = data["rotulo"].tolist()
    eixo_x = alt.X(
        "rotulo:N",
        sort=ordem,
        title=None,
        axis=alt.Axis(labels=False, ticks=False, domainColor=COLOR_INK, domainWidth=1.4),
    )
    dicas = [
        alt.Tooltip("fundo:N", title="FIDC"),
        alt.Tooltip("categoria_estrutural:N", title="categoria"),
        alt.Tooltip("competencia:N", title="competência"),
        alt.Tooltip("pl_mm:Q", title="PL R$ mm", format=",.1f"),
        alt.Tooltip("sub_atual_pct:Q", title="subordinação atual %", format=",.2f"),
        alt.Tooltip("referencia_pct:Q", title="mínimo exigido %", format=",.2f"),
        alt.Tooltip("referencia_tipo:N", title="base do mínimo"),
        alt.Tooltip("folga_pp:Q", title="folga p.p.", format=",.2f"),
    ]
    eixo_y = alt.Y(
        "menor:Q",
        title="% do patrimônio líquido",
        scale=alt.Scale(domainMin=0, nice=False),
        axis=alt.Axis(gridColor=COLOR_GRID, domain=False, ticks=False, orient="right"),
    )

    # A haste vermelha e grossa é a única marca que muda de espessura: ela sai
    # do fundo que não alcança o mínimo, e é onde o olho deve cair primeiro.
    hastes = (
        alt.Chart(data)
        .mark_rule(strokeWidth=1.2, color=COLOR_STEM)
        .encode(x=eixo_x, y=eixo_y, y2="maior:Q", tooltip=dicas)
        .transform_filter(alt.datum.falta == False)  # noqa: E712 — Vega precisa do literal
    )
    hastes_falta = (
        alt.Chart(data)
        .mark_rule(strokeWidth=3, color=COLOR_GAP)
        .encode(x=eixo_x, y=eixo_y, y2="maior:Q", tooltip=dicas)
        .transform_filter(alt.datum.falta == True)  # noqa: E712
    )
    # Os dois pontos entram na mesma camada, em formato longo, para que a
    # legenda saia sozinha e com uma entrada por série — em vez de três
    # camadas mudas e uma legenda escrita à mão em outro lugar.
    pontos = pd.concat(
        [
            data.assign(valor=data["maior"], serie=SERIE_MAIOR),
            data.assign(
                valor=data["menor"],
                serie=np.where(data["falta"], SERIE_ATUAL, SERIE_MINIMO),
            ),
        ],
        ignore_index=True,
    )
    marcas = (
        alt.Chart(pontos)
        .mark_point(filled=True, stroke=SURFACE, strokeWidth=1.2)
        .encode(
            x=eixo_x,
            y=alt.Y("valor:Q", title=None),
            color=alt.Color(
                "serie:N",
                scale=alt.Scale(
                    domain=[SERIE_MAIOR, SERIE_ATUAL, SERIE_MINIMO],
                    range=[COLOR_HIGHER, COLOR_CURRENT, COLOR_MINIMUM],
                ),
                legend=alt.Legend(title=None, orient="top", direction="horizontal"),
            ),
            size=alt.Size(
                "serie:N",
                scale=alt.Scale(
                    domain=[SERIE_MAIOR, SERIE_ATUAL, SERIE_MINIMO],
                    range=[130, 70, 70],
                ),
                legend=None,
            ),
            order=alt.Order("serie:N", sort="descending"),
            tooltip=dicas,
        )
    )
    rotulos = (
        alt.Chart(data[data["falta"]])
        .mark_text(dy=-14, fontSize=10, fontWeight="bold", color=COLOR_GAP, angle=0)
        .encode(x=eixo_x, y=alt.Y("maior:Q", title=None), text="rotulo:N", tooltip=dicas)
    )
    return (
        alt.layer(hastes, hastes_falta, marcas, rotulos)
        .resolve_scale(y="shared")
        .properties(height=height)
    )


def figure_png_bytes(figure, *, dpi: int = 200) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi, facecolor=SURFACE)
    return buffer.getvalue()


__all__ = [
    "ACTIVE_TOLERANCE_MONTHS",
    "ORIGEM_CARTEIRA_101",
    "ORIGEM_MANUAL",
    "REGISTRY_COLUMNS",
    "REGISTRY_NAME",
    "COLOR_CURRENT",
    "COLOR_GAP",
    "COLOR_HIGHER",
    "COLOR_MINIMUM",
    "NAO_CLASSIFICADO",
    "PortfolioPosition",
    "RegistryError",
    "altair_dumbbell",
    "chart_frame",
    "dumbbell_figure",
    "figure_png_bytes",
    "format_cnpj",
    "load_registry",
    "normalize_cnpj",
    "registry_path",
    "remove_entry",
    "resolve_portfolio",
    "save_entry",
    "seed_registry",
    "short_fund_name",
]
