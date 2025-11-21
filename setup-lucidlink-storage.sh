#!/bin/bash
#
# Azure Blob Storage Setup for LucidLink Filespace
# Based on LucidLink Azure configuration requirements
#

set -e

# Configuration
RESOURCE_GROUP="lucidlink-storage-rg"
LOCATION="eastus"
STORAGE_ACCOUNT_NAME="llstorage${RANDOM}${RANDOM}"  # Must be globally unique, lowercase, alphanumeric
CONTAINER_NAME="lucidlink-filespace"
SKU="Standard_LRS"  # Locally redundant storage (change to Standard_GRS for geo-redundant)

echo "========================================="
echo "LucidLink Azure Blob Storage Setup"
echo "========================================="
echo ""
echo "Configuration:"
echo "  Resource Group: ${RESOURCE_GROUP}"
echo "  Location: ${LOCATION}"
echo "  Storage Account: ${STORAGE_ACCOUNT_NAME}"
echo "  Container: ${CONTAINER_NAME}"
echo "  SKU: ${SKU}"
echo ""

# Check if logged in to Azure
echo "Checking Azure CLI login status..."
if ! az account show &>/dev/null; then
    echo "ERROR: Not logged in to Azure. Please run 'az login' first."
    exit 1
fi

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo "Using subscription: ${SUBSCRIPTION_ID}"
echo ""

# Create Resource Group
echo "Creating resource group..."
az group create \
    --name "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --tags \
        Purpose="LucidLink Storage" \
        ManagedBy="Azure CLI"

echo ""

# Create Storage Account with LucidLink-compatible settings
echo "Creating storage account..."
az storage account create \
    --name "${STORAGE_ACCOUNT_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --sku "${SKU}" \
    --kind StorageV2 \
    --access-tier Hot \
    --https-only true \
    --allow-blob-public-access false \
    --min-tls-version TLS1_2 \
    --tags \
        Purpose="LucidLink Filespace Storage" \
        ManagedBy="Azure CLI"

echo ""

# Disable blob soft delete (required for LucidLink)
echo "Configuring blob service properties (disabling soft delete)..."
az storage account blob-service-properties update \
    --account-name "${STORAGE_ACCOUNT_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --enable-delete-retention false \
    --enable-container-delete-retention false

echo ""

# Get storage account key
echo "Retrieving storage account key..."
STORAGE_KEY=$(az storage account keys list \
    --resource-group "${RESOURCE_GROUP}" \
    --account-name "${STORAGE_ACCOUNT_NAME}" \
    --query '[0].value' -o tsv)

echo ""

# Create blob container
echo "Creating blob container..."
az storage container create \
    --name "${CONTAINER_NAME}" \
    --account-name "${STORAGE_ACCOUNT_NAME}" \
    --account-key "${STORAGE_KEY}" \
    --public-access off

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Storage Account Details:"
echo "  Name: ${STORAGE_ACCOUNT_NAME}"
echo "  Key: ${STORAGE_KEY}"
echo "  Container: ${CONTAINER_NAME}"
echo "  Endpoint: https://${STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
echo ""
echo "LucidLink Initialization Command:"
echo ""
echo "  lucid init-azure \\"
echo "    --fs <your-filespace.domain> \\"
echo "    --https \\"
echo "    --account-name ${STORAGE_ACCOUNT_NAME} \\"
echo "    --account-key '${STORAGE_KEY}' \\"
echo "    --container-name ${CONTAINER_NAME} \\"
echo "    --block-size 256K"
echo ""
echo "Configuration saved to: lucidlink-azure-config.txt"
echo ""

# Save configuration to file
cat > lucidlink-azure-config.txt <<EOF
# LucidLink Azure Blob Storage Configuration
# Generated: $(date)

Resource Group: ${RESOURCE_GROUP}
Location: ${LOCATION}
Storage Account Name: ${STORAGE_ACCOUNT_NAME}
Storage Account Key: ${STORAGE_KEY}
Container Name: ${CONTAINER_NAME}
Blob Endpoint: https://${STORAGE_ACCOUNT_NAME}.blob.core.windows.net

# LucidLink Initialization Command:
lucid init-azure \\
  --fs <your-filespace.domain> \\
  --https \\
  --account-name ${STORAGE_ACCOUNT_NAME} \\
  --account-key '${STORAGE_KEY}' \\
  --container-name ${CONTAINER_NAME} \\
  --block-size 256K

# Configuration Details:
- HTTPS Only: Enabled (secure transfer required)
- Blob Soft Delete: Disabled (required for LucidLink)
- Container Soft Delete: Disabled (required for LucidLink)
- Public Access: Disabled (private container)
- Minimum TLS Version: 1.2
- Performance Tier: Standard
- Redundancy: ${SKU}
- Access Tier: Hot
EOF

echo "IMPORTANT: Save the storage account key securely!"
echo "It will be needed to initialize the LucidLink filespace."
