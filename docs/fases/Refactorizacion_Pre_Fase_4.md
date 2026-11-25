# Refactorización Pre-Fase 4 — Optimización, Modularización y Clean Code

> **Propósito:** Registro histórico de las mejoras de rendimiento, arquitectura interna y legibilidad aplicadas tras completar la Fase 3 y antes de implementar `C5 Clustering` y `C6 Process Mining`. Sirve como insumo técnico directo para la redacción del Capítulo IV de la tesis.

---

## 1. Motivación del corte técnico

Con las Fases 1–3 operativas, las pruebas funcionales sobre datasets pequeños (240 a 5,000 eventos) pasaban correctamente; sin embargo, una auditoría de código identificó cuellos de botella algorítmicos ($O(N^2)$ en estado de ventanas y envíos secuenciales a Kafka) y duplicación de orquestación entre `dsm_core` y `C4`. Se ejecutó esta refactorización para garantizar escalabilidad ante históricos reales de Moodle (RF-18), consistencia metodológica entre flujo y *batch* (ADR-10, RF-20) y una base modular limpia para `C5`–`C9`.

---

## 2. Resumen de cambios y justificación

| Área | Qué cambió | Por qué (impacto técnico / tesis) |
| :--- | :--- | :--- |
| **Estado incremental en `C4` y `dsm_core`** ([manager.py](../../libs/dsm_core/src/dsm_core/windowing/manager.py)) | `ingest_with_state` y `flush_run_with_state` almacenan cada evento una sola vez (`ev:{run_id}:{event_id}`) y mantienen en `window_state` un índice ligero por `event_ids`, liberando claves tras el cierre y podando ventanas vencidas por `watermark`. | Elimina la re-validación y re-serialización $O(N^2)$ de todo el historial abierto en RocksDB en cada evento (especialmente crítica en la ventana `course`), manteniendo latencia $O(1)$ por evento (RF-18). |
| **Publicación en lote en `C2`** ([producer.py](../../libs/dsm_common/src/dsm_common/messaging/producer.py), [routes.py](../../services/ingestion-gateway/src/dsm_gateway/api/routes.py)) | Se añadió `EventProducer.publish_batch` (`asyncio.gather` sobre `aiokafka` con `acks="all"`) y se unificó `normalize_or_dlq` retornando `CanonicalEvent \| DlqEvent`. | Sustituye $N$ viajes de red secuenciales por lote (`POST /api/v1/events/batch` y `/eof`) por despacho concurrente, preservando orden por clave `u` y aumentando el *throughput* en modo `max`. |
| **Precompilación HLE y `WindowContext`** ([noise_filter.py](../../libs/dsm_core/src/dsm_core/preprocessing/noise_filter.py), [hle_mapper.py](../../libs/dsm_core/src/dsm_core/preprocessing/hle_mapper.py), [base.py](../../libs/dsm_core/src/dsm_core/features/base.py)) | `NoiseFilter` y `HLEMapper` compilan reglas YAML al arrancar (*fail-fast*) evaluando `extract_match_context` una sola vez; `WindowContext` reemplaza diccionarios sin tipo y cachea `group_events_into_sessions`. | Evita reconstruir conjuntos y recalcular sesiones entre extractores (`session_count`, `mean_session_duration_sec`) o reordenar listas ya ordenadas por `t`. |
| **Única fuente de verdad en `C4`** ([pipeline.py](../../libs/dsm_core/src/dsm_core/pipeline.py), [processor.py](../../services/preprocessor/src/dsm_preprocessor/processor.py)) | `PreprocessorHandler` delega toda la lógica analítica y de estado en `PreprocessingEngine`, dejando `C4` como cascarón delgado de Quix Streams y métricas propias ([metrics.py](../../services/preprocessor/src/dsm_preprocessor/metrics.py)). | Garantiza que `C4` (*stream*) y `C9` (*batch*) ejecuten exactamente la misma implementación de filtrado, HLE, ventanas y features (ADR-10, RF-20). |
| **Desacoplamiento y utilidades en `dsm_common`** ([pyproject.toml](../../libs/dsm_common/pyproject.toml), [postgres.py](../../libs/dsm_common/src/dsm_common/storage/postgres.py), [server.py](../../libs/dsm_common/src/dsm_common/observability/server.py), [time.py](../../libs/dsm_common/src/dsm_common/time.py)) | `dsm_common` separa drivers opcionales mediante extras (`kafka`, `postgres`, `observability`); `PostgresRunRepository` adopta `asyncpg.Pool`; se centralizan `ensure_utc`, `Granularity` y el servidor HTTP `/health`+`/metrics`. | Mantiene a `dsm_core` libre de infraestructura (ADR-10), habilita concurrencia segura en `C7 Query API` y evita duplicar el servidor de observabilidad en `C5` y `C6`. |
| **Clean Code, CLI y Dockerfiles** ([scheduler.py](../../services/replayer/src/dsm_replayer/scheduler.py), [generator.py](../../services/replayer/src/dsm_replayer/generator.py), [demo/](../../scripts/demo), [pyproject.toml](../../pyproject.toml)) | Se dividieron funciones extensas en `C3` y se modularizó `scripts/demo_menu.py` por fase; los `Dockerfile`s cachean dependencias con `--no-install-workspace`; `ruff` suma `C4`, `SIM`, `RET`, `PIE`, `RUF` y `S101` (cero `assert` fuera de `tests/`) y se suprimieron comentarios redundantes. | Mejora la mantenibilidad, acelera reconstrucciones de contenedores y deja reglas automáticas de calidad antes de incorporar el núcleo de ML y minería de procesos. |

---

## 3. Verificación tras los cambios

- **Calidad estática (`ruff check .` y `uv lock --check --offline`):** 0 errores bajo reglas estrictas y *lockfile* consistente.
- **Pruebas unitarias (`pytest -v`):** **54/54** pruebas aprobadas (incluyendo validación *fail-fast* de reglas HLE, caché de sesiones en `WindowContext`, publicación en lote y limpieza total de claves `ev:*` tras `EOF`).
- **Validación E2E contra Docker (`scripts/demo_menu.py --step all`):**
  - Todos los contenedores (`kafka`, `postgres`, `mongodb`, `neo4j`, `redpanda-console`, `ingestion-gateway`, `preprocessor`) en estado `healthy`.
  - **Fase 2 (`5,000` eventos, modo `max`):** completada en `3.601 s` (**`1,388.7 ev/s`**), 0 pérdidas y 0 eventos fuera de orden por estudiante.
  - **Fase 3 (`10x` vs `max`):** `259` ventanas y `259` trazas 100 % idénticas en las 4 granularidades (`daily`, `weekly`, `monthly`, `course`) con 100 % de ruido filtrado.
