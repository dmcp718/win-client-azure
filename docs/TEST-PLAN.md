# Test Plan - LucidLink Windows Client Deployment

**Test Date**: _________
**Tester**: _________
**AWS Region**: _________
**LucidLink Filespace**: _________

---

## Test Objectives

Verify the complete lifecycle of a single Windows instance deployment:
1. Deploy instance with LucidLink auto-configuration
2. Verify LucidLink mount is successful
3. Stop instance to validate cost-saving feature
4. Start instance and verify functionality
5. Destroy instance and verify cleanup

---

## Prerequisites

- [ ] AWS credentials configured (IAM user or admin)
- [ ] Subscribed to NVIDIA RTX AMI: https://aws.amazon.com/marketplace/pp/prodview-f4reygwmtxipu
- [ ] LucidLink credentials available (filespace, username, password)
- [ ] Terraform installed and verified: `terraform -version`
- [ ] AWS CLI installed and verified: `aws --version`
- [ ] Python 3.8+ and uv installed
- [ ] Repository cloned: `git clone https://github.com/dmcp718/ll-win-client-aws.git`
- [ ] Dependencies installed: `uv sync`
- [ ] Amazon DCV client installed on local machine

**Start Time**: _________

---

## Test Case 1: Configuration

**Objective**: Configure deployment settings

**Steps**:
1. Run script: `uv run ll-win-client-aws.py`
2. Select **Option 1: Configure Client Deployment**
3. Enter AWS configuration:
   - AWS Region: _________
   - AWS Access Key ID: _________
   - AWS Secret Access Key: _________
   - VPC CIDR block: (use default or enter custom)
4. Enter LucidLink configuration:
   - Filespace domain: _________
   - Username: _________
   - Password: _________
   - Mount point drive: (use default L:)
5. Enter instance configuration:
   - Instance type: g4dn.xlarge (recommended for test)
   - Number of instances: **1**
   - Root volume size: (use default 100GB)
   - SSH key: (optional, press Enter to skip)

**Expected Results**:
- [ ] Configuration saved successfully
- [ ] Config file created at: `~/.ll-win-client/config.json`
- [ ] Success message displayed

**Actual Results**: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 2: View Configuration

**Objective**: Verify configuration was saved correctly

**Steps**:
1. Select **Option 2: View Configuration**
2. Review displayed settings

**Expected Results**:
- [ ] All AWS settings displayed correctly
- [ ] LucidLink filespace domain shown
- [ ] Instance type shows g4dn.xlarge
- [ ] Instance count shows 1
- [ ] Credentials are obfuscated (not shown in plain text)

**Actual Results**: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 3: Deploy Instance

**Objective**: Deploy single Windows instance with LucidLink

**Steps**:
1. Select **Option 3: Deploy Client Instances**
2. Review Terraform plan
3. Confirm deployment
4. Wait for deployment to complete (10-15 minutes expected)

**Expected Results**:
- [ ] Terraform plan shows resources to be created:
  - 1 VPC
  - 1 Subnet
  - 1 Internet Gateway
  - 1 Security Group
  - 1 EC2 Instance
  - 1 IAM Role
  - 1 Secrets Manager Secret
  - 1 CloudWatch Log Group
- [ ] Deployment completes without errors
- [ ] Success message displayed
- [ ] DCV connection files created at: `~/Desktop/LucidLink-DCV/`
- [ ] Files include:
  - `ll-win-client-1.dcv`
  - `PASSWORDS.txt`

**Actual Results**: _________

**Terraform Output** (copy instance ID): _________

**Deployment Time**: _________ minutes

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 4: Verify Deployment Status

**Objective**: Check instance is running

**Steps**:
1. Select **Option 4: View Deployment Status**
2. Review instance information

**Expected Results**:
- [ ] Instance status shows "running"
- [ ] Public IP address displayed
- [ ] Instance ID displayed
- [ ] All status checks passing (may take 5-10 minutes)

**Actual Results**:
- Instance ID: _________
- Public IP: _________
- Status: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 5: DCV Connection

**Objective**: Connect to instance via Amazon DCV

**Steps**:
1. Wait 15-20 minutes after deployment for full initialization
2. Navigate to `~/Desktop/LucidLink-DCV/`
3. Open `PASSWORDS.txt` and copy password
4. Double-click `ll-win-client-1.dcv`
5. DCV client should launch
6. Enter credentials:
   - Username: `Administrator`
   - Password: (from PASSWORDS.txt)
