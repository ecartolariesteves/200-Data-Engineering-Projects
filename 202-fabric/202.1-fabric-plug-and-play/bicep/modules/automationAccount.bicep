// modules/automationAccount.bicep
param name                    string
param location                string
param tags                    object
param logAnalyticsWorkspaceId string

// ── Automation Account with System-Assigned Managed Identity ──
resource aa 'Microsoft.Automation/automationAccounts@2023-11-01' = {
  name:     name
  location: location
  tags:     tags
  identity: {
    type: 'SystemAssigned'  // MI used by Runbooks — no secrets needed
  }
  properties: {
    sku: { name: 'Basic' }
    publicNetworkAccess: true
    disableLocalAuth:    false
  }
}

// ── Diagnostic settings → Log Analytics ──────────────────────
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name:  'diag-${name}'
  scope: aa
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { category: 'JobLogs',        enabled: true }
      { category: 'JobStreams',      enabled: true }
      { category: 'DscNodeStatus',  enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// ── Outputs ───────────────────────────────────────────────────
output name        string = aa.name
output principalId string = aa.identity.principalId  // MI Object ID
output resourceId  string = aa.id
