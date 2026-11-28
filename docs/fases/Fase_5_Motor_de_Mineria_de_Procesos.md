# Fase 5 — Motor de Minería de Procesos Educativos (`dsm_core.process_mining` + `C6`)

> **Propósito:** Explicar qué se construyó en la Fase 5, cómo se descubren y fusionan aditivamente grafos de flujo directo (**DFG**) con **PM4Py** (**ADR-08**, **ADR-10**, **ADR-13**) en paralelo con el clustering evolutivo, cómo se persiste la topología en **Neo4j Community** (**ADR-03**) y cómo validar el servicio continuo `C6 Process Mining Engine`.

---

## 1. Visión general: ¿Qué logramos en la Fase 5?

Con las Fases 3 y 4 en marcha, `C4 Preprocessor` emite trazas secuenciales de HLE hacia `analytics.traces` y `C5 Clustering Engine` emite asignaciones `(u -> cluster_id)` hacia `analytics.assignments`. En la **Fase 5** completamos la segunda rama de la analítica dual concurrente:

1. **Dominio analítico puro en `libs/dsm_core` (`ADR-10`):** sin dependencias de Kafka ni Neo4j, se implementaron el contrato `ProcessDiscovery`, la implementación `PM4PyDFGDiscovery` sobre `PM4Py` (`discover_dfg` y `discover_performance_dfg`), las operaciones algebraicas aditivas (`add_dfg_in_place` y `subtract_dfg_in_place`), el registro declarativo (`PROCESS_DISCOVERY_REGISTRY`) y el orquestador concurrente `ProcessMiningEngine`.
2. **Contratos y repositorio Neo4j en `libs/dsm_common`:** se añadieron los modelos `DfgNode`, `DfgEdge` y `DfgGraphDocument` junto con `Neo4jGraphRepository` (driver asíncrono oficial de Neo4j) e `InMemoryGraphRepository` para pruebas rápidas sin contenedores.
3. **Servicio continuo `C6 Process Mining Engine` (`services/process-mining`):** consume concurrentemente `analytics.traces` y `analytics.assignments`, construye de inmediato el DFG individual de cada estudiante, consolida aditivamente el DFG de cada clúster al recibir su asignación (sin importar el orden de llegada), persiste nodos `:Activity` / `:Boundary` y relaciones `:DFG` en Neo4j y expone `/health` y `/metrics` en el puerto `8006`.

---

## 2. Los 4 bloques construidos en esta fase

### Bloque 1: Esquemas DFG y repositorio Neo4j ([dsm_common](../../libs/dsm_common/src/dsm_common))
- **`schemas/analytics.py`:** incorpora `DfgNode` (`activity` o `boundary`), `DfgEdge` (`freq`, `total_time_sec`, `mean_time_sec`, `trace_support_count`, `support`) y `DfgGraphDocument` (`scope` = `student` | `cluster`, `scope_id`, `trace_count`, `ingested_to_graph_ms`), alineados con la Sección 6.4 de [arquitectura.md](../arquitectura.md).
- **`storage/neo4j.py`:** define `GraphRepository`, `Neo4jGraphRepository` (transacciones atómicas `execute_write` con `UNWIND` sobre `:Activity`, `:Boundary` y `:DFG`, asegurando las restricciones e índices de [constraints.cypher](../../deploy/neo4j/init/constraints.cypher)) e `InMemoryGraphRepository`.

### Bloque 2: Descubrimiento DFG y aditividad en `dsm_core.process_mining` ([process_mining/](../../libs/dsm_core/src/dsm_core/process_mining))
- **`ProcessDiscovery`** ([base.py](../../libs/dsm_core/src/dsm_core/process_mining/base.py)): interfaz común con `build_student_dfg(trace)` y `merge_dfgs(dfgs)`.
- **`PM4PyDFGDiscovery`** ([pm4py_dfg.py](../../libs/dsm_core/src/dsm_core/process_mining/pm4py_dfg.py)): ordena determinísticamente la traza por `(t, event_id)`, invoca `pm4py.discover_dfg` y `pm4py.discover_performance_dfg` para calcular frecuencias y duraciones acumuladas entre transiciones consecutivas, y añade nodos frontera `:Boundary` (`START` y `END`) cuando `include_boundaries: true` en [config/process_mining.yaml](../../config/process_mining.yaml).
- **`models.py`:** implementa `add_dfg_in_place` y `subtract_dfg_in_place` manteniendo exactitud algebraica en `freq`, `total_time_sec`, `mean_time_sec = total_time_sec / freq` y `support = trace_support_count / trace_count` (con soporte por traza acotado a `1` por estudiante aunque la arista se repita dentro de su misma traza).

