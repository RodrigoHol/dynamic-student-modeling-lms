# Servicio C3: Replayer / Simulador (`dsm-replayer`)

Implementa el componente **C3 (Replayer / Simulador)** definido en [docs/arquitectura.md](../../docs/arquitectura.md) (ADR-01, ADR-12, Sección 8.5): lee registros históricos de Moodle o datasets sintéticos en orden cronológico estricto por `t` original y los emite asíncronamente hacia **C2 Ingestion Gateway** con control de velocidad, registrando la corrida y su configuración versionada en **PostgreSQL**.

## Parsers enchufables (`SourceParser`)

| Formato (`--format`) | Clase | Origen soportado |
| :--- | :--- | :--- |
| `moodle_csv` | `MoodleCsvExportParser` | Exportación CSV desde la interfaz web de Moodle (encabezados en español o inglés). |
| `moodle_db` | `MoodleDbLogParser` | Volcado CSV o JSONL de la tabla `mdl_logstore_standard_log`. |
| `synthetic_jsonl` | `SyntheticJsonlParser` | Datasets sintéticos en formato JSON Lines generados por `dsm-replayer`. |

Si se omite `--format` en `replay`, el CLI detecta automáticamente el formato inspeccionando la extensión y los encabezados del archivo.

## Uso del CLI

### 1. Generar un dataset sintético realista compatible con Moodle

```powershell
.\.venv\Scripts\dsm-replayer.exe generate data/synthetic/synthetic_course_5000.jsonl `
  --format synthetic_jsonl `
  --students 50 `
  --weeks 8 `
  --target-events 5000 `
  --seed 42
```

El generador distribuye a los estudiantes entre cinco perfiles conductuales (`consistent_active`, `deadline_driven`, `passive_reader`, `at_risk_declining`, `improving`) alineados con las reglas de `config/hle_catalog.yaml`.

### 2. Reproducir un dataset hacia C2 Ingestion Gateway

```powershell
# Velocidad máxima (envío por lotes secuenciales preservando orden por t)
.\.venv\Scripts\dsm-replayer.exe replay data/synthetic/synthetic_course_5000.jsonl --speed max

# Velocidad acelerada respetando deltas temporales relativos (p. ej. 100x)
.\.venv\Scripts\dsm-replayer.exe replay data/samples/sample_moodle_export.csv --speed 100x --max-delay 2.0

# Sin registro en PostgreSQL (modo prueba)
.\.venv\Scripts\dsm-replayer.exe replay data/samples/sample_synthetic.jsonl --speed max --no-db
```
