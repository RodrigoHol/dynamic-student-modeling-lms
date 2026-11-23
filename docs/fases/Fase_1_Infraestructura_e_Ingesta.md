# Fase 1 — Cimientos, Infraestructura Kappa y Puerta de Ingesta (`C2`)

> **Propósito:** Explicar de forma clara qué se construyó en la Fase 1, cómo se corresponde directamente con el diseño conceptual de la tesis ([tesis/main.md](../tesis/main.md), Capítulo III) y cómo demostrar su funcionamiento paso a paso ante la dirección de tesis mediante las interfaces web del sistema.

---

## 1. Visión general: ¿Qué logramos en la Fase 1?

En términos de la arquitectura propuesta en la tesis ([arquitectura_general_kappa.jpg](../diagrams/arquitectura_general_kappa.jpg)), la Fase 1 materializó por completo la **Capa I (Telemetría e Ingesta Continua)** —incluyendo el **Registro Continuo Inmutable**— y dejó preparados los almacenes de datos vacíos de la **Capa III (Persistencia de Estado Operativo)**.

En el Capítulo III de la tesis (Secciones III.2.2 y III.3.1), cada interacción de un estudiante en el LMS sigue cuatro principios:
1. Se recibe de forma **asíncrona y no bloqueante**, sin frenar la plataforma educativa.
2. Se protege la identidad del alumno antes de persistir el evento.
3. Se transforma en la **tupla canónica** $E = \langle u, a, r, t, M \rangle$ (usuario seudonimizado, acción, recurso, estampa temporal original y metadatos).
4. Se inserta en un **registro continuo inmutable de solo adición (*append-only log*)**, donde la historia nunca se borra ni altera.

---

## 2. Los 4 bloques construidos en esta fase

### Bloque 1: La librería base `dsm_common` ([libs/dsm_common](../../libs/dsm_common))
Contiene las piezas transversales que todos los servicios del sistema comparten para garantizar un mismo contrato de datos:
- **Contrato del evento canónico ([events.py](../../libs/dsm_common/src/dsm_common/schemas/events.py)):** Define en Pydantic `RawEventInput`, `CanonicalEvent` ($E = \langle u, a, r, t, M \rangle$) y `DlqEvent`. Si un evento entrante viola la estructura o tipos esperados, se detecta automáticamente.
- **Seudonimización determinista ([pseudonymizer.py](../../libs/dsm_common/src/dsm_common/privacy/pseudonymizer.py)):** Convierte el identificador real del estudiante (por ejemplo `"matricula_202301"`) mediante criptografía `HMAC-SHA256` con clave secreta en un seudónimo fijo como `"usr_d79ed09d465e52ac"`. Un mismo estudiante siempre produce el mismo seudónimo (permitiendo seguir su evolución entre ventanas temporales), pero nadie puede revertir el código para conocer su identidad real.
- **Configuración y cargador YAML ([settings.py](../../libs/dsm_common/src/dsm_common/config/settings.py), [loader.py](../../libs/dsm_common/src/dsm_common/config/loader.py)):** Lee y valida los cinco archivos de configuración analítica alojados en [config/](../../config) (catálogo HLE provisional, extractores de características, ventanas disjuntas, algoritmo de clustering y minería de procesos).
- **Mensajería y métricas ([topics.py](../../libs/dsm_common/src/dsm_common/messaging/topics.py), [producer.py](../../libs/dsm_common/src/dsm_common/messaging/producer.py), [metrics.py](../../libs/dsm_common/src/dsm_common/observability/metrics.py)):** Centraliza los nombres de topics de Kafka, el productor asíncrono y los contadores Prometheus de ingesta.

### Bloque 2: La puerta de entrada `C2 Ingestion Gateway` ([services/ingestion-gateway](../../services/ingestion-gateway))
Es un microservicio web construido con **FastAPI** que actúa como punto único de entrada:
- Recibe peticiones HTTP (`POST /api/v1/events` y `POST /api/v1/events/batch`).
- Aplica la seudonimización sobre `raw_user_id` para obtener `u`.
- Estampa el reloj de recepción del sistema (`ingested_at`) manteniendo intacto el reloj histórico del evento (`t`), clave para separar el cálculo determinista de ventanas de la medición real de latencia (ADR-12).
- Publica los eventos válidos en el topic inmutable `lms.events.canonical` usando `u` como clave de partición (garantizando orden cronológico estricto por estudiante) y responde `HTTP 202 Accepted`.
- Si llega un evento malformado o incompleto, en lugar de caer o perder el registro, lo deriva a la cola de cuarentena **DLQ (*Dead Letter Queue*)** `lms.events.dlq` respondiendo `HTTP 422`.

### Bloque 3: El Registro Continuo Inmutable en Apache Kafka ([docker-compose.yml](../../deploy/docker-compose.yml))
Se desplegó **Apache Kafka 3.8.0 en modo KRaft** (sin Zookeeper) con inicialización automática de los cinco topics definidos en la arquitectura ([create-topics.sh](../../deploy/kafka/create-topics.sh)):
- `lms.events.canonical`: configurado con **retención infinita (`retention.ms = -1`)**. Materializa literalmente el cilindro *«Registro Continuo Inmutable (Log de sólo adición / Append-Only)»* de la Figura III.1 de la tesis.
- `lms.events.dlq`: resguarda eventos inválidos para auditoría.
- `analytics.features`, `analytics.traces` y `analytics.assignments`: canales preparados para las Fases 3, 4 y 5.

