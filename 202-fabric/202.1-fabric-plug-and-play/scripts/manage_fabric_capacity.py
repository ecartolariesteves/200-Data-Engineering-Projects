"""
manage_fabric_capacity.py
─────────────────────────
Manages Azure Fabric Capacity: start, stop, and scale (F2 ↔ F4).

Auth modes:
  - service_principal  → used locally or in CI/CD
  - managed_identity   → used inside Azure Automation Runbooks

Usage:
  python manage_fabric_capacity.py --env dev --action start
  python manage_fabric_capacity.py --env prod --action scale --sku F4
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from azure.identity import ClientSecretCredential, ManagedIdentityCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.keyvault.secrets import SecretClient
import requests

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"

FABRIC_API = "https://api.fabric.microsoft.com/v1"
AZURE_MGMT = "https://management.azure.com"


# ── Config helpers ────────────────────────────────────────────
def load_config(env: str) -> dict:
    env_file = CONFIG_DIR / f"env-{env}.json"
    if not env_file.exists():
        raise FileNotFoundError(f"Config not found: {env_file}")
    with open(env_file) as f:
        cfg = json.load(f)
    fabric_file = CONFIG_DIR / "fabric-config.json"
    with open(fabric_file) as f:
        cfg["fabric_config"] = json.load(f)
    return cfg


# ── Authentication ────────────────────────────────────────────
def get_credential(cfg: dict):
    """
    Returns an Azure credential based on env config.
    - managed_identity → no secrets required (Runbook)
    - service_principal → reads secret from Key Vault or env var
    """
    mode = cfg["auth"]["mode"]

    if mode == "managed_identity":
        log.info("Auth: Managed Identity")
        return ManagedIdentityCredential()

    if mode == "service_principal":
        log.info("Auth: Service Principal")
        client_id = cfg["auth"]["client_id"]
        tenant_id = cfg["azure"]["tenant_id"]

        # Try env var first (CI/CD), then Key Vault
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        if not client_secret:
            log.info("Secret not in env — fetching from Key Vault...")
            client_secret = _get_secret_from_kv(cfg)

        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

    raise ValueError(f"Unknown auth mode: {mode}")


def _get_secret_from_kv(cfg: dict) -> str:
    kv_name = cfg["naming"]["key_vault"]
    kv_uri  = f"https://{kv_name}.vault.azure.net"
    secret_name = cfg["auth"]["client_secret_kv_name"]

    # Bootstrap credential using env vars for KV access
    bootstrap = ClientSecretCredential(
        tenant_id=cfg["azure"]["tenant_id"],
        client_id=cfg["auth"]["client_id"],
        client_secret=os.environ["AZURE_CLIENT_SECRET_BOOTSTRAP"],
    )
    client = SecretClient(vault_url=kv_uri, credential=bootstrap)
    return client.get_secret(secret_name).value


# ── Token helpers ─────────────────────────────────────────────
def get_fabric_token(credential) -> str:
    token = credential.get_token("https://analysis.windows.net/powerbi/api/.default")
    return token.token


def get_mgmt_token(credential) -> str:
    token = credential.get_token(f"{AZURE_MGMT}/.default")
    return token.token


# ── Fabric Capacity actions ───────────────────────────────────
def get_capacity_details(cfg: dict, mgmt_token: str) -> dict:
    sub  = cfg["azure"]["subscription_id"]
    rg   = cfg["naming"]["resource_group"]
    name = cfg["naming"]["fabric_capacity"]
    url  = f"{AZURE_MGMT}/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}?api-version=2023-11-01"

    resp = requests.get(url, headers={"Authorization": f"Bearer {mgmt_token}"})
    resp.raise_for_status()
    data = resp.json()
    log.info(f"Capacity '{name}' — State: {data['properties']['state']}, SKU: {data['sku']['name']}")
    return data


def start_capacity(cfg: dict, mgmt_token: str):
    sub  = cfg["azure"]["subscription_id"]
    rg   = cfg["naming"]["resource_group"]
    name = cfg["naming"]["fabric_capacity"]
    url  = f"{AZURE_MGMT}/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}/resume?api-version=2023-11-01"

    log.info(f"Starting Fabric capacity: {name}")
    resp = requests.post(url, headers={"Authorization": f"Bearer {mgmt_token}"})
    if resp.status_code in (200, 202):
        log.info("Start request accepted.")
    else:
        log.error(f"Failed to start: {resp.status_code} — {resp.text}")
        resp.raise_for_status()


def stop_capacity(cfg: dict, mgmt_token: str):
    sub  = cfg["azure"]["subscription_id"]
    rg   = cfg["naming"]["resource_group"]
    name = cfg["naming"]["fabric_capacity"]
    url  = f"{AZURE_MGMT}/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}/suspend?api-version=2023-11-01"

    log.info(f"Stopping Fabric capacity: {name}")
    resp = requests.post(url, headers={"Authorization": f"Bearer {mgmt_token}"})
    if resp.status_code in (200, 202):
        log.info("Stop request accepted.")
    else:
        log.error(f"Failed to stop: {resp.status_code} — {resp.text}")
        resp.raise_for_status()


def scale_capacity(cfg: dict, mgmt_token: str, new_sku: str):
    sub  = cfg["azure"]["subscription_id"]
    rg   = cfg["naming"]["resource_group"]
    name = cfg["naming"]["fabric_capacity"]
    url  = f"{AZURE_MGMT}/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Fabric/capacities/{name}?api-version=2023-11-01"

    payload = {"sku": {"name": new_sku, "tier": "Fabric"}}
    log.info(f"Scaling capacity '{name}' to {new_sku}")
    resp = requests.patch(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {mgmt_token}",
            "Content-Type":  "application/json",
        },
    )
    if resp.status_code in (200, 202):
        log.info(f"Scale to {new_sku} accepted.")
    else:
        log.error(f"Failed to scale: {resp.status_code} — {resp.text}")
        resp.raise_for_status()


# ── Entry point ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Manage Azure Fabric Capacity")
    parser.add_argument("--env",    required=True, choices=["dev", "prod"])
    parser.add_argument("--action", required=True, choices=["start", "stop", "scale", "status"])
    parser.add_argument("--sku",    default=None,  choices=["F2", "F4"],
                        help="Target SKU for scale action")
    args = parser.parse_args()

    cfg        = load_config(args.env)
    credential = get_credential(cfg)
    mgmt_token = get_mgmt_token(credential)

    if args.action == "status":
        get_capacity_details(cfg, mgmt_token)

    elif args.action == "start":
        get_capacity_details(cfg, mgmt_token)
        start_capacity(cfg, mgmt_token)

    elif args.action == "stop":
        get_capacity_details(cfg, mgmt_token)
        stop_capacity(cfg, mgmt_token)

    elif args.action == "scale":
        if not args.sku:
            parser.error("--sku is required for scale action")
        get_capacity_details(cfg, mgmt_token)
        scale_capacity(cfg, mgmt_token, args.sku)

    log.info("Done.")


if __name__ == "__main__":
    main()
