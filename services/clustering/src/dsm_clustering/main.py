from __future__ import annotations

from dsm_clustering.app import main_async
from dsm_clustering.config import ClusteringServiceSettings


def main() -> None:
    main_async(ClusteringServiceSettings())


if __name__ == "__main__":
    main()
