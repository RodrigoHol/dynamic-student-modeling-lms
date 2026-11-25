# Fase 2 — Replayer / Simulador e Inyección de Datos (`C3`)

> **Propósito:** Explicar qué se construyó en la Fase 2, cómo garantiza la reproducibilidad temporal exigida por la tesis ([tesis/main.md](../tesis/main.md), Secciones I.3, III.2.1 y III.3.1; ADR-01 y ADR-12) y cómo ejecutar y verificar la ingesta continua de un curso completo.

---

## 1. Visión general: ¿Qué logramos en la Fase 2?

En la Fase 1 quedó lista la puerta de entrada (`C2 Ingestion Gateway`), el log inmutable en Apache Kafka y los esquemas vacíos de la Capa III. En la **Fase 2** implementamos el emisor principal del sistema (**C3 Replayer / Simulador**), el generador de cursos sintéticos realistas compatibles con Moodle y el repositorio de trazabilidad de corridas en PostgreSQL (`runs`, `hle_catalog_versions` y `run_configs`).

De acuerdo con **ADR-01** y **ADR-12**, el Replayer separa estrictamente los dos relojes del sistema:
1. Conserva intacta la estampa cronológica original del estudiante (`t`), garantizando que todo dataset se reproduzca en orden cronológico no decreciente por estudiante.
2. Emite las peticiones HTTP hacia `C2`, permitiendo variar el factor de aceleración (`1x`, `10x`, `100x`, `max`) para medir throughput y latencia real desde `ingested_at` sin alterar la partición temporal futura de las ventanas.

---

## 2. Los 4 bloques construidos en esta fase

### Bloque 1: Trazabilidad de corridas en `dsm_common` ([postgres.py](../../libs/dsm_common/src/dsm_common/storage/postgres.py))
- Se implementó `RunRepository` y su adaptador asíncrono `PostgresRunRepository` (sobre `asyncpg`), junto con `InMemoryRunRepository` para pruebas rápidas sin base de datos.
- Al iniciar una corrida, `start_run` inserta la fila correspondiente en `runs` (`status = 'running'`) y guarda en `hle_catalog_versions` y `run_configs` una fotografía inmutable de los cinco archivos YAML de [config/](../../config) (`hle_catalog.yaml`, `features.yaml`, `windows.yaml`, `clustering.yaml`, `process_mining.yaml`) y su hash SHA-256 (RF-19).
- Al finalizar o fallar, `complete_run` / `fail_run` actualiza `status`, `events_processed` y `finished_at`.

### Bloque 2: Parsers enchufables `SourceParser` ([parsers/](../../services/replayer/src/dsm_replayer/parsers))
Se definió el contrato abstracto `SourceParser` y tres implementaciones registradas en [registry.py](../../services/replayer/src/dsm_replayer/parsers/registry.py) con autodetección de formato (`detect_format`):
- **`MoodleCsvExportParser`** ([moodle_csv.py](../../services/replayer/src/dsm_replayer/parsers/moodle_csv.py)): interpreta exportaciones estándar de bitácoras de Moodle en español e inglés, normaliza componentes/acciones hacia `RawEventInput` y reordena cronológicamente por `(t, fila)`.
- **`MoodleDbLogParser`** ([moodle_db.py](../../services/replayer/src/dsm_replayer/parsers/moodle_db.py)): lee volcados CSV o JSONL de la tabla relacional `mdl_logstore_standard_log` convirtiendo `timecreated` a UTC.
- **`SyntheticJsonlParser`** ([synthetic.py](../../services/replayer/src/dsm_replayer/parsers/synthetic.py)): consume archivos `.jsonl` generados localmente garantizando orden cronológico estricto.

### Bloque 3: Generador sintético compatible con Moodle ([generator.py](../../services/replayer/src/dsm_replayer/generator.py))
- `generate_synthetic_events` produce de forma determinista (controlada por `seed`) sesiones realistas para múltiples semanas y estudiantes distribuidos en cinco arquetipos conductuales (`consistent_active`, `deadline_driven`, `passive_reader`, `at_risk_declining`, `improving`) alineados con las reglas de `config/hle_catalog.yaml` más una fracción configurable de ruido operativo (`log_report_viewed`).
- `write_synthetic_dataset` permite exportar exactamente el mismo curso a `synthetic_jsonl`, `moodle_csv` o `moodle_db`.
- Se versionaron tres muestras pequeñas de 80 eventos en [data/samples/](../../data/samples) (`sample_synthetic.jsonl`, `sample_moodle_export.csv`, `sample_moodle_db_log.csv`).

### Bloque 4: Despachador asíncrono y CLI `dsm-replayer` ([scheduler.py](../../services/replayer/src/dsm_replayer/scheduler.py), [cli.py](../../services/replayer/src/dsm_replayer/cli.py))
- `ReplayDispatcher` soporta modo temporizado (`1x`, `10x`, `100x`, escalando deltas entre eventos consecutivos) y modo `max` (envío secuencial por lotes hacia `POST /api/v1/events/batch` con reintentos ante errores transitorios y sin carreras de ordenamiento).
- El CLI `dsm-replayer` expone los subcomandos `generate` y `replay`, además de integrarse en el workspace `uv` y en [docker-compose.yml](../../deploy/docker-compose.yml) bajo el perfil `replay`.

---

## 3. Guía de demostración paso a paso

1. **Levantar la infraestructura base (si no está activa):**
   ```powershell
   docker compose -f deploy/docker-compose.yml up -d --wait
   ```

2. **Generar un curso sintético de 5,000 eventos (50 estudiantes, 8 semanas):**
   ```powershell
   .\.venv\Scripts\dsm-replayer.exe generate data/synthetic/synthetic_course_5000.jsonl --target-events 5000 --students 50 --weeks 8 --seed 42
   ```

3. **Ejecutar el replay en velocidad máxima hacia `C2 Ingestion Gateway`:**
   ```powershell
   .\.venv\Scripts\dsm-replayer.exe replay data/synthetic/synthetic_course_5000.jsonl --speed max --run-id run_phase2_verify_5000
   ```

4. **Verificar en las interfaces y almacenes:**
   - **PostgreSQL (`runs` y `run_configs`):** confirmar `status = 'completed'` y `events_processed = 5000` para `run_phase2_verify_5000`.
   - **Redpanda Console (`http://localhost:8080` → `lms.events.canonical`):** comprobar los 5,000 eventos canónicos con `u` seudonimizado, `run_id = 'run_phase2_verify_5000'` y orden cronológico estricto `t` por estudiante.

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 2 construimos el emisor principal de flujos (`C3 Replayer`): implementamos la interfaz `SourceParser` con adaptadores para exportaciones CSV de Moodle, volcados de `mdl_logstore_standard_log` y JSONL sintético; desarrollamos un generador determinista de cursos con cinco perfiles conductuales; e integramos el despachador asíncrono con control de velocidad y registro trazable de corridas y configuraciones YAML en PostgreSQL (`runs` y `run_configs`).»*
