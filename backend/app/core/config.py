from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://locater:locater@localhost:5432/locater"
    sync_database_url: str = "postgresql+psycopg://locater:locater@localhost:5432/locater"
    amap_api_key: str = ""
    admin_api_key: str = "change-me"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    hema_store_locator_url: AnyHttpUrl | None = Field(
        default="https://www.freshippo.com/",
        alias="ADAPTER_HEMA_STORE_LOCATOR_URL",
    )
    hema_source_url: AnyHttpUrl | None = Field(default=None, alias="ADAPTER_HEMA_SOURCE_URL")
    rt_mart_store_locator_url: AnyHttpUrl | None = Field(
        default="https://www.rt-mart.com.cn/stores/store?size=8&memLiteClub=9&typeMarket=1&typeSuper=2&typeClub=5",
        alias="ADAPTER_RT_MART_STORE_LOCATOR_URL",
    )
    rt_mart_page_size: int = Field(default=100, alias="ADAPTER_RT_MART_PAGE_SIZE")
    seven_eleven_chengdu_city_id: str = Field(default="1310", alias="ADAPTER_SEVEN_ELEVEN_CHENGDU_CITY_ID")
    seven_eleven_amap_keyword: str = Field(default="7-ELEVEN", alias="ADAPTER_SEVEN_ELEVEN_AMAP_KEYWORD")
    seven_eleven_amap_keywords: str | None = Field(
        default="7-ELEVEN,7-11便利店,7-ELEVEn",
        alias="ADAPTER_SEVEN_ELEVEN_AMAP_KEYWORDS",
    )
    seven_eleven_amap_cities: str | None = Field(default=None, alias="ADAPTER_SEVEN_ELEVEN_AMAP_CITIES")
    aldi_store_locator_url: AnyHttpUrl | None = Field(
        default="https://www.aldi.cn/ourshops/physicalstore/",
        alias="ADAPTER_ALDI_STORE_LOCATOR_URL",
    )
    family_mart_store_list_url: AnyHttpUrl | None = Field(
        default="https://www.yidianlife.com/Family_Mart.html",
        alias="ADAPTER_FAMILY_MART_STORE_LIST_URL",
    )
    yonghui_store_list_url: AnyHttpUrl | None = Field(
        default="https://ccc.spdb.com.cn/miniSite/2228/cfb6e3d/yh.shtml",
        alias="ADAPTER_YONGHUI_STORE_LIST_URL",
    )
    walmart_amap_keywords: str | None = Field(default="沃尔玛(", alias="ADAPTER_WALMART_AMAP_KEYWORDS")
    walmart_sams_amap_keywords: str | None = Field(
        default="山姆会员商店",
        alias="ADAPTER_WALMART_SAMS_AMAP_KEYWORDS",
    )
    walmart_amap_cities: str | None = Field(default=None, alias="ADAPTER_WALMART_AMAP_CITIES")
    kfc_store_portal_url: AnyHttpUrl | None = Field(
        default="https://order.kfc.com.cn/store-portal",
        alias="ADAPTER_KFC_STORE_PORTAL_URL",
    )
    kfc_search_keyword: str | None = Field(default=" ", alias="ADAPTER_KFC_SEARCH_KEYWORD")
    kfc_page_size: int = Field(default=50, alias="ADAPTER_KFC_PAGE_SIZE")
    kfc_grid_span_km: float = Field(default=35.0, alias="ADAPTER_KFC_GRID_SPAN_KM")
    kfc_grid_step_km: float = Field(default=2.5, alias="ADAPTER_KFC_GRID_STEP_KM")
    kfc_city_concurrency: int = Field(default=5, alias="ADAPTER_KFC_CITY_CONCURRENCY")
    mcdonalds_search_url: AnyHttpUrl | None = Field(
        default="https://www.mcdonalds.com.cn/ajaxs/search_by_point",
        alias="ADAPTER_MCDONALDS_SEARCH_URL",
    )
    mcdonalds_checkpoint_dir: str = Field(
        default="/tmp/mcdonalds-checkpoint",
        alias="ADAPTER_MCDONALDS_CHECKPOINT_DIR",
    )
    mcdonalds_reset_checkpoint: bool = Field(default=False, alias="ADAPTER_MCDONALDS_RESET_CHECKPOINT")
    mcdonalds_deliveryinfo_city_concurrency: int = Field(
        default=10,
        alias="ADAPTER_MCDONALDS_DELIVERYINFO_CITY_CONCURRENCY",
    )
    mcdonalds_deliveryinfo_grid_workers: int = Field(
        default=3,
        alias="ADAPTER_MCDONALDS_DELIVERYINFO_GRID_WORKERS",
    )
    mcdonalds_deliveryinfo_page_concurrency: int = Field(
        default=32,
        alias="ADAPTER_MCDONALDS_DELIVERYINFO_PAGE_CONCURRENCY",
    )
    seven_fresh_api_base: AnyHttpUrl | None = Field(
        default="https://www.7fresh.com/sevenFresh/api",
        alias="ADAPTER_SEVEN_FRESH_API_BASE",
    )

    @property
    def mcdonalds_checkpoint_path(self) -> Path:
        return Path(self.mcdonalds_checkpoint_dir)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
