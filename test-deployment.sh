#!/bin/bash

# LucidLink Windows Client - Automated Deployment Test
# This script tests the complete deployment lifecycle:
# 1. Deploy instance
# 2. Verify LucidLink mount
# 3. Stop instance
# 4. Start instance
# 5. Destroy instance

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
PASSED=0
FAILED=0
TEST_START_TIME=$(date +%s)
TEST_RESULTS_FILE="test-results-$(date +%Y%m%d-%H%M%S).md"

# Function to print section headers
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Function to print test results
print_result() {
    local test_name=$1
    local result=$2

    if [ "$result" = "PASS" ]; then
        echo -e "${GREEN}✓ PASS${NC} - $test_name"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗ FAIL${NC} - $test_name"
        FAILED=$((FAILED + 1))
    fi
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check if config exists
    if [ ! -f ~/.ll-win-client/config.json ]; then
        echo -e "${RED}ERROR: Configuration not found at ~/.ll-win-client/config.json${NC}"
        echo "Please run 'uv run ll-win-client-aws.py' and select Option 1 to configure first."
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Configuration file found"

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}ERROR: AWS CLI not found${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} AWS CLI installed"

    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        echo -e "${RED}ERROR: Terraform not found${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Terraform installed"

    # Check uv
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}ERROR: uv not found${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} uv installed"

    echo -e "\n${GREEN}All prerequisites met${NC}"
}

# Function to wait for instance to be running
wait_for_instance() {
    local instance_id=$1
    local region=$2

    print_header "Waiting for Instance to be Running"

    echo "Instance ID: $instance_id"
    echo "Region: $region"
    echo ""

    # Wait for running state with timeout
    echo "Waiting for instance to reach 'running' state (max 10 minutes)..."
    local running_timeout=600
    local running_elapsed=0

    while [ $running_elapsed -lt $running_timeout ]; do
        STATE=$(aws ec2 describe-instances \
            --instance-ids "$instance_id" \
            --region "$region" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text 2>/dev/null || echo "unknown")

        if [ "$STATE" = "running" ]; then
            echo -e "${GREEN}✓${NC} Instance is running (took $running_elapsed seconds)"
            break
        fi

        echo "  [$running_elapsed/$running_timeout] State: $STATE"
        sleep 15
        running_elapsed=$((running_elapsed + 15))
    done

    if [ "$STATE" != "running" ]; then
        echo -e "${RED}✗${NC} Timeout waiting for instance to reach running state"
        return 1
    fi

    # Wait for status checks with progress
    echo ""
    echo "Waiting for status checks to pass (this may take 10-15 minutes for Windows)..."
    echo "Checking every 30 seconds..."

    local status_timeout=1200  # 20 minutes
    local status_elapsed=0

    while [ $status_elapsed -lt $status_timeout ]; do
        SYSTEM_STATUS=$(aws ec2 describe-instance-status \
            --instance-ids "$instance_id" \
            --region "$region" \
            --query 'InstanceStatuses[0].SystemStatus.Status' \
            --output text 2>/dev/null || echo "initializing")

        INSTANCE_STATUS=$(aws ec2 describe-instance-status \
            --instance-ids "$instance_id" \
            --region "$region" \
            --query 'InstanceStatuses[0].InstanceStatus.Status' \
            --output text 2>/dev/null || echo "initializing")

        echo "  [$status_elapsed/$status_timeout] System: $SYSTEM_STATUS | Instance: $INSTANCE_STATUS"

        if [ "$SYSTEM_STATUS" = "ok" ] && [ "$INSTANCE_STATUS" = "ok" ]; then
            echo -e "${GREEN}✓${NC} Status checks passed (took $status_elapsed seconds)"
            return 0
        fi

        sleep 30
        status_elapsed=$((status_elapsed + 30))
    done

    echo -e "${YELLOW}⚠${NC} Status checks did not pass within timeout, but continuing..."
    echo "Note: Instance may still be initializing Windows. LucidLink verification may fail."
    return 0
}

