# deploy.ps1
# ─────────────────────────────────────────────────────────────
# Deploys the full Fabric Plug & Play infrastructure via Bicep.
# Usage:
#   .\deploy.ps1 -Env dev
#   .\deploy.ps1 -Env prod
# ─────────────────────────────────────────────────────────────

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("dev","prod")]
    [string]$Env,

    [string]$Location = "eastus"
)

$ErrorActionPreference = "Stop"

Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Fabric Plug & Play — Deploy [$Env]"    -ForegroundColor Cyan
Write-Host "════════════════════════════════════════" -ForegroundColor Cyan

# ── Load env config ───────────────────────────────────────────
$ConfigFile = "$PSScriptRoot/../config/env-$Env.json"
if (-not (Test-Path $ConfigFile)) {
    Write-Error "Config not found: $ConfigFile"
    exit 1
}
$Config = Get-Content $ConfigFile | ConvertFrom-Json

$SubscriptionId         = $Config.azure.subscription_id
$ServicePrincipalObjId  = Read-Host "Service Principal Object ID (for Key Vault access)"
$FabricAdminEmail       = $Config.fabric.admin_email

# ── Set subscription ──────────────────────────────────────────
Write-Host "`n[1/4] Setting subscription: $SubscriptionId" -ForegroundColor Yellow
az account set --subscription $SubscriptionId

# ── Validate Bicep ────────────────────────────────────────────
Write-Host "`n[2/4] Validating Bicep template..." -ForegroundColor Yellow
az deployment sub validate `
    --location $Location `
    --template-file "$PSScriptRoot/../bicep/main.bicep" `
    --parameters `
        environment=$Env `
        location=$Location `
        fabricAdminEmail=$FabricAdminEmail `
        servicePrincipalObjectId=$ServicePrincipalObjId

if ($LASTEXITCODE -ne 0) {
    Write-Error "Bicep validation failed."
    exit 1
}
Write-Host "✅ Validation passed." -ForegroundColor Green

# ── Deploy ────────────────────────────────────────────────────
Write-Host "`n[3/4] Deploying infrastructure..." -ForegroundColor Yellow
$DeploymentName = "fpp-deploy-$Env-$(Get-Date -Format 'yyyyMMddHHmm')"

$Output = az deployment sub create `
    --name $DeploymentName `
    --location $Location `
    --template-file "$PSScriptRoot/../bicep/main.bicep" `
    --parameters `
        environment=$Env `
        location=$Location `
        fabricAdminEmail=$FabricAdminEmail `
        servicePrincipalObjectId=$ServicePrincipalObjId `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deployment failed."
    exit 1
}

# ── Post-deploy: upload Runbooks ──────────────────────────────
Write-Host "`n[4/4] Uploading Runbooks to Automation Account..." -ForegroundColor Yellow
$RgName = $Output.properties.outputs.resourceGroupName.value
$AaName = $Output.properties.outputs.automationAccountName.value

foreach ($Runbook in @("fabric_start", "fabric_stop")) {
    $RunbookFile = "$PSScriptRoot/../runbooks/$Runbook.py"
    Write-Host "  → $Runbook"
    az automation runbook create `
        --resource-group $RgName `
        --automation-account-name $AaName `
        --name $Runbook `
        --type Python3 `
        --location $Location | Out-Null

    az automation runbook replace-content `
        --resource-group $RgName `
        --automation-account-name $AaName `
        --name $Runbook `
        --content "@$RunbookFile" | Out-Null

    az automation runbook publish `
        --resource-group $RgName `
        --automation-account-name $AaName `
        --name $Runbook | Out-Null
}

Write-Host "`n════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ Deployment complete!"                  -ForegroundColor Green
Write-Host "  Resource Group  : $RgName"               -ForegroundColor Green
Write-Host "  Automation Acct : $AaName"               -ForegroundColor Green
Write-Host "════════════════════════════════════════`n" -ForegroundColor Green
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. Set Automation Account Variables (see automation/schedule.json)" -ForegroundColor White
Write-Host "  2. Assign 'Contributor' role to the Automation Account Managed Identity on the Resource Group" -ForegroundColor White
Write-Host "  3. Run: python scripts/manage_fabric_capacity.py --env $Env --action status" -ForegroundColor White
