# Dynamic Student Modeling LMS

Plataforma orientada a eventos (arquitectura tipo Kappa) para automatizar el modelado dinámico e interpretable de patrones de interacción estudiantil en Sistemas de Gestión de Aprendizaje (LMS), combinando minería de flujos de datos (*Data Stream Mining*) y minería de procesos educativos (*Educational Process Mining*).

## Documentación del proyecto

- **Arquitectura y decisiones técnicas (base Capítulo IV):** [docs/arquitectura.md](./docs/arquitectura.md)
- **Hoja de ruta y criterios de paso:** [docs/Fases_De_Implementacion.md](./docs/Fases_De_Implementacion.md)
- **Explicación detallada por fases:** [docs/fases/README.md](./docs/fases/README.md)
- **Tesis (copia de referencia):** [docs/tesis/main.md](./docs/tesis/main.md)

---

## Estado actual: Fases 1 a 7 completadas (`C2`–`C10` completas)

### Fase 1 — Infraestructura base y puerta de ingesta (`C2`)
- **Workspace Python 3.12 (`uv`):** librería compartida `libs/dsm_common` (esquema canónico $E = \langle u, a, r, t, M \rangle$, seudonimización determinista `HMAC-SHA256`, cargador de YAML en `config/`, productores Kafka, métricas Prometheus y repositorio de corridas en PostgreSQL) y esqueleto `libs/dsm_core`.
- **Puerta de ingesta `C2 Ingestion Gateway` (`services/ingestion-gateway`):** API asíncrona en FastAPI (`POST /api/v1/events`, `/api/v1/events/batch` y `/api/v1/runs/{run_id}/eof`) que valida, seudonimiza `u`, agrega `ingested_at` y publica en `lms.events.canonical` (o enruta errores a `lms.events.dlq`).
- **Infraestructura en Docker Compose (`deploy/docker-compose.yml`):** Apache Kafka 3.8.0 (modo KRaft sin Zookeeper) con creación automática de topics, Redpanda Console, PostgreSQL 16 (7 tablas relacionales), MongoDB 7.0 Community (colecciones e índices) y Neo4j 5.23 Community (restricciones e índices de grafos).
- Guía de demostración: [docs/fases/Fase_1_Infraestructura_e_Ingesta.md](./docs/fases/Fase_1_Infraestructura_e_Ingesta.md).

### Fase 2 — Replayer / Simulador e inyección de datos (`C3`)
- **Parsers enchufables `SourceParser` (`services/replayer`):** adaptadores con autodetección de formato y ordenamiento cronológico estricto por `t` para exportaciones CSV de Moodle (`moodle_csv`), volcados de `mdl_logstore_standard_log` (`moodle_db`) y JSONL sintético (`synthetic_jsonl`).
- **Generador sintético realista:** genera cursos deterministas con 5 arquetipos conductuales alineados con [config/hle_catalog.yaml](./config/hle_catalog.yaml) y muestras versionadas en [data/samples](./data/samples).
- **Despachador asíncrono y CLI (`dsm-replayer`):** controla la velocidad de emisión (`1x`, `10x`, `100x`, `max`) hacia `C2`, emite señal de cierre EOF (`--emit-eof`) y registra la corrida junto con su snapshot YAML en PostgreSQL (`runs`, `hle_catalog_versions` y `run_configs`).
- Guía de demostración: [docs/fases/Fase_2_Replayer_y_Datos_Sinteticos.md](./docs/fases/Fase_2_Replayer_y_Datos_Sinteticos.md).

### Fase 3 — Preprocesamiento, HLE y ventanas múltiples (`dsm_core` + `C4`)
- **Dominio analítico puro (`libs/dsm_core`):** sin dependencias de Kafka ni bases de datos (ADR-10), implementa `NoiseFilter`, `HLEMapper`, el particionador y gestor de ventanas disjuntas por `t` (`daily`, `weekly`, `monthly`, `course`) con periodo de gracia (`MultiGranularityWindowManager`) y los 6 extractores configurables (`FeaturePipeline`).
- **Procesador continuo `C4 Preprocessor` (`services/preprocessor`):** servicio sobre Quix Streams + RocksDB que consume `lms.events.canonical`, mantiene el estado de ventanas por estudiante y publica vectores y trazas HLE en `analytics.features` y `analytics.traces` (clave `granularity:u`), exponiendo `GET /health` y `GET /metrics` en el puerto `8004`.
- Guía de demostración: [docs/fases/Fase_3_Preprocesamiento_HLE_y_Ventanas.md](./docs/fases/Fase_3_Preprocesamiento_HLE_y_Ventanas.md).

