// modules/resourceGroup.bicep
// targetScope must be subscription for RG creation
targetScope = 'subscription'

param name     string
param location string
param tags     object

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name:     name
  location: location
  tags:     tags
}

output name     string = rg.name
output location string = rg.location