7. Accept any certificate warnings

**Expected Results**:
- [ ] DCV client opens connection dialog
- [ ] Connection succeeds
- [ ] Windows desktop displayed
- [ ] No errors or black screen

**Actual Results**: _________

**Connection Time**: _________ minutes after deployment

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

**Note**: If connection fails, wait longer (up to 20 minutes) and retry.

---

## Test Case 6: Verify LucidLink Mount

**Objective**: Confirm LucidLink is installed and mounted

**Steps** (via DCV session):
1. Open File Explorer
2. Check for `L:` drive
3. Open PowerShell and run:
   ```powershell
   Get-PSDrive L
   ```
4. Check LucidLink service:
   ```powershell
   Get-Service -Name "Lucid"
   ```
5. Verify mount with LucidLink CLI:
   ```powershell
   lucid status
   ```
6. View initialization log:
   ```powershell
   Get-Content C:\lucidlink-init.log -Tail 50
   ```

**Expected Results**:
- [ ] `L:` drive visible in File Explorer
- [ ] `Get-PSDrive L` shows LucidLink provider
- [ ] Lucid service status is "Running"
- [ ] `lucid status` shows filespace mounted
- [ ] `lucidlink-init.log` shows successful installation and mount
- [ ] Can browse `L:\` drive and see filespace contents

**Actual Results**:
- L: drive present: ⬜ Yes ⬜ No
- Lucid service status: _________
- Mount status: _________
- Log errors (if any): _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 7: Verify GPU and DCV

**Objective**: Confirm GPU is accessible and DCV is working properly

**Steps** (via DCV session):
1. Open Device Manager (devmgmt.msc)
2. Expand "Display adapters"
3. Verify NVIDIA T4 GPU present
4. Open Command Prompt and run:
   ```cmd
   nvidia-smi
   ```
5. Check DCV service:
   ```powershell
   Get-Service -Name "DCV Server"
   ```

**Expected Results**:
- [ ] NVIDIA Tesla T4 GPU visible in Device Manager
- [ ] `nvidia-smi` shows GPU details (driver version, memory, etc.)
- [ ] DCV Server service is "Running"
- [ ] No graphics artifacts or performance issues in DCV session

**Actual Results**: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 8: Stop Instance

**Objective**: Test stop functionality for cost savings

**Steps**:
1. Disconnect from DCV session
2. Return to script main menu
3. Select **Option 6: Stop All Instances**
4. Confirm stop action
5. Wait for instances to stop (2-5 minutes)

**Expected Results**:
- [ ] Script identifies running instance
- [ ] Confirmation prompt displayed
- [ ] Stop operation initiated
- [ ] Success message: "All instances have been stopped"
- [ ] Reminder about storage costs displayed
- [ ] No errors during stop

**Actual Results**: _________

**Stop Time**: _________ minutes

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 9: Verify Instance Stopped

**Objective**: Confirm instance is in stopped state

**Steps**:
1. Select **Option 4: View Deployment Status**
2. Verify instance status
3. Try to connect via DCV (should fail)
4. Check AWS Console (optional)

**Expected Results**:
- [ ] Instance status shows "stopped"
- [ ] DCV connection fails (expected)
- [ ] Instance still exists (not terminated)
- [ ] Public IP may be released (expected behavior)

**Actual Results**:
- Instance status: _________
- DCV connection: ⬜ Failed (expected) ⬜ Success (unexpected)

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 10: Start Instance

**Objective**: Test start functionality and verify instance resumes

**Steps**:
1. Select **Option 7: Start All Instances**
2. Confirm start action
3. Wait for instances to start (2-5 minutes)

**Expected Results**:
- [ ] Script identifies stopped instance
- [ ] Confirmation prompt displayed
- [ ] Start operation initiated
- [ ] Success message: "All instances have been started"
- [ ] Connection file location displayed
- [ ] No errors during start

**Actual Results**: _________

**Start Time**: _________ minutes

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 11: Verify Instance Restarted

**Objective**: Confirm instance is running and accessible

**Steps**:
1. Select **Option 4: View Deployment Status**
2. Wait 5 minutes for instance to fully initialize
3. Reconnect via DCV using `ll-win-client-1.dcv`
4. Verify LucidLink mount still works

**Expected Results**:
- [ ] Instance status shows "running"
- [ ] New public IP assigned (may differ from original)
- [ ] DCV connection succeeds
- [ ] `L:` drive still mounted
- [ ] LucidLink service running
- [ ] All data accessible

**Actual Results**:
- New public IP: _________
- DCV connection: ⬜ Success ⬜ Fail
- L: drive status: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 12: Regenerate Connection Files

**Objective**: Test connection file regeneration

**Steps**:
1. Disconnect from DCV
2. Select **Option 5: Regenerate Connection Files (DCV)**
3. Confirm password retrieval

**Expected Results**:
- [ ] Script retrieves current instance information
- [ ] Password retrieved via SSM
- [ ] New DCV files generated
- [ ] Files updated at: `~/Desktop/LucidLink-DCV/`
- [ ] Connection works with regenerated files

**Actual Results**: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 13: Destroy Instance

**Objective**: Clean up all resources

**Steps**:
1. Select **Option 8: Destroy Client Instances**
2. Type "yes" to confirm destruction
3. Wait for Terraform destroy to complete (5-10 minutes)

**Expected Results**:
- [ ] Confirmation prompt displayed
- [ ] Terraform destroy plan shown
- [ ] All resources destroyed:
  - EC2 Instance terminated
  - VPC deleted
  - Subnet deleted
  - Internet Gateway deleted
  - Security Group deleted
  - IAM Role deleted
  - Secrets Manager Secret deleted
  - CloudWatch Log Group deleted
- [ ] Success message displayed
- [ ] No errors during destruction

**Actual Results**: _________

**Destroy Time**: _________ minutes

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Case 14: Verify Complete Cleanup

**Objective**: Confirm all AWS resources removed

**Steps**:
1. Select **Option 4: View Deployment Status**
2. Check for any remaining resources
3. Verify in AWS Console (optional):
   - EC2 → Instances (should show terminated)
   - VPC → Your VPCs (ll-win-client-vpc should be gone)
   - Secrets Manager (ll-win-client secret should be gone)

**Expected Results**:
- [ ] Script reports no instances found or deployment not found
- [ ] No ll-win-client resources in AWS Console
- [ ] Terraform state clean

**Actual Results**: _________

**Status**: ⬜ Pass ⬜ Fail ⬜ Blocked

**Time Completed**: _________

---

## Test Results Summary

**Total Test Cases**: 14
**Passed**: ___ / 14
**Failed**: ___ / 14
**Blocked**: ___ / 14

**Total Test Duration**: _________ minutes

### Pass/Fail Criteria

- **PASS**: All critical test cases (3, 6, 8, 9, 13, 14) must pass
- **FAIL**: Any critical test case fails

**Overall Result**: ⬜ PASS ⬜ FAIL

---

## Issues Found

| Test Case # | Issue Description | Severity | Status |
|-------------|-------------------|----------|--------|
| | | ⬜ Critical ⬜ Major ⬜ Minor | ⬜ Open ⬜ Resolved |
| | | ⬜ Critical ⬜ Major ⬜ Minor | ⬜ Open ⬜ Resolved |
| | | ⬜ Critical ⬜ Major ⬜ Minor | ⬜ Open ⬜ Resolved |

**Severity Definitions**:
- **Critical**: Blocks test completion or causes data loss
- **Major**: Significant functionality broken, workaround exists
- **Minor**: Cosmetic or minor inconvenience

---

## Notes and Observations

_Record any additional observations, performance notes, or suggestions here_:

```
[Your notes here]
```

---

## Log Files Collected

- [ ] Script log: `/tmp/ll-win-client-aws-*.log`
- [ ] Instance log: `C:\lucidlink-init.log` (via DCV)
- [ ] CloudWatch logs: `/aws/ec2/ll-win-client`
- [ ] Terraform state: `terraform/clients/terraform.tfstate` (if debugging needed)

---

## Cost Analysis

**Estimated Total Cost for Test** (approximate):
- Instance runtime: _________ hours × $0.50/hour = $__________
- Storage: _________ hours × $0.01/hour = $__________
- **Total**: $__________

---

## Sign-off

**Tester Signature**: ________________________
**Date**: _________

**Review Notes**: _________

---

**Test Plan Version**: 1.0
**Last Updated**: 2025-11-02
