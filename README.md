# Dynamic Student Modeling LMS

Plataforma orientada a eventos (arquitectura tipo Kappa) para automatizar el modelado dinámico e interpretable de patrones de interacción estudiantil en Sistemas de Gestión de Aprendizaje (LMS), combinando minería de flujos de datos (*Data Stream Mining*) y minería de procesos educativos (*Educational Process Mining*).

## Documentación del proyecto

- **Arquitectura y decisiones técnicas (base Capítulo IV):** [docs/arquitectura.md](./docs/arquitectura.md)
- **Hoja de ruta y criterios de paso:** [docs/Fases_De_Implementacion.md](./docs/Fases_De_Implementacion.md)
- **Explicación detallada por fases:** [docs/fases/README.md](./docs/fases/README.md)
- **Tesis (copia de referencia):** [docs/tesis/main.md](./docs/tesis/main.md)

---

## Estado actual: Fase 1 completada — Infraestructura base y puerta de ingesta (`C2`)

En la **Fase 1** se implementó y verificó la Capa I de la arquitectura Kappa junto con la inicialización de la persistencia de estado operativo:

- **Workspace Python 3.12 (`uv`):** librería compartida `libs/dsm_common` (esquema canónico $E = \langle u, a, r, t, M \rangle$, seudonimización determinista `HMAC-SHA256`, cargador de YAML en `config/`, productores Kafka y métricas Prometheus) y esqueleto `libs/dsm_core`.
- **Puerta de ingesta `C2 Ingestion Gateway` (`services/ingestion-gateway`):** API asíncrona en FastAPI (`POST /api/v1/events` y `/api/v1/events/batch`) que valida, seudonimiza `u`, agrega `ingested_at` y publica en `lms.events.canonical` (o enruta errores a `lms.events.dlq`).
- **Infraestructura en Docker Compose (`deploy/docker-compose.yml`):** Apache Kafka 3.8.0 (modo KRaft sin Zookeeper) con creación automática de topics, Redpanda Console, PostgreSQL 16 (7 tablas relacionales), MongoDB 7.0 Community (colecciones e índices) y Neo4j 5.23 Community (restricciones e índices de grafos).

Para una explicación detallada orientada a demostración y revisión de tesis, consulta [docs/fases/Fase_1_Infraestructura_e_Ingesta.md](./docs/fases/Fase_1_Infraestructura_e_Ingesta.md).

---

## Cómo ejecutar el proyecto

### 1. Levantar los contenedores (Docker Compose)

Asegúrate de tener **Docker Desktop** abierto y ejecuta desde la raíz del repositorio:

```powershell
# Construir el gateway y levantar toda la infraestructura en segundo plano
docker compose -f deploy/docker-compose.yml up -d --build

# Verificar que todos los contenedores estén activos y saludables (healthy)
docker compose -f deploy/docker-compose.yml ps
```

Si es la primera vez que arrancas Neo4j o necesitas asegurar sus restricciones Cypher iniciales:

```powershell
docker exec dsm-neo4j cypher-shell -u neo4j -p dsm_neo4j_pass -f /init/constraints.cypher
```

Para detener los contenedores (conservando los volúmenes de datos):

```powershell
docker compose -f deploy/docker-compose.yml down
```

### 2. Entorno local de desarrollo, pruebas y linter (Python 3.12 + `uv`)

```powershell
# Instalar y sincronizar todas las dependencias del workspace
uv sync --all-packages

# Ejecutar pruebas unitarias y linter usando los binarios directos del entorno virtual
.\.venv\Scripts\pytest.exe -v
.\.venv\Scripts\ruff.exe check .
```

---

## Interfaces gráficas web disponibles

Con los contenedores corriendo, puedes acceder desde tu navegador a las siguientes herramientas visuales:

| Servicio | URL | Credenciales | Qué hace | Para qué sirve |
| :--- | :--- | :--- | :--- | :--- |
| **Swagger / OpenAPI (`C2 Ingestion Gateway`)** | http://localhost:8000/docs | Sin autenticación (local) | Documentación web interactiva generada por FastAPI con todos los endpoints del Gateway (`/api/v1/events`, `/api/v1/events/batch`, `/health`, `/metrics`). | Probar el envío de eventos JSON reales o malformados desde el navegador, observar el código de respuesta (`202` o `422`) y verificar la seudonimización inmediata de `u`. |
| **Redpanda Console (Visor de Kafka)** | http://localhost:8080 | Sin autenticación (local) | Panel visual conectado al broker Apache Kafka para explorar topics, particiones y mensajes almacenados. | Inspeccionar en vivo el registro inmutable `lms.events.canonical` (donde cada evento ya figura como $E = \langle u, a, r, t, M \rangle$ con retención infinita) y auditar los eventos rechazados en `lms.events.dlq`. |
| **Neo4j Browser (Base de datos de grafos)** | http://localhost:7474 | Usuario: `neo4j`<br>Contraseña: `dsm_neo4j_pass` | Consola gráfica oficial del motor Neo4j Community para consultar nodos, relaciones e índices mediante Cypher. | Verificar las restricciones e índices topológicos (`:Activity`, `:Boundary`, `:DFG`) y, a partir de la Fase 5, visualizar de forma interactiva los grafos de rutas de aprendizaje (DFG) por estudiante y por clúster. |
