"""
fabric_start.py — Azure Automation Runbook
───────────────────────────────────────────
Starts the Fabric Capacity for the target environment.
Uses Managed Identity — no credentials required.

Parameters (Automation Variables, set in the Automation Account):
  - FABRIC_ENV           : dev | prod
  - FABRIC_SUBSCRIPTION  : Azure Subscription ID
  - FABRIC_RESOURCE_GROUP: Resource Group name
  - FABRIC_CAPACITY_NAME : Fabric Capacity resource name
"""

import logging
import os
import sys
import automationassets  # Available inside Azure Automation runtime

import requests
from azure.identity import ManagedIdentityCredential

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

AZURE_MGMT = "https://management.azure.com"


def get_automation_variable(name: str) -> str:
    """Read an Automation Account Variable (encrypted or plain)."""
    return automationassets.get_automation_variable(name)


def get_mgmt_token() -> str:
    credential = ManagedIdentityCredential()
    token = credential.get_token(f"{AZURE_MGMT}/.default")
    return token.token


def start_capacity(sub: str, rg: str, name: str, token: str):
    url = (
        f"{AZURE_MGMT}/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Fabric/capacities/{name}/resume"
        f"?api-version=2023-11-01"
    )
    log.info(f"Sending START to Fabric capacity: {name}")
    resp = requests.post(url, headers={"Authorization": f"Bearer {token}"})

    if resp.status_code in (200, 202):
        log.info("✅ Fabric capacity start request accepted.")
    else:
        log.error(f"❌ Failed: HTTP {resp.status_code} — {resp.text}")
        raise Exception(f"Start failed: {resp.text}")


def main():
    log.info("=== Runbook: fabric_start ===")

    sub  = get_automation_variable("FABRIC_SUBSCRIPTION")
    rg   = get_automation_variable("FABRIC_RESOURCE_GROUP")
    name = get_automation_variable("FABRIC_CAPACITY_NAME")

    log.info(f"Target: {name} in {rg} ({sub})")

    token = get_mgmt_token()
    start_capacity(sub, rg, name, token)

    log.info("=== Runbook completed ===")


if __name__ == "__main__":
    main()
