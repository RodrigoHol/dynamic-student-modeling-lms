# Explicación Detallada por Fases de Implementación

Esta carpeta reúne la documentación explicativa y de demostración de cada fase completada del proyecto, pensada para facilitar las revisiones de avance con la dirección de tesis y alimentar la redacción técnica del sistema.

| Fase | Documento | Estado | Resumen |
| :--- | :--- | :--- | :--- |
| **Fase 1** | [Fase_1_Infraestructura_e_Ingesta.md](./Fase_1_Infraestructura_e_Ingesta.md) | Completada | Capa I (telemetría, puerta de ingesta `C2`, seudonimización, Kafka KRaft inmutable) y esquemas iniciales de Capa III (PostgreSQL, MongoDB, Neo4j). |
| **Fase 2** | [Fase_2_Replayer_y_Datos_Sinteticos.md](./Fase_2_Replayer_y_Datos_Sinteticos.md) | Completada | `C3 Replayer`, interfaz `SourceParser` (`moodle_csv`, `moodle_db`, `synthetic_jsonl`), generador sintético y registro de corridas en PostgreSQL. |
| **Fase 3** | [Fase_3_Preprocesamiento_HLE_y_Ventanas.md](./Fase_3_Preprocesamiento_HLE_y_Ventanas.md) | Completada | Núcleo puro `dsm_core` (filtro de ruido, `HLEMapper`, 4 ventanas disjuntas por `t` y `FeaturePipeline`) y servicio continuo `C4 Preprocessor` sobre Quix Streams + RocksDB hacia `analytics.features` y `analytics.traces`. |
| **Corte técnico** | [Refactorizacion_Pre_Fase_4.md](./Refactorizacion_Pre_Fase_4.md) | Completada | Optimización $O(1)$ de estado en RocksDB, despacho en lote Kafka (`publish_batch`), `asyncpg.Pool`, `WindowContext`, unificación `dsm_core` ↔ `C4`, modularización de `scripts/demo/` y reglas estrictas en `ruff`. |
| **Fase 4** | *Pendiente* | Por implementar | Clustering evolutivo incremental (`DenStream` / `DBSTREAM`, `C5`) hacia MongoDB. |
| **Fase 5** | *Pendiente* | Por implementar | Minería de procesos educativos (`PM4Py`, DFG individual y aditivo, `C6`) hacia Neo4j. |
| **Fase 6** | *Pendiente* | Por implementar | `C7 Query API` y tablero docente `C8` en Vue 3 + PrimeVue. |
| **Fase 7** | *Pendiente* | Por implementar | `C9 Experiment Runner` (línea base *batch*, métricas Silueta, ARI, Fitness, Precision) y `C10 Observabilidad`. |

Para consultar los criterios técnicos de aceptación (*Definition of Done*) de cada etapa, véase [Fases_De_Implementacion.md](../Fases_De_Implementacion.md).
