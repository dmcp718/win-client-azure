# LucidLink Azure Blob Storage Setup

## Overview

This document describes the Azure Blob Storage configuration for LucidLink Filespace.

## Created Resources

### Resource Group
- **Name**: `lucidlink-storage-rg`
- **Location**: `eastus`
- **Purpose**: Container for LucidLink storage resources

### Storage Account
- **Name**: `llstorage249558354`
- **Location**: `eastus`
- **SKU**: Standard_LRS (Locally Redundant Storage)
- **Kind**: StorageV2
- **Performance Tier**: Standard
- **Access Tier**: Hot

### Storage Account Configuration (LucidLink-Compatible)

✅ **HTTPS Only**: Enabled (secure transfer required)
✅ **Blob Soft Delete**: Disabled (required for LucidLink)
✅ **Container Soft Delete**: Disabled (required for LucidLink)
✅ **Public Access**: Disabled (private container)
✅ **Minimum TLS Version**: 1.2
✅ **Hierarchical Namespace**: Disabled (LucidLink provides the namespace)

### Blob Container
- **Name**: `lucidlink-filespace`
- **Public Access**: Off (private)
- **Endpoint**: `https://llstorage249558354.blob.core.windows.net`

## LucidLink Initialization

Use the following command to initialize a LucidLink filespace with this storage:

```bash
lucid init-azure \
  --fs <your-filespace.domain> \
  --https \
  --account-name llstorage249558354 \
  --account-key '<your-storage-account-key>' \
  --container-name lucidlink-filespace \
  --block-size 256K
```

**Important**: Replace the placeholders:
- `<your-filespace.domain>` with your actual filespace domain (e.g., `myproject.lucidlink`)
- `<your-storage-account-key>` with the key from `lucidlink-azure-config.txt`

## Configuration File

Detailed configuration has been saved to `lucidlink-azure-config.txt` including:
- Storage account name and key
- Container name
- Blob endpoint
- Initialization command

## Key Features

### Security
- All traffic is HTTPS-only
- Storage account key authentication
- Private container (no public access)
- TLS 1.2 minimum encryption

### Redundancy
- **Standard_LRS**: 3 copies within a single datacenter
- **Upgrade Option**: Change to Standard_GRS for geo-redundant storage (6 copies across two regions)

### Performance
- **Hot Access Tier**: Optimized for frequently accessed data
- **Standard Performance**: Cost-effective for most workloads

## Important Notes

1. **Save the Storage Account Key**: The key is required to initialize and access the LucidLink filespace
2. **Soft Delete Disabled**: Required for LucidLink compatibility - do not enable
3. **Block Size**: 256K recommended for optimal performance
4. **Container**: Can be changed, but update the initialization command accordingly

## Cleanup

To remove all resources:

```bash
az group delete --name lucidlink-storage-rg --yes --no-wait
```

## Cost Estimate

- **Storage**: ~$0.018/GB/month (Hot tier, LRS)
- **Transactions**: Varies based on usage
- **Data Transfer**: Outbound data transfer charges apply

## Integration with Windows VMs

The LucidLink client on Windows VMs will connect to this storage backend. The VM deployment already includes:
- LucidLink client installation
- Windows Service configuration
- Automatic mounting to drive letter

## References

- [LucidLink Azure Documentation](https://support.lucidlink.com/hc/en-us/articles/34440380130829-Microsoft-Azure)
- [Azure Blob Storage Pricing](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/)
- [LucidLink Init Command Reference](https://support.lucidlink.com/)
