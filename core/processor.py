"""core/processor.py — Calcula trechos de dragagem EN/VZ a partir dos extremos.

Para cada par de extremos consecutivos (E1 → E2):
- Determina status EN (enchente) ou VZ (vazante)
- Inicio = arredondar_nearest_15min(E1 + 1h)
- Fim    = inicio + 4h  (sempre exatamente 4 horas)
- Fim cortado em 00:00 quando inicio < meia-noite e fim > meia-noite
- Data do trecho = data do inicio arredondado
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta


def _round_nearest_15(t: datetime) -> datetime:
    """Arredonda horário para o múltiplo de 15 minutos mais próximo.

    Regra: resto = minutos % 15
      <= 7  → arredonda para baixo (slot anterior)
      >= 8  → arredonda para cima (próximo slot)

    Exemplos:
      09:42 → 09:45  (resto=12, cima)
      17:16 → 17:15  (resto=1, baixo)
      18:14 → 18:15  (resto=14, cima)
      12:06 → 12:00  (resto=6, baixo)
      23:55 → 00:00  (resto=10, cima → passa meia-noite)
    """
    m = t.minute
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

        # Status: EN (enchente) se maré sobe, VZ (vazante) se desce
        status = "EN" if e2["mare"] > e1["mare"] else "VZ"

        # Início: E1 + 1h, arredondado para nearest 15min
        inicio_arr = _round_nearest_15(dt1 + timedelta(hours=1))

        # Fim: sempre exatamente início + 4h
        fim_arr = inicio_arr + timedelta(hours=4)

        # Limite de meia-noite: se início é antes de 00:00 do dia seguinte ao E1
        # e fim ultrapassa, cortar fim em 00:00
        meia_noite = datetime.combine(dt1.date() + timedelta(days=1), datetime.min.time())
        if inicio_arr < meia_noite < fim_arr:
            fim_arr = meia_noite

        # Data do trecho = data do início arredondado (não necessariamente data de E1)
        data_trecho = inicio_arr.strftime("%d/%m/%Y")
        mes = inicio_arr.month

        # Indicador de fim no dia seguinte ao início (após corte)
        fim_dia_seguinte = "S" if fim_arr.date() > inicio_arr.date() else "N"

        # Horários reais (contexto, sem arredondamento)
        inicio_real_str = (dt1 + timedelta(hours=1)).strftime("%H:%M")
        fim_real_str = (inicio_arr + timedelta(hours=4)).strftime("%H:%M")  # fim sem corte

        # Amplitude formatada
        amplitude = _format_amplitude(e1["mare"], e2["mare"])

        trechos.append({
            "data": data_trecho,
            "status": status,
            "amplitude": amplitude,
            "inicio": inicio_arr.strftime("%H:%M"),
            "fim": fim_arr.strftime("%H:%M"),
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
              f"(real {t['inicio_real']})  "
              f"dia+1={t['fim_dia_seguinte']}")

    print("\nÚltimos 5 trechos:")
    for t in trechos[-5:]:
        print(f"  {t['data']} {t['status']} amp={t['amplitude']}  "
              f"{t['inicio']}-{t['fim']}  "
              f"(real {t['inicio_real']})  "
              f"dia+1={t['fim_dia_seguinte']}")

    # Estatísticas
    en_count = sum(1 for t in trechos if t["status"] == "EN")
    vz_count = sum(1 for t in trechos if t["status"] == "VZ")
    ds_count = sum(1 for t in trechos if t["fim_dia_seguinte"] == "S")
    print(f"\nEN: {en_count} | VZ: {vz_count} | Fim dia seguinte: {ds_count}")

    # Validar casos de teste
    print("\n=== Validando casos de teste ===")
    test_cases = [
        ("08:42", "09:45", "13:45"),
        ("16:16", "17:15", "21:15"),
        ("17:14", "18:15", "22:15"),
        ("11:06", "12:00", "16:00"),
        ("22:55", "00:00", "04:00"),
        ("21:59", "23:00", "00:00"),
        ("10:23", "11:30", "15:30"),
        ("04:12", "05:15", "09:15"),
    ]
    base = datetime(2026, 4, 13)
    for e1_hora, exp_inicio, exp_fim in test_cases:
        h, m = int(e1_hora[:2]), int(e1_hora[3:])
        dt1 = base.replace(hour=h, minute=m)
        inicio_arr = _round_nearest_15(dt1 + timedelta(hours=1))
        fim_arr = inicio_arr + timedelta(hours=4)
        meia_noite = datetime.combine(dt1.date() + timedelta(days=1), datetime.min.time())
        if inicio_arr < meia_noite < fim_arr:
            fim_arr = meia_noite
        got_inicio = inicio_arr.strftime("%H:%M")
        got_fim = fim_arr.strftime("%H:%M")
        ok = got_inicio == exp_inicio and got_fim == exp_fim
        status_str = "OK" if ok else f"FALHOU (esperado {exp_inicio}-{exp_fim})"
        print(f"  E1={e1_hora} → {got_inicio}-{got_fim}  {status_str}")
