"""Identidade de cultura: normalização exata, sem inferir compatibilidade a partir de nomes de produtos."""

import unicodedata
from typing import Any


def normalize_crop(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value.strip().casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def product_supports_crop(product: dict[str, Any], crop: object) -> bool:
    requested = normalize_crop(crop)
    supported = product.get("supported_crops")
    return bool(requested and isinstance(supported, list) and requested in {normalize_crop(c) for c in supported})
