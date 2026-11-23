# Explicación Detallada por Fases de Implementación

Esta carpeta reúne la documentación explicativa y de demostración de cada fase completada del proyecto, pensada para facilitar las revisiones de avance con la dirección de tesis y alimentar la redacción técnica del sistema.

| Fase | Documento | Estado | Resumen |
| :--- | :--- | :--- | :--- |
| **Fase 1** | [Fase_1_Infraestructura_e_Ingesta.md](./Fase_1_Infraestructura_e_Ingesta.md) | Completada | Capa I (telemetría, puerta de ingesta `C2`, seudonimización, Kafka KRaft inmutable) y esquemas iniciales de Capa III (PostgreSQL, MongoDB, Neo4j). |
| **Fase 2** | *Pendiente* | Por implementar | `C3 Replayer`, interfaz `SourceParser` para históricos de Moodle y generador sintético. |
| **Fase 3** | *Pendiente* | Por implementar | Preprocesamiento en `dsm_core`, mapeo a Eventos de Alto Nivel (HLE) y ventanas múltiples (`C4`). |
| **Fase 4** | *Pendiente* | Por implementar | Clustering evolutivo incremental (`DenStream` / `DBSTREAM`, `C5`) hacia MongoDB. |
| **Fase 5** | *Pendiente* | Por implementar | Minería de procesos educativos (`PM4Py`, DFG individual y aditivo, `C6`) hacia Neo4j. |
| **Fase 6** | *Pendiente* | Por implementar | `C7 Query API` y tablero docente `C8` en Vue 3 + PrimeVue. |
| **Fase 7** | *Pendiente* | Por implementar | `C9 Experiment Runner` (línea base *batch*, métricas Silueta, ARI, Fitness, Precision) y `C10 Observabilidad`. |

Para consultar los criterios técnicos de aceptación (*Definition of Done*) de cada etapa, véase [Fases_De_Implementacion.md](../Fases_De_Implementacion.md).