### Bloque 4: Las 3 bases de datos de estado operativo (Capa III)
Aunque su llenado ocurrirá en las Fases 2 a 7, los tres motores quedaron en ejecución y con su estructura inicializada:
- **PostgreSQL 16** ([01_schema.sql](../../deploy/postgres/init/01_schema.sql)): 7 tablas relacionales (`courses`, `resources`, `users_roles`, `hle_catalog_versions`, `runs`, `run_configs`, `experiment_metrics`) para metadatos institucionales y reproducibilidad experimental por `run_id`.
- **MongoDB 7.0 Community** ([01_indexes.js](../../deploy/mongo/init/01_indexes.js)): colecciones `student_profiles` y `cluster_snapshots` con índices únicos compuestos sobre `{run_id, granularity, window_id, student_id}` para los perfiles dinámicos.
- **Neo4j 5.23 Community** ([constraints.cypher](../../deploy/neo4j/init/constraints.cypher)): restricciones de unicidad sobre `:Activity` y `:Boundary` e índice sobre las relaciones `:DFG` para las rutas de aprendizaje.

---

## 3. Guía de las interfaces gráficas web (Cómo demostrarlo)

Una vez levantados los contenedores, existen **tres interfaces web** accesibles desde el navegador que permiten demostrar el funcionamiento sin usar comandos de terminal:

### A. Swagger / OpenAPI (`C2 Ingestion Gateway`) — http://localhost:8000/docs
- **Qué es:** Documentación web interactiva generada automáticamente por FastAPI a partir de los esquemas Pydantic del Gateway.
- **Qué hace:** Muestra los endpoints disponibles (`POST /api/v1/events`, `POST /api/v1/events/batch`, `GET /health`, `GET /metrics`), su formato JSON esperado y permite ejecutar peticiones reales desde el navegador.
- **Para qué sirve en la demostración:** Permite enviar un evento de prueba frente al director de tesis y observar en vivo cómo el Gateway acepta el evento (`HTTP 202`), seudonimiza al estudiante y agrega `ingested_at`.

**Ejemplo rápido para probar en Swagger:**
1. Abrir http://localhost:8000/docs y desplegar `POST /api/v1/events`.
2. Pulsar **"Try it out"**, pegar el siguiente JSON y pulsar **"Execute"**:
   ```json
   {
     "raw_user_id": "alu_demo_01",
     "action": "submitted",
     "resource": {
       "resource_id": "assign_03",
       "resource_type": "assign",
       "name": "Tarea 3: Arboles de decision"
     },
     "timestamp": "2024-09-18T14:23:11Z",
     "metadata": {
       "course_id": "course_105",
       "source_format": "moodle_csv",
       "component": "mod_assign"
     }
   }
   ```
3. Verificar la respuesta `202` con `"u": "usr_..."` (distinto de `"alu_demo_01"`).

### B. Redpanda Console (Visor de Apache Kafka) — http://localhost:8080
- **Qué es:** Interfaz web conectada al broker Kafka para inspeccionar topics, particiones y mensajes almacenados.
- **Qué hace:** Permite explorar visualmente el contenido de los topics en tiempo real sin usar herramientas de línea de comandos de Kafka.
- **Para qué sirve en la demostración:** Al hacer clic en **Topics → `lms.events.canonical` → Messages**, se comprueba en vivo que el evento enviado desde Swagger quedó almacenado en formato canónico $E = \langle u, a, r, t, M \rangle$ con clave de partición igual al seudónimo `u` y retención infinita. De igual forma, en `lms.events.dlq` se muestran los eventos rechazados por error de validación.

### C. Neo4j Browser (Base de datos de grafos) — http://localhost:7474
- **Qué es:** Consola visual oficial del motor de grafos Neo4j Community.
- **Qué hace:** Permite ejecutar consultas Cypher e inspeccionar visualmente los nodos, relaciones, restricciones e índices del almacén topológico.
- **Credenciales locales:** Usuario `neo4j`, contraseña `dsm_neo4j_pass`.
- **Para qué sirve en el proyecto:** En esta fase permite comprobar que el esquema topológico (`:Activity`, `:Boundary`, `:DFG`) ya está preparado (`SHOW CONSTRAINTS; SHOW INDEXES;`). A partir de la **Fase 5**, mostrará gráficamente los *Directly-Follows Graphs* (DFG) de las rutas de aprendizaje por estudiante y por clúster.

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 1 materializamos la Capa I de la arquitectura Kappa: desplegamos en contenedores Docker el registro continuo inmutable en Apache Kafka (modo KRaft), inicializamos los esquemas de las tres bases de datos del almacén híbrido de estado operativo (PostgreSQL, MongoDB y Neo4j) e implementamos en Python/FastAPI el Gateway de Ingesta (`C2`), el cual valida, seudonimiza mediante HMAC-SHA256 y publica cada interacción estudiantil en el formato canónico $E = \langle u, a, r, t, M \rangle$, derivando cualquier payload inválido hacia una cola de auditoría (DLQ).»*
