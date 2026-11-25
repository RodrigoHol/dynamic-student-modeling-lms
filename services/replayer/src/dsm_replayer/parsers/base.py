from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from dsm_common.schemas import RawEventInput
from dsm_common.time import ensure_utc


def ensure_file_exists(file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Archivo de eventos no encontrado: {path}")
    return path


def parse_datetime_utc(raw_value: str | int | float, formats: tuple[str, ...] = ()) -> datetime:
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(float(raw_value), tz=UTC)

    text = str(raw_value).strip()
    if not text:
        raise ValueError("La marca temporal está vacía.")

    if text.isdigit():
        return datetime.fromtimestamp(float(text), tz=UTC)
    try:
        return datetime.fromtimestamp(float(text), tz=UTC)
    except ValueError:
        pass

    for fmt in formats:
        try:
            return ensure_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue

    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    return ensure_utc(datetime.fromisoformat(normalized))


def iter_chronological(indexed_rows: list[tuple[int, RawEventInput]]) -> Iterator[RawEventInput]:
    indexed_rows.sort(key=lambda item: (item[1].timestamp, item[0]))
    for _, event in indexed_rows:
        yield event


class SourceParser(ABC):
    @property
    @abstractmethod
    def format_name(self) -> str: ...

    @abstractmethod
    def parse_stream(self, file_path: str | Path) -> Iterator[RawEventInput]: ...
