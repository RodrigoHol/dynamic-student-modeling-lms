# Fase 4 — Motor de Clustering Evolutivo (`dsm_core.clustering` + `C5`)

> **Propósito:** Explicar qué se construyó en la Fase 4, cómo se desacoplan los algoritmos evolutivos sobre **River** mediante interfaz y registro declarativo (**ADR-04**, **ADR-08**, **ADR-10**), cómo se calculan la explicabilidad por `z_score` y las transiciones entre ventanas, y cómo validar el servicio continuo `C5 Clustering Engine` contra MongoDB y Kafka.

---

## 1. Visión general: ¿Qué logramos en la Fase 4?

Con la Fase 3 operativa, `C4 Preprocessor` ya emite vectores numéricos de características hacia `analytics.features` para las cuatro granularidades (`daily`, `weekly`, `monthly`, `course`). En la **Fase 4** cerramos la primera rama de la analítica dual concurrente:

1. **Dominio analítico puro en `libs/dsm_core` (`ADR-10`):** sin dependencias de Kafka ni MongoDB, se implementaron la interfaz `ClusteringAlgorithm`, los adaptadores intercambiables `DenStreamAdapter` y `DBSTREAMAdapter` sobre `River`, el registro declarativo (`CLUSTERING_REGISTRY`), el escalado/estadísticas *online* mediante el algoritmo de Welford (`OnlineFeatureStats`), la explicabilidad por `z_score`, el rastreador de transiciones (`TransitionTracker`) y el orquestador puro `ClusteringEngine`.
2. **Contratos y persistencia en `libs/dsm_common`:** se añadieron los esquemas `StudentProfileDocument`, `ClusterSnapshotDocument` y `ClusterAssignmentMessage`, junto con `MongoProfileRepository` (`PyMongo` asíncrono nativo sobre las colecciones `student_profiles` y `cluster_snapshots`).
3. **Servicio continuo `C5 Clustering Engine` (`services/clustering`):** consume continuamente `analytics.features`, mantiene un modelo evolutivo completamente aislado por cada `(run_id, granularity)`, persiste perfiles y snapshots de centroides en MongoDB, publica asignaciones `(u -> cluster_id)` en `analytics.assignments` (clave `granularity:window_id`) y expone `/health` y `/metrics` en el puerto `8005`.

---

## 2. Los 4 bloques construidos en esta fase

### Bloque 1: Esquemas, configuración y repositorio MongoDB ([dsm_common](../../libs/dsm_common/src/dsm_common))
- **`schemas/analytics.py`:** incorpora `StudentProfileDocument` (`_id = "{run_id}:{granularity}:{window_id}:{student_id}"`), `ClusterSnapshotDocument` (`_id = "{run_id}:{granularity}:{window_id}"`) y `ClusterAssignmentMessage`, alineados con el modelo documental de la Sección 6.3 de [arquitectura.md](../arquitectura.md) y los índices de [01_indexes.js](../../deploy/mongo/init/01_indexes.js).
- **`config/loader.py` y [config/clustering.yaml](../../config/clustering.yaml):** amplían `ClusteringConfig` con `scale_features`, `top_k_features` y `algorithm_params` por algoritmo (`denstream` y `dbstream`). El método `effective_params()` permite conmutar entre algoritmos modificando únicamente `algorithm:` en YAML.
- **`storage/mongo.py`:** define `ProfileRepository`, `MongoProfileRepository` (`upsert` idempotente vía `replace_one(..., upsert=True)`) e `InMemoryProfileRepository` para pruebas rápidas sin contenedores.

### Bloque 2: Algoritmos evolutivos intercambiables en `dsm_core.clustering` ([clustering/](../../libs/dsm_core/src/dsm_core/clustering))
- **`ClusteringAlgorithm`** ([base.py](../../libs/dsm_core/src/dsm_core/clustering/base.py)): contrato uniforme con `learn_one`, `predict_one` (`-1` para outliers o modelos aún no inicializados), `get_centroid`, `distance_to_centroid` y `snapshot`.
- **`DenStreamAdapter`** ([denstream.py](../../libs/dsm_core/src/dsm_core/clustering/denstream.py)): envuelve `river.cluster.DenStream`, valida *fail-fast* el invariante `mu * beta > 1.0`, protege el estado previo a `n_samples_init` retornando `-1` y serializa micro-clústeres (`p_micro_clusters` y `o_micro_clusters`).
- **`DBSTREAMAdapter`** ([dbstream.py](../../libs/dsm_core/src/dsm_core/clustering/dbstream.py)): envuelve `river.cluster.DBSTREAM` con el mismo contrato de centroides, pesos y snapshots.
- **`CLUSTERING_REGISTRY` y `ClusteringEngine`** ([registry.py](../../libs/dsm_core/src/dsm_core/clustering/registry.py), [engine.py](../../libs/dsm_core/src/dsm_core/clustering/engine.py)): aíslan el estado algorítmico por `(run_id, granularity)` para que la densidad diaria no contamine los modelos semanal, mensual o de curso, estandarizan incrementalmente las características antes del clustering y desescalan los centroides en `cluster_snapshots` para mantener unidades legibles para el docente.

