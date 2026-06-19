"""
analysis.py — Lógica de análisis del Stock Analyzer
====================================================
Combina datos de EDGAR + yfinance, calcula ratios, score de calidad
estilo Buffett/Ackman y valoración por DCF.
"""

# --- Umbrales del screener de calidad ---
THRESHOLDS = {
    "roe": 0.15, "gross_margin": 0.40, "op_margin": 0.15,
    "net_margin": 0.10, "fcf_margin": 0.08, "rev_growth": 0.05,
    "net_debt_ebitda": 3.0, "fcf_conversion": 0.80,
}
WEIGHTS = {
    "roe": 16, "gross_margin": 12, "op_margin": 14, "net_margin": 10,
    "fcf_margin": 14, "rev_growth": 12, "net_debt_ebitda": 12,
    "fcf_conversion": 10,
}
LABELS = {
    "roe": "ROE", "gross_margin": "Margen bruto", "op_margin": "Margen op.",
    "net_margin": "Margen neto", "fcf_margin": "Margen FCF",
    "rev_growth": "Crec. ingresos", "net_debt_ebitda": "Deuda neta/EBITDA",
    "fcf_conversion": "Conversión FCF",
}

# --- Supuestos DCF por defecto (editables en la UI) ---
DCF_DEFAULTS = {
    "growth_1_5": 0.10, "growth_6_10": 0.05, "terminal_growth": 0.025,
    "discount_rate": 0.09, "margin_of_safety": 0.30,
}


def _last(series):
    return series[-1][1] if series else None


def build_metrics(edgar, yf_data):
    """Fusiona EDGAR (preferente para fundamentales) + yfinance (precio/respaldo)."""
    m = {}
    m["name"] = (yf_data or {}).get("name") or (edgar or {}).get("name")
    m["price"] = (yf_data or {}).get("price")
    m["currency"] = (yf_data or {}).get("currency", "USD")
    m["market_cap"] = (yf_data or {}).get("market_cap")
    m["shares"] = (yf_data or {}).get("shares")
    m["sector"] = (yf_data or {}).get("sector")
    m["source"] = "EDGAR + yfinance" if edgar else "yfinance"

    # Fundamentales: EDGAR primero, yfinance como respaldo
    if edgar:
        rev = _last(edgar["revenue"])
        ni = _last(edgar["net_income"])
        gp = _last(edgar["gross_profit"])
        oi = _last(edgar["operating_income"])
        eq = _last(edgar["equity"])
        ocf = _last(edgar["operating_cash_flow"])
        capex = _last(edgar["capex"])
        cash = _last(edgar["cash"])
        debt = _last(edgar["long_term_debt"])
        fcf = (ocf - capex) if (ocf is not None and capex is not None) else None
        m["revenue_series"] = edgar["revenue"]
        m["ni_series"] = edgar["net_income"]
        m["fcf"] = fcf
    else:
        rev = None; ni = None; gp = None; oi = None
        eq = None; cash = (yf_data or {}).get("cash")
        debt = (yf_data or {}).get("debt")
        fcf = (yf_data or {}).get("fcf")
        m["revenue_series"] = []
        m["ni_series"] = []
        m["fcf"] = fcf

    yd = yf_data or {}
    # Ratios — usar EDGAR si hay, si no yfinance
    m["roe"] = (ni / eq) if (ni and eq) else yd.get("roe")
    m["gross_margin"] = (gp / rev) if (gp and rev) else yd.get("gross_margin")
    m["op_margin"] = (oi / rev) if (oi and rev) else yd.get("op_margin")
    m["net_margin"] = (ni / rev) if (ni and rev) else yd.get("net_margin")
    m["fcf_margin"] = (fcf / rev) if (fcf and rev) else None
    m["rev_growth"] = yd.get("rev_growth")
    m["fcf_conversion"] = (fcf / ni) if (fcf and ni and ni > 0) else None

    ebitda = yd.get("ebitda")
    net_debt = (debt or 0) - (cash or 0)
    m["net_debt_ebitda"] = (net_debt / ebitda) if ebitda else None

    m["pe"] = yd.get("pe")
    m["forward_pe"] = yd.get("forward_pe")
    m["cash"] = cash
    m["debt"] = debt
    m["beta"] = yd.get("beta")
    m["equity_val"] = yd.get("market_cap")
    m["_edgar"] = edgar  # dict crudo de EDGAR para el motor profesional

    # Ratings de analistas
    m["rec_key"] = yd.get("rec_key")
    m["rec_mean"] = yd.get("rec_mean")
    m["n_analysts"] = yd.get("n_analysts")
    m["target_mean"] = yd.get("target_mean")
    m["target_high"] = yd.get("target_high")
    m["target_low"] = yd.get("target_low")
    return m


def passes(metric, value):
    if value is None:
        return None
    th = THRESHOLDS[metric]
    if metric == "net_debt_ebitda":
        return value < th
    return value >= th


def quality_score(m):
    total, earned, detail = 0, 0, {}
    for k, w in WEIGHTS.items():
        v = m.get(k)
        ok = passes(k, v)
        total += w
        if ok is None:
            detail[k] = (v, None)
            continue
        if ok:
            earned += w
        detail[k] = (v, ok)
    return (round(earned / total * 100) if total else 0), detail


def verdict_label(score):
    if score >= 75: return "★ Excelente", "#16a34a"
    if score >= 55: return "✓ Sólido", "#65a30d"
    if score >= 40: return "△ Revisar", "#d97706"
    return "✗ Descartar", "#dc2626"


def rating_label(rec_mean):
    """Convierte la media de yfinance (1=strong buy..5=sell) a etiqueta."""
    if rec_mean is None:
        return "Sin cobertura", "#94a3b8"
    if rec_mean <= 1.5: return "Compra fuerte", "#16a34a"
    if rec_mean <= 2.5: return "Compra", "#65a30d"
    if rec_mean <= 3.5: return "Mantener", "#d97706"
    if rec_mean <= 4.5: return "Vender", "#ea580c"
    return "Venta fuerte", "#dc2626"


def run_dcf(fcf, shares, cash, debt, a):
    """Valor intrínseco por acción. Devuelve dict con resultado y desglose."""
    if not fcf or not shares or fcf <= 0:
        return None
    r = a["discount_rate"]
    cur, pv_sum, rows = fcf, 0.0, []
    for yr in range(1, 11):
        g = a["growth_1_5"] if yr <= 5 else a["growth_6_10"]
        cur *= (1 + g)
        pv = cur / (1 + r) ** yr
        pv_sum += pv
        rows.append({"año": yr, "fcf_proyectado": cur, "valor_presente": pv})
    tv = cur * (1 + a["terminal_growth"]) / (r - a["terminal_growth"])
    pv_tv = tv / (1 + r) ** 10
    equity = pv_sum + pv_tv + (cash or 0) - (debt or 0)
    iv = equity / shares
    return {
        "intrinsic_value": iv,
        "buy_below": iv * (1 - a["margin_of_safety"]),
        "rows": rows,
        "pv_explicit": pv_sum,
        "pv_terminal": pv_tv,
    }
