"""
pro_analysis.py — Análisis de nivel profesional
=================================================
Lo que un analista de equity research / hedge fund espera ver:

  - ROIC vs WACC (¿crea o destruye valor?)
  - Reverse DCF (¿qué crecimiento implica el precio actual?)
  - DCF con 3 escenarios (bear / base / bull) + matriz de sensibilidad
  - Piotroski F-Score (9 puntos, calidad fundamental)
  - Altman Z-Score (riesgo de quiebra)
  - Tendencia de márgenes y dilución de acciones
  - Validación de datos y banderas rojas

Todo opera sobre el dict de EDGAR (series anuales) + datos de yfinance.
Uso educativo, no es consejo de inversión.
"""

import math


def _last(series):
    return series[-1][1] if series else None


def _prev(series):
    return series[-2][1] if series and len(series) >= 2 else None


# ============================================================
#  ROIC vs WACC — el corazón de la creación de valor
# ============================================================
def compute_roic(edgar, tax_rate=0.21):
    """ROIC = NOPAT / capital invertido. NOPAT = EBIT * (1 - tasa)."""
    if not edgar:
        return None
    ebit = _last(edgar.get("operating_income", []))
    equity = _last(edgar.get("equity", []))
    debt = _last(edgar.get("long_term_debt", []))
    cash = _last(edgar.get("cash", []))
    if ebit is None or equity is None:
        return None
    invested = equity + (debt or 0) - (cash or 0)
    if invested <= 0:
        return None
    nopat = ebit * (1 - tax_rate)
    return nopat / invested


def estimate_wacc(m, risk_free=0.04, market_premium=0.05, default_beta=1.1):
    """
    WACC simplificado. Sin beta fiable gratis, usamos beta por defecto.
    Coste de deuda estimado vía gasto por intereses / deuda.
    """
    beta = m.get("beta") or default_beta
    cost_equity = risk_free + beta * market_premium
    equity = m.get("equity_val") or m.get("market_cap")
    debt = m.get("debt") or 0
    if not equity:
        return cost_equity
    total = equity + debt
    w_e = equity / total
    w_d = debt / total
    cost_debt_after_tax = 0.05 * (1 - 0.21)  # estimación conservadora
    return w_e * cost_equity + w_d * cost_debt_after_tax


def value_creation(roic, wacc):
    """Spread ROIC - WACC. >0 crea valor."""
    if roic is None or wacc is None:
        return None, None
    spread = roic - wacc
    if spread > 0.05:   return spread, "Crea valor con holgura"
    if spread > 0:      return spread, "Crea valor (margen estrecho)"
    if spread > -0.03:  return spread, "Apenas cubre el coste de capital"
    return spread, "Destruye valor"


# ============================================================
#  REVERSE DCF — qué crecimiento implica el precio actual
# ============================================================
def reverse_dcf(price, shares, fcf, cash, debt, discount_rate=0.09,
                terminal_growth=0.025, years=10):
    """
    Despeja el crecimiento implícito: ¿qué CAGR de FCF justifica el precio?
    Búsqueda binaria sobre el crecimiento.
    """
    if not all([price, shares, fcf]) or fcf <= 0:
        return None
    target_equity = price * shares

    def implied_equity(g):
        cur, pv = fcf, 0.0
        for yr in range(1, years + 1):
            cur *= (1 + g)
            pv += cur / (1 + discount_rate) ** yr
        tv = cur * (1 + terminal_growth) / (discount_rate - terminal_growth)
        pv += tv / (1 + discount_rate) ** years
        return pv + (cash or 0) - (debt or 0)

    lo, hi = -0.10, 0.60
    for _ in range(60):
        mid = (lo + hi) / 2
        if implied_equity(mid) < target_equity:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ============================================================
#  DCF con escenarios + matriz de sensibilidad
# ============================================================
def dcf_scenarios(fcf, shares, cash, debt, base, years=10):
    """Tres escenarios: bear (-40% crecimiento), base, bull (+40%)."""
    if not fcf or not shares or fcf <= 0:
        return None

    def single(g1, g2, term, disc):
        cur, pv = fcf, 0.0
        for yr in range(1, years + 1):
            g = g1 if yr <= 5 else g2
            cur *= (1 + g)
            pv += cur / (1 + disc) ** yr
        tv = cur * (1 + term) / (disc - term)
        pv += tv / (1 + disc) ** years
        return (pv + (cash or 0) - (debt or 0)) / shares

    g1, g2 = base["growth_1_5"], base["growth_6_10"]
    term, disc = base["terminal_growth"], base["discount_rate"]
    return {
        "bear": single(g1 * 0.6, g2 * 0.6, term, disc + 0.01),
        "base": single(g1, g2, term, disc),
        "bull": single(g1 * 1.4, g2 * 1.4, term, disc - 0.005),
    }


