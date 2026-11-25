from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from dsm_common.schemas import RawEventInput
from dsm_replayer.parsers.base import SourceParser, ensure_file_exists, iter_chronological


class SyntheticJsonlParser(SourceParser):
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
                event = RawEventInput.model_validate(json.loads(stripped))
                parsed_rows.append((idx, event))

        yield from iter_chronological(parsed_rows)
