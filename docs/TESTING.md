# Testing Guide

Guide for testing LucidLink Windows Client deployments.

---

## Quick Test

### Automated Test Script

Run the complete deployment lifecycle test automatically:

```bash
# 1. Configure credentials first (one-time setup)
uv run ll-win-client-aws.py
# Select Option 1: Configure Client Deployment
# Enter AWS and LucidLink credentials
# Exit (Option 9)

# 2. Run automated test
./test-deployment.sh
```

**What the test does:**
1. ✅ Deploys 1 instance (g4dn.xlarge)
2. ✅ Waits for instance to be ready
3. ✅ Verifies LucidLink mount via SSM
4. ✅ Stops instance
5. ✅ Starts instance
6. ✅ Verifies LucidLink still works after restart
7. ✅ Destroys all resources
8. ✅ Generates test results report

**Test Duration**: ~25-35 minutes

**Output**:
- Console output with real-time status
- Test results file: `test-results-YYYYMMDD-HHMMSS.md`

---

## Manual Test Plan

For detailed step-by-step manual testing, see: **[TEST-PLAN.md](TEST-PLAN.md)**

The manual test plan includes:
- 14 detailed test cases with checkboxes
- Expected vs actual result tracking
- DCV connection testing
- GPU verification
- Issue tracking template
- Cost analysis

---

## Test Script Details

### Prerequisites

Before running `./test-deployment.sh`:

1. **Configure credentials**:
   ```bash
   uv run ll-win-client-aws.py
   # Option 1: Configure Client Deployment
   ```

2. **Verify AWS CLI access**:
   ```bash
   aws sts get-caller-identity
   ```

3. **Subscribe to NVIDIA AMI** (one-time):
   - Visit: https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu
   - Click "Continue to Subscribe"

### What Gets Tested

| Test | Description | Verification Method |
|------|-------------|-------------------|
| Deploy Infrastructure | Terraform creates all resources | Terraform output |
| Instance Running | EC2 instance reaches running state | AWS CLI wait |
| Status Checks | Instance passes 2/2 status checks | AWS CLI wait |
| LucidLink Drive | L: drive exists | SSM PowerShell |
| LucidLink Service | Service is running | SSM PowerShell |
| LucidLink Mount | Filespace mounted | SSM `lucid status` |
| Stop Instance | Instance stops successfully | AWS CLI verify state |
| Start Instance | Instance starts successfully | AWS CLI verify state |
| Mount After Restart | LucidLink still works | SSM verification |
| Destroy Infrastructure | All resources removed | Terraform destroy |
| Instance Terminated | EC2 instance terminated | AWS CLI verify state |

### Test Results

After completion, you'll get:

**Console Output**:
```
========================================
TEST SUMMARY
========================================

Test End Time: Wed Nov  2 14:35:22 PDT 2025
Total Test Duration: 28 minutes 45 seconds

Deployment Time: 12 minutes 30 seconds
Stop Time: 2 minutes 15 seconds
Start Time: 1 minutes 50 seconds
Destroy Time: 8 minutes 10 seconds

✓ Tests Passed: 11
✗ Tests Failed: 0
Total Tests: 11

========================================
ALL TESTS PASSED ✓
========================================
```

**Test Results File** (`test-results-YYYYMMDD-HHMMSS.md`):
- Summary with pass/fail counts
- Timing for each phase
- Instance details
- Success rate percentage

---

## Troubleshooting Tests

### "Configuration not found"

**Problem**: `~/.ll-win-client/config.json` doesn't exist

**Solution**:
```bash
uv run ll-win-client-aws.py
# Select Option 1: Configure Client Deployment
# Enter credentials and settings
# Exit (Option 9)
```

### "Instance status checks timeout"

**Problem**: Status checks take longer than expected

**Cause**: First boot can take 15-20 minutes

**Solution**: Wait longer, test script includes appropriate waits

