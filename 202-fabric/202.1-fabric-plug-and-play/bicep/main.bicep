// =============================================================
// main.bicep — Fabric Plug & Play
// Scope: Subscription (required for Resource Group creation)
// =============================================================
targetScope = 'subscription'

// ── Parameters ───────────────────────────────────────────────
@description('Environment name: dev | prod')
@allowed(['dev', 'prod'])
param environment string

@description('Azure region for all resources')
param location string = 'eastus'

@description('Project prefix used in all resource names')
param projectPrefix string = 'fpp'

@description('Fabric Capacity SKU: F2 or F4')
@allowed(['F2', 'F4'])
param fabricSku string = 'F2'

@description('Admin email for Fabric Capacity')
param fabricAdminEmail string

@description('Object ID of the Service Principal (for Key Vault access policy)')
param servicePrincipalObjectId string

@description('Tags applied to all resources')
param tags object = {
  project: 'fabric-plug-and-play'
  environment: environment
  managedBy: 'bicep'
}

// ── Naming convention ────────────────────────────────────────
var baseName = '${projectPrefix}-${environment}'
var rgName   = 'rg-${baseName}'

// ── Resource Group ───────────────────────────────────────────
module rg 'modules/resourceGroup.bicep' = {
  name: 'deploy-rg'
  params: {
    name:     rgName
    location: location
    tags:     tags
  }
}

// ── Log Analytics Workspace ──────────────────────────────────
module logAnalytics 'modules/logAnalytics.bicep' = {
  name:  'deploy-loganalytics'
  scope: resourceGroup(rgName)
  dependsOn: [rg]
  params: {
    name:     'law-${baseName}'
    location: location
    tags:     tags
  }
}

// ── Key Vault ────────────────────────────────────────────────
module keyVault 'modules/keyVault.bicep' = {
  name:  'deploy-keyvault'
  scope: resourceGroup(rgName)
  dependsOn: [rg]
  params: {
    name:                   'kv-${baseName}'
    location:               location
    tags:                   tags
    servicePrincipalObjectId: servicePrincipalObjectId
    logAnalyticsWorkspaceId:  logAnalytics.outputs.workspaceId
  }
}

// ── Automation Account ───────────────────────────────────────
module automationAccount 'modules/automationAccount.bicep' = {
  name:  'deploy-automation'
  scope: resourceGroup(rgName)
  dependsOn: [rg, logAnalytics]
  params: {
    name:                    'aa-${baseName}'
    location:                location
    tags:                    tags
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
  }
}

// ── Fabric Capacity ──────────────────────────────────────────
module fabricCapacity 'modules/fabricCapacity.bicep' = {
  name:  'deploy-fabric'
  scope: resourceGroup(rgName)
  dependsOn: [rg]
  params: {
    name:        'fabric-${baseName}'
    location:    location
    tags:        tags
    sku:         fabricSku
    adminEmail:  fabricAdminEmail
  }
}

// ── Outputs ──────────────────────────────────────────────────
output resourceGroupName      string = rgName
output automationAccountName  string = automationAccount.outputs.name
output keyVaultName           string = keyVault.outputs.name
output fabricCapacityName     string = fabricCapacity.outputs.name
output logAnalyticsWorkspaceId string = logAnalytics.outputs.workspaceId
