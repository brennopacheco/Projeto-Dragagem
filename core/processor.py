"""core/processor.py — Calcula trechos de dragagem EN/VZ a partir dos extremos.

Para cada par de extremos consecutivos (E1 → E2):
- Determina status EN (enchente) ou VZ (vazante)
- Calcula inicio_real/fim_real (±1h dos extremos)
- Arredonda para grade de 30 min (com exceção de minutos iguais)
- Garante mínimo de 4h de dragagem
- Limita fim em 00:00
- Calcula amplitude formatada
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta


def _round_up_30(t: datetime) -> datetime:
    """Arredonda horário para CIMA na grade de 30 minutos.

    07:14 → 07:30
    07:30 → 07:30  (já está na grade)
    07:31 → 08:00
    23:51 → 00:00 (dia seguinte)
    """
    m = t.minute
    s = t.second
    if s == 0 and m % 30 == 0:
        return t  # já na grade
    # Próxima marca de 30 min
    next_mark = (m // 30 + 1) * 30
    delta = next_mark - m
    result = t.replace(second=0, microsecond=0) + timedelta(minutes=delta)
    return result


def _round_nearest_15(t: datetime) -> datetime:
    """Arredonda horário para o múltiplo de 15 minutos mais próximo.

    07:17 → 07:15
    07:08 → 07:15
    07:07 → 07:00
    07:53 → 07:45
    07:52 → 07:45
    07:38 → 07:45
    """
    m = t.minute
    # Marcas de 15 min: 0, 15, 30, 45, 60(=próxima hora)
    nearest = round(m / 15) * 15
    delta = nearest - m
    return t.replace(second=0, microsecond=0) + timedelta(minutes=delta)


def _format_amplitude(mare_e1: float, mare_e2: float) -> str:
    """Calcula amplitude e formata com 2 casas (segunda sempre zero).

    abs(mare_E2 - mare_E1), arredondado para 1 casa decimal (half-up),
    exibido com 2 casas forçando a segunda como zero.
    Ex: 4.94 → "4.90", 5.58 → "5.60", 4.55 → "4.60"
    """
    raw = abs(mare_e2 - mare_e1)
    # Arredondamento half-up para 1 casa decimal
    rounded = math.floor(raw * 10 + 0.5) / 10
    return f"{rounded:.1f}0"


def calcular_trechos(extremos: list[dict]) -> list[dict]:
    """Calcula trechos EN/VZ a partir da lista de extremos.

    Parâmetros:
        extremos: lista ordenada por data/hora, cada item:
            {"data": "DD/MM/YYYY", "hora": "HH:MM", "mare": float}

    Retorna lista de trechos:
        {
            "data", "status", "amplitude", "inicio", "fim",
            "inicio_real", "fim_real", "fim_dia_seguinte",
            "e1_data", "e1_hora", "e1_mare",
            "e2_data", "e2_hora", "e2_mare", "mes"
        }
    """
    if len(extremos) < 2:
        return []

    trechos: list[dict] = []

    for i in range(len(extremos) - 1):
        e1 = extremos[i]
        e2 = extremos[i + 1]

        # Converter para datetime
        dt1 = datetime.strptime(f"{e1['data']} {e1['hora']}", "%d/%m/%Y %H:%M")
        dt2 = datetime.strptime(f"{e2['data']} {e2['hora']}", "%d/%m/%Y %H:%M")

        # Status
        if e2["mare"] > e1["mare"]:
            status = "EN"
        else:
            status = "VZ"

        # Limites reais (sem arredondamento)
        inicio_real_dt = dt1 + timedelta(hours=1)
        fim_real_dt = dt2 - timedelta(hours=1)

        inicio_real_str = inicio_real_dt.strftime("%H:%M")
        fim_real_str = fim_real_dt.strftime("%H:%M")

        # Indicador de cruzamento de dia (antes do arredondamento)
        fim_dia_seguinte = "S" if fim_real_dt.date() > dt1.date() else "N"

        # Arredondamento para grade de 30 min
        min_inicio = inicio_real_dt.minute
        min_fim = fim_real_dt.minute

        if min_inicio == min_fim:
            # Exceção: mesmos minutos → arredondar ao múltiplo de 15 mais próximo
            inicio_arr = _round_nearest_15(inicio_real_dt)
            fim_arr = _round_nearest_15(fim_real_dt)
        else:
            inicio_arr = _round_up_30(inicio_real_dt)
            fim_arr = _round_up_30(fim_real_dt)

        # Regra das 4 horas mínimas
        diff = fim_arr - inicio_arr
        if diff < timedelta(hours=4):
            fim_arr = inicio_arr + timedelta(hours=4)

        # Limite máximo: 00:00 do dia seguinte ao dia de E1
        meia_noite = datetime.combine(dt1.date() + timedelta(days=1),
                                      datetime.min.time())
        if fim_arr > meia_noite:
            fim_arr = meia_noite

        # Formatar horários arredondados
        inicio_str = inicio_arr.strftime("%H:%M")
        fim_str = fim_arr.strftime("%H:%M")

        # Amplitude formatada
        amplitude = _format_amplitude(e1["mare"], e2["mare"])

        # Data do trecho = dia do E1
        data_trecho = dt1.strftime("%d/%m/%Y")
        mes = dt1.month

        trechos.append({
            "data": data_trecho,
            "status": status,
            "amplitude": amplitude,
            "inicio": inicio_str,
            "fim": fim_str,
            "inicio_real": inicio_real_str,
            "fim_real": fim_real_str,
            "fim_dia_seguinte": fim_dia_seguinte,
            "e1_data": e1["data"],
            "e1_hora": e1["hora"],
            "e1_mare": e1["mare"],
            "e2_data": e2["data"],
            "e2_hora": e2["hora"],
            "e2_mare": e2["mare"],
            "mes": mes,
        })

    return trechos


# ---------------------------------------------------------------------------
# Execução direta (teste)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from core.extractor import extract_extremos

    pdf = sys.argv[1] if len(sys.argv) > 1 else "13 - TERMINAL DA ALUMAR - 49 - 51.pdf"

    print("=== Extraindo extremos... ===")
    extremos = extract_extremos(pdf)
    print(f"Total extremos: {len(extremos)}")

    print("\n=== Calculando trechos... ===")
    trechos = calcular_trechos(extremos)
    print(f"Total trechos: {len(trechos)}")

    print("\nPrimeiros 10 trechos:")
    for t in trechos[:10]:
        print(f"  {t['data']} {t['status']} amp={t['amplitude']}  "
              f"{t['inicio']}-{t['fim']}  "
              f"(real {t['inicio_real']}-{t['fim_real']})  "
              f"dia+1={t['fim_dia_seguinte']}")

    print("\nÚltimos 5 trechos:")
    for t in trechos[-5:]:
        print(f"  {t['data']} {t['status']} amp={t['amplitude']}  "
              f"{t['inicio']}-{t['fim']}  "
              f"(real {t['inicio_real']}-{t['fim_real']})  "
              f"dia+1={t['fim_dia_seguinte']}")

    # Estatísticas
    en_count = sum(1 for t in trechos if t["status"] == "EN")
    vz_count = sum(1 for t in trechos if t["status"] == "VZ")
    ds_count = sum(1 for t in trechos if t["fim_dia_seguinte"] == "S")
    print(f"\nEN: {en_count} | VZ: {vz_count} | Fim dia seguinte: {ds_count}")