### Fase 4 — Motor de clustering evolutivo (`dsm_core.clustering` + `C5`)
- **Núcleo puro en `libs/dsm_core`:** interfaz `ClusteringAlgorithm`, registro declarativo (`CLUSTERING_REGISTRY`) y adaptadores intercambiables `DenStreamAdapter` y `DBSTREAMAdapter` sobre `River`, aislamiento estricto por `(run_id, granularity)`, estandarización y `z_score` incrementales en $O(1)$ (`OnlineFeatureStats` / Welford) y detección de transiciones entre ventanas (`TransitionTracker`).
- **Servicio continuo `C5 Clustering Engine` (`services/clustering`):** consume `analytics.features`, realiza `upsert` de perfiles dinámicos (`student_profiles`) y centroides (`cluster_snapshots`) en MongoDB, publica asignaciones `(u -> cluster_id)` en `analytics.assignments` y expone `GET /health` y `GET /metrics` en el puerto `8005`.
- Guía de demostración: [docs/fases/Fase_4_Motor_de_Clustering_Evolutivo.md](./docs/fases/Fase_4_Motor_de_Clustering_Evolutivo.md).

### Fase 5 — Motor de minería de procesos educativos (`dsm_core.process_mining` + `C6`)
- **Núcleo puro en `libs/dsm_core`:** interfaz `ProcessDiscovery`, implementación `PM4PyDFGDiscovery` sobre `PM4Py`, registro declarativo (`PROCESS_DISCOVERY_REGISTRY`), fusión y sustracción algebraica exacta de grafos DFG (`add_dfg_in_place`, `subtract_dfg_in_place`) y orquestador concurrente `ProcessMiningEngine` (ADR-13).
- **Servicio continuo `C6 Process Mining Engine` (`services/process-mining`):** consume concurrentemente `analytics.traces` y `analytics.assignments`, calcula DFG individuales en paralelo a `C5`, consolida aditivamente los DFG por clúster en Neo4j (`:Activity`, `:Boundary`, `:DFG`) y expone `GET /health` y `GET /metrics` en el puerto `8006`.
- Guía de demostración: [docs/fases/Fase_5_Motor_de_Mineria_de_Procesos.md](./docs/fases/Fase_5_Motor_de_Mineria_de_Procesos.md).

### Fase 6 — API de consulta y Dashboard Docente (`C7` + `C8`)
- **Query API `C7` (`services/query-api`):** FastAPI con autenticación JWT por roles (`teacher`, `admin`), lectura políglota sobre PostgreSQL, MongoDB y Neo4j, y puente WebSocket desde `analytics.assignments` en el puerto `8007`.
- **Dashboard Docente `C8` (`frontend/dashboard`):** SPA en Vue 3 + TypeScript + PrimeVue + `vue-echarts` (Sankey, distribución, `z_score`) + Cytoscape.js (`cytoscape-dagre` para grafos DFG) servida en el puerto `8088`.
- Guía de demostración: [docs/fases/Fase_6_API_de_Consulta_y_Dashboard.md](./docs/fases/Fase_6_API_de_Consulta_y_Dashboard.md).

### Fase 7 — Validación experimental y observabilidad (`C9` + `C10`)
- **Experiment Runner `C9` (`experiments/`):** CLI `dsm-experiments` compartiendo `dsm_core` (ADR-10) para ejecutar la línea base *batch* (`K-Means` + `PM4Py` inductivo), calcular Silueta, ARI, Fitness, Precision y percentiles de latencia en PostgreSQL (`experiment_metrics`) y exportar tablas CSV/LaTeX y figuras PNG.
- **Observabilidad `C10` (`deploy/observability/`):** Prometheus (`9091`) y Grafana (`3001`) con datasource y tablero preaprovisionados.
- Guía de demostración: [docs/fases/Fase_7_Validacion_Experimental_y_Observabilidad.md](./docs/fases/Fase_7_Validacion_Experimental_y_Observabilidad.md).

---

## Menú interactivo de demostración y verificación

Para llevar control de avance y demostrar el sistema paso a paso (p. ej. ante la dirección de tesis) sin memorizar comandos largos, ejecuta el menú interactivo en PowerShell desde la raíz del repositorio (con **Docker Desktop** abierto):

