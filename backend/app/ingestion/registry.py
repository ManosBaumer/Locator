from collections.abc import Callable

from app.ingestion.adapters.base import BaseChainAdapter

AdapterFactory = Callable[[], BaseChainAdapter]
_registry: dict[str, AdapterFactory] = {}


def register(chain_slug: str) -> Callable[[type[BaseChainAdapter]], type[BaseChainAdapter]]:
    def decorator(adapter_cls: type[BaseChainAdapter]) -> type[BaseChainAdapter]:
        _registry[chain_slug] = adapter_cls
        return adapter_cls

    return decorator


def get_adapter(chain_slug: str) -> BaseChainAdapter:
    try:
        return _registry[chain_slug]()
    except KeyError as exc:
        raise ValueError(f"No adapter registered for chain: {chain_slug}") from exc


def registered_chains() -> list[str]:
    return sorted(_registry)
