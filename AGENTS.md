# Reglas e Instrucciones del Proyecto — Dynamic Student Modeling LMS

Este repo implementa mi tesis (*«Implementación y validación de la automatización del modelado dinámico e interpretable de patrones de interacción estudiantil en LMS»*).

Al iniciar una nueva conversación, tarea o fase:
1. Lee `docs/arquitectura.md`, `docs/Fases_De_Implementacion.md` y `docs/fases/README.md` para conocer el diseño completo y qué fases ya están terminadas.
2. Lee los archivos YAML de configuración analítica en `config/` (`hle_catalog.yaml`, `features.yaml`, `windows.yaml`, `clustering.yaml`, `process_mining.yaml`).
3. Revisa `docs/tesis/main.md` únicamente cuando necesites contexto conceptual del Capítulo III/I y cítalo **siempre por número de sección**, nunca por número de línea (ADR-15).

---

## Convenciones arquitectónicas permanentes

- **Arquitectura tipo Kappa y dirección de dependencias (ADR-00, ADR-10):**
  - Dependencias estrictas: `services/* → dsm_core → dsm_common`; `experiments → dsm_core`.
  - **`libs/dsm_core` es dominio analítico 100% puro: nunca importa Kafka ni bases de datos** (`aiokafka`, `quixstreams`, `asyncpg`, `pymongo`, `neo4j`, etc.). Los servicios en `services/` son cascarones delgados de E/S alrededor de `dsm_core` y `dsm_common`.
- **Separación de relojes (ADR-12):**
  - Toda asignación a ventanas disjuntas (`daily`, `weekly`, `monthly`, `course`) opera estrictamente sobre el **tiempo del evento (`t`)** original del LMS.
  - Toda métrica de desempeño computacional y latencia se mide desde **`ingested_at`** hasta la persistencia final.
- **Extensibilidad declarativa (ADR-04, ADR-05):**
  - Los algoritmos, reglas HLE, extractores de características, ventanas y parsers se desacoplan mediante interfaces abstractas y se configuran vía YAML en `config/`, registrando su snapshot en PostgreSQL (`run_configs`) por `run_id`.
- **Privacidad y manejo de datos (ADR-14):**
  - Ningún identificador estudiantil real se almacena en claro en Kafka ni en las bases analíticas (seudonimización determinista `HMAC-SHA256` en `C2`).
  - Nunca se versionan datos estudiantiles reales en Git (`data/raw/` y `data/synthetic/` están excluidos; únicamente se versionan muestras pequeñas anonimizadas en `data/samples/`).
- **Monorepo Python 3.12 con `uv` (ADR-09):**
  - Un único `uv.lock` en la raíz. Usa `uv sync --all-packages` para mantener todos los miembros del workspace instalados en `.venv`. Cada servicio declara solo sus dependencias reales.

---

## Calidad de código, eficiencia y legibilidad

- **Eficiencia en flujo continuo (*hot path*):** diseña el estado con complejidad $O(1)$ por evento/vector; evita re-serializar o recomputar historiales completos en cada mensaje. Precompila reglas/configuraciones al arranque (*fail-fast*), reutiliza *pools*/clientes de BD y agrupa E/S cuando proceses lotes.
- **Clean code y única fuente de verdad:** mantén funciones cortas con una sola responsabilidad, tipos explícitos (Pydantic/`dataclass` en lugar de `dict` sin tipar) y toda lógica analítica centralizada en `dsm_core` sin duplicarla en `services/` ni `experiments/`.
- **Código explicable:** usa nombres de dominio claros con unidades explícitas (`_sec`, `_ms`). No escribas comentarios que narren código obvio; documenta únicamente fórmulas matemáticas, invariantes de concurrencia/ventanas y el *porqué* de decisiones no triviales.

---

## Reglas operativas importantes en este entorno Windows

- Usa siempre `.\.venv\Scripts\pytest.exe` y `.\.venv\Scripts\ruff.exe` directamente (y `.\.venv\Scripts\python.exe` o los ejecutables en `.\.venv\Scripts\` para scripts y CLIs del proyecto).
- **Ejecuta `pytest` y cualquier verificación contra Docker o `localhost` fuera del sandbox (`BypassSandbox: true`)** para evitar que `pytest-asyncio` o los sockets locales se queden colgados.
- En PowerShell 5.1 utiliza `;` (y comprobación de `$LASTEXITCODE`) en lugar de `&&`.
- En Python asíncrono sobre Windows (`ProactorEventLoop`), usa **`asyncpg`** para PostgreSQL (evitar `psycopg` async por incompatibilidad con `ProactorEventLoop`).
- Si escribes un script temporal de verificación que lea topics de Kafka con `aiokafka`, usa `await consumer.getmany(timeout_ms=2000)` en bucle deteniéndote al alcanzar `end_offsets` de todas las particiones (**esto aplica solo en scripts temporales de verificación**; los servicios productivos como `C4`, `C5` y `C6` deben consumir de forma continua).

---

## Protocolo estándar al completar cada fase

1. Verificar que todas las pruebas unitarias (`.\.venv\Scripts\pytest.exe -v`) y el linter (`.\.venv\Scripts\ruff.exe check .`) pasen con 0 errores y 0 advertencias.
2. Ejecutar y comprobar el Criterio de Paso (*Definition of Done*) definido en `docs/Fases_De_Implementacion.md` contra el stack Docker (`deploy/docker-compose.yml`).
3. Incorporar la comprobación de la nueva fase en el menú interactivo `scripts/demo_menu.py` para demostración y control de avance.
4. Crear la guía didáctica de la fase en `docs/fases/Fase_N_<Nombre>.md` (siguiendo el formato de `Fase_1` y `Fase_2`) y actualizar `docs/fases/README.md` y el `README.md` principal.
