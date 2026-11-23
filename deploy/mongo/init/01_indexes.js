const database = db.getSiblingDB("dsm_lms");

database.createCollection("student_profiles");
database.student_profiles.createIndex(
  { run_id: 1, granularity: 1, window_id: 1, student_id: 1 },
  { unique: true, name: "uq_profile_run_gran_window_student" }
);
database.student_profiles.createIndex(
  { run_id: 1, course_id: 1, granularity: 1, "clustering.cluster_id": 1 },
  { name: "idx_profile_cluster_lookup" }
);

database.createCollection("cluster_snapshots");
database.cluster_snapshots.createIndex(
  { run_id: 1, granularity: 1, window_id: 1 },
  { unique: true, name: "uq_snapshot_run_gran_window" }
);
