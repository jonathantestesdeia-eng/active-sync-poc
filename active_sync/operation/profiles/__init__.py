"""Seleção centralizada dos perfis de processamento."""

from active_sync.config import ProcessingProfile

from .base import ProcessingStrategy, ProfileBatch, ProfilePersistResult
from .performance import PERFORMANCE_RECONCILIATION_RULES, PerformanceProfile
from .supertrack import SuperTrackProfile, build_supertrack_movements, is_cancelled


def get_processing_profile(profile: ProcessingProfile) -> ProcessingStrategy:
    if profile is ProcessingProfile.SUPERTRACK:
        return SuperTrackProfile()
    if profile is ProcessingProfile.PERFORMANCE:
        return PerformanceProfile()
    raise ValueError(f"Perfil de processamento inválido: {profile!r}.")


__all__ = [
    "PERFORMANCE_RECONCILIATION_RULES",
    "PerformanceProfile",
    "ProcessingStrategy",
    "ProfileBatch",
    "ProfilePersistResult",
    "SuperTrackProfile",
    "build_supertrack_movements",
    "get_processing_profile",
    "is_cancelled",
]
