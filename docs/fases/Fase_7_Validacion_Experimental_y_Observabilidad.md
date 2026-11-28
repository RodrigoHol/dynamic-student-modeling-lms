# Fase 7 — Validación Experimental, Línea Base Batch y Observabilidad (`C9` + `C10`)

> **Propósito:** Explicar qué se construyó en la Fase 7 para validar cuantitativamente la tesis (**RF-18** a **RF-21**, Capítulo V): el módulo `C9 Experiment Runner` (`experiments/`) compartiendo `dsm_core` con la línea base *batch* (**ADR-10**), el cálculo de métricas objetivas y la pila de observabilidad `C10` (Prometheus + Grafana).

---

## 1. Visión general: ¿Qué logramos en la Fase 7?

1. **Línea base *batch* justa (`experiments/src/dsm_experiments/baseline/`):** reutiliza exactamente el mismo `PreprocessingEngine` de `dsm_core` (reglas HLE, 4 granularidades y extractores) y ejecuta `StandardScaler` + `K-Means` (`scikit-learn`) junto con descubrimiento global `PM4Py` por ventana.
2. **Métricas científicas (`experiments/src/dsm_experiments/metrics/`):**
   - **Calidad y consistencia:** Coeficiente de Silueta y *Adjusted Rand Index* (**ARI**) tanto para concordancia *stream* vs. *batch* como para reproducibilidad entre corridas repetidas.
   - **Minería de procesos:** *Fitness* y *Precision* mediante `pm4py.discover_petri_net_inductive` + *token-based replay*.
   - **Desempeño computacional:** percentiles de latencia (`p50`, `p95`, `p99` en ms) y throughput (eventos/s).
3. **Exportación para el Capítulo V (`reports/exporter.py`):** genera `metrics_summary.csv`, `comparison_table.tex` (tabla LaTeX lista para la tesis), `summary.json` y `comparison_metrics.png`.
4. **Observabilidad `C10` (`deploy/observability/`):** Prometheus recolecta `/metrics` de `C2`, `C4`, `C5`, `C6` y `C7`, y Grafana aprovisiona automáticamente el datasource Prometheus y el tablero `DSM LMS — Desempeño y Latencias`.

---

## 2. Uso rápido de `dsm-experiments`

```powershell
# Benchmark reproducible stream (DenStream / DBSTREAM) vs batch (K-Means + PM4Py)
.\.venv\Scripts\dsm-experiments.exe benchmark data/samples/sample_synthetic.jsonl --output-dir experiments/results/sample --no-pg

# Evaluar una corrida en vivo registrada en MongoDB y guardar métricas en PostgreSQL
.\.venv\Scripts\dsm-experiments.exe evaluate-run <run_id> --dataset <ruta_dataset.jsonl> --output-dir experiments/results/live
```

---

## 3. Verificación automatizada (Etapa 8 del menú)

```powershell
.\.venv\Scripts\pytest.exe -v
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 8
```

La Etapa 8 verifica la disponibilidad de Prometheus (`http://localhost:9091`) y Grafana (`http://localhost:3001`), reproduce una corrida completa en vivo, calcula y persiste métricas en `experiment_metrics` (PostgreSQL) y genera los reportes CSV, LaTeX, JSON y PNG de comparación *stream* vs. *batch*.

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 7 completamos `C9 Experiment Runner` y `C10 Observabilidad`: ejecutamos la línea base batch (`K-Means` + `PM4Py`) sobre las mismas transformaciones puras de `dsm_core` (ADR-10), calculamos Silueta, ARI, Fitness, Precision y percentiles de latencia (`p50`/`p95`/`p99`) en `experiment_metrics` exportando tablas LaTeX/CSV y gráficas listas para el Capítulo V, y habilitamos el monitoreo continuo en Prometheus y Grafana.»*
