"""Descubrimiento seguro del provider Trainingym."""

from .config import TrainingymProviderConfig
from .discovery import TrainingymDiscoveryResult, TrainingymDiscoveryService

__all__ = [
    "TrainingymDiscoveryResult",
    "TrainingymDiscoveryService",
    "TrainingymProviderConfig",
]
