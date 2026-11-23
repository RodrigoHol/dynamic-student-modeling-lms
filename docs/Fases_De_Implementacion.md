# Fases de Implementación y Ruta de Trabajo

> **Propósito:** Definir la hoja de ruta incremental del proyecto (Fases 0 a 7), detallando los objetivos técnicos, entregables y criterios objetivos de verificación (*Definition of Done*) necesarios para avanzar entre etapas. Cada fase construye sobre la anterior y aporta evidencia directa para los Capítulos IV (Implementación) y V (Validación y Resultados) de la tesis ([tesis/main.md](./tesis/main.md)).

---

## Tabla resumen de fases

| Fase | Nombre | Componentes principales | RF cubiertos | Aporte a la tesis |
| :--- | :--- | :--- | :--- | :--- |
| **Fase 0** *(Completada)* | Diseño arquitectónico y estructura | [arquitectura.md](./arquitectura.md), esqueleto de carpetas | Base transversal | Base teórica-técnica del Cap. IV (ADR-00 a ADR-15) |
| **Fase 1** | Cimientos, infraestructura y puerta de ingesta | Workspace `uv`, `dsm_common`, Docker Compose, **C2 Gateway** | RF-01 a RF-04 | Infraestructura Kappa y registro canónico inmutable |
| **Fase 2** | Simulador de históricos y datos sintéticos | **C3 Replayer**, `SourceParser`, generador sintético | RF-05 | Diseño del entorno de simulación experimental |
| **Fase 3** | Preprocesamiento, HLE y ventanas múltiples | `dsm_core` (HLE/ventanas/features), **C4 Preprocessor** | RF-06 a RF-10 | Consolidación del dataset y ventanas disjuntas por `t` |
| **Fase 4** | Motor de clustering evolutivo en flujo | `dsm_core.clustering`, **C5 Clustering Engine** → MongoDB | RF-11, RF-12, RF-14 | Modelado dinámico de perfiles y transiciones |
| **Fase 5** | Motor de minería de procesos educativos | `dsm_core.process_mining`, **C6 Process Mining Engine** → Neo4j | RF-13, RF-14 | Descubrimiento topológico DFG individual y aditivo |
| **Fase 6** | API de consulta y dashboard de interpretabilidad | **C7 Query API**, **C8 Dashboard** (Vue 3 + PrimeVue) | RF-15 a RF-17 | Capa de mediación e interpretabilidad docente |
| **Fase 7** | Validación experimental, línea base batch y métricas | **C9 Experiment Runner**, **C10 Observabilidad** | RF-18 a RF-21 | Tablas, gráficas y respuestas a las 3 preguntas (Cap. V) |

---

## Detalle de cada fase, entregables y criterio de paso (*Definition of Done*)

### Fase 0 — Diseño arquitectónico y estructura del repositorio *(Completada)*
- **En qué consiste:**
  - Formalizar las decisiones técnicas y arquitectónicas en [arquitectura.md](./arquitectura.md) (ADR-00 a ADR-15), alineadas con el diseño Kappa del Capítulo III.
  - Organizar la documentación (`docs/tesis/`, `docs/diagrams/`) y crear el esqueleto inicial de carpetas (`config/`, `libs/`, `services/`, `frontend/`, `experiments/`, `deploy/`, `data/`, `scripts/`, `tests/`).
- **Producto entregable:** Documento maestro [arquitectura.md](./arquitectura.md) y estructura base del repositorio versionada en Git.

---

### Fase 1 — Cimientos, infraestructura y puerta de ingesta (`C2`)
- **En qué consiste:**
  - Eliminar el prototipo exploratorio viejo en `src/`.
  - Inicializar el workspace de `uv` (`pyproject.toml` raíz, `uv.lock`, `ruff`, `pytest`).
  - Construir `libs/dsm_common`: modelos Pydantic (`CanonicalEvent`), seudonimización `HMAC-SHA256`, cargador de YAML y cliente productor de Kafka.
  - Configurar [docker-compose.yml](../deploy/docker-compose.yml) con Apache Kafka 3.x (modo KRaft), Redpanda Console (visor web de topics), MongoDB Community, Neo4j Community y PostgreSQL (con su script SQL inicial de tablas).
  - Implementar el servicio **C2 Ingestion Gateway** en FastAPI (`POST /api/v1/events`).
