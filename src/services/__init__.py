"""Service layer exports.

`CompaniesHouseApiService` is imported from `src.services.api_service` directly: it depends on the
ETL package, and re-exporting it here would create an import cycle (etl -> intelligence -> services).
"""
from src.services.db_service import DatabaseService
from src.services.geo_service import GeoService, haversine_km, resolve_postcode_coords
from src.services.vector_service import VectorService, cosine_ngram_similarity

__all__ = [
    "DatabaseService",
    "GeoService",
    "VectorService",
    "cosine_ngram_similarity",
    "haversine_km",
    "resolve_postcode_coords",
]
