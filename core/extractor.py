"""core/extractor.py — Extrai extremos de maré do PDF da tábua DHN/HIDROMARES.

Formato suportado: DHN/HIDROMARES, 3 páginas, 4 meses por página,
2 colunas de dias por mês (dias 1-16 à esquerda, 17-31 à direita).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

# ---------------------------------------------------------------------------
# Constantes de layout
# ---------------------------------------------------------------------------

# Página (0-based) → lista de números de mês na ordem das colunas
_PAGE_MONTHS: list[list[int]] = [
    [1, 2, 3, 4],    # página 0: Jan, Fev, Mar, Abr
    [5, 6, 7, 8],    # página 1: Mai, Jun, Jul, Ago
    [9, 10, 11, 12], # página 2: Set, Out, Nov, Dez
]

# Linhas de cabeçalho ocupam y < 107; dados começam a partir daqui
_DATA_Y_MIN = 107.0

# ---------------------------------------------------------------------------
# Padrões regex
# ---------------------------------------------------------------------------

_RE_DAY = re.compile(r"^\d{2}$")
_RE_HHMM = re.compile(r"^\d{4}$")
_RE_ALT = re.compile(r"^-?\d+\.\d+$")

# Token fundido "DIA_SEMANA + HHMM", ex: "DOM0712", "SÁB0649"
# SÁB pode aparecer com caracteres de substituição de encoding (S.{1,3}B)
_RE_DOW_HHMM = re.compile(
    r"^(?:SEG|TER|QUA|QUI|SEX|S.{1,3}B|DOM)(\d{4})$"
)

# Cabeçalho — tolerante a problemas de encoding (ex: Ã→replacement char)
_RE_H_LOC = re.compile(r"(.+?)\s*\(ESTADO DO (.+?)\)\s*-\s*(\d{4})")
_RE_H_LAT = re.compile(r"Latitude\s+([\d\W'.\s]+?[NS])(?:\s|$)")
_RE_H_LON = re.compile(r"Longitude\s+([\d\W'.\s]+?[WE])(?:\s|$)")
_RE_H_FUSO = re.compile(r"Fuso\s+(UTC\s*[\d.+-]+)")
_RE_H_NIVEL = re.compile(r"N.vel\s+M.dio\s+([\d.]+)\s*m")

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _detect_col_bounds(page_words: list[dict]) -> list[float]:
    """
    Detecta os limites das 8 sub-colunas a partir da linha de cabeçalho "HORA".

    A linha HORA fica em y ≈ 95-107 e contém 8 tokens "HORA".
    Os limites são os pontos médios entre colunas adjacentes,
    com 0 e 600 como extremos.
    """
    hora_xs = sorted(
        w["x0"] for w in page_words
        if w["text"] == "HORA" and 90 <= w["top"] <= _DATA_Y_MIN
    )
    if len(hora_xs) != 8:
        # Fallback: valores medidos na página 0 (Jan-Abr)
        hora_xs = [76.0, 139.8, 203.6, 267.4, 331.2, 394.9, 458.7, 522.5]

    bounds: list[float] = [0.0]
    for a, b in zip(hora_xs, hora_xs[1:]):
        bounds.append((a + b) / 2.0)
    bounds.append(hora_xs[-1] + 60.0)  # margem após a última coluna
    return bounds


def _subcol(x0: float, bounds: list[float]) -> int:
    """Mapeia coordenada x0 para índice de sub-coluna (0–7) dado os limites."""
    for i, bound in enumerate(bounds[1:], 1):
        if x0 < bound:
            return i - 1
    return 7


def _group_rows(words: list[dict], tol: float = 5.0) -> list[list[dict]]:
    """
    Agrupa palavras em linhas por proximidade de y.

    Palavras com |y_word - y_ref| ≤ tol são consideradas mesma linha.
    Retorna lista de grupos, cada grupo ordenado por x0.
    """
    if not words:
        return []
    words = sorted(words, key=lambda w: w["top"])
    groups: list[list[dict]] = []
    cur: list[dict] = [words[0]]
    ref_y: float = words[0]["top"]
    for w in words[1:]:
        if w["top"] - ref_y <= tol:
            cur.append(w)
        else:
            groups.append(sorted(cur, key=lambda w: w["x0"]))
            cur = [w]
            ref_y = w["top"]
    groups.append(sorted(cur, key=lambda w: w["x0"]))
    return groups


def _parse_subcol(words: list[dict], year: int, month: int) -> list[dict]:
    """
    Parseia uma sub-coluna de palavras extraindo extremos de maré.

    Cada dia começa quando aparece um token de 2 dígitos (01-31).
    O token pode estar na mesma linha que o primeiro extremo.
    Tokens fundidos DIA_SEMANA+HHMM (ex: DOM0712) são decompostos.

    Retorna lista de {"data": "DD/MM/YYYY", "hora": "HH:MM", "mare": float}.
    """
    results: list[dict] = []
    rows = _group_rows(words)

    cur_day: int | None = None
    cur_extremes: list[tuple[str, float]] = []  # (HHMM, altitude)

    def _flush() -> None:
        """Salva extremos do dia corrente nos resultados."""
        if cur_day is None or not cur_extremes:
            return
        try:
            d = date(year, month, cur_day)
        except ValueError:
            return  # dia inválido para o mês (ex: 31 de fevereiro)
        date_str = d.strftime("%d/%m/%Y")
        for hhmm, alt in cur_extremes:
            results.append({
                "data": date_str,
                "hora": f"{hhmm[:2]}:{hhmm[2:]}",
                "mare": alt,
            })

    for row in rows:
        day_val: int | None = None
        hhmm_val: str | None = None
        alt_val: float | None = None

        for w in row:
            t = w["text"]

            # Token fundido DIA_SEMANA+HHMM (ex: "DOM0712")
            m = _RE_DOW_HHMM.match(t)
            if m:
                hhmm_val = m.group(1)
                continue

            # Número do dia (2 dígitos, 01-31)
            if _RE_DAY.match(t):
                n = int(t)
                if 1 <= n <= 31:
                    day_val = n
                continue

            # Hora no formato HHMM
            if _RE_HHMM.match(t):
                h, mn = int(t[:2]), int(t[2:])
                if h <= 23 and mn <= 59:
                    hhmm_val = t
                continue

            # Altitude (ex: "5.59", "-0.12")
            if _RE_ALT.match(t):
                alt_val = float(t)

        # Novo dia: salvar anterior e reiniciar
        if day_val is not None and day_val != cur_day:
            _flush()
            cur_day = day_val
            cur_extremes = []

        # Registrar extremo se par (hora, altitude) encontrado na linha
        if hhmm_val is not None and alt_val is not None and cur_day is not None:
            cur_extremes.append((hhmm_val, alt_val))

    _flush()
    return results


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def extract_metadata(pdf_path: str | Path) -> dict:
    """
    Extrai metadados do cabeçalho da tábua de marés.

    Retorna dict com:
        local, estado, ano, latitude, longitude, fuso, nivel_medio
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        text = pdf.pages[0].extract_text() or ""

    meta: dict = {}

    m = _RE_H_LOC.search(text)
    if m:
        meta["local"] = m.group(1).strip()
        meta["estado"] = m.group(2).strip()
        meta["ano"] = int(m.group(3))

    m = _RE_H_LAT.search(text)
    if m:
        meta["latitude"] = m.group(1).strip()

    m = _RE_H_LON.search(text)
    if m:
        meta["longitude"] = m.group(1).strip()

    m = _RE_H_FUSO.search(text)
    if m:
        meta["fuso"] = m.group(1).strip()

    m = _RE_H_NIVEL.search(text)
    if m:
        meta["nivel_medio"] = float(m.group(1))

    return meta


