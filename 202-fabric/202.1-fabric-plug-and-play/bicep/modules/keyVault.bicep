// modules/keyVault.bicep
param name                    string
param location                string
param tags                    object
param servicePrincipalObjectId string   // SP — used for local/CI deployments
param logAnalyticsWorkspaceId  string

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name:     name
  location: location
  tags:     tags
  properties: {
    sku:      { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableSoftDelete:        true
    softDeleteRetentionInDays: 7
    enableRbacAuthorization:  false   // using access policies for simplicity
    accessPolicies: [
      // Service Principal — full secrets access (local dev / CI)
      {
        tenantId: subscription().tenantId
        objectId: servicePrincipalObjectId
        permissions: {
          secrets: [ 'get', 'list', 'set', 'delete' ]
        }
      }
    ]
    networkAcls: {
      bypass:        'AzureServices'
      defaultAction: 'Allow'           // tighten per environment in prod
    }
  }
}

// ── Diagnostic settings ───────────────────────────────────────
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name:  'diag-${name}'
  scope: kv
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { category: 'AuditEvent',              enabled: true }
      { category: 'AzurePolicyEvaluationDetails', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output name       string = kv.name
output vaultUri   string = kv.properties.vaultUri
output resourceId string = kv.id
