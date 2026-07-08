from abc import ABC, abstractmethod
from typing import Any

from app.schemas.poi import NormalizedLocation, RawLocation


class BaseChainAdapter(ABC):
    chain_slug: str
    adapter_version = "0.1.0"
    source_url: str | None = None

    @abstractmethod
    async def fetch_raw_data(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        raise NotImplementedError

    @abstractmethod
    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        raise NotImplementedError
