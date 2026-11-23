CREATE CONSTRAINT activity_unique IF NOT EXISTS
FOR (a:Activity) REQUIRE (a.course_id, a.hle_code) IS UNIQUE;

CREATE CONSTRAINT boundary_unique IF NOT EXISTS
FOR (b:Boundary) REQUIRE (b.course_id, b.name) IS UNIQUE;

CREATE INDEX dfg_lookup IF NOT EXISTS
FOR ()-[r:DFG]-() ON (r.run_id, r.granularity, r.window_id, r.scope, r.scope_id);