### "LucidLink mount verification failed"

**Possible causes**:
1. LucidLink credentials incorrect
2. Filespace not accessible
3. Network issues
4. UserData script failed

**Debug steps**:
```bash
# Get instance ID from test output, then:
aws ssm start-session --target <instance-id>

# Once connected, check log:
Get-Content C:\lucidlink-init.log

# Check service:
Get-Service -Name "Lucid"

# Check mount:
lucid status
```

### "SSM command timeout"

**Problem**: SSM agent not responding

**Solution**:
- Wait 5 more minutes for SSM agent initialization
- Check instance has SSM IAM role attached
- Verify security group allows outbound HTTPS

### Test script exits early

**Problem**: Script exits on error

**Cause**: `set -e` makes script exit on any error

**Solution**: Review error message, fix issue, rerun test

---

## Cost Estimation

**Test Cost** (approximate, us-east-1):

| Resource | Time | Cost |
|----------|------|------|
| g4dn.xlarge | ~30 min | ~$0.25 |
| EBS Storage | ~30 min | ~$0.01 |
| **Total** | | **~$0.26** |

**Note**: Actual cost may vary by region and exact runtime.

---

## Continuous Testing

### Run Tests Regularly

Recommended testing schedule:

- **Before production deployments**: Always run test
- **After code changes**: Run test to verify
- **Weekly**: Validate infrastructure still works
- **After AWS service changes**: Verify compatibility

### Automated CI/CD Integration

Add to your CI/CD pipeline:

```yaml
# Example GitHub Actions
- name: Test Deployment
  run: |
    uv sync
    ./test-deployment.sh
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

**Note**: Requires credentials stored as secrets and config.json committed (encrypted) or generated in CI.

---

## Test Scenarios

### Scenario 1: Quick Smoke Test

**Purpose**: Verify basic functionality
**Duration**: ~15 minutes

```bash
./test-deployment.sh
```

### Scenario 2: Full Manual Test

**Purpose**: Comprehensive testing including DCV, GPU, applications
**Duration**: ~45-60 minutes

Follow: [TEST-PLAN.md](TEST-PLAN.md)

### Scenario 3: Multi-Instance Test

**Purpose**: Test with multiple instances

**Steps**:
1. Configure for 3 instances: `uv run ll-win-client-aws.py` → Option 1
2. Modify `test-deployment.sh` to loop through all instances
3. Run test

### Scenario 4: Performance Test

**Purpose**: Measure deployment speed and resource performance

**Additional checks**:
- Time to DCV connection
- GPU performance (nvidia-smi)
- LucidLink mount performance
- Network throughput

---

## Test Data

### Sample Test Configuration

**AWS**:
- Region: us-east-1
- Instance Type: g4dn.xlarge
- Volume Size: 100GB
- VPC CIDR: 10.0.0.0/16

**LucidLink**:
- Filespace: (your test filespace)
- Mount Point: L:

**Expected Results**:
- Deployment: 10-15 minutes
- Stop: 2-3 minutes
- Start: 1-2 minutes
- Destroy: 5-10 minutes

---

## Reporting Issues

If tests fail:

1. **Capture test results file**: `test-results-*.md`
2. **Save logs**:
   ```bash
   # Script log
   ls -la /tmp/ll-win-client-aws-*.log

   # Terraform logs
   cd terraform/clients
   terraform show
   ```
3. **Screenshot error messages**
4. **Open GitHub issue**: https://github.com/dmcp718/ll-win-client-aws/issues

Include:
- Test results file
- Error messages
- AWS region
- Instance type
- Terraform version
- AWS CLI version

---

## Related Documentation

- **[TEST-PLAN.md](TEST-PLAN.md)** - Detailed manual test plan with 14 test cases
- **[DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md)** - Complete deployment walkthrough
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[Main README](../README.md)** - Project overview and quick start

---

**Last Updated**: 2025-11-02
