-- Esquema relacional institucional y de trazabilidad experimental (Sección 6.5)

CREATE TABLE IF NOT EXISTS courses (
    course_id TEXT PRIMARY KEY,
    external_code TEXT,
    title TEXT NOT NULL,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS resources (
    resource_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    external_id TEXT,
    resource_type TEXT NOT NULL,
    title TEXT,
    hle_default_hint TEXT
);

CREATE TABLE IF NOT EXISTS users_roles (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'admin')),
    assigned_courses_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hle_catalog_versions (
    hle_version TEXT PRIMARY KEY,
    yaml_hash CHAR(64) NOT NULL,
    rules_json JSONB NOT NULL,
    is_provisional BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('stream', 'batch')),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    source_dataset TEXT NOT NULL,
    speed_factor TEXT,
    events_processed INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS run_configs (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    clustering_algorithm TEXT NOT NULL,
    clustering_params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    seed INTEGER NOT NULL,
    active_granularities_json JSONB NOT NULL,
    windows_config_json JSONB NOT NULL,
    features_version TEXT NOT NULL,
    features_list_json JSONB NOT NULL,
    hle_version TEXT NOT NULL REFERENCES hle_catalog_versions(hle_version),
    raw_yaml_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS experiment_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    granularity TEXT NOT NULL,
    window_id TEXT NOT NULL,
    silhouette_score DOUBLE PRECISION,
    ari_score DOUBLE PRECISION,
    pm_fitness DOUBLE PRECISION,
    pm_precision DOUBLE PRECISION,
    p50_latency_ms DOUBLE PRECISION,
    p95_latency_ms DOUBLE PRECISION,
    p99_latency_ms DOUBLE PRECISION,
    throughput_eps DOUBLE PRECISION,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resources_course ON resources(course_id);
CREATE INDEX IF NOT EXISTS idx_metrics_run_granularity ON experiment_metrics(run_id, granularity, window_id);
