"""Brand settings supplied by consumers of the generic web shell."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Brand:
    product_name: str
    provider_label: str
    client_label: str
    logo_url: str = "/logo.png"
    accent: str = "ambar"