def extract_extremos(pdf_path: str | Path) -> list[dict]:
    """
    Extrai todos os extremos de maré do PDF da tábua DHN/HIDROMARES.

    Retorna lista ordenada por data/hora:
        [{"data": "DD/MM/YYYY", "hora": "HH:MM", "mare": float}, ...]
    """
    meta = extract_metadata(pdf_path)
    year: int = meta.get("ano", datetime.today().year)

    results: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            if page_idx >= len(_PAGE_MONTHS):
                break
            months = _PAGE_MONTHS[page_idx]  # ex: [1, 2, 3, 4]

            # Extrair todas as palavras da página
            all_words = page.extract_words()

            # Detectar limites de coluna a partir do cabeçalho HORA
            col_bounds = _detect_col_bounds(all_words)

            # Palavras abaixo do cabeçalho
            data_words = [w for w in all_words if w["top"] >= _DATA_Y_MIN]

            # Distribuir nas 8 sub-colunas pelo x0
            subcols: list[list[dict]] = [[] for _ in range(8)]
            for w in data_words:
                subcols[_subcol(w["x0"], col_bounds)].append(w)

            # Parsear cada sub-coluna
            for sc_idx, sc_words in enumerate(subcols):
                month_pos = sc_idx // 2   # 0-3: qual dos 4 meses
                month_num = months[month_pos]
                extremes = _parse_subcol(sc_words, year, month_num)
                results.extend(extremes)

    # Ordenar por data/hora
    results.sort(
        key=lambda e: datetime.strptime(e["data"] + " " + e["hora"], "%d/%m/%Y %H:%M")
    )
    return results


