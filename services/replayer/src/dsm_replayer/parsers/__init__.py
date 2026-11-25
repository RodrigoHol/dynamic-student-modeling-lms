"""Parsers enchufables (`SourceParser`) para históricos de Moodle y datos sintéticos."""

from dsm_replayer.parsers.base import SourceParser
from dsm_replayer.parsers.moodle_csv import MoodleCsvExportParser
from dsm_replayer.parsers.moodle_db import MoodleDbLogParser
from dsm_replayer.parsers.registry import PARSER_REGISTRY, create_parser, detect_format
from dsm_replayer.parsers.synthetic import SyntheticJsonlParser

__all__ = [
    "MoodleCsvExportParser",
    "MoodleDbLogParser",
    "PARSER_REGISTRY",
    "SourceParser",
    "SyntheticJsonlParser",
    "create_parser",
    "detect_format",
]
