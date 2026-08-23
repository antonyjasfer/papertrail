param accountName string = 'papertrailcosmosdev2026'
param location string = 'centralindia'
param tags object = {
  project: 'papertrail'
  environment: 'development'
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2025-11-01-preview' = {
  name: accountName
  location: location
  kind: 'GlobalDocumentDB'
  tags: tags

  properties: {
    databaseAccountOfferType: 'Standard'

    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }

    locations: [
      {
        locationName: 'centralindia'
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]

    enableFreeTier: true
    disableLocalAuth: true
    disableKeyBasedMetadataWriteAccess: true

    enableMultipleWriteLocations: false
    enableAutomaticFailover: false

    backupPolicy: {
      type: 'Continuous'
      continuousModeProperties: {
        tier: 'Continuous7Days'
      }
    }

    publicNetworkAccess: 'Enabled'
    isVirtualNetworkFilterEnabled: false
    networkAclBypass: 'None'
  }
}
