from dsm_common.config import AppSettings


class QueryApiSettings(AppSettings):
    query_api_host: str = "0.0.0.0"
    query_api_port: int = 8007
    jwt_secret: str = "change-me-in-production-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://localhost:8088,http://localhost:3000"
    query_enable_ws_kafka_bridge: bool = True
    query_ws_consumer_group: str = "dsm-query-api-ws-v1"
    query_seed_demo_users: bool = True

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
