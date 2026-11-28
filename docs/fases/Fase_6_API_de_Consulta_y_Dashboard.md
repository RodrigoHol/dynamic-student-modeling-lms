# Fase 6 — API de Consulta y Dashboard Docente (`C7` + `C8`)

> **Propósito:** Explicar qué se construyó en la Fase 6 para cerrar la capa de mediación e interpretabilidad (**ADR-02**, **ADR-11**): el servicio `C7 Query API` en FastAPI (lectura políglota + autenticación JWT por roles + WebSocket en vivo) y el tablero docente `C8` en Vue 3 + TypeScript + PrimeVue + Apache ECharts + Cytoscape.js.

---

## 1. Visión general: ¿Qué logramos en la Fase 6?

Con las capas de ingesta (`C2`–`C3`), transformación (`C4`), clustering evolutivo (`C5`) y minería de procesos (`C6`) materializando el estado en PostgreSQL, MongoDB y Neo4j, la **Fase 6** expone esa información de forma interpretable para el docente:

1. **Servicio `C7 Query API` (`services/query-api`):** lee exclusivamente del estado materializado (nunca del log histórico de Kafka, cumpliendo **RF-15**), autentica mediante JWT con roles (`teacher` y `admin`) y difunde en tiempo real eventos `window_updated` por WebSocket desde `analytics.assignments`.
2. **Tablero docente `C8 Dashboard` (`frontend/dashboard`):** SPA en Vue 3 + TypeScript + Vite + Pinia + PrimeVue con filtros globales (`course_id`, `run_id`, `granularity`, `window_id`), diagrama Sankey de evolución, visor interactivo de grafos DFG (`Cytoscape.js` + `cytoscape-dagre`) y ficha explicable del estudiante (`z_score` + comparación DFG individual vs. clúster).

---

## 2. Los 4 bloques construidos en esta fase

### Bloque 1: Autenticación y autorización por roles (`auth.py`)
- Hashing seguro con `PBKDF2-HMAC-SHA256` + tokens JWT firmados (`PyJWT`) y dependencias FastAPI (`get_current_user`, `require_roles`).
- Al iniciar, `C7` asegura usuarios demo en `users_roles` (`docente / docente123` con rol `teacher`, y `admin / admin123` con rol `admin`).

### Bloque 2: Repositorio políglota y agregación Sankey (`repositories.py`)
- **`PolyglotQueryRepository`** combina consultas sobre PostgreSQL (`courses`, `runs`, `run_configs`, `users_roles`, `experiment_metrics`), MongoDB (`student_profiles`, `cluster_snapshots`) y Neo4j (`:Activity`, `:Boundary`, `:DFG`).
- Construye la evolución temporal (`ClusterEvolutionResponse`), nodos y enlaces Sankey entre ventanas consecutivas y la ficha cronológica del estudiante.

### Bloque 3: Endpoints REST y puente WebSocket (`api/routes.py`, `websocket.py`)
- REST (`/api/v1/auth/login`, `/api/v1/courses`, `/api/v1/runs`, `/api/v1/runs/{run_id}/windows`, `/api/v1/runs/{run_id}/clusters/evolution`, `/api/v1/runs/{run_id}/clusters/{cluster_id}/students`, `/api/v1/runs/{run_id}/students`, `/api/v1/runs/{run_id}/students/{student_id}`, `/api/v1/runs/{run_id}/dfg`, `/api/v1/runs/{run_id}/metrics`).
- WebSocket (`/ws/runs/{run_id}` y `/ws/updates`) alimentado en segundo plano por `KafkaAssignmentsWsBridge` para refrescar automáticamente el dashboard ante cierres de ventana.

### Bloque 4: Dashboard Docente `C8` (`frontend/dashboard`)
- **Evolución de clústeres (`ClusterEvolutionView.vue`):** Sankey y distribución por ventana en `vue-echarts`, con selección interactiva de clúster e integrantes.
- **Grafos de procesos (`ProcessGraphView.vue`):** layout jerárquico `dagre` sobre `Cytoscape.js` con grosor/etiqueta configurable por frecuencia, tiempo medio (`s`) o soporte (`%`).
- **Ficha explicable (`StudentProfileView.vue`):** historial de transiciones, gráfico de `z_score` y comparación lado a lado del DFG individual frente al DFG de su clúster.

---

## 3. Guía de demostración paso a paso

1. **Pruebas unitarias, linter y compilación frontend:**
   ```powershell
   .\.venv\Scripts\pytest.exe -v
   .\.venv\Scripts\ruff.exe check .
   Push-Location frontend/dashboard; npm run build; Pop-Location
   ```

2. **Levantar stack Docker y comprobar Fase 6 (Etapa 7 del menú):**
   ```powershell
   docker compose -f deploy/docker-compose.yml up -d --build --wait
   .\.venv\Scripts\python.exe scripts\demo_menu.py --step 7
   ```

3. **Abrir el tablero web en el navegador:**
   - URL: `http://localhost:8088` (credenciales demo: `docente / docente123`).

---

## 4. Resumen ejecutivo para exposición

> *«En la Fase 6 cerramos la capa de mediación e interpretabilidad con `C7 Query API` (FastAPI, JWT por roles, WebSocket sobre `analytics.assignments` y consultas políglotas sobre PostgreSQL, MongoDB y Neo4j) y `C8 Dashboard` (Vue 3, PrimeVue, ECharts y Cytoscape.js), permitiendo al docente seguir en tiempo real las transiciones Sankey, los grafos DFG y la justificación por `z_score` de cada estudiante.»*
