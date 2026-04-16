#!/usr/bin/env bash
# deploy.sh
# ─────────────────────────────────────────────────────────────
# Deploys the full Fabric Plug & Play infrastructure via Bicep.
# Usage:
#   ./scripts/deploy.sh dev
#   ./scripts/deploy.sh prod
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ENV="${1:-}"
if [[ -z "$ENV" || ! "$ENV" =~ ^(dev|prod)$ ]]; then
  echo "Usage: $0 <dev|prod>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/config/env-$ENV.json"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "❌ Config not found: $CONFIG_FILE"
  exit 1
fi

echo "════════════════════════════════════════"
echo "  Fabric Plug & Play — Deploy [$ENV]"
echo "════════════════════════════════════════"

# ── Read config ───────────────────────────────────────────────
SUBSCRIPTION_ID=$(jq -r '.azure.subscription_id'  "$CONFIG_FILE")
LOCATION=$(jq -r '.azure.location'                "$CONFIG_FILE")
FABRIC_ADMIN=$(jq -r '.fabric.admin_email'         "$CONFIG_FILE")

echo ""
read -rp "Service Principal Object ID (for Key Vault access): " SP_OBJECT_ID

# ── Set subscription ──────────────────────────────────────────
echo ""
echo "[1/4] Setting subscription: $SUBSCRIPTION_ID"
az account set --subscription "$SUBSCRIPTION_ID"

# ── Validate ──────────────────────────────────────────────────
echo ""
echo "[2/4] Validating Bicep template..."
az deployment sub validate \
  --location "$LOCATION" \
  --template-file "$ROOT_DIR/bicep/main.bicep" \
  --parameters \
    environment="$ENV" \
    location="$LOCATION" \
    fabricAdminEmail="$FABRIC_ADMIN" \
    servicePrincipalObjectId="$SP_OBJECT_ID"

echo "✅ Validation passed."

# ── Deploy ────────────────────────────────────────────────────
echo ""
echo "[3/4] Deploying infrastructure..."
DEPLOYMENT_NAME="fpp-deploy-$ENV-$(date +%Y%m%d%H%M)"

OUTPUT=$(az deployment sub create \
  --name "$DEPLOYMENT_NAME" \
  --location "$LOCATION" \
  --template-file "$ROOT_DIR/bicep/main.bicep" \
  --parameters \
    environment="$ENV" \
    location="$LOCATION" \
    fabricAdminEmail="$FABRIC_ADMIN" \
    servicePrincipalObjectId="$SP_OBJECT_ID" \
  --output json)

RG_NAME=$(echo "$OUTPUT" | jq -r '.properties.outputs.resourceGroupName.value')
AA_NAME=$(echo "$OUTPUT" | jq -r '.properties.outputs.automationAccountName.value')

# ── Upload Runbooks ───────────────────────────────────────────
echo ""
echo "[4/4] Uploading Runbooks to Automation Account..."

for RUNBOOK in fabric_start fabric_stop; do
  RUNBOOK_FILE="$ROOT_DIR/runbooks/$RUNBOOK.py"
  echo "  → $RUNBOOK"

  az automation runbook create \
    --resource-group "$RG_NAME" \
    --automation-account-name "$AA_NAME" \
    --name "$RUNBOOK" \
    --type Python3 \
    --location "$LOCATION" > /dev/null

  az automation runbook replace-content \
    --resource-group "$RG_NAME" \
    --automation-account-name "$AA_NAME" \
    --name "$RUNBOOK" \
    --content "@$RUNBOOK_FILE" > /dev/null

  az automation runbook publish \
    --resource-group "$RG_NAME" \
    --automation-account-name "$AA_NAME" \
    --name "$RUNBOOK" > /dev/null
done

echo ""
echo "════════════════════════════════════════"
echo "  ✅ Deployment complete!"
echo "  Resource Group  : $RG_NAME"
echo "  Automation Acct : $AA_NAME"
echo "════════════════════════════════════════"
echo ""
echo "NEXT STEPS:"
echo "  1. Set Automation Account Variables (see automation/schedule.json)"
echo "  2. Assign 'Contributor' role to the Automation Account Managed Identity on the Resource Group"
echo "  3. Run: python scripts/manage_fabric_capacity.py --env $ENV --action status"