def sensitivity_matrix(fcf, shares, cash, debt, base, years=10):
    """Matriz valor intrínseco: crecimiento (filas) x tasa descuento (columnas)."""
    if not fcf or not shares or fcf <= 0:
        return None
    g_base = base["growth_1_5"]
    d_base = base["discount_rate"]
    growths = [g_base - 0.04, g_base - 0.02, g_base, g_base + 0.02, g_base + 0.04]
    discounts = [d_base - 0.02, d_base - 0.01, d_base, d_base + 0.01, d_base + 0.02]

    def single(g1, disc):
        cur, pv = fcf, 0.0
        for yr in range(1, years + 1):
            g = g1 if yr <= 5 else base["growth_6_10"]
            cur *= (1 + g)
            pv += cur / (1 + disc) ** yr
        tv = cur * (1 + base["terminal_growth"]) / (disc - base["terminal_growth"])
        pv += tv / (1 + disc) ** years
        return (pv + (cash or 0) - (debt or 0)) / shares

    matrix = []
    for g in growths:
        row = [single(max(g, 0.0), d) for d in discounts]
        matrix.append(row)
    return {
        "growths": growths, "discounts": discounts, "matrix": matrix,
    }


# ============================================================
#  PIOTROSKI F-SCORE (0-9) — calidad fundamental
# ============================================================
def piotroski_fscore(edgar):
    """
    9 criterios binarios. >=7 fuerte, <=2 débil.
    Necesita al menos 2 años de datos.
    """
    if not edgar:
        return None
    ni = edgar.get("net_income", [])
    ocf = edgar.get("operating_cash_flow", [])
    assets = edgar.get("total_assets", [])
    ltd = edgar.get("long_term_debt", [])
    ca = edgar.get("current_assets", [])
    cl = edgar.get("current_liabilities", [])
    rev = edgar.get("revenue", [])
    gp = edgar.get("gross_profit", [])
    shares = edgar.get("shares_diluted", [])

    points, detail = 0, {}

    def add(name, cond):
        nonlocal points
        ok = bool(cond) if cond is not None else None
        detail[name] = ok
        if ok:
            points += 1

    ni_now, ni_prev = _last(ni), _prev(ni)
    ocf_now = _last(ocf)
    assets_now, assets_prev = _last(assets), _prev(assets)
    avg_assets = ((assets_now or 0) + (assets_prev or 0)) / 2 or None

    # Rentabilidad
    add("ROA positivo", ni_now is not None and assets_now and ni_now > 0)
    add("OCF positivo", ocf_now is not None and ocf_now > 0)
    roa_now = (ni_now / assets_now) if (ni_now and assets_now) else None
    roa_prev = (ni_prev / assets_prev) if (ni_prev and assets_prev) else None
    add("ROA mejora", roa_now is not None and roa_prev is not None and roa_now > roa_prev)
    add("OCF > Beneficio neto (calidad)", ocf_now is not None and ni_now is not None and ocf_now > ni_now)

    # Apalancamiento / liquidez
    ltd_now, ltd_prev = _last(ltd), _prev(ltd)
    add("Deuda L/P baja", ltd_now is not None and ltd_prev is not None and ltd_now <= ltd_prev)
    cr_now = (_last(ca) / _last(cl)) if (_last(ca) and _last(cl)) else None
    cr_prev = (_prev(ca) / _prev(cl)) if (_prev(ca) and _prev(cl)) else None
    add("Liquidez corriente mejora", cr_now is not None and cr_prev is not None and cr_now > cr_prev)
    sh_now, sh_prev = _last(shares), _prev(shares)
    add("Sin dilución de acciones", sh_now is not None and sh_prev is not None and sh_now <= sh_prev * 1.01)

    # Eficiencia
    gm_now = (_last(gp) / _last(rev)) if (_last(gp) and _last(rev)) else None
    gm_prev = (_prev(gp) / _prev(rev)) if (_prev(gp) and _prev(rev)) else None
    add("Margen bruto mejora", gm_now is not None and gm_prev is not None and gm_now > gm_prev)
    at_now = (_last(rev) / assets_now) if (_last(rev) and assets_now) else None
    at_prev = (_prev(rev) / assets_prev) if (_prev(rev) and assets_prev) else None
    add("Rotación activos mejora", at_now is not None and at_prev is not None and at_now > at_prev)

    return {"score": points, "detail": detail}