```powershell
.\.venv\Scripts\python.exe scripts\demo_menu.py
```

El menú muestra el estado de cada etapa en pantalla y permite ejecutarlas individualmente o en secuencia:

| Opción | Etapa | Qué ejecuta y valida |
| :--- | :--- | :--- |
| `0` | Limpieza total | `docker compose down -v` (borra contenedores y volúmenes para probar desde cero, pide confirmación). |
| `1` | Entorno, tests y linter | `uv sync --all-packages`, `.\.venv\Scripts\pytest.exe -v` y `.\.venv\Scripts\ruff.exe check .`. |
| `2` | Comprobar **Fase 1** | Levanta el stack Docker en estado `healthy`, aplica constraints en Neo4j, prueba `GET /health` y `POST /api/v1/events` (evento válido `202` seudonimizado y malformado `422` a DLQ) y verifica esquemas en PostgreSQL, MongoDB y Neo4j. |
| `3` | Comprobar **Fase 2** | Genera 5,000 eventos sintéticos (50 estudiantes, 8 semanas), ejecuta `dsm-replayer replay --speed max` y valida en PostgreSQL (`runs` y `run_configs`) y Kafka (`lms.events.canonical`: 5,000 eventos, cero pérdidas y orden cronológico por estudiante). |
| `4` | Comprobar **Fase 3** | Verifica `C4 Preprocessor`, genera un curso multi-semana con ruido y ejecuta la **prueba de determinismo `10x` vs `max`**, confirmando 100% de igualdad en `analytics.features` y `analytics.traces` en las 4 granularidades (`daily`, `weekly`, `monthly`, `course`). |
| `5` | Comprobar **Fase 4** | Verifica `C5 Clustering Engine` con `denstream` (perfiles, transiciones y `z_score` en MongoDB + `analytics.assignments` para las 4 granularidades) y el intercambio declarativo a `dbstream` modificando únicamente `config/clustering.yaml`. |
| `6` | Comprobar **Fase 5** | Verifica `C6 Process Mining Engine` sobre `PM4Py` y Neo4j, comprobando algebraicamente que cada grafo DFG de clúster (`freq`, `total_time_sec`, `mean_time_sec`, `support`) coincide exactamente con la suma de los DFG individuales de sus miembros en las 4 granularidades. |
| `7` | Comprobar **Fase 6** | Verifica `C7 Query API` (JWT + REST + WebSocket en vivo) y `C8 Dashboard` (`http://localhost:8088`). |
| `8` | Comprobar **Fase 7** | Verifica `C10` (Prometheus + Grafana), ejecuta `dsm-experiments evaluate-run` y `benchmark`, valida `experiment_metrics` en PostgreSQL y exporta CSV/LaTeX/JSON/PNG. |
| `9` | Apagar stack | `docker compose down` (detiene contenedores conservando los datos). |
| `a` | Demostración completa | Ejecuta en orden las etapas `1 → 2 → 3 → 4 → 5 → 6 → 7 → 8`. |
| `s` | Estado e interfaces | Muestra `docker compose ps` y las URLs locales para inspección visual. |

También puedes lanzar cualquier etapa directamente sin menú interactivo usando `--step`:

```powershell
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 1
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 2
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 3
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 4
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 5
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 6
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 7
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 8
.\.venv\Scripts\python.exe scripts\demo_menu.py --step all
```

---

## Cómo ejecutar el proyecto manualmente

### 1. Entorno local de desarrollo, pruebas y linter (Python 3.12 + `uv`)

```powershell
# Instalar y sincronizar todas las dependencias del workspace
uv sync --all-packages

# Ejecutar pruebas unitarias y linter usando los binarios directos del entorno virtual
.\.venv\Scripts\pytest.exe -v
.\.venv\Scripts\ruff.exe check .
```

### 2. Levantar o detener los contenedores (Docker Compose)

```powershell
# Construir el gateway y levantar toda la infraestructura esperando healthchecks
docker compose -f deploy/docker-compose.yml up -d --build --wait

# Verificar estado de contenedores
docker compose -f deploy/docker-compose.yml ps

# Asegurar restricciones Cypher iniciales en Neo4j
docker exec dsm-neo4j cypher-shell -u neo4j -p dsm_neo4j_pass -f /init/constraints.cypher

# Detener contenedores (añade -v para borrar también los volúmenes)
docker compose -f deploy/docker-compose.yml down
```

### 3. Generar y reproducir un curso sintético (`dsm-replayer`)