### Bloque 3: Explicabilidad y detección de transiciones ([explainability/](../../libs/dsm_core/src/dsm_core/explainability))
- **`OnlineFeatureStats` y `compute_top_contributing_features`** ([feature_importance.py](../../libs/dsm_core/src/dsm_core/explainability/feature_importance.py)):
  - Mantiene media y varianza incrementales en $O(D)$ por vector mediante el algoritmo de Welford sin almacenar historiales en memoria.
  - Calcula el `z_score` de cada característica respecto al centroide del clúster asignado (o respecto a la media poblacional en el caso de outliers o primer integrante) y selecciona las `top_k` variables ordenadas por `|z_score|`.
- **`TransitionTracker`** ([transitions.py](../../libs/dsm_core/src/dsm_core/explainability/transitions.py)):
  - Registra en $O(1)$ por estudiante el último `(window_start, window_id, cluster_id)` para calcular `previous_cluster_id` y `transition_detected`, siendo idempotente si una misma ventana se reprocesa.

### Bloque 4: Servicio continuo `C5 Clustering Engine` ([services/clustering](../../services/clustering))
- **`ClusteringServiceProcessor`** ([processor.py](../../services/clustering/src/dsm_clustering/processor.py)): valida `FeatureVectorMessage`, invoca `ClusteringEngine`, persiste perfil y snapshot en MongoDB, publica `ClusterAssignmentMessage` en `analytics.assignments` (clave `granularity:window_id`) y enruta payloads inválidos a `lms.events.dlq`.
- **`app.py` y `main.py`:** consumen continuamente `analytics.features` con `AIOKafkaConsumer`, registran métricas Prometheus (incluyendo la latencia `ingested_at → perfil` según **ADR-12**) y sirven `/health` y `/metrics` en el puerto `8005` dentro de [docker-compose.yml](../../deploy/docker-compose.yml).

---

## 3. Guía de demostración paso a paso

1. **Verificar pruebas unitarias, pureza arquitectónica de `dsm_core` y linter:**
   ```powershell
   .\.venv\Scripts\pytest.exe -v
   .\.venv\Scripts\ruff.exe check .
   ```

2. **Levantar o actualizar el stack Docker (incluyendo `dsm-clustering`):**
   ```powershell
   docker compose -f deploy/docker-compose.yml up -d --build --wait
   ```

3. **Ejecutar la comprobación automatizada de Fase 4 (Etapa 5 del menú):**
   ```powershell
   .\.venv\Scripts\python.exe scripts\demo_menu.py --step 5
   ```
   Esta etapa ejecuta automáticamente ambos criterios de paso:
   - Reproduce un curso sintético de 30 estudiantes y 8 semanas con `algorithm: denstream`, verificando en MongoDB (`student_profiles` y `cluster_snapshots`) y en Kafka (`analytics.assignments`) las 4 granularidades (`daily`, `weekly`, `monthly`, `course`), `cluster_id`, `previous_cluster_id`, `transition_detected`, `top_contributing_features` y `latencies_ms.ingested_to_profile`.
   - Cambia `algorithm: denstream` por `algorithm: dbstream` en [config/clustering.yaml](../../config/clustering.yaml), reinicia `dsm-clustering` sin modificar código fuente, ejecuta una segunda corrida y comprueba que MongoDB y `analytics.assignments` registran los perfiles bajo `algorithm: "dbstream"` (restaurando al finalizar `denstream`).

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 4 implementamos el motor de clustering evolutivo `C5` sobre `River` (`DenStream` y `DBSTREAM`) desacoplado tras la interfaz `ClusteringAlgorithm` en `dsm_core`, con estandarización y estadísticas `z_score` incrementales en $O(1)$ mediante Welford, detección de transiciones entre ventanas consecutivas, persistencia de perfiles y snapshots de centroides en MongoDB y emisión en vivo hacia `analytics.assignments`. Validamos la ejecución completa para las cuatro granularidades y el intercambio declarativo de `denstream` a `dbstream` modificando únicamente `config/clustering.yaml` sin alterar código.»*
