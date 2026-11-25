# C4 Preprocessor (`dsm-preprocessor`)

Servicio continuo sobre **Quix Streams + RocksDB** que consume el registro inmutable `lms.events.canonical`, delega toda la lógica analítica a `dsm_core` (ADR-10) y produce ventanas disjuntas paralelas hacia `analytics.features` y `analytics.traces` (ADR-05, ADR-07, ADR-12).

## Flujo de procesamiento
1. Descarta ruido operativo configurado en `config/hle_catalog.yaml` (`NoiseFilter`).
2. Mapea acciones técnicas a Eventos de Alto Nivel (`HLEMapper`).
3. Asigna cada evento simultáneamente a las cuatro granularidades (`daily`, `weekly`, `monthly`, `course`) según la estampa original `t` con periodo de gracia (`grace_period_seconds`).
4. Al cierre de ventana por watermark o marcador `run_eof`, calcula el vector de características (`FeaturePipeline`) y la traza ordenada HLE, publicando ambos en Kafka con clave `granularity:u`.
5. Expone `GET /health` y `GET /metrics` (Prometheus) en el puerto `8004`.

## Ejecución local
```powershell
.\.venv\Scripts\dsm-preprocessor.exe
```
