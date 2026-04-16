// modules/fabricCapacity.bicep
param name       string
param location   string
param tags       object
param sku        string   // F2 | F4
param adminEmail string

resource fabricCapacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name:     name
  location: location
  tags:     tags
  sku: {
    name: sku
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: [ adminEmail ]
    }
  }
}

output name       string = fabricCapacity.name
output resourceId string = fabricCapacity.id
output state      string = fabricCapacity.properties.state
