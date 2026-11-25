# Scripts de utilidad y demostración

Atajos de línea de comandos para desarrollo local, control de avance y demostración frente a la dirección de tesis.

## Menú interactivo de verificación (`demo_menu.py`)

Permite ejecutar paso a paso (o en secuencia completa) la comprobación de las **Fases 1 y 2**:

```powershell
# Abrir el menú interactivo en terminal
.\.venv\Scripts\python.exe scripts\demo_menu.py
```

También admite ejecución directa de una etapa concreta mediante `--step`:

```powershell
# 1. Pruebas unitarias y linter (pytest + ruff)
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 1

# 2. Levantar Docker Compose y validar Fase 1 (C2 Gateway, Kafka, PostgreSQL, MongoDB, Neo4j)
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 2

# 3. Generar 5,000 eventos sintéticos, ejecutar C3 Replayer y validar PostgreSQL + Kafka
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 3

# Ejecutar Etapas 1 -> 2 -> 3 en secuencia
.\.venv\Scripts\python.exe scripts\demo_menu.py --step all

# Apagar contenedores (conservando volúmenes) o reiniciar desde cero (down -v)
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 4
.\.venv\Scripts\python.exe scripts\demo_menu.py --step 0 --yes
```
