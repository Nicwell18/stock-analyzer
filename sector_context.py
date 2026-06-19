"""
sector_context.py — Contexto sectorial
========================================
Un ROE del 15% es excelente para una utility y mediocre para software.
Sin contexto sectorial, el score de calidad miente.

Estas son medianas TÍPICAS por sector (aproximadas, de mercados desarrollados).
No sustituyen a una base de datos en vivo, pero dan el contexto que un análisis
absoluto pierde. Ajusta si tienes datos mejores.

Fuente: rangos típicos de referencia del mercado. Uso educativo.
"""

# Medianas orientativas por sector de yfinance
SECTOR_MEDIANS = {
    "Technology": {
        "roe": 0.18, "gross_margin": 0.60, "op_margin": 0.22,
        "net_margin": 0.18, "rev_growth": 0.12, "net_debt_ebitda": 0.5, "pe": 28,
    },
    "Communication Services": {
        "roe": 0.15, "gross_margin": 0.50, "op_margin": 0.18,
        "net_margin": 0.14, "rev_growth": 0.08, "net_debt_ebitda": 1.8, "pe": 20,
    },
    "Consumer Cyclical": {
        "roe": 0.16, "gross_margin": 0.38, "op_margin": 0.10,
        "net_margin": 0.07, "rev_growth": 0.07, "net_debt_ebitda": 2.0, "pe": 18,
    },
    "Consumer Defensive": {
        "roe": 0.17, "gross_margin": 0.35, "op_margin": 0.13,
        "net_margin": 0.09, "rev_growth": 0.04, "net_debt_ebitda": 2.2, "pe": 21,
    },
    "Healthcare": {
        "roe": 0.15, "gross_margin": 0.58, "op_margin": 0.18,
        "net_margin": 0.12, "rev_growth": 0.09, "net_debt_ebitda": 1.5, "pe": 22,
    },
    "Financial Services": {
        "roe": 0.12, "gross_margin": 0.90, "op_margin": 0.35,
        "net_margin": 0.25, "rev_growth": 0.06, "net_debt_ebitda": None, "pe": 13,
    },
    "Industrials": {
        "roe": 0.15, "gross_margin": 0.32, "op_margin": 0.12,
        "net_margin": 0.08, "rev_growth": 0.06, "net_debt_ebitda": 2.0, "pe": 19,
    },
    "Energy": {
        "roe": 0.13, "gross_margin": 0.40, "op_margin": 0.15,
        "net_margin": 0.10, "rev_growth": 0.05, "net_debt_ebitda": 1.8, "pe": 12,
    },
    "Utilities": {
        "roe": 0.10, "gross_margin": 0.45, "op_margin": 0.22,
        "net_margin": 0.12, "rev_growth": 0.03, "net_debt_ebitda": 4.5, "pe": 18,
    },
    "Real Estate": {
        "roe": 0.09, "gross_margin": 0.60, "op_margin": 0.30,
        "net_margin": 0.20, "rev_growth": 0.05, "net_debt_ebitda": 6.0, "pe": 30,
    },
    "Basic Materials": {
        "roe": 0.13, "gross_margin": 0.28, "op_margin": 0.13,
        "net_margin": 0.09, "rev_growth": 0.05, "net_debt_ebitda": 1.8, "pe": 14,
    },
}

# Si el sector no está mapeado, usamos una media general
GENERIC = {
    "roe": 0.14, "gross_margin": 0.42, "op_margin": 0.15,
    "net_margin": 0.10, "rev_growth": 0.06, "net_debt_ebitda": 2.0, "pe": 18,
}

HIGHER_BETTER = {"roe", "gross_margin", "op_margin", "net_margin", "rev_growth"}
LOWER_BETTER = {"net_debt_ebitda", "pe"}


def get_benchmark(sector):
    return SECTOR_MEDIANS.get(sector, GENERIC)


def compare_to_sector(m):
    """
    Compara cada métrica de la empresa con la mediana de su sector.
    Devuelve lista de dicts con la comparación.
    """
    sector = m.get("sector")
    bench = get_benchmark(sector)
    metrics = ["roe", "gross_margin", "op_margin", "net_margin",
               "rev_growth", "net_debt_ebitda", "pe"]
    out = []
    for k in metrics:
        company = m.get(k)
        median = bench.get(k)
        if company is None or median is None:
            continue
        if k in HIGHER_BETTER:
            better = company > median
            ratio = company / median if median else None
        else:
            better = company < median
            ratio = median / company if company else None
        out.append({
            "metric": k, "company": company, "median": median,
            "better": better, "ratio": ratio,
        })
    return {"sector": sector or "Genérico", "items": out}
