# Especificación Técnica: Módulo Auditor de Riesgo y Liquidez (XLS-65 / XLS-66)

## Métricas Clave de Riesgo
- **LTV (Loan-to-Value):** Proporción de la deuda respecto al valor del colateral:
  $$LTV = \left(\frac{\text{Deuda Pendiente}}{\text{Valor del Colateral}}\right) \times 100$$
- **DSCR (Debt Service Coverage Ratio):** Ratio de cobertura del servicio de deuda:
  $$DSCR = \frac{\text{Ingresos Netos Operativos}}{\text{Servicio de Deuda}}$$
- **Categorización de Salud:**
  - **SALUDABLE:** $LTV \le 75\%$ y $DSCR \ge 1.25$
  - **ESTRÉS:** $75\% < LTV \le 85\%$ o $1.10 \le DSCR < 1.25$
  - **CRÍTICO:** $LTV > 85\%$ o $DSCR < 1.10$
