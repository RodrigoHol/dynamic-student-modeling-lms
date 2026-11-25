# Fase 3 — Preprocesamiento, Abstracción HLE y Ventanas Múltiples (`dsm_core` + `C4`)

> **Propósito:** Explicar qué se construyó en la Fase 3, cómo se garantiza la separación estricta entre dominio analítico puro y E/S (**ADR-10**), cómo operan el mapeo a Eventos de Alto Nivel (HLE) y las cuatro ventanas disjuntas por tiempo del evento `t` (**ADR-05**, **ADR-07**, **ADR-12**), y cómo verificar el determinismo `10x` vs `max`.

---

## 1. Visión general: ¿Qué logramos en la Fase 3?

Con las Fases 1 y 2 completadas, el sistema ya ingería eventos canónicos $E = \langle u, a, r, t, M \rangle$ hacia Apache Kafka (`lms.events.canonical`). En la **Fase 3** implementamos el corazón de transformación semántica y temporal de la Capa II:

1. **Señal determinista de fin de corrida (`RunEofEvent`):** `C3 Replayer` emite al término de cada replay un marcador `POST /api/v1/runs/{run_id}/eof` hacia `C2`, el cual publica un `RunEofEvent` por estudiante en `lms.events.canonical` usando la misma clave de partición `u`. Esto garantiza que las ventanas finales (en especial `course` con `close_on_eof: true`) se cierren ordenadamente cuando termina el histórico.
2. **Núcleo analítico 100% puro en `libs/dsm_core` (ADR-10):** sin ninguna dependencia de Kafka ni bases de datos, se implementaron el filtro de ruido (`NoiseFilter`), el mapeador `HLEMapper`, el gestor de ventanas múltiples (`MultiGranularityWindowManager`), los extractores configurables (`FeatureExtractor` / `FeaturePipeline`) y el ensamblador de salidas (`PreprocessingEngine`).
3. **Servicio continuo `C4 Preprocessor` (`services/preprocessor`):** construido sobre **Quix Streams + RocksDB** (`ADR-07`), consume continuamente `lms.events.canonical`, delega la lógica analítica a `dsm_core`, persiste el estado de ventanas por estudiante en RocksDB y emite vectores y trazas hacia `analytics.features` y `analytics.traces` (con clave `granularity:u`), además de derivar mensajes malformados a `lms.events.dlq`.

---

## 2. Los 4 bloques construidos en esta fase

### Bloque 1: Contratos analíticos y marcador EOF ([dsm_common](../../libs/dsm_common/src/dsm_common/schemas))
- **`analytics.py`:** define `FeatureVectorMessage`, `TraceEventItem` y `TraceMessage` con normalización estricta de marcas temporales a UTC.
- **`events.py`:** añade `RunEofRequest` y `RunEofEvent` (`event_type = "run_eof"`).
- **`C2` (`routes.py`) y `C3` (`scheduler.py`, `cli.py`):** exponen `POST /api/v1/runs/{run_id}/eof` y la bandera `--emit-eof / --no-emit-eof` (activada por defecto en el CLI de `dsm-replayer`).
- **`observability/metrics.py`:** incorpora contadores e histograma Prometheus para `C4` (`dsm_preprocessor_events_total`, `dsm_preprocessor_windows_closed_total`, `dsm_preprocessor_late_events_dropped_total` y `dsm_preprocessor_processing_latency_seconds`).

### Bloque 2: Filtrado de ruido y mapeo HLE en `dsm_core` ([preprocessing/](../../libs/dsm_core/src/dsm_core/preprocessing))
- **`NoiseFilter`** ([noise_filter.py](../../libs/dsm_core/src/dsm_core/preprocessing/noise_filter.py)): descarta interacciones operativas sin valor pedagógico declaradas en `ignore_noise` de [config/hle_catalog.yaml](../../config/hle_catalog.yaml) (como `log_report_viewed` y `course_user_report_viewed`).
- **`HLEMapper`** ([hle_mapper.py](../../libs/dsm_core/src/dsm_core/preprocessing/hle_mapper.py)): evalúa ordenadamente las reglas YAML (`component`, `action`, `target`, `*_in`, `eventname_contains`) y asigna el código HLE (`ACCESO_CURSO`, `CONSULTA_RECURSO`, `PARTICIPACION_FORO`, `ENVIO_TAREA`, `INTENTO_CUESTIONARIO`, `REVISION_RETROALIMENTACION` o `default_hle = "OTRO"`).

