"""Parser para datasets sintéticos en formato JSON Lines (`.jsonl`)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from dsm_common.schemas import RawEventInput
from dsm_replayer.parsers.base import SourceParser, ensure_file_exists


class SyntheticJsonlParser(SourceParser):
    """Lee eventos sintéticos en formato JSONL y los emite en orden cronológico por `t`."""

    @property
    def format_name(self) -> str:
        return "synthetic_jsonl"

    def parse_stream(self, file_path: str | Path) -> Iterator[RawEventInput]:
        path = ensure_file_exists(file_path)
        parsed_rows: list[tuple[int, RawEventInput]] = []

        with path.open("r", encoding="utf-8-sig") as handle:
            for idx, line in enumerate(handle):
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                event = RawEventInput.model_validate(payload)
                parsed_rows.append((idx, event))

        parsed_rows.sort(key=lambda item: (item[1].timestamp, item[0]))
        for _, event in parsed_rows:
            yield event
