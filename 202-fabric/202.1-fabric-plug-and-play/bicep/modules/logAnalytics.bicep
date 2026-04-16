// modules/logAnalytics.bicep
param name     string
param location string
param tags     object

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name:     name
  location: location
  tags:     tags
  properties: {
    sku:                  { name: 'PerGB2018' }
    retentionInDays:      30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery:     'Enabled'
  }
}

output workspaceId   string = law.id
output workspaceName string = law.name
output customerId    string = law.properties.customerId
