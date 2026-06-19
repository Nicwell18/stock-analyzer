"""
app.py — Stock Analyzer PRO 📊
===============================
Dashboard de análisis fundamental de nivel profesional.
Fuentes: EDGAR (SEC) + yfinance.

Incluye: score de calidad, ROIC vs WACC, reverse DCF, DCF con escenarios y
matriz de sensibilidad, Piotroski F-Score, Altman Z-Score, contexto sectorial,
tendencias de márgenes, dilución, validación de datos y comparación múltiple.

LANZAR:  streamlit run app.py
Uso educativo. No es consejo de inversión.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import data_sources as ds
import analysis as an
import pro_analysis as pa
import sector_context as sc

st.set_page_config(page_title="Stock Analyzer PRO", page_icon="📊", layout="wide")

st.markdown("""
<style>
  .big-num { font-size: 2.1rem; font-weight: 700; line-height: 1; }
  .sub { color:#64748b; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em;}
  .pill { display:inline-block; padding:4px 14px; border-radius:999px;
          color:white; font-weight:600; font-size:0.9rem;}
  div[data-testid="stMetricValue"] { font-size: 1.4rem; }
</style>
""", unsafe_allow_html=True)


# ---------- formato ----------
def fmt_money(v, cur="USD"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    sym = "$" if cur == "USD" else ("€" if cur == "EUR" else "")
    a = abs(v)
    if a >= 1e12: return f"{sym}{v/1e12:.2f}T"
    if a >= 1e9:  return f"{sym}{v/1e9:.2f}B"
    if a >= 1e6:  return f"{sym}{v/1e6:.1f}M"
    return f"{sym}{v:,.2f}"

def fmt_pct(v):
    return "—" if v is None else f"{v*100:.1f}%"

def fmt_x(v):
    return "—" if v is None else f"{v:.2f}x"


@st.cache_data(ttl=900, show_spinner=False)
def load_stock(ticker):
    try:
        yf_data = ds.get_yfinance(ticker)
    except Exception:
        yf_data = None
    if yf_data is None:
        return None
    try:
        edgar = ds.get_edgar(ticker)
    except Exception:
        edgar = None
    return an.build_metrics(edgar, yf_data)


# ============================ SIDEBAR ============================
st.sidebar.title("📊 Stock Analyzer PRO")
st.sidebar.caption("EDGAR (SEC) + yfinance · análisis de nivel profesional")

mode = st.sidebar.radio("Modo", ["🔍 Analizar empresa", "⚖️ Comparar empresas"])

st.sidebar.divider()
st.sidebar.subheader("Supuestos DCF (escenario base)")
a = dict(an.DCF_DEFAULTS)
a["growth_1_5"] = st.sidebar.slider("Crecimiento años 1-5", 0.0, 0.30,
                                     an.DCF_DEFAULTS["growth_1_5"], 0.01)
a["growth_6_10"] = st.sidebar.slider("Crecimiento años 6-10", 0.0, 0.20,
                                      an.DCF_DEFAULTS["growth_6_10"], 0.01)
a["terminal_growth"] = st.sidebar.slider("Crecimiento terminal", 0.0, 0.04,
                                          an.DCF_DEFAULTS["terminal_growth"], 0.005)
a["discount_rate"] = st.sidebar.slider("Tasa de descuento (WACC)", 0.05, 0.15,
                                        an.DCF_DEFAULTS["discount_rate"], 0.005)
a["margin_of_safety"] = st.sidebar.slider("Margen de seguridad", 0.0, 0.50,
                                           an.DCF_DEFAULTS["margin_of_safety"], 0.05)
st.sidebar.divider()
st.sidebar.caption("⚠️ Educativo. No es consejo de inversión.")


# ============================ ANALIZAR ============================
def analyze_company(ticker):
    with st.spinner(f"Cargando {ticker}…"):
        m = load_stock(ticker)
    if m is None:
        st.error(f"No se pudieron cargar datos para {ticker}.")
        st.info("📡 Causa más probable: **Yahoo Finance ha limitado las peticiones** "
                "(error de rate limit, común en Streamlit Cloud al compartir servidor). "
                "Espera 1-2 minutos y vuelve a intentarlo, o recarga la página. "
                "Si persiste, prueba más tarde: el límite se levanta solo.")
        return
    edgar = m.get("_edgar")

    st.header(f"{m['name']} · {ticker}")
    top = st.columns(5)
    top[0].metric("Precio", fmt_money(m.get("price"), m["currency"]))
    top[1].metric("Capitalización", fmt_money(m.get("market_cap"), m["currency"]))
    top[2].metric("PER", fmt_x(m.get("pe")))
    top[3].metric("PER fwd", fmt_x(m.get("forward_pe")))
    top[4].metric("Sector", (m.get("sector") or "—")[:18])
    st.caption(f"Fuente: {m['source']}")

    flags = pa.data_quality_flags(edgar, m)
    for level, msg in flags:
        if level == "warn":
            st.warning("⚑ " + msg)
        elif level == "ok":
            st.success("✓ " + msg)
        else:
            st.info("ℹ " + msg)

    tabs = st.tabs([
        "📈 Resumen", "💰 Valoración", "🏥 Salud financiera",
        "🏭 vs Sector", "📊 Tendencias", "🔬 Datos crudos",
    ])

    # ---------- RESUMEN ----------
    with tabs[0]:
        label, color = an.rating_label(m.get("rec_mean"))
        n = m.get("n_analysts")
        st.markdown(f'<span class="pill" style="background:{color}">'
                    f'Analistas: {label}{f" · {n} analistas" if n else ""}</span>',
                    unsafe_allow_html=True)
        if m.get("target_mean") and m.get("price"):
            up = (m["target_mean"] / m["price"] - 1) * 100
            c = st.columns(3)
            c[0].metric("Objetivo medio", fmt_money(m["target_mean"], m["currency"]), f"{up:+.1f}%")
            c[1].metric("Objetivo alto", fmt_money(m.get("target_high"), m["currency"]))
            c[2].metric("Objetivo bajo", fmt_money(m.get("target_low"), m["currency"]))
        st.divider()

        col1, col2 = st.columns([1, 1])
        with col1:
            score, detail = an.quality_score(m)
            vlabel, vcolor = an.verdict_label(score)
            st.markdown(f'<div class="sub">Score de calidad</div>'
                        f'<div class="big-num" style="color:{vcolor}">{score}/100</div>'
                        f'<span class="pill" style="background:{vcolor}">{vlabel}</span>',
                        unsafe_allow_html=True)
        with col2:
            roic = pa.compute_roic(edgar)
            wacc = pa.estimate_wacc(m)
            spread, slabel = pa.value_creation(roic, wacc)
            st.markdown('<div class="sub">Creación de valor (ROIC − WACC)</div>',
                        unsafe_allow_html=True)
            if spread is not None:
                col = "#16a34a" if spread > 0 else "#dc2626"
                st.markdown(f'<div class="big-num" style="color:{col}">{spread*100:+.1f} pp</div>'
                            f'<span style="color:#64748b">ROIC {fmt_pct(roic)} vs WACC {fmt_pct(wacc)}</span><br>'
                            f'<span class="pill" style="background:{col}">{slabel}</span>',
                            unsafe_allow_html=True)
            else:
                st.info("Datos insuficientes para ROIC/WACC.")
        st.divider()

        score, detail = an.quality_score(m)
        rows = []
        for k, w in an.WEIGHTS.items():
            v, ok = detail[k]
            status = "Cumple" if ok else ("No cumple" if ok is False else "Sin dato")
            rows.append({"Criterio": an.LABELS[k], "Estado": status, "Peso": w})
        df = pd.DataFrame(rows)
        cmap = {"Cumple": "#16a34a", "No cumple": "#dc2626", "Sin dato": "#cbd5e1"}
        fig = px.bar(df, x="Peso", y="Criterio", color="Estado", orientation="h",
                     color_discrete_map=cmap, height=300,
                     title="Criterios de calidad (estilo Buffett)")
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0),
                          legend=dict(orientation="h", y=1.12), yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

        hist = ds.get_price_history(ticker, "1y")
        if hist is not None:
            pf = go.Figure()
            pf.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines",
                                    line=dict(color="#0ea5e9", width=2)))
            pf.update_layout(height=260, title="Precio (1 año)",
                             margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(pf, use_container_width=True)

    # ---------- VALORACIÓN ----------
    with tabs[1]:
        st.subheader("DCF con escenarios")
        sce = pa.dcf_scenarios(m.get("fcf"), m.get("shares"),
                               m.get("cash"), m.get("debt"), a)
        price = m.get("price")
        cur = m.get("currency")
        if sce is None:
            st.warning("No se puede calcular DCF: FCF negativo o datos incompletos.")
        else:
            c = st.columns(4)
            c[0].metric("Bear", fmt_money(sce["bear"], cur),
                        f"{(sce['bear']/price-1)*100:+.0f}%" if price else None)
            c[1].metric("Base", fmt_money(sce["base"], cur),
                        f"{(sce['base']/price-1)*100:+.0f}%" if price else None)
            c[2].metric("Bull", fmt_money(sce["bull"], cur),
                        f"{(sce['bull']/price-1)*100:+.0f}%" if price else None)
            c[3].metric("Precio actual", fmt_money(price, cur))

            sfig = go.Figure()
            sfig.add_bar(x=["Bear", "Base", "Bull"],
                         y=[sce["bear"], sce["base"], sce["bull"]],
                         marker_color=["#dc2626", "#2563eb", "#16a34a"])
            if price:
                sfig.add_hline(y=price, line_dash="dash", line_color="#475569",
                               annotation_text=f"Precio actual {fmt_money(price, cur)}")
            sfig.update_layout(height=320, title="Rango de valoración",
                               margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(sfig, use_container_width=True)

        st.divider()
        st.subheader("Reverse DCF — expectativas implícitas en el precio")
        impl = pa.reverse_dcf(price, m.get("shares"), m.get("fcf"),
                              m.get("cash"), m.get("debt"), a["discount_rate"],
                              a["terminal_growth"])
        if impl is not None:
            st.markdown(f'El precio actual implica un crecimiento de FCF del '
                        f'**{impl*100:.1f}% anual** durante 10 años.')
            base_g = a["growth_1_5"]
            if impl > base_g + 0.03:
                st.error(f"El mercado exige más crecimiento ({impl*100:.1f}%) "
                         f"que tu supuesto base ({base_g*100:.0f}%). Posible sobrevaloración: "
                         "habría que creer un escenario muy optimista para justificar el precio.")
            elif impl < base_g - 0.03:
                st.success(f"El mercado solo exige {impl*100:.1f}% de crecimiento, "
                           f"menos que tu base ({base_g*100:.0f}%). Posible margen de seguridad.")
            else:
                st.info(f"El crecimiento implícito ({impl*100:.1f}%) está en línea con "
                        f"tu supuesto base ({base_g*100:.0f}%). Precio razonable.")
        else:
            st.warning("No se puede calcular el reverse DCF (FCF negativo o datos incompletos).")

        st.divider()
        st.subheader("Matriz de sensibilidad")
        st.caption("Valor intrínseco según crecimiento (filas) y tasa de descuento (columnas)")
        sm = pa.sensitivity_matrix(m.get("fcf"), m.get("shares"),
                                   m.get("cash"), m.get("debt"), a)
        if sm:
            cols = [f"WACC {d*100:.1f}%" for d in sm["discounts"]]
            idx = [f"Crec. {g*100:.0f}%" for g in sm["growths"]]
            heat = go.Figure(data=go.Heatmap(
                z=sm["matrix"], x=cols, y=idx, colorscale="RdYlGn",
                text=[[fmt_money(v, cur) for v in row] for row in sm["matrix"]],
                texttemplate="%{text}", textfont={"size": 11},
                colorbar=dict(title="Valor")))
            heat.update_layout(height=380, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(heat, use_container_width=True)
            if price:
                st.caption(f"Precio actual de referencia: **{fmt_money(price, cur)}**. "
                           "Verde = infravalorada según ese par de supuestos.")
        else:
            st.warning("No se puede calcular la matriz (FCF negativo o datos incompletos).")

    # ---------- SALUD FINANCIERA ----------
    with tabs[2]:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Piotroski F-Score")
            st.caption("Calidad fundamental, 0-9. ≥7 fuerte · ≤2 débil")
            pf = pa.piotroski_fscore(edgar)
            if pf:
                score = pf["score"]
                color = "#16a34a" if score >= 7 else "#d97706" if score >= 4 else "#dc2626"
                st.markdown(f'<div class="big-num" style="color:{color}">{score}/9</div>',
                            unsafe_allow_html=True)
                for name, ok in pf["detail"].items():
                    mark = "✅" if ok else ("❌" if ok is False else "➖")
                    st.write(f"{mark} {name}")
            else:
                st.info("Requiere ≥2 años de datos de EDGAR.")
        with col2:
            st.subheader("Altman Z-Score")
            st.caption("Riesgo de quiebra. >2.99 seguro · <1.81 riesgo")
            az = pa.altman_zscore(edgar, m.get("market_cap"))
            if az:
                z = az["z"]
                color = "#16a34a" if z > 2.99 else "#d97706" if z > 1.81 else "#dc2626"
                st.markdown(f'<div class="big-num" style="color:{color}">{z:.2f}</div>'
                            f'<span class="pill" style="background:{color}">{az["zone"]}</span>',
                            unsafe_allow_html=True)
                g = go.Figure(go.Indicator(
                    mode="gauge+number", value=z,
                    gauge={"axis": {"range": [0, 8]}, "bar": {"color": color},
                           "steps": [
                               {"range": [0, 1.81], "color": "#fecaca"},
                               {"range": [1.81, 2.99], "color": "#fed7aa"},
                               {"range": [2.99, 8], "color": "#bbf7d0"}]}))
                g.update_layout(height=220, margin=dict(l=20, r=20, t=20, b=10))
                st.plotly_chart(g, use_container_width=True)
            else:
                st.info("Requiere datos de balance de EDGAR.")

        st.divider()
        st.subheader("Dilución de acciones")
        dil = pa.share_dilution(edgar)
        if dil:
            color = "#16a34a" if "Recompra" in dil["verdict"] else \
                    "#64748b" if "Estable" in dil["verdict"] else "#dc2626"
            st.markdown(f'CAGR de acciones: **{dil["cagr"]*100:+.1f}%/año** · '
                        f'<span class="pill" style="background:{color}">{dil["verdict"]}</span>',
                        unsafe_allow_html=True)
            df = pd.DataFrame(dil["series"], columns=["fecha", "acciones"])
            f = px.line(df, x="fecha", y="acciones", markers=True, height=260,
                        title="Acciones diluidas en circulación")
            f.update_layout(margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(f, use_container_width=True)
        else:
            st.info("Requiere ≥2 años de datos de acciones en EDGAR.")

    # ---------- vs SECTOR ----------
    with tabs[3]:
        comp = sc.compare_to_sector(m)
        st.subheader(f"Comparación con el sector: {comp['sector']}")
        st.caption("Medianas sectoriales orientativas. Verde = mejor que la mediana.")
        if comp["items"]:
            names = {"roe": "ROE", "gross_margin": "Margen bruto",
                     "op_margin": "Margen op.", "net_margin": "Margen neto",
                     "rev_growth": "Crec. ingresos",
                     "net_debt_ebitda": "Deuda neta/EBITDA", "pe": "PER"}
            rows = []
            for it in comp["items"]:
                pct_fmt = it["metric"] not in ("net_debt_ebitda", "pe")
                rows.append({
                    "Métrica": names[it["metric"]],
                    "Empresa": fmt_pct(it["company"]) if pct_fmt else fmt_x(it["company"]),
                    "Mediana sector": fmt_pct(it["median"]) if pct_fmt else fmt_x(it["median"]),
                    "Veredicto": "✅ Mejor" if it["better"] else "❌ Peor",
                })
            st.dataframe(pd.DataFrame(rows).set_index("Métrica"), use_container_width=True)

            pct_items = [it for it in comp["items"]
                         if it["metric"] in ("roe", "gross_margin", "op_margin",
                                             "net_margin", "rev_growth")]
            if pct_items:
                bfig = go.Figure()
                cats = [names[it["metric"]] for it in pct_items]
                bfig.add_bar(x=cats, y=[it["company"]*100 for it in pct_items],
                             name="Empresa", marker_color="#2563eb")
                bfig.add_bar(x=cats, y=[it["median"]*100 for it in pct_items],
                             name="Mediana sector", marker_color="#cbd5e1")
                bfig.update_layout(barmode="group", height=340,
                                   title="Empresa vs mediana sectorial (%)",
                                   margin=dict(l=0, r=0, t=40, b=0),
                                   legend=dict(orientation="h", y=1.12))
                st.plotly_chart(bfig, use_container_width=True)
        else:
            st.info("No hay métricas suficientes para comparar.")

    # ---------- TENDENCIAS ----------
    with tabs[4]:
        st.subheader("Evolución de márgenes")
        mt = pa.margin_trends(edgar)
        if mt:
            df = pd.DataFrame(mt)
            f = go.Figure()
            for col, name, color in [("bruto", "Margen bruto", "#2563eb"),
                                     ("operativo", "Margen operativo", "#16a34a"),
                                     ("neto", "Margen neto", "#d97706")]:
                f.add_trace(go.Scatter(x=df["fecha"], y=df[col]*100, mode="lines+markers",
                                       name=name, line=dict(color=color)))
            f.update_layout(height=340, title="Márgenes a lo largo del tiempo (%)",
                            margin=dict(l=0, r=0, t=40, b=0),
                            legend=dict(orientation="h", y=1.12))
            st.plotly_chart(f, use_container_width=True)
        else:
            st.info("Sin histórico de EDGAR para mostrar tendencias.")

        st.divider()
        st.subheader("Ingresos y beneficio (datos SEC)")
        if edgar and edgar.get("revenue"):
            dr = pd.DataFrame(edgar["revenue"], columns=["fecha", "Ingresos"])
            f2 = go.Figure()
            f2.add_bar(x=dr["fecha"], y=dr["Ingresos"], name="Ingresos",
                       marker_color="#2563eb")
            if edgar.get("net_income"):
                dn = pd.DataFrame(edgar["net_income"], columns=["fecha", "Beneficio"])
                f2.add_bar(x=dn["fecha"], y=dn["Beneficio"], name="Beneficio neto",
                           marker_color="#16a34a")
            f2.update_layout(barmode="group", height=340,
                             margin=dict(l=0, r=0, t=10, b=0),
                             legend=dict(orientation="h", y=1.12))
            st.plotly_chart(f2, use_container_width=True)
        else:
            st.info("Sin datos de EDGAR (empresa no-USA).")

    # ---------- DATOS CRUDOS ----------
    with tabs[5]:
        st.subheader("Todos los ratios")
        rr = {
            "ROE": fmt_pct(m.get("roe")),
            "Margen bruto": fmt_pct(m.get("gross_margin")),
            "Margen operativo": fmt_pct(m.get("op_margin")),
            "Margen neto": fmt_pct(m.get("net_margin")),
            "Margen FCF": fmt_pct(m.get("fcf_margin")),
            "Crecimiento ingresos": fmt_pct(m.get("rev_growth")),
            "Deuda neta/EBITDA": fmt_x(m.get("net_debt_ebitda")),
            "Conversión FCF": fmt_x(m.get("fcf_conversion")),
            "PER": fmt_x(m.get("pe")),
            "PER adelantado": fmt_x(m.get("forward_pe")),
            "FCF": fmt_money(m.get("fcf"), m["currency"]),
            "Caja": fmt_money(m.get("cash"), m["currency"]),
            "Deuda": fmt_money(m.get("debt"), m["currency"]),
            "Beta": f'{m.get("beta"):.2f}' if m.get("beta") else "—",
        }
        st.table(pd.DataFrame(rr.items(), columns=["Ratio", "Valor"]))
        if edgar:
            st.caption(f"CIK SEC: {edgar.get('cik')} · "
                       f"{len(edgar.get('revenue', []))} años de histórico")


# ============================ COMPARAR ============================
def compare_companies(raw):
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()][:6]
    rows, valid = [], {}
    prog = st.progress(0.0)
    for i, tk in enumerate(tickers):
        m = load_stock(tk)
        prog.progress((i + 1) / len(tickers))
        if m is None:
            continue
        valid[tk] = m
        score, _ = an.quality_score(m)
        roic = pa.compute_roic(m.get("_edgar"))
        wacc = pa.estimate_wacc(m)
        spread = (roic - wacc) if (roic and wacc) else None
        pf = pa.piotroski_fscore(m.get("_edgar"))
        az = pa.altman_zscore(m.get("_edgar"), m.get("market_cap"))
        rlabel, _ = an.rating_label(m.get("rec_mean"))
        rows.append({
            "Ticker": tk, "Empresa": m["name"][:22], "Score": score,
            "ROIC-WACC": spread, "Piotroski": pf["score"] if pf else None,
            "Altman Z": az["z"] if az else None,
            "ROE": m.get("roe"), "M. FCF": m.get("fcf_margin"),
            "Crec.": m.get("rev_growth"), "PER": m.get("pe"),
            "Analistas": rlabel,
        })
    prog.empty()
    if not rows:
        st.error("No se obtuvieron datos para esos tickers.")
        return

    df = pd.DataFrame(rows).sort_values("Score", ascending=False)

    st.subheader("Tabla comparativa")
    show = df.copy()
    show["ROIC-WACC"] = show["ROIC-WACC"].apply(lambda v: f"{v*100:+.1f}pp" if v is not None else "—")
    show["Altman Z"] = show["Altman Z"].apply(lambda v: f"{v:.1f}" if v is not None else "—")
    for c in ["ROE", "M. FCF", "Crec."]:
        show[c] = show[c].apply(fmt_pct)
    show["PER"] = show["PER"].apply(fmt_x)
    st.dataframe(show.set_index("Ticker"), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Ranking por calidad")
        f = px.bar(df, x="Score", y="Ticker", orientation="h", color="Score",
                   color_continuous_scale="RdYlGn", range_color=[0, 100],
                   text="Score", height=300)
        f.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis_title=None)
        st.plotly_chart(f, use_container_width=True)
    with c2:
        st.subheader("Creación de valor (ROIC − WACC)")
        dfv = df.dropna(subset=["ROIC-WACC"]).copy()
        if not dfv.empty:
            dfv["spread_pp"] = dfv["ROIC-WACC"] * 100
            f = px.bar(dfv, x="spread_pp", y="Ticker", orientation="h",
                       color="spread_pp", color_continuous_scale="RdYlGn",
                       text=dfv["spread_pp"].apply(lambda v: f"{v:+.1f}pp"), height=300)
            f.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis_title=None,
                            xaxis_title="ROIC − WACC (pp)")
            st.plotly_chart(f, use_container_width=True)
        else:
            st.info("Sin datos de ROIC para los tickers (¿empresas no-USA?).")

    st.subheader("Perfil de rentabilidad")
    metrics = ["ROE", "M. FCF", "Crec."]
    radar = go.Figure()
    for _, r in df.iterrows():
        vals = [(r[mm] or 0) * 100 for mm in metrics]
        radar.add_trace(go.Scatterpolar(r=vals + [vals[0]],
                                        theta=metrics + [metrics[0]],
                                        fill="toself", name=r["Ticker"]))
    radar.update_layout(height=420, polar=dict(radialaxis=dict(visible=True)),
                        margin=dict(l=40, r=40, t=20, b=20))
    st.plotly_chart(radar, use_container_width=True)

    st.subheader("Rendimiento del precio (1 año, base 100)")
    pfig = go.Figure()
    for tk in valid:
        h = ds.get_price_history(tk, "1y")
        if h is None or h.empty:
            continue
        norm = h["Close"] / h["Close"].iloc[0] * 100
        pfig.add_trace(go.Scatter(x=h.index, y=norm, name=tk, mode="lines"))
    pfig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0),
                       yaxis_title="Base 100")
    st.plotly_chart(pfig, use_container_width=True)


# ============================ MAIN ============================
if mode == "🔍 Analizar empresa":
    st.title("Análisis de empresa")
    ticker = st.text_input("Ticker", value="AAPL",
                           help="AAPL, MSFT, NVDA, O, VICI… Empresas USA tienen datos SEC.")
    if ticker:
        analyze_company(ticker.upper())
else:
    st.title("Comparar empresas")
    raw = st.text_input("Tickers separados por coma", value="AAPL, MSFT, GOOGL",
                        help="Hasta 6 empresas.")
    if raw:
        compare_companies(raw)

st.divider()
st.caption("⚠️ Herramienta educativa. No constituye consejo de inversión. "
           "Datos: SEC EDGAR + yfinance. Verifica siempre con los filings originales.")