### Bloque 3: Orquestador concurrente `ProcessMiningEngine` ([engine.py](../../libs/dsm_core/src/dsm_core/process_mining/engine.py))
- Maneja de forma simétrica los dos órdenes posibles de llegada entre Kafka topics (**ADR-13**):
  - **Traza primero → Asignación después:** materializa al instante el DFG individual (`scope="student"`) y, al llegar `ClusterAssignmentMessage`, suma en $O(|E_{\text{student}}|)$ al acumulador del clúster (`scope="cluster"`).
  - **Asignación primero → Traza después:** retiene la asignación pendiente por `(run_id, granularity, window_id, u)` y consolida ambos grafos en cuanto arriba `TraceMessage`.
- Soporta idempotencia ante mensajes duplicados y reasignación de clúster dentro de una misma ventana (restando del clúster anterior o eliminándolo si queda vacío).

### Bloque 4: Servicio continuo `C6 Process Mining Engine` ([services/process-mining](../../services/process-mining))
- **`ProcessMiningServiceProcessor`** ([processor.py](../../services/process-mining/src/dsm_process_mining/processor.py)): valida `TraceMessage` y `ClusterAssignmentMessage`, persiste grafos individuales y agregados en Neo4j, elimina clústeres vacíos y enruta payloads inválidos a `lms.events.dlq`.
- **`app.py` y `main.py`:** consumen continuamente `analytics.traces` y `analytics.assignments` con `AIOKafkaConsumer`, registran latencias Prometheus (`ingested_at → grafo`) según **ADR-12** y sirven `/health` y `/metrics` en el puerto `8006` dentro de [docker-compose.yml](../../deploy/docker-compose.yml).

---

## 3. Guía de demostración paso a paso

1. **Verificar pruebas unitarias, pureza arquitectónica de `dsm_core` y linter:**
   ```powershell
   .\.venv\Scripts\pytest.exe -v
   .\.venv\Scripts\ruff.exe check .
   ```

2. **Levantar o actualizar el stack Docker (incluyendo `dsm-process-mining`):**
   ```powershell
   docker compose -f deploy/docker-compose.yml up -d --build --wait
   ```

3. **Ejecutar la comprobación automatizada de Fase 5 (Etapa 6 del menú):**
   ```powershell
   .\.venv\Scripts\python.exe scripts\demo_menu.py --step 6
   ```
   Esta etapa genera y reproduce un curso sintético de 30 estudiantes y 8 semanas, verifica que Neo4j contenga los grafos `:DFG` de `scope="student"` y `scope="cluster"` en las cuatro granularidades (`daily`, `weekly`, `monthly`, `course`) y comprueba algebraicamente que cada arista de clúster (`freq`, `total_time_sec`, `mean_time_sec`, `support`, `trace_count`) coincide con la suma exacta de los DFG individuales de sus integrantes según MongoDB.

4. **Inspección visual en Neo4j Browser (`http://localhost:7474`):**
   Utiliza el `run_id` y `window_id` impresos por la Etapa 6 en una consulta Cypher:
   ```cypher
   MATCH (s)-[r:DFG {
     run_id: '<run_id>',
     granularity: 'weekly',
     window_id: '<window_id>',
     scope: 'cluster',
     scope_id: '0'
   }]->(t)
   RETURN s, r, t;
   ```

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 5 implementamos el motor de minería de procesos educativos `C6` sobre `PM4Py` y **Neo4j Community**. Aprovechando la propiedad aditiva de los Directly-Follows Graphs (ADR-13), `C6` procesa las trazas individuales en paralelo con el clustering evolutivo `C5` y consolida incrementalmente en $O(|E|)$ las frecuencias, tiempos medios y soporte de cada clúster para las cuatro granularidades temporales, quedando verificada la coincidencia exacta entre los DFG individuales y los agregados por clúster.»*