- **Producto entregable:**
  - Clúster local levantado con un único comando, esquema inicializado en las 3 bases de datos y `C2` recibiendo eventos por HTTP.
- **Criterio para pasar a la Fase 2 (Verificación):**
  1. `docker compose up -d` levanta todos los contenedores en estado `healthy`.
  2. Enviar un evento JSON válido con `curl` a `C2` devuelve `HTTP 202`, y en Redpanda Console se observa el evento en el topic `lms.events.canonical` con `u` seudonimizado e `ingested_at` asignado.
  3. Enviar un evento malformado lo enruta a `lms.events.dlq` sin detener el servicio.
  4. `uv run pytest` pasa los tests unitarios de `dsm_common`.

---

### Fase 2 — Replayer / Simulador e inyección de datos (`C3`)
- **En qué consiste:**
  - Definir la interfaz `SourceParser` en **C3 Replayer**.
  - Crear un generador de datos sintéticos realistas con formato compatible con Moodle (por ejemplo, 50 estudiantes a lo largo de 8 semanas con distintos perfiles de participación) en `data/samples/` y `data/synthetic/`.
  - Implementar los parsers para exportación CSV de Moodle y tabla `mdl_logstore_standard_log` (listos para ajustarse al recibir el histórico real del curso).
  - Programar el despachador asíncrono con control de velocidad (`1x`, `10x`, `100x`, `max`) y registro de `run_id` en PostgreSQL.
- **Producto entregable:**
  - CLI ejecutable (`dsm-replayer`) capaz de reproducir un curso completo hacia `C2` respetando el orden cronológico original `t`.
- **Criterio para pasar a la Fase 3 (Verificación):**
  1. Ejecutar el Replayer en modo `max` con un dataset sintético de 5,000 eventos registra la corrida en la tabla `runs` de PostgreSQL.
  2. Los 5,000 eventos aparecen en orden cronológico por estudiante dentro de `lms.events.canonical` con cero pérdidas.

---

### Fase 3 — Preprocesamiento, abstracción HLE y ventanas múltiples (`C4`)
- **En qué consiste:**
  - Crear los archivos provisionales `config/hle_catalog.yaml`, `config/features.yaml` y `config/windows.yaml`.
  - Implementar en `libs/dsm_core` (100% Python puro, sin Kafka ni bases de datos): filtro de ruido, `HLEMapper`, particionador de ventanas disjuntas por `t` (`daily`, `weekly`, `monthly`, `course`) y extractores de características (`FeatureExtractor`).
  - Construir **C4 Preprocessor** con Quix Streams consumiendo `lms.events.canonical` y emitiendo al cierre de cada ventana hacia `analytics.features` y `analytics.traces`.
- **Producto entregable:**
  - Tubería de transformación semántica y agregación por ventana operando en paralelo sobre las 4 granularidades.
- **Criterio para pasar a la Fase 4 (Verificación):**
  1. **Prueba de determinismo:** correr el mismo dataset con el Replayer a velocidad `10x` y luego a velocidad `max` produce **exactamente** los mismos vectores en `analytics.features` y las mismas trazas en `analytics.traces` para cada `(granularity, window_id)`.
  2. Unit tests en `libs/dsm_core/tests` validan el cálculo de características y el cierre de ventanas con eventos tardíos.

---

### Fase 4 — Motor de clustering evolutivo (`C5`)
- **En qué consiste:**
  - Implementar en `libs/dsm_core/clustering` la interfaz `ClusteringAlgorithm`, el registro de algoritmos y los adaptadores `DenStreamAdapter` y `DBSTREAMAdapter` sobre `River`, más el cálculo de explicabilidad (`z_score` de características frente al centroide) y el detector de transiciones entre ventanas.
  - Construir **C5 Clustering Engine**: consume `analytics.features`, mantiene un modelo independiente por `(run_id, granularity)`, guarda perfiles y snapshots de centroides en **MongoDB** y publica la asignación `(u -> cluster_id)` en `analytics.assignments`.
- **Producto entregable:**
  - Perfiles dinámicos evolucionando ventana a ventana en MongoDB y emitiendo asignaciones de clúster en tiempo real.
- **Criterio para pasar a la Fase 5 (Verificación):**
  1. Tras reproducir el curso sintético, MongoDB contiene los documentos en `student_profiles` para las 4 granularidades, con `cluster_id`, `previous_cluster_id`, `transition_detected` y `top_contributing_features`.
  2. Cambiar `algorithm: denstream` a `algorithm: dbstream` en `config/clustering.yaml` y relanzar funciona sin modificar código fuente.

