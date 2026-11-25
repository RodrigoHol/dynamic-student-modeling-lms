# Dynamic Student Modeling LMS

Plataforma orientada a eventos (arquitectura tipo Kappa) para automatizar el modelado dinámico e interpretable de patrones de interacción estudiantil en Sistemas de Gestión de Aprendizaje (LMS), combinando minería de flujos de datos (*Data Stream Mining*) y minería de procesos educativos (*Educational Process Mining*).

## Documentación del proyecto

- **Arquitectura y decisiones técnicas (base Capítulo IV):** [docs/arquitectura.md](./docs/arquitectura.md)
- **Hoja de ruta y criterios de paso:** [docs/Fases_De_Implementacion.md](./docs/Fases_De_Implementacion.md)
- **Explicación detallada por fases:** [docs/fases/README.md](./docs/fases/README.md)
- **Tesis (copia de referencia):** [docs/tesis/main.md](./docs/tesis/main.md)

---

## Estado actual: Fases 1 y 2 completadas (`C2` + `C3`)

### Fase 1 — Infraestructura base y puerta de ingesta (`C2`)
- **Workspace Python 3.12 (`uv`):** librería compartida `libs/dsm_common` (esquema canónico $E = \langle u, a, r, t, M \rangle$, seudonimización determinista `HMAC-SHA256`, cargador de YAML en `config/`, productores Kafka, métricas Prometheus y repositorio de corridas en PostgreSQL) y esqueleto `libs/dsm_core`.
- **Puerta de ingesta `C2 Ingestion Gateway` (`services/ingestion-gateway`):** API asíncrona en FastAPI (`POST /api/v1/events` y `/api/v1/events/batch`) que valida, seudonimiza `u`, agrega `ingested_at` y publica en `lms.events.canonical` (o enruta errores a `lms.events.dlq`).
- **Infraestructura en Docker Compose (`deploy/docker-compose.yml`):** Apache Kafka 3.8.0 (modo KRaft sin Zookeeper) con creación automática de topics, Redpanda Console, PostgreSQL 16 (7 tablas relacionales), MongoDB 7.0 Community (colecciones e índices) y Neo4j 5.23 Community (restricciones e índices de grafos).
- Guía de demostración: [docs/fases/Fase_1_Infraestructura_e_Ingesta.md](./docs/fases/Fase_1_Infraestructura_e_Ingesta.md).

### Fase 2 — Replayer / Simulador e inyección de datos (`C3`)
- **Parsers enchufables `SourceParser` (`services/replayer`):** adaptadores con autodetección de formato y ordenamiento cronológico estricto por `t` para exportaciones CSV de Moodle (`moodle_csv`), volcados de `mdl_logstore_standard_log` (`moodle_db`) y JSONL sintético (`synthetic_jsonl`).
- **Generador sintético realista:** genera cursos deterministas con 5 arquetipos conductuales alineados con [config/hle_catalog.yaml](./config/hle_catalog.yaml) y muestras versionadas en [data/samples](./data/samples).
- **Despachador asíncrono y CLI (`dsm-replayer`):** controla la velocidad de emisión (`1x`, `10x`, `100x`, `max`) hacia `C2` y registra la corrida junto con su snapshot YAML en PostgreSQL (`runs`, `hle_catalog_versions` y `run_configs`).
- Guía de demostración: [docs/fases/Fase_2_Replayer_y_Datos_Sinteticos.md](./docs/fases/Fase_2_Replayer_y_Datos_Sinteticos.md).

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
| `4` | Apagar stack | `docker compose down` (detiene contenedores conservando los datos). |
| `a` | Demostración completa | Ejecuta en orden las etapas `1 → 2 → 3`. |
| `s` | Estado e interfaces | Muestra `docker compose ps` y las URLs locales para inspección visual. |

También puedes lanzar cualquier etapa directamente sin menú interactivo usando `--step`:

```powershell
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 1
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 2
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 3
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
| **Swagger / OpenAPI (`C2 Ingestion Gateway`)** | http://localhost:8000/docs | Sin autenticación (local) | Documentación web interactiva generada por FastAPI con todos los endpoints del Gateway (`/api/v1/events`, `/api/v1/events/batch`, `/health`, `/metrics`). | Probar el envío de eventos JSON reales o malformados desde el navegador, observar el código de respuesta (`202` o `422`) y verificar la seudonimización inmediata de `u`. |
| **Redpanda Console (Visor de Kafka)** | http://localhost:8080 | Sin autenticación (local) | Panel visual conectado al broker Apache Kafka para explorar topics, particiones y mensajes almacenados. | Inspeccionar en vivo el registro inmutable `lms.events.canonical` (donde cada evento ya figura como $E = \langle u, a, r, t, M \rangle$ con retención infinita) y auditar los eventos rechazados en `lms.events.dlq`. |
| **Neo4j Browser (Base de datos de grafos)** | http://localhost:7474 | Usuario: `neo4j`<br>Contraseña: `dsm_neo4j_pass` | Consola gráfica oficial del motor Neo4j Community para consultar nodos, relaciones e índices mediante Cypher. | Verificar las restricciones e índices topológicos (`:Activity`, `:Boundary`, `:DFG`) y, a partir de la Fase 5, visualizar de forma interactiva los grafos de rutas de aprendizaje (DFG) por estudiante y por clúster. |
