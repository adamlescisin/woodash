import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TENANT_DIR = Path(os.environ.get("TENANT_DIR", Path(__file__).resolve().parents[2] / "tenants"))


@dataclass
class Tenant:
    id: str
    name: str
    currency: str
    timezone: str
    database_url_env: str
    email: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    vat_payer: bool = True
    woo: dict = field(default_factory=dict)
    margin: dict = field(default_factory=dict)
    ga4: dict = field(default_factory=dict)

    @property
    def database_url(self) -> str:
        return os.environ[self.database_url_env]

    def has(self, flag: str) -> bool:
        return bool(self.features.get(flag))


def load_tenant(tenant_id: str) -> Tenant:
    path = TENANT_DIR / f"{tenant_id}.yml"
    if not path.exists():
        raise KeyError(f"unknown tenant {tenant_id!r}")
    return Tenant(**yaml.safe_load(path.read_text()))


def woo_client(tenant: Tenant):
    from .woo import WooClient

    w = tenant.woo
    return WooClient(os.environ[w["url_env"]], os.environ[w["key_env"]], os.environ[w["secret_env"]])
