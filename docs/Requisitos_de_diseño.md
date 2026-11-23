| Capa | ID | Función |
| --- | --- | --- |
| I. Ingesta | RF-01 | Recibir eventos del LMS (Moodle) sin bloquearlo |
|  | RF-02 | Validar y normalizar cada evento a la tupla canónica E = ⟨u, a, r, t, M⟩ |
|  | RF-03 | Seudonimizar `u` (privacidad de los estudiantes) |
|  | RF-04 | Escribir el evento en el log inmutable de solo adición (append-only) |
|  | RF-05 | Reproducir logs históricos (CSV de Moodle o un dataset público) como si fueran flujo en vivo |
| II. Analítica | RF-06 | Filtrar ruido: eventos administrativos, duplicados, llamadas técnicas |
|  | RF-07 | Mapear acciones atómicas a Eventos de Alto Nivel (HLE) con un catálogo configurable |
|  | RF-08 | Asignar eventos a ventanas disjuntas de tamaño Δt por tiempo del evento, con tolerancia para eventos tardíos |
|  | RF-09 | Al cerrar cada ventana, calcular el vector de características de cada estudiante |
|  | RF-10 | Al cerrar cada ventana, construir la traza ordenada de cada estudiante |
|  | RF-11 | Clustering evolutivo incremental: actualizar micro-clústeres y centroides y asignar un perfil |
|  | RF-12 | Registrar las transiciones de clúster de cada estudiante entre ventanas |
|  | RF-13 | Minería de procesos: un DFG por estudiante y otro por clúster en cada ventana, con frecuencias y tiempos |
| III. Persistencia | RF-14 | Persistir perfiles en un almacén semiestructurado, grafos en uno de grafos y metadatos en uno relacional |
| IV. Presentación | RF-15 | API de consulta sobre el estado materializado (nunca sobre el log) |
|  | RF-16 | Dashboard para el docente: evolución de clústeres, DFG por perfil y ficha del estudiante con su "por qué" |
|  | RF-17 | Autenticación y roles (docente y administrador) |
| V. Validación | RF-18 | Medir latencia de extremo a extremo (t del evento → estado persistido) y el throughput |
|  | RF-19 | Reproducibilidad: cada ejecución con `run_id`, configuración versionada (Δt, parámetros, semillas) y repetición determinista |
|  | RF-20 | Línea base batch: mismo dataset con K-Means y descubrimiento de procesos sobre todo el log, para la pregunta 3 |
|  | RF-21 | Métricas de calidad: silueta, estabilidad entre corridas (ARI) y fitness/precisión de los modelos de proceso |