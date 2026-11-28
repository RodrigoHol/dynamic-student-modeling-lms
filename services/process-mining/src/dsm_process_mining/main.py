from __future__ import annotations

from dsm_process_mining.app import main_async
from dsm_process_mining.config import ProcessMiningServiceSettings


def main() -> None:
    main_async(ProcessMiningServiceSettings())


if __name__ == "__main__":
    main()