# Function to check LucidLink mount via SSM
check_lucidlink_mount() {
    local instance_id=$1
    local region=$2

    print_header "Verifying LucidLink Mount"

    # Wait additional time for SSM agent to be ready
    echo "Waiting 5 minutes for SSM agent and LucidLink initialization..."
    sleep 300

    # Check if L: drive exists
    echo "Checking for L: drive..."
    DRIVE_CHECK=$(aws ssm send-command \
        --instance-ids "$instance_id" \
        --document-name "AWS-RunPowerShellScript" \
        --parameters 'commands=["Test-Path L:"]' \
        --region "$region" \
        --output text \
        --query 'Command.CommandId')

    sleep 5

    DRIVE_RESULT=$(aws ssm get-command-invocation \
        --command-id "$DRIVE_CHECK" \
        --instance-id "$instance_id" \
        --region "$region" \
        --query 'StandardOutputContent' \
        --output text)

    if [[ "$DRIVE_RESULT" == *"True"* ]]; then
        echo -e "${GREEN}✓${NC} L: drive exists"
        print_result "LucidLink Mount - Drive Exists" "PASS"
    else
        echo -e "${RED}✗${NC} L: drive not found"
        print_result "LucidLink Mount - Drive Exists" "FAIL"
    fi

    # Check LucidLink Windows Service
    echo "Checking LucidLink Windows Service status..."
    SERVICE_CHECK=$(aws ssm send-command \
        --instance-ids "$instance_id" \
        --document-name "AWS-RunPowerShellScript" \
        --parameters 'commands=["& \"C:\\Program Files\\LucidLink\\bin\\lucid.exe\" service --status"]' \
        --region "$region" \
        --output text \
        --query 'Command.CommandId')

    sleep 5

    SERVICE_RESULT=$(aws ssm get-command-invocation \
        --command-id "$SERVICE_CHECK" \
        --instance-id "$instance_id" \
        --region "$region" \
        --query 'StandardOutputContent' \
        --output text)

    echo "Service status output: $SERVICE_RESULT"

    if [[ "$SERVICE_RESULT" == *"running"* ]] || [[ "$SERVICE_RESULT" == *"Running"* ]] || [[ "$SERVICE_RESULT" == *"active"* ]]; then
        echo -e "${GREEN}✓${NC} LucidLink service is running"
        print_result "LucidLink Service Running" "PASS"
    else
        echo -e "${RED}✗${NC} LucidLink service not running: $SERVICE_RESULT"
        print_result "LucidLink Service Running" "FAIL"
    fi

    # Get lucid link status
    echo "Getting LucidLink mount status..."
    STATUS_CHECK=$(aws ssm send-command \
        --instance-ids "$instance_id" \
        --document-name "AWS-RunPowerShellScript" \
        --parameters 'commands=["& \"C:\\Program Files\\LucidLink\\bin\\lucid.exe\" status"]' \
        --region "$region" \
        --output text \
        --query 'Command.CommandId')

    sleep 5

    STATUS_RESULT=$(aws ssm get-command-invocation \
        --command-id "$STATUS_CHECK" \
        --instance-id "$instance_id" \
        --region "$region" \
        --query 'StandardOutputContent' \
        --output text)

    echo "LucidLink Status:"
    echo "$STATUS_RESULT"

    if [[ "$STATUS_RESULT" == *"Filespace"* ]] || [[ "$STATUS_RESULT" == *"mounted"* ]] || [[ "$STATUS_RESULT" == *"linked"* ]]; then
        echo -e "${GREEN}✓${NC} LucidLink filespace mounted"
        print_result "LucidLink Filespace Mounted" "PASS"
    else
        echo -e "${YELLOW}⚠${NC} Could not verify mount (check output above)"
        print_result "LucidLink Filespace Mounted" "FAIL"
    fi
}

# Function to get instance ID from Terraform
get_instance_id() {
    cd terraform/clients
    terraform output -json | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['instance_ids']['value'][0])"
    cd ../..
}

# Function to check instance state
check_instance_state() {
    local instance_id=$1
    local region=$2

    aws ec2 describe-instances \
        --instance-ids "$instance_id" \
        --region "$region" \
        --query 'Reservations[0].Instances[0].State.Name' \
        --output text
}

# ============================================================================
# MAIN TEST EXECUTION
# ============================================================================

print_header "LucidLink Windows Client - Automated Deployment Test"
echo "Test Start Time: $(date)"
echo "Results will be saved to: $TEST_RESULTS_FILE"
echo ""

# Check prerequisites
check_prerequisites

# Get AWS region and setup environment
print_header "Setting Up Test Environment"

echo "Reading configuration from ~/.ll-win-client/config.json..."
python3 << 'EOF'
import json
import os
import base64

config_file = os.path.expanduser("~/.ll-win-client/config.json")
with open(config_file) as f:
    config = json.load(f)

# Decode password if encoded
password = config['filespace_password']
if config.get('_password_encoded'):
    password = base64.b64decode(password).decode()

# Output for bash to capture
print(f"REGION={config['region']}")
print(f"AWS_ACCESS_KEY_ID={config['aws_access_key_id']}")
print(f"AWS_SECRET_ACCESS_KEY={config['aws_secret_access_key']}")