def validate_extremos(extremos: list[dict]) -> list[str]:
    """
    Valida a lista de extremos extraídos.

    Retorna lista de avisos (lista vazia = OK).
    """
    if not extremos:
        return ["Nenhum extremo extraído."]

    warnings: list[str] = []
    total = len(extremos)

    if not (1400 <= total <= 1500):
        warnings.append(
            f"Total de extremos fora do esperado: {total} (esperado 1400-1500)"
        )

    # Agrupar por (ano, mês, dia)
    from collections import defaultdict

    by_month_day: dict[tuple, list] = defaultdict(list)
    for e in extremos:
        d = e["data"]
        key = (int(d[6:10]), int(d[3:5]), int(d[:2]))
        by_month_day[key].append(e)

    # Verificar número de dias por mês
    months_seen: dict[tuple, set] = defaultdict(set)
    for (yr, mon, day) in by_month_day:
        months_seen[(yr, mon)].add(day)

    for (yr, mon), days in months_seen.items():
        n = len(days)
        if not (28 <= n <= 31):
            warnings.append(f"{yr}-{mon:02d}: {n} dias (esperado 28-31)")

    # Verificar extremos por dia e limites de altura
    for (yr, mon, day), exts in by_month_day.items():
        n = len(exts)
        label = f"{yr}-{mon:02d}-{day:02d}"
        if not (3 <= n <= 4):
            warnings.append(f"{label}: {n} extremos (esperado 3 ou 4)")
        for e in exts:
            if not (-1.0 <= e["mare"] <= 8.0):
                warnings.append(
                    f"Altura inválida: {e['data']} {e['hora']} → {e['mare']} m"
                )

    return warnings


# ---------------------------------------------------------------------------
# Execução direta (teste)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    pdf = sys.argv[1] if len(sys.argv) > 1 else "13 - TERMINAL DA ALUMAR - 49 - 51.pdf"

    print("=== Metadados ===")
    meta = extract_metadata(pdf)
    for k, v in meta.items():
        print(f"  {k}: {v}")

    print("\n=== Extraindo extremos... ===")
    extremos = extract_extremos(pdf)
    print(f"Total: {len(extremos)} extremos")

    print("\nPrimeiros 10:")
    for e in extremos[:10]:
        print(f"  {e}")

    print("\nÚltimos 5:")
    for e in extremos[-5:]:
        print(f"  {e}")

    print("\n=== Validação ===")
    warns = validate_extremos(extremos)
    if warns:
        for w in warns:
            print(f"  AVISO: {w}")
    else:
        print("  OK — sem avisos")
