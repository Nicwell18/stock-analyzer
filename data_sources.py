"""
data_sources.py — Capa de datos del Stock Analyzer
===================================================
Combina dos fuentes:
  - EDGAR (SEC): fundamentales oficiales de empresas USA (fuente primaria)
  - yfinance: precios en tiempo real, ratings de analistas, empresas no-USA

Todas las funciones cachean resultados para no repetir llamadas.
"""

import time
import requests
import pandas as pd
import yfinance as yf
import streamlit as st

# ⚠️ CAMBIA por tu email real (la SEC lo exige; si no, error 403)
USER_AGENT = "Pedro - Analisis Personal (tu.email@ejemplo.com)"
HEADERS = {"User-Agent": USER_AGENT}

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

CONCEPT_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "total_liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt"],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "ebit": ["OperatingIncomeLoss"],
}


def _get_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    time.sleep(0.12)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=86400)  # mapping ticker->CIK cambia poco; cachear 1 día
def _ticker_map():
    return _get_json(TICKERS_URL)


def ticker_to_cik(ticker):
    data = _ticker_map()
    ticker = ticker.upper()
    for entry in data.values():
        if entry["ticker"].upper() == ticker:
            return str(entry["cik_str"]).zfill(10), entry["title"]
    return None, None


def _extract_series(facts, key, annual_only=True):
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in CONCEPT_TAGS[key]:
        node = us_gaap.get(tag)
        if not node:
            continue
        unit_data = next(iter(node.get("units", {}).values()), [])
        seen, series = set(), []
        for it in unit_data:
            if annual_only and it.get("form") not in ("10-K", "20-F"):
                continue
            k = (it.get("end"), it.get("val"))
            if k in seen:
                continue
            seen.add(k)
            series.append((it["end"], it["val"]))
        if series:
            series.sort(key=lambda x: x[0])
            return series
    return []


@st.cache_data(ttl=3600)
def get_edgar(ticker):
    """Fundamentales oficiales de la SEC. None si no es empresa SEC."""
    cik, title = ticker_to_cik(ticker)
    if not cik:
        return None
    facts = _get_json(FACTS_URL.format(cik=cik))
    out = {"name": title, "cik": cik, "source": "EDGAR (SEC)"}
    for key in CONCEPT_TAGS:
        out[key] = _extract_series(facts, key)
    return out


@st.cache_data(ttl=900)  # precios: refrescar cada 15 min
def get_yfinance(ticker):
    """Precio, market cap, ratings de analistas y fundamentales de respaldo."""
    t = yf.Ticker(ticker)
    info = t.info
    if not info or info.get("regularMarketPrice") is None:
        return None

    # Ratings agregados de analistas (gratis)
    reco = None
    try:
        rec = t.recommendations
        if rec is not None and not rec.empty:
            reco = rec.tail(1).to_dict("records")[0]
    except Exception:
        pass

    return {
        "name": info.get("shortName", ticker),
        "price": info.get("regularMarketPrice"),
        "currency": info.get("currency", "USD"),
        "market_cap": info.get("marketCap"),
        "shares": info.get("sharesOutstanding"),
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "fcf": info.get("freeCashflow"),
        "cash": info.get("totalCash"),
        "debt": info.get("totalDebt"),
        "roe": info.get("returnOnEquity"),
        "gross_margin": info.get("grossMargins"),
        "op_margin": info.get("operatingMargins"),
        "net_margin": info.get("profitMargins"),
        "rev_growth": info.get("revenueGrowth"),
        "ebitda": info.get("ebitda"),
        "beta": info.get("beta"),
        "total_liabilities": None,
        # Ratings
        "rec_key": info.get("recommendationKey"),       # 'buy', 'strong_buy'...
        "rec_mean": info.get("recommendationMean"),      # 1=strong buy .. 5=sell
        "n_analysts": info.get("numberOfAnalystOpinions"),
        "target_mean": info.get("targetMeanPrice"),
        "target_high": info.get("targetHighPrice"),
        "target_low": info.get("targetLowPrice"),
        "reco_detail": reco,
        "source": "yfinance",
        "sector": info.get("sector"),
        "industry": info.get("industry"),
    }


@st.cache_data(ttl=900)
def get_price_history(ticker, period="1y"):
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    return hist if not hist.empty else None


def series_last_two(series):
    """Devuelve (actual, anterior) de una serie [(fecha, valor)]."""
    if not series:
        return None, None
    if len(series) == 1:
        return series[-1][1], None
    return series[-1][1], series[-2][1]