---

### Fase 5 — Motor de minería de procesos educativos (`C6`)
- **En qué consiste:**
  - Implementar en `libs/dsm_core/process_mining` la construcción del DFG individual con `PM4Py` y la operación de fusión aditiva (`merge_dfgs`) de frecuencias y tiempos de transición.
  - Construir **C6 Process Mining Engine**: consume `analytics.traces` (calcula el DFG individual en paralelo a `C5`) y, al recibir `analytics.assignments`, consolida el DFG de cada clúster y persiste nodos `:Activity` y aristas `:DFG` en **Neo4j**.
- **Producto entregable:**
  - Modelos topológicos de rutas de aprendizaje por estudiante y por clúster almacenados en Neo4j para cada ventana y granularidad.
- **Criterio para pasar a la Fase 6 (Verificación):**
  1. En el navegador de Neo4j (`localhost:7474`), una consulta Cypher filtrada por `(run_id, granularity, window_id, cluster_id)` devuelve el grafo dirigido con frecuencias (`freq`) y tiempos medios (`mean_time_sec`) consistentes con la suma de las trazas individuales de los miembros de ese clúster.

---

### Fase 6 — API de consulta y Dashboard Docente (`C7` + `C8`)
- **En qué consiste:**
  - Implementar **C7 Query API** en FastAPI: endpoints REST de lectura hacia MongoDB, Neo4j y PostgreSQL (cursos, corridas, evolución de clústeres, DFG por clúster/estudiante, ficha explicable del alumno), WebSocket de notificación de cierre de ventana y autenticación JWT básica.
  - Construir **C8 Dashboard** en **Vue 3 + TypeScript + Vite + Pinia + Vue Router + PrimeVue**:
    - Selector global de curso, corrida (`run_id`), granularidad (`daily`/`weekly`/`monthly`/`course`) y ventana.
    - Vista de evolución de clústeres con diagrama Sankey/aluvial y distribución (`vue-echarts`).
    - Visor interactivo del grafo de procesos DFG (`Cytoscape.js` + `cytoscape-dagre`) donde el grosor de arista refleja frecuencia o tiempo.
    - Ficha del estudiante: historial de transiciones, variables que justifican su clúster actual y comparación entre su ruta individual y la ruta de su clúster.
- **Producto entregable:**
  - Plataforma completa de extremo a extremo operable desde el navegador web.
- **Criterio para pasar a la Fase 7 (Verificación):**
  1. Al correr el Replayer en vivo, el dashboard actualiza las ventanas automáticamente vía WebSocket sin recargar la página.
  2. Un usuario docente puede seleccionar un clúster en una ventana semanal, inspeccionar su grafo DFG y abrir el detalle de un estudiante que cambió de clúster viendo explícitamente qué variables y qué secuencia de actividades explican ese cambio.

---

### Fase 7 — Validación experimental, línea base batch y observabilidad (`C9` + `C10`)
- **En qué consiste:**
  - Configurar **C10 Observabilidad** (Prometheus + Grafana) recolectando latencias `ingested_at → persistencia` (p50, p95, p99) y throughput (eventos/s).
  - Implementar **C9 Experiment Runner** (`experiments/`):
    - Ejecución automatizada de la **línea base batch** (`K-Means` en `scikit-learn` + descubrimiento global en `PM4Py`) usando exactamente los mismos módulos de `dsm_core`.
    - Cálculo de métricas por corrida y ventana: Coeficiente de Silueta, estabilidad/concordancia **ARI** (entre corridas repetidas y entre *stream* vs. *batch*) y **Fitness / Precision** de los modelos de proceso.
    - Exportación de tablas en CSV/LaTeX y figuras listas para insertar en el Capítulo V de la tesis.
- **Producto entregable:**
  - Batería experimental ejecutada sobre el histórico real entregado por la dirección de tesis y reportes cuantitativos reproducibles.
- **Criterio de cierre del proyecto:**
  1. Se cuenta con las métricas completas en `experiment_metrics` (PostgreSQL) y archivos exportados que responden con evidencia numérica las 3 preguntas de investigación (latencia bajo distintos factores de carga, interpretabilidad estructural y comparativa *stream* vs. *batch*).