# ============================================================
#  ALTMAN Z-SCORE — riesgo de quiebra
# ============================================================
def altman_zscore(edgar, market_cap):
    """
    Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E
    >2.99 zona segura · 1.81-2.99 gris · <1.81 riesgo.
    """
    if not edgar:
        return None
    assets = _last(edgar.get("total_assets", []))
    if not assets:
        return None
    ca = _last(edgar.get("current_assets", []))
    cl = _last(edgar.get("current_liabilities", []))
    re = _last(edgar.get("retained_earnings", []))
    ebit = _last(edgar.get("operating_income", []))
    rev = _last(edgar.get("revenue", []))
    total_liab = _last(edgar.get("total_liabilities", []))

    wc = (ca - cl) if (ca is not None and cl is not None) else None
    A = (wc / assets) if wc is not None else 0
    B = (re / assets) if re is not None else 0
    C = (ebit / assets) if ebit is not None else 0
    D = (market_cap / total_liab) if (market_cap and total_liab) else 0
    E = (rev / assets) if rev is not None else 0

    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
    if z > 2.99:   zone = "Segura"
    elif z > 1.81: zone = "Gris"
    else:          zone = "Riesgo de quiebra"
    return {"z": z, "zone": zone}


# ============================================================
#  TENDENCIAS — márgenes y dilución a lo largo del tiempo
# ============================================================
def margin_trends(edgar):
    """Serie de márgenes bruto/operativo/neto por año."""
    if not edgar:
        return []
    rev = dict(edgar.get("revenue", []))
    gp = dict(edgar.get("gross_profit", []))
    oi = dict(edgar.get("operating_income", []))
    ni = dict(edgar.get("net_income", []))
    out = []
    for date in sorted(rev):
        r = rev[date]
        if not r:
            continue
        out.append({
            "fecha": date,
            "bruto": gp.get(date, 0) / r if date in gp else None,
            "operativo": oi.get(date, 0) / r if date in oi else None,
            "neto": ni.get(date, 0) / r if date in ni else None,
        })
    return out


def share_dilution(edgar):
    """Tendencia de acciones diluidas (¿la empresa diluye al accionista?)."""
    series = edgar.get("shares_diluted", []) if edgar else []
    if len(series) < 2:
        return None
    first, last = series[0][1], series[-1][1]
    years = len(series) - 1
    if not first or first <= 0:
        return None
    cagr = (last / first) ** (1 / years) - 1
    return {"series": series, "cagr": cagr,
            "verdict": "Recompra (bueno)" if cagr < -0.005
                       else "Estable" if cagr < 0.01
                       else "Dilución (vigilar)"}


# ============================================================
#  VALIDACIÓN DE DATOS — banderas rojas
# ============================================================
def data_quality_flags(edgar, m):
    """Detecta inconsistencias y huecos que un profesional debe conocer."""
    flags = []
    if not edgar:
        flags.append(("info", "Sin datos de EDGAR: empresa no-USA o sin filings. "
                              "Los fundamentales vienen solo de yfinance."))
        return flags

    rev = edgar.get("revenue", [])
    if len(rev) < 3:
        flags.append(("warn", f"Histórico corto: solo {len(rev)} años de ingresos en EDGAR."))

    # Salto anómalo en ingresos (>60% o caída >40%)
    if len(rev) >= 2:
        cur, prev = rev[-1][1], rev[-2][1]
        if prev and cur:
            chg = cur / prev - 1
            if chg > 0.6:
                flags.append(("warn", f"Salto de ingresos +{chg*100:.0f}% último año: "
                                      "¿adquisición o cambio contable? Verifica."))
            elif chg < -0.4:
                flags.append(("warn", f"Caída de ingresos {chg*100:.0f}% último año. Investiga la causa."))

    # FCF negativo
    if m.get("fcf") is not None and m["fcf"] < 0:
        flags.append(("warn", "FCF negativo: el DCF no es fiable aquí."))

    # Beneficio neto negativo
    ni = _last(edgar.get("net_income", []))
    if ni is not None and ni < 0:
        flags.append(("warn", "Beneficio neto negativo: muchos ratios pierden sentido."))

    # Equity negativo
    eq = _last(edgar.get("equity", []))
    if eq is not None and eq < 0:
        flags.append(("warn", "Fondos propios negativos: estructura de capital atípica."))

    if not flags:
        flags.append(("ok", "Sin banderas rojas evidentes en los datos."))
    return flags
