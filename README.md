# 📊 Stock Analyzer PRO

Dashboard de análisis fundamental de **nivel profesional**.
Combina datos oficiales de la **SEC (EDGAR)** con **yfinance**.
Pensado para análisis serio estilo Buffett / Ackman.

---

## Instalación (una vez)

```bash
pip install -r requirements.txt
```

## ⚠️ Paso obligatorio

Edita `data_sources.py`, línea `USER_AGENT`, con tu nombre y email reales.
La SEC rechaza peticiones sin esto (error 403):

```python
USER_AGENT = "Tu Nombre - Analisis Personal (tu.email@real.com)"
```

## Lanzar

```bash
streamlit run app.py
```

Se abre en el navegador (http://localhost:8501).

---

## Qué incluye

### Modo "Analizar empresa" — 6 pestañas

**📈 Resumen**
- Rating agregado de analistas + precio objetivo
- Score de calidad 0-100 (8 criterios estilo Buffett)
- **ROIC vs WACC**: el spread que mide si la empresa crea o destruye valor
- Gráfico de criterios y precio a 1 año

**💰 Valoración**
- **DCF con 3 escenarios** (bear / base / bull) frente al precio actual
- **Reverse DCF**: qué crecimiento implica el precio actual (lo que de verdad
  usan los profesionales para detectar sobre/infravaloración)
- **Matriz de sensibilidad**: valor intrínseco según crecimiento × WACC

**🏥 Salud financiera**
- **Piotroski F-Score** (0-9): calidad fundamental con 9 criterios
- **Altman Z-Score**: riesgo de quiebra, con medidor visual
- **Dilución de acciones**: ¿recompra o diluye al accionista?

**🏭 vs Sector**
- Cada ratio comparado con la mediana de su sector
  (un ROE del 15% no significa lo mismo en software que en utilities)

**📊 Tendencias**
- Evolución de márgenes (bruto/operativo/neto) en el tiempo
- Ingresos y beneficio histórico (datos SEC)

**🔬 Datos crudos**
- Tabla completa de todos los ratios

### Modo "Comparar empresas" (hasta 6)
- Tabla comparativa con Score, ROIC-WACC, Piotroski, Altman
- Ranking por calidad y por creación de valor
- Radar de rentabilidad
- Rendimiento de precio normalizado (base 100)

---

## Arquitectura (modular)

| Archivo | Responsabilidad |
|---------|-----------------|
| `app.py` | Interfaz y gráficos (Streamlit + Plotly) |
| `data_sources.py` | Conexión a EDGAR + yfinance |
| `analysis.py` | Ratios, score de calidad, DCF básico |
| `pro_analysis.py` | ROIC/WACC, reverse DCF, escenarios, Piotroski, Altman |
| `sector_context.py` | Medianas sectoriales |

Para cambiar un umbral o añadir una métrica, sabes exactamente dónde tocar.

---

## Fuentes y límites

| Dato | Fuente | Límite |
|------|--------|--------|
| Fundamentales históricos | EDGAR (SEC) | Solo empresas USA |
| Precio, market cap, ratings, beta | yfinance | Todo el mundo |

- Empresas europeas (Inditex…) no están en EDGAR → caen en yfinance y la app avisa.
- Ratings: solo el **agregado** gratuito (compra/mantener/venta). El desglose por
  banco ("Jefferies dice X") requiere API de pago.
- Las medianas sectoriales son orientativas, no una base de datos en vivo.
- El WACC usa una beta por defecto si yfinance no la da; ajústalo con criterio.

---

## Cómo lo usaría un profesional

1. **Reverse DCF primero**: ¿qué espera el mercado? Si exige 25% de crecimiento,
   ya sabes que el listón está altísimo.
2. **ROIC vs WACC**: si no supera el coste de capital, el crecimiento destruye valor.
3. **Piotroski + Altman**: filtro rápido de calidad y solvencia.
4. **vs Sector**: contexto. Nada se juzga en absoluto.
5. **Escenarios + sensibilidad**: nunca un número único; un rango con probabilidades.

El número es el punto de partida del análisis, no la conclusión.
El juicio sobre el *moat* y la directiva sigue siendo tuyo.

**Uso educativo. No es consejo de inversión.**