```powershell
.\.venv\Scripts\dsm-replayer.exe generate data/synthetic/synthetic_course_5000.jsonl --target-events 5000 --students 50 --weeks 8 --seed 42
.\.venv\Scripts\dsm-replayer.exe replay data/synthetic/synthetic_course_5000.jsonl --speed max
```

---

## Interfaces gráficas web disponibles

Con los contenedores corriendo, puedes acceder desde tu navegador a las siguientes herramientas visuales:

| Servicio | URL | Credenciales | Qué hace | Para qué sirve |
| :--- | :--- | :--- | :--- | :--- |
| **Swagger / OpenAPI (`C2 Ingestion Gateway`)** | http://localhost:8000/docs | Sin autenticación (local) | Documentación web interactiva generada por FastAPI con todos los endpoints del Gateway (`/api/v1/events`, `/api/v1/events/batch`, `/api/v1/runs/{run_id}/eof`, `/health`, `/metrics`). | Probar el envío de eventos JSON reales o malformados desde el navegador, observar el código de respuesta (`202` o `422`) y verificar la seudonimización inmediata de `u`. |
| **C4 Preprocessor (`dsm-preprocessor`)** | http://localhost:8004/health | Sin autenticación (local) | Endpoint operativo de salud (`/health`) y métricas Prometheus (`/metrics`) del procesador continuo Quix Streams. | Confirmar disponibilidad del procesador de ventanas y consultar contadores de eventos mapeados, ruido filtrado y ventanas cerradas. |
| **C5 Clustering Engine (`dsm-clustering`)** | http://localhost:8005/health | Sin autenticación (local) | Endpoint operativo de salud (`/health`) y métricas Prometheus (`/metrics`) del motor de clustering evolutivo sobre River. | Confirmar disponibilidad de `C5` y consultar vectores procesados, transiciones detectadas, outliers y latencia `ingested_to_profile`. |
| **C6 Process Mining Engine (`dsm-process-mining`)** | http://localhost:8006/health | Sin autenticación (local) | Endpoint operativo de salud (`/health`) y métricas Prometheus (`/metrics`) del motor de minería de procesos educativos sobre PM4Py. | Confirmar disponibilidad de `C6` y consultar trazas, asignaciones procesadas, grafos DFG persistidos y latencia `ingested_to_graph`. |
| **C7 Query API (`dsm-query-api`)** | http://localhost:8007/docs | JWT (`docente / docente123` o `admin / admin123`) | API REST y WebSocket sobre el estado materializado en MongoDB, Neo4j y PostgreSQL. | Consultar perfiles, evolución Sankey, grafos DFG y métricas experimentales. |
| **C8 Dashboard Docente (`dsm-dashboard`)** | http://localhost:8088 | `docente / docente123` | Interfaz web de interpretabilidad (Vue 3 + PrimeVue + ECharts + Cytoscape.js). | Visualizar transiciones entre clústeres, grafos DFG y ficha explicable del estudiante en tiempo real. |
| **Prometheus (`C10`)** | http://localhost:9091 | Sin autenticación (local) | Recolector de métricas de desempeño de los servicios `C2`, `C4`, `C5`, `C6` y `C7`. | Inspeccionar series temporales de throughput y latencias por etapa. |
| **Grafana (`C10`)** | http://localhost:3001 | `admin / admin` | Tablero de observabilidad preaprovisionado (`DSM LMS — Desempeño y Latencias`). | Monitorear p50/p95/p99 `ingested_at -> persistencia` y throughput bajo carga. |
| **Redpanda Console (Visor de Kafka)** | http://localhost:8080 | Sin autenticación (local) | Panel visual conectado al broker Apache Kafka para explorar topics, particiones y mensajes almacenados. | Inspeccionar en vivo el registro inmutable `lms.events.canonical` (donde cada evento ya figura como $E = \langle u, a, r, t, M \rangle$ con retención infinita) y auditar los eventos rechazados en `lms.events.dlq`. |
| **Neo4j Browser (Base de datos de grafos)** | http://localhost:7474 | Usuario: `neo4j`<br>Contraseña: `dsm_neo4j_pass` | Consola gráfica oficial del motor Neo4j Community para consultar nodos, relaciones e índices mediante Cypher. | Verificar las restricciones e índices topológicos (`:Activity`, `:Boundary`, `:DFG`) y, a partir de la Fase 5, visualizar de forma interactiva los grafos de rutas de aprendizaje (DFG) por estudiante y por clúster. |