### Bloque 3: Ventanas disjuntas por `t` y extractores de características ([windowing/](../../libs/dsm_core/src/dsm_core/windowing), [features/](../../libs/dsm_core/src/dsm_core/features))
- **`compute_window_spec` y `MultiGranularityWindowManager`** ([boundaries.py](../../libs/dsm_core/src/dsm_core/windowing/boundaries.py), [manager.py](../../libs/dsm_core/src/dsm_core/windowing/manager.py)):
  - Segmenta cada evento en paralelo sobre las cuatro granularidades definidas en [config/windows.yaml](../../config/windows.yaml) usando **exclusivamente** el tiempo original del evento `t` (ADR-12):
    - `daily`: `[YYYY-MM-DD 00:00Z, +24h)`
    - `weekly`: semana ISO `[lunes 00:00Z, +7d)` (`YYYY-Www`)
    - `monthly`: mes calendario (`YYYY-MM`) o bloques fijos de 30 días (`mode: fixed_30d`)
    - `course`: ventana única del curso completo (`close_on_eof: true`)
  - Aplica marca de agua por `t` más `grace_period_seconds` (300s): acepta eventos tardíos dentro del periodo de gracia, descarta eventos posteriores al cierre de ventana, deduplica por `event_id` y serializa su estado a diccionario JSON compatible con RocksDB.
- **`FeaturePipeline` y los 6 extractores** ([extractors.py](../../libs/dsm_core/src/dsm_core/features/extractors.py), [registry.py](../../libs/dsm_core/src/dsm_core/features/registry.py)):
  - `total_events`, `active_days`, `hle_frequency_per_category` (una columna fija por cada HLE del catálogo), `regularity_index` (entropía de Shannon normalizada en `[0.0, 1.0]`), `session_count` y `mean_session_duration_sec` (agrupando por `session_hash` o umbral de inactividad de 1,800s).

### Bloque 4: Servicio `C4 Preprocessor` con Quix Streams ([services/preprocessor](../../services/preprocessor))
- **`PreprocessorHandler`** ([processor.py](../../services/preprocessor/src/dsm_preprocessor/processor.py)): función stateful ejecutada por Quix Streams con estado respaldado en RocksDB por clave `u`.
- **`build_application`** ([app.py](../../services/preprocessor/src/dsm_preprocessor/app.py)): conecta `lms.events.canonical` con `analytics.features`, `analytics.traces` (clave `granularity:u`) y `lms.events.dlq` (clave `dlq_id`).
- **`main.py` y `Dockerfile`:** exponen `GET /health` y `GET /metrics` en el puerto `8004` y ejecutan el servicio de forma continua dentro de [docker-compose.yml](../../deploy/docker-compose.yml).

---

## 3. Guía de demostración paso a paso

1. **Verificar pruebas unitarias y pureza arquitectónica de `dsm_core`:**
   ```powershell
   .\.venv\Scripts\pytest.exe -v
   .\.venv\Scripts\ruff.exe check .
   ```
   *(Incluye `test_architecture_purity.py`, que audita el AST de `dsm_core` confirmando cero importaciones de Kafka o bases de datos).*

2. **Levantar o actualizar el stack Docker (incluyendo `dsm-preprocessor`):**
   ```powershell
   docker compose -f deploy/docker-compose.yml up -d --build --wait
   ```

3. **Ejecutar la prueba de determinismo `10x` vs `max` (Etapa 4 del menú):**
   ```powershell
   .\.venv\Scripts\python.exe scripts\demo_menu.py --step 4
   ```
   Esta prueba genera un curso sintético multi-semana con ruido operativo, lo reproduce primero a velocidad `10x` y luego a velocidad `max`, y verifica en Kafka (`analytics.features` y `analytics.traces`) que:
   - Están presentes las 4 granularidades (`daily`, `weekly`, `monthly`, `course`).
   - El 100% del ruido (`log_report_viewed`) fue filtrado.
   - Los vectores de características y las secuencias ordenadas de trazas HLE son **100% idénticos** entre `10x` y `max` para cada `(granularity, window_id, u)`.

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 3 implementamos el núcleo analítico puro en `dsm_core` (filtro de ruido, mapeador declarativo HLE, gestor de las cuatro ventanas disjuntas por tiempo del evento `t` con periodo de gracia y los seis extractores de características) y desplegamos `C4 Preprocessor` sobre Quix Streams + RocksDB. Validamos además el criterio de determinismo reproduciendo el mismo curso a velocidades `10x` y `max`, obteniendo exactamente los mismos 259 vectores en `analytics.features` y las mismas 259 trazas en `analytics.traces` en las cuatro granularidades.»*