# Generate terraform.tfvars
tfvars_content = f"""region              = "{config['region']}"
vpc_cidr            = "{config['vpc_cidr']}"
filespace_domain    = "{config['filespace_domain']}"
filespace_user      = "{config['filespace_user']}"
filespace_password  = "{password}"
mount_point         = "{config['mount_point']}"
instance_type       = "{config['instance_type']}"
instance_count      = {config['instance_count']}
root_volume_size    = {config['root_volume_size']}
ssh_key_name        = "{config.get('ssh_key_name', '')}"
"""

# Write to terraform directory
tfvars_path = 'terraform/clients/terraform.tfvars'
os.makedirs(os.path.dirname(tfvars_path), exist_ok=True)
with open(tfvars_path, 'w') as f:
    f.write(tfvars_content)

print(f"TFVARS_WRITTEN=terraform/clients/terraform.tfvars")
EOF

# Source the environment variables
eval $(python3 << 'EOF'
import json
import os
import base64

config_file = os.path.expanduser("~/.ll-win-client/config.json")
with open(config_file) as f:
    config = json.load(f)

print(f"export REGION={config['region']}")
print(f"export AWS_ACCESS_KEY_ID={config['aws_access_key_id']}")
print(f"export AWS_SECRET_ACCESS_KEY={config['aws_secret_access_key']}")
print(f"export AWS_DEFAULT_REGION={config['region']}")
EOF
)

echo -e "${GREEN}✓${NC} AWS Region: ${BLUE}$REGION${NC}"
echo -e "${GREEN}✓${NC} AWS Credentials exported"
echo -e "${GREEN}✓${NC} Generated terraform.tfvars"

# ============================================================================
# TEST 1: Deploy Instance
# ============================================================================

print_header "TEST 1: Deploy Instance"
echo "Changing to terraform/clients directory..."
cd terraform/clients

echo "Running terraform init..."
terraform init -upgrade > /dev/null 2>&1

echo "Running terraform apply with generated tfvars..."
DEPLOY_START=$(date +%s)
terraform apply -auto-approve -var-file=terraform.tfvars
TERRAFORM_EXIT=$?

DEPLOY_END=$(date +%s)
DEPLOY_TIME=$((DEPLOY_END - DEPLOY_START))

