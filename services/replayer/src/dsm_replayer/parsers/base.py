"""Contrato base y utilidades compartidas para parsers de históricos LMS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from dsm_common.schemas import RawEventInput


def ensure_file_exists(file_path: str | Path) -> Path:
    """Valida que el archivo de entrada exista y sea un fichero regular."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Archivo de eventos no encontrado: {path}")
    return path


def parse_datetime_utc(raw_value: str | int | float, formats: tuple[str, ...] = ()) -> datetime:
    """Convierte una estampa ISO-8601, epoch o cadena formateada a `datetime` UTC."""
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(float(raw_value), tz=UTC)

    text = str(raw_value).strip()
    if not text:
        raise ValueError("La marca temporal está vacía.")

    if text.isdigit():
        return datetime.fromtimestamp(float(text), tz=UTC)
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        return datetime.fromtimestamp(numeric, tz=UTC)

    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            continue

    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    parsed_iso = datetime.fromisoformat(normalized)
    if parsed_iso.tzinfo is None:
        return parsed_iso.replace(tzinfo=UTC)
    return parsed_iso.astimezone(UTC)


class SourceParser(ABC):
    """Adapta distintos formatos de exportación histórica hacia el payload del Gateway."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Identificador canónico del formato de entrada."""

    @abstractmethod
    def parse_stream(self, file_path: str | Path) -> Iterator[RawEventInput]:
        """Genera eventos ordenados cronológicamente por `t` original en UTC."""
