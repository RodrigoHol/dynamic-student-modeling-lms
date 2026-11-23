#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
KAFKA_TOPICS="/opt/kafka/bin/kafka-topics.sh"

create_topic() {
  local name="$1"
  local partitions="$2"
  local retention_ms="$3"

  "$KAFKA_TOPICS" --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$name" \
    --partitions "$partitions" \
    --replication-factor 1 \
    --config "retention.ms=${retention_ms}"
}

create_topic "lms.events.canonical" 3 -1
create_topic "lms.events.dlq" 1 2592000000
create_topic "analytics.features" 3 604800000
create_topic "analytics.traces" 3 604800000
create_topic "analytics.assignments" 3 604800000

echo "[kafka-init] Topics verificados/creados correctamente."