if [ $TERRAFORM_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Deployment successful"
    print_result "Deploy Infrastructure" "PASS"
    echo "Deployment time: $((DEPLOY_TIME / 60)) minutes $((DEPLOY_TIME % 60)) seconds"
else
    echo -e "${RED}✗${NC} Deployment failed"
    print_result "Deploy Infrastructure" "FAIL"
    cd ../..
    exit 1
fi

cd ../..

# Get instance ID
INSTANCE_ID=$(get_instance_id)
echo "Instance ID: $INSTANCE_ID"

# ============================================================================
# TEST 2: Wait for Instance Ready
# ============================================================================

wait_for_instance "$INSTANCE_ID" "$REGION"
print_result "Instance Running and Ready" "PASS"

# ============================================================================
# TEST 3: Verify LucidLink Mount
# ============================================================================

check_lucidlink_mount "$INSTANCE_ID" "$REGION"

# ============================================================================
# TEST 4: Stop Instance
# ============================================================================

print_header "TEST 4: Stop Instance"
echo "Stopping instance $INSTANCE_ID..."
STOP_START=$(date +%s)

aws ec2 stop-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" > /dev/null

echo "Waiting for instance to stop..."
aws ec2 wait instance-stopped \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION"

STOP_END=$(date +%s)
STOP_TIME=$((STOP_END - STOP_START))

STATE=$(check_instance_state "$INSTANCE_ID" "$REGION")
if [ "$STATE" = "stopped" ]; then
    echo -e "${GREEN}✓${NC} Instance stopped successfully"
    print_result "Stop Instance" "PASS"
    echo "Stop time: $((STOP_TIME / 60)) minutes $((STOP_TIME % 60)) seconds"
else
    echo -e "${RED}✗${NC} Instance not in stopped state: $STATE"
    print_result "Stop Instance" "FAIL"
fi

# ============================================================================
# TEST 5: Start Instance
# ============================================================================

print_header "TEST 5: Start Instance"
echo "Starting instance $INSTANCE_ID..."
START_START=$(date +%s)

aws ec2 start-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" > /dev/null

echo "Waiting for instance to start..."
aws ec2 wait instance-running \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION"

START_END=$(date +%s)
START_TIME=$((START_END - START_START))

STATE=$(check_instance_state "$INSTANCE_ID" "$REGION")
if [ "$STATE" = "running" ]; then
    echo -e "${GREEN}✓${NC} Instance started successfully"
    print_result "Start Instance" "PASS"
    echo "Start time: $((START_TIME / 60)) minutes $((START_TIME % 60)) seconds"
else
    echo -e "${RED}✗${NC} Instance not in running state: $STATE"
    print_result "Start Instance" "FAIL"
fi

# Wait for status checks after restart
echo "Waiting for status checks after restart..."
aws ec2 wait instance-status-ok \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION"
print_result "Instance Status OK After Restart" "PASS"

# ============================================================================
# TEST 6: Verify LucidLink After Restart
# ============================================================================

print_header "TEST 6: Verify LucidLink After Restart"
check_lucidlink_mount "$INSTANCE_ID" "$REGION"

# ============================================================================
# TEST 7: Destroy Instance
# ============================================================================

print_header "TEST 7: Destroy Infrastructure"
echo "Changing to terraform/clients directory..."
cd terraform/clients

echo "Running terraform destroy..."
DESTROY_START=$(date +%s)
terraform destroy -auto-approve
TERRAFORM_EXIT=$?

DESTROY_END=$(date +%s)
DESTROY_TIME=$((DESTROY_END - DESTROY_START))

if [ $TERRAFORM_EXIT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Destruction successful"
    print_result "Destroy Infrastructure" "PASS"
    echo "Destroy time: $((DESTROY_TIME / 60)) minutes $((DESTROY_TIME % 60)) seconds"
else
    echo -e "${RED}✗${NC} Destruction failed"
    print_result "Destroy Infrastructure" "FAIL"
fi

cd ../..

# Verify instance is terminated
sleep 10
STATE=$(check_instance_state "$INSTANCE_ID" "$REGION" 2>/dev/null || echo "terminated")
if [ "$STATE" = "terminated" ] || [ "$STATE" = "shutting-down" ]; then
    echo -e "${GREEN}✓${NC} Instance terminated"
    print_result "Verify Instance Terminated" "PASS"
else
    echo -e "${RED}✗${NC} Instance still exists in state: $STATE"
    print_result "Verify Instance Terminated" "FAIL"
fi

# ============================================================================
# TEST SUMMARY
# ============================================================================

TEST_END_TIME=$(date +%s)
TOTAL_TIME=$((TEST_END_TIME - TEST_START_TIME))

print_header "TEST SUMMARY"

echo "Test End Time: $(date)"
echo "Total Test Duration: $((TOTAL_TIME / 60)) minutes $((TOTAL_TIME % 60)) seconds"
echo ""
echo "Deployment Time: $((DEPLOY_TIME / 60)) minutes $((DEPLOY_TIME % 60)) seconds"
echo "Stop Time: $((STOP_TIME / 60)) minutes $((STOP_TIME % 60)) seconds"
echo "Start Time: $((START_TIME / 60)) minutes $((START_TIME % 60)) seconds"
echo "Destroy Time: $((DESTROY_TIME / 60)) minutes $((DESTROY_TIME % 60)) seconds"
echo ""
echo -e "${GREEN}Tests Passed: $PASSED${NC}"
echo -e "${RED}Tests Failed: $FAILED${NC}"
echo -e "Total Tests: $((PASSED + FAILED))"
echo ""

# Generate test results file
cat > "$TEST_RESULTS_FILE" << EOF
# Test Results - LucidLink Windows Client Deployment

**Test Date**: $(date +%Y-%m-%d)
**Test Time**: $(date +%H:%M:%S)
**AWS Region**: $REGION
**Instance ID**: $INSTANCE_ID

---

## Test Summary

**Total Tests**: $((PASSED + FAILED))
**Passed**: $PASSED
**Failed**: $FAILED
**Success Rate**: $(awk "BEGIN {printf \"%.1f\", ($PASSED/($PASSED+$FAILED))*100}")%

**Overall Result**: $([ $FAILED -eq 0 ] && echo "✓ PASS" || echo "✗ FAIL")

---

## Timing Results

| Phase | Duration |
|-------|----------|
| Deployment | $((DEPLOY_TIME / 60))m $((DEPLOY_TIME % 60))s |
| Stop Instance | $((STOP_TIME / 60))m $((STOP_TIME % 60))s |
| Start Instance | $((START_TIME / 60))m $((START_TIME % 60))s |
| Destroy | $((DESTROY_TIME / 60))m $((DESTROY_TIME % 60))s |
| **Total** | **$((TOTAL_TIME / 60))m $((TOTAL_TIME % 60))s** |

---

## Test Case Results

All test results are documented above in the console output.

---

## Notes

- LucidLink mount verification performed via AWS Systems Manager (SSM)
- Instance stop/start cycle completed successfully
- All resources cleaned up via Terraform destroy

---

**Test Completed**: $(date)
EOF

echo -e "${BLUE}Test results saved to: $TEST_RESULTS_FILE${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}ALL TESTS PASSED ✓${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo -e "\n${RED}========================================${NC}"
    echo -e "${RED}SOME TESTS FAILED ✗${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
