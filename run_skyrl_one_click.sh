#!/bin/bash
################################################################################
# VulRL One-Click Setup and Run Script
################################################################################
# This script automates the entire setup process from a fresh Linux machine:
# 1. Install system dependencies (uv, docker, redis, python)
# 2. Setup Worker Orchestrator Python environment
# 3. Download Qwen 14B model from HuggingFace
# 4. Start required services (Redis, Worker Router)
# 5. Launch SkyRL training
#
# Prerequisites:
# - Fresh Linux machine (Ubuntu/Debian or CentOS/Fedora)
# - Sudo privileges
# - Internet connection
# - ~50GB free disk space
# - GPU with 40GB+ VRAM (recommended for 14B model)
#
# Usage:
#   bash run_skyrl_one_click.sh
#
# Configuration via environment variables:
#   MODEL_DIR=/path/to/models NUM_GPUS=2 bash run_skyrl_one_click.sh
################################################################################

set -e  # Exit on error

# ============================================================================
# CONFIGURATION (Edit these or set via environment variables)
# ============================================================================

# Script paths
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
WORKER_ORCH_DIR="$REPO_ROOT/worker_orchestrator"
SKYRL_DIR="$REPO_ROOT/SkyRL/skyrl-train"
EZ_GENERATOR_SRC="$WORKER_ORCH_DIR/ez_generator"
VULRL_TARGET_DIR="$SKYRL_DIR/vulrl_inside_skyrl_v2"

# Training data
TRAIN_DATA="$REPO_ROOT/dataset/cve_vulhub/train_vulhub_easy.parquet"

# Model configuration
# For production: Qwen/Qwen2.5-14B-Instruct (~28GB)
# MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-14B-Instruct}"
# MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/qwen2.5-14b}"

# For testing: Qwen/Qwen2.5-1.5B-Instruct (~3GB, faster download)
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-1.5B-Instruct}"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/qwen2.5-1.5b}"

# Training parameters (minimal settings for quick test)
CHECKPOINT_DIR="${CHECKPOINT_DIR:-$REPO_ROOT/ckpts/vulrl_skyrl_oneclick}"
NUM_GPUS="${NUM_GPUS:-1}"
EPOCHS="${EPOCHS:-1}"
N_SAMPLES_PER_PROMPT="${N_SAMPLES_PER_PROMPT:-1}"
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-10}"  # Number of parallel cases
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-10}"
MAX_STEPS="${MAX_STEPS:-30}"
LEARNING_RATE="${LEARNING_RATE:-1e-6}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.4}"

# Service configuration
WORKER_ROUTER_PORT=12345
REDIS_PORT=6379
USE_DOCKER_REDIS="${USE_DOCKER_REDIS:-false}"  # Set to 'true' to use Docker for Redis

# Script behavior
NO_SUDO="${NO_SUDO:-false}"  # Set to 'true' to skip system package installation
SKIP_DEPS_CHECK="${SKIP_DEPS_CHECK:-false}"  # Set to 'true' to assume all deps installed

# Logging (kept for redis.type file if using Docker Redis)
LOG_DIR="$REPO_ROOT/logs"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_section() {
    echo ""
    echo "============================================================================"
    echo "$1"
    echo "============================================================================"
    echo ""
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if port is in use
port_in_use() {
    netstat -tuln 2>/dev/null | grep -q ":$1 " || ss -tuln 2>/dev/null | grep -q ":$1 "
}

# Detect OS
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    elif [ -f /etc/redhat-release ]; then
        OS="rhel"
    else
        OS="unknown"
    fi
    
    log_info "Detected OS: $OS $OS_VERSION"
}

# ============================================================================
# PHASE 1: CHECK/INSTALL SYSTEM DEPENDENCIES
# ============================================================================

check_required_commands() {
    log_section "Phase 1: Checking System Dependencies"
    
    local missing_deps=()
    
    # Check required commands
    log_info "Checking required dependencies..."
    
    if ! command_exists python3.12; then
        missing_deps+=("python3.12")
        log_warning "Python 3.12 not found"
    else
        log_success "Python 3.12 found"
    fi
    
    if ! command_exists uv; then
        missing_deps+=("uv")
        log_warning "uv not found"
    else
        log_success "uv found"
    fi
    
    if ! command_exists docker; then
        missing_deps+=("docker")
        log_warning "Docker not found"
    else
        log_success "Docker found"
    fi
    
    # Docker Compose
    if ! docker compose version >/dev/null 2>&1 && ! command_exists docker-compose; then
        missing_deps+=("docker-compose")
        log_warning "Docker Compose not found"
    else
        log_success "Docker Compose found"
    fi
    
    # Redis check
    if [ "$USE_DOCKER_REDIS" = "true" ]; then
        log_info "Using Docker for Redis (system Redis not required)"
    else
        if ! command_exists redis-server; then
            missing_deps+=("redis-server")
            log_warning "Redis not found"
        else
            log_success "Redis found"
        fi
    fi
    
    # If NO_SUDO mode and missing deps, show instructions and exit
    if [ "$NO_SUDO" = "true" ] && [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "NO_SUDO mode enabled but missing dependencies: ${missing_deps[*]}"
        echo ""
        echo "Please install the following manually:"
        echo ""
        for dep in "${missing_deps[@]}"; do
            case "$dep" in
                python3.12)
                    echo "  Python 3.12:"
                    echo "    Ubuntu/Debian: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt-get install python3.12 python3.12-venv"
                    echo "    Or download from: https://www.python.org/downloads/"
                    ;;
                uv)
                    echo "  uv:"
                    echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
                    ;;
                docker)
                    echo "  Docker:"
                    echo "    Ubuntu/Debian: sudo apt-get install docker.io"
                    echo "    Or follow: https://docs.docker.com/engine/install/"
                    ;;
                docker-compose)
                    echo "  Docker Compose:"
                    echo "    Ubuntu/Debian: sudo apt-get install docker-compose-plugin"
                    ;;
                redis-server)
                    echo "  Redis (or set USE_DOCKER_REDIS=true):"
                    echo "    Ubuntu/Debian: sudo apt-get install redis-server"
                    ;;
            esac
        done
        echo ""
        exit 1
    fi
    
    # Return the list of missing dependencies
    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo "${missing_deps[@]}"
    fi
}

install_system_deps() {
    # Check what's missing first
    local missing_deps
    missing_deps=$(check_required_commands)
    
    # If nothing missing, skip installation
    if [ -z "$missing_deps" ]; then
        log_success "Phase 1 complete: All dependencies already installed"
        return 0
    fi
    
    # If NO_SUDO mode, we already exited in check_required_commands
    # So if we're here, we can use sudo
    
    detect_os
    
    # Check if running as root or has sudo
    if [ "$EUID" -eq 0 ]; then
        log_warning "Running as root."
        SUDO=""
    elif command_exists sudo; then
        SUDO="sudo"
        log_info "Will use sudo to install missing packages: $missing_deps"
    else
        log_error "Missing dependencies but no sudo available."
        log_info "Either install sudo, run as root, or set NO_SUDO=true and install manually."
        exit 1
    fi
    
    # Update package lists
    log_info "Updating package lists..."
    case "$OS" in
        ubuntu|debian)
            $SUDO apt-get update -qq
            ;;
        centos|rhel|fedora)
            $SUDO yum update -y -q || $SUDO dnf update -y -q
            ;;
        *)
            log_warning "Unknown OS. Skipping package update."
            ;;
    esac
    
    # Install Python 3.12 (required by SkyRL)
    log_info "Checking Python 3.12..."
    if ! command_exists python3.12; then
        log_info "Installing Python 3.12..."
        case "$OS" in
            ubuntu|debian)
                $SUDO apt-get install -y software-properties-common
                $SUDO add-apt-repository -y ppa:deadsnakes/ppa
                $SUDO apt-get update -qq
                $SUDO apt-get install -y python3.12 python3.12-venv python3.12-dev
                ;;
            centos|rhel|fedora)
                log_error "Python 3.12 not found. Please install manually from https://www.python.org/downloads/"
                exit 1
                ;;
        esac
    fi
    log_success "Python 3.12 installed"
    
    # Install uv (Python package manager for SkyRL)
    log_info "Checking uv..."
    if ! command_exists uv; then
        log_info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Add uv to PATH for this session
        export PATH="$HOME/.local/bin:$PATH"
        if ! command_exists uv; then
            log_error "uv installation failed. Please install manually."
            exit 1
        fi
    fi
    log_success "uv installed"
    
    # Install Docker
    log_info "Checking Docker..."
    if ! command_exists docker; then
        log_info "Installing Docker..."
        case "$OS" in
            ubuntu|debian)
                $SUDO apt-get install -y docker.io
                ;;
            centos|rhel|fedora)
                $SUDO yum install -y docker || $SUDO dnf install -y docker
                ;;
        esac
        $SUDO systemctl enable docker
        $SUDO systemctl start docker
        # Add current user to docker group
        $SUDO usermod -aG docker $USER || true
        log_warning "You may need to log out and back in for Docker permissions to take effect."
    fi
    log_success "Docker installed"
    
    # Install Docker Compose
    log_info "Checking Docker Compose..."
    if ! docker compose version >/dev/null 2>&1 && ! command_exists docker-compose; then
        log_info "Installing Docker Compose..."
        case "$OS" in
            ubuntu|debian)
                $SUDO apt-get install -y docker-compose-plugin || $SUDO apt-get install -y docker-compose
                ;;
            centos|rhel|fedora)
                $SUDO yum install -y docker-compose || $SUDO dnf install -y docker-compose
                ;;
        esac
    fi
    log_success "Docker Compose installed"
    
    # Install Redis
    log_info "Checking Redis..."
    if ! command_exists redis-server; then
        log_info "Installing Redis..."
        case "$OS" in
            ubuntu|debian)
                $SUDO apt-get install -y redis-server
                ;;
            centos|rhel|fedora)
                $SUDO yum install -y redis || $SUDO dnf install -y redis
                ;;
        esac
    fi
    log_success "Redis installed"
    
    # Install other utilities
    log_info "Installing utilities (curl, git, build-essential)..."
    case "$OS" in
        ubuntu|debian)
            $SUDO apt-get install -y curl git build-essential python3-pip
            ;;
        centos|rhel|fedora)
            $SUDO yum install -y curl git gcc gcc-c++ make python3-pip || \
            $SUDO dnf install -y curl git gcc gcc-c++ make python3-pip
            ;;
    esac
    
    log_success "Phase 1 complete: All system dependencies installed"
}

# ============================================================================
# PHASE 2: SETUP WORKER ORCHESTRATOR
# ============================================================================

setup_worker_orchestrator() {
    log_section "Phase 2: Setting Up Worker Orchestrator"
    
    cd "$WORKER_ORCH_DIR"
    
    # Create virtual environment
    if [ ! -d "venv" ]; then
        log_info "Creating Python virtual environment..."
        python3.12 -m venv venv
        log_success "Virtual environment created"
    else
        log_success "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    log_info "Activating virtual environment..."
    source venv/bin/activate
    
    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip --quiet
    
    # Install dependencies
    log_info "Installing Worker Orchestrator dependencies..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt --quiet
        log_success "Dependencies installed"
    else
        log_error "requirements.txt not found in $WORKER_ORCH_DIR"
        exit 1
    fi
    
    # Verify critical packages
    log_info "Verifying installation..."
    python3 -c "import fastapi, redis, docker, pandas" 2>/dev/null
    if [ $? -eq 0 ]; then
        log_success "All critical packages verified"
    else
        log_error "Some packages failed to import"
        exit 1
    fi
    
    cd "$REPO_ROOT"
    log_success "Phase 2 complete: Worker Orchestrator ready"
}

# ============================================================================
# PHASE 3: DOWNLOAD MODEL
# ============================================================================

install_huggingface_cli() {
    log_info "Installing HuggingFace Hub..."
    cd "$WORKER_ORCH_DIR"
    source venv/bin/activate
    pip install huggingface-hub --quiet
    log_success "HuggingFace Hub installed"
}

download_model() {
    log_section "Phase 3: Downloading Model from HuggingFace"
    
    log_info "Model: $MODEL_NAME"
    log_info "Destination: $MODEL_DIR"
    
    # Estimate size based on model name
    if [[ "$MODEL_NAME" == *"1.5B"* ]]; then
        log_warning "Model size: ~3GB (1.5B parameters)"
        log_warning "Download time: 5-10 minutes depending on connection speed"
    elif [[ "$MODEL_NAME" == *"14B"* ]]; then
        log_warning "Model size: ~28GB (14B parameters)"
        log_warning "Download time: 30-60 minutes depending on connection speed"
    else
        log_warning "Model size: varies by model"
        log_warning "Download time: depends on model size and connection speed"
    fi
    echo ""
    
    # Check if model already exists
    if [ -f "$MODEL_DIR/config.json" ]; then
        log_success "Model already exists at $MODEL_DIR"
        log_info "Skipping download. To re-download, delete: $MODEL_DIR"
        return 0
    fi
    
    # Install HuggingFace CLI if needed
    cd "$WORKER_ORCH_DIR"
    source venv/bin/activate
    if ! command_exists hf; then
        install_huggingface_cli
    fi
    
    # Create model directory
    mkdir -p "$MODEL_DIR"
    
    # Download model
    log_info "Starting download..."
    log_info "You can monitor progress below. Press Ctrl+C to abort."
    echo ""
    
    # Note: hf command doesn't have --resume-download or --local-dir-use-symlinks
    # Downloads are automatically resumed if interrupted
    hf download "$MODEL_NAME" \
        --local-dir "$MODEL_DIR"
    
    # Verify download
    if [ -f "$MODEL_DIR/config.json" ]; then
        log_success "Model downloaded successfully to $MODEL_DIR"
    else
        log_error "Model download failed or incomplete"
        exit 1
    fi
    
    cd "$REPO_ROOT"
    log_success "Phase 3 complete: Model ready"
}

# ============================================================================
# PHASE 4: START SERVICES
# ============================================================================

start_redis() {
    log_info "Starting Redis server..."
    
    if port_in_use $REDIS_PORT; then
        log_success "Redis already running on port $REDIS_PORT"
        return 0
    fi
    
    if [ "$USE_DOCKER_REDIS" = "true" ]; then
        log_info "Starting Redis in Docker (no sudo needed)..."
        docker run -d \
            --name vulrl-redis \
            --rm \
            -p $REDIS_PORT:6379 \
            redis:7-alpine \
            redis-server --appendonly yes
        
        sleep 3
        
        if port_in_use $REDIS_PORT; then
            log_success "Redis running in Docker on port $REDIS_PORT"
            # Create marker file for cleanup
            mkdir -p "$LOG_DIR"
            echo "redis-docker" > "$LOG_DIR/redis.type"
            return 0
        else
            log_error "Failed to start Redis in Docker"
            exit 1
        fi
    fi
    
    # Try system Redis without sudo first
    if command_exists redis-server; then
        log_info "Starting Redis without sudo..."
        redis-server --daemonize yes --port $REDIS_PORT --dir /tmp 2>/dev/null || true
        sleep 2
    fi
    
    # If still not running and we have systemctl, try with sudo
    if ! port_in_use $REDIS_PORT && command_exists systemctl && [ "$NO_SUDO" != "true" ]; then
        log_info "Trying to start Redis with systemd..."
        sudo systemctl start redis-server 2>/dev/null || sudo systemctl start redis 2>/dev/null || true
        sleep 2
    fi
    
    # Verify Redis is running
    if port_in_use $REDIS_PORT; then
        log_success "Redis running on port $REDIS_PORT"
    else
        log_error "Failed to start Redis"
        log_info "Try manually: redis-server --daemonize yes --port $REDIS_PORT"
        log_info "Or use Docker Redis: USE_DOCKER_REDIS=true bash run_skyrl_one_click.sh"
        exit 1
    fi
}

start_worker_router() {
    log_info "Starting Worker Router..."
    
    if port_in_use $WORKER_ROUTER_PORT; then
        log_success "Worker Router already running on port $WORKER_ROUTER_PORT"
        return 0
    fi
    
    cd "$WORKER_ORCH_DIR"
    source venv/bin/activate
    
    # Create logs directory if it doesn't exist
    mkdir -p logs
    
    # Start in background with logging
    log_info "Launching Worker Router in background..."
    # Redirect output to logs directory where it naturally belongs
    nohup bash start_worker_router.sh > logs/worker_router.log 2>&1 &
    WORKER_ROUTER_PID=$!
    echo $WORKER_ROUTER_PID > logs/worker_router.pid
    
    # Wait for startup (with timeout)
    log_info "Waiting for Worker Router to start (max 60s)..."
    for i in {1..60}; do
        if port_in_use $WORKER_ROUTER_PORT; then
            log_success "Worker Router started (PID: $WORKER_ROUTER_PID)"
            break
        fi
        if [ $i -eq 60 ]; then
            log_error "Worker Router failed to start within 60 seconds"
            log_info "Check logs at: $WORKER_ORCH_DIR/logs/"
            exit 1
        fi
        sleep 1
    done
    
    # Health check
    log_info "Performing health check..."
    sleep 5  # Give it a moment to fully initialize
    
    if curl -s "http://localhost:$WORKER_ROUTER_PORT/health" >/dev/null 2>&1; then
        log_success "Worker Router health check passed"
    else
        log_warning "Worker Router is running but health check failed"
        log_info "Continuing anyway... (may need manual verification)"
    fi
    
    cd "$REPO_ROOT"
}

start_services() {
    log_section "Phase 4: Starting Services"
    
    start_redis
    start_worker_router
    
    log_success "Phase 4 complete: All services running"
}

# ============================================================================
# PHASE 5: PREPARE TRAINING
# ============================================================================

verify_training_data() {
    log_info "Verifying training data..."
    
    if [ ! -f "$TRAIN_DATA" ]; then
        log_error "Training data not found at: $TRAIN_DATA"
        log_info "Expected location: $TRAIN_DATA"
        exit 1
    fi
    
    log_success "Training data found: $TRAIN_DATA"
}

verify_skyrl_and_scripts() {
    log_info "Verifying SkyRL and training scripts..."
    
    # Check if SkyRL directory exists
    if [ ! -d "$SKYRL_DIR" ]; then
        log_error "SkyRL directory not found at: $SKYRL_DIR"
        log_info "Please ensure SkyRL is cloned at: $REPO_ROOT/SkyRL"
        exit 1
    fi
    log_success "SkyRL directory found"
    
    # Check if training script exists
    if [ ! -f "$EZ_GENERATOR_SRC/run_vulrl_skyrl.sh" ]; then
        log_error "Training script not found at: $EZ_GENERATOR_SRC/run_vulrl_skyrl.sh"
        exit 1
    fi
    log_success "Training script found"
}

prepare_training() {
    log_section "Phase 5: Preparing Training Environment"
    
    verify_training_data
    verify_skyrl_and_scripts
    
    # Create checkpoint directory
    mkdir -p "$CHECKPOINT_DIR"
    log_success "Checkpoint directory: $CHECKPOINT_DIR"
    
    log_success "Phase 5 complete: Training environment ready"
}

# ============================================================================
# PHASE 6: LAUNCH TRAINING
# ============================================================================

launch_training() {
    log_section "Phase 6: Launching SkyRL Training"
    
    cd "$EZ_GENERATOR_SRC"
    
    log_info "Configuration:"
    echo "  Model: $MODEL_DIR"
    echo "  Training Data: $TRAIN_DATA"
    echo "  Epochs: $EPOCHS"
    echo "  Batch Size: $TRAIN_BATCH_SIZE"
    echo "  Max Steps per Rollout: $MAX_STEPS"
    echo "  Training GPUs: $NUM_GPUS"
    echo "  GPU Memory Utilization: $GPU_MEMORY_UTILIZATION"
    echo "  Checkpoint Dir: $CHECKPOINT_DIR"
    echo ""
    echo "Worker Router: http://localhost:$WORKER_ROUTER_PORT"
    echo "Worker Router Logs: $WORKER_ORCH_DIR/logs/"
    echo "Training Logs: $SKYRL_DIR/outputs/"
    echo ""
    
    log_warning "Training is about to start. This may take several hours."
    log_info "Press Ctrl+C to stop training at any time."
    echo ""
    
    sleep 3
    
    log_info "Starting training using run_vulrl_skyrl.sh..."
    echo ""
    echo "========================================================================"
    echo "TRAINING OUTPUT (Press Ctrl+C to stop)"
    echo "========================================================================"
    echo ""
    
    # Export configuration as environment variables for the training script
    export MODEL_PATH="$MODEL_DIR"
    export TRAIN_DATA="$TRAIN_DATA"
    export EPOCHS="$EPOCHS"
    export N_SAMPLES_PER_PROMPT="$N_SAMPLES_PER_PROMPT"
    export TRAIN_BATCH_SIZE="$TRAIN_BATCH_SIZE"
    export EVAL_BATCH_SIZE="$EVAL_BATCH_SIZE"
    export MAX_STEPS="$MAX_STEPS"
    export LEARNING_RATE="$LEARNING_RATE"
    export NUM_GPUS="$NUM_GPUS"
    export CHECKPOINT_DIR="$CHECKPOINT_DIR"
    export GPU_MEMORY_UTILIZATION="$GPU_MEMORY_UTILIZATION"
    export WORKER_ORCHESTRATOR_PATH="$WORKER_ORCH_DIR"
    export SKYRL_PATH="$SKYRL_DIR"
    export WANDB_MODE="disabled"
    
    # Call the existing training script
    bash run_vulrl_skyrl.sh
    
    TRAIN_EXIT_CODE=$?
    
    echo ""
    echo "========================================================================"
    if [ $TRAIN_EXIT_CODE -eq 0 ]; then
        log_success "Training completed successfully!"
    else
        log_error "Training exited with code: $TRAIN_EXIT_CODE"
    fi
    echo "========================================================================"
    echo ""
    
    log_info "Checkpoints saved to: $CHECKPOINT_DIR"
    log_info "Worker Router logs: $WORKER_ORCH_DIR/logs/"
    log_info "Training logs: $SKYRL_DIR/outputs/"
    
    cd "$REPO_ROOT"
}

# ============================================================================
# CLEANUP HANDLER
# ============================================================================

cleanup() {
    echo ""
    log_warning "Received interrupt signal. Cleaning up..."
    
    # Stop Worker Router
    if [ -f "$WORKER_ORCH_DIR/logs/worker_router.pid" ]; then
        WORKER_PID=$(cat "$WORKER_ORCH_DIR/logs/worker_router.pid")
        if kill -0 "$WORKER_PID" 2>/dev/null; then
            log_info "Stopping Worker Router (PID: $WORKER_PID)..."
            kill "$WORKER_PID"
            sleep 2
            # Force kill if still running
            if kill -0 "$WORKER_PID" 2>/dev/null; then
                log_warning "Force killing Worker Router..."
                kill -9 "$WORKER_PID"
            fi
            log_success "Worker Router stopped"
        else
            log_info "Worker Router already stopped"
        fi
    fi
    
    # Note: Keep Redis running as it's a shared service
    log_info "Redis is still running (shared service)."
    log_info "To stop Redis manually:"
    
    if [ -f "$LOG_DIR/redis.type" ] && [ "$(cat $LOG_DIR/redis.type)" = "redis-docker" ]; then
        echo "  docker stop vulrl-redis"
    else
        echo "  redis-cli shutdown"
    fi
    
    echo ""
    log_success "Cleanup complete. You can run the script again for a fresh start."
    
    exit 130
}

trap cleanup INT TERM

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log_section "VulRL One-Click Setup and Run Script"
    
    log_info "Repository: $REPO_ROOT"
    
    if [ "$NO_SUDO" = "true" ]; then
        log_warning "NO_SUDO mode enabled - will not install system packages"
    fi
    
    if [ "$USE_DOCKER_REDIS" = "true" ]; then
        log_info "Using Docker for Redis (no system Redis needed)"
    fi
    
    log_info "This script will:"
    echo "  1. Check/Install system dependencies (uv, docker, python)"
    echo "  2. Setup Worker Orchestrator Python environment"
    echo "  3. Download Qwen 14B model (~28GB)"
    echo "  4. Start services (Redis, Worker Router)"
    echo "  5. Launch SkyRL training"
    echo ""
    log_warning "Prerequisites:"
    echo "  - Linux machine (Ubuntu/Debian recommended)"
    if [ "$NO_SUDO" = "true" ]; then
        echo "  - All dependencies pre-installed (NO_SUDO mode)"
    else
        echo "  - Sudo privileges (or set NO_SUDO=true)"
    fi
    echo "  - Internet connection"
    if [[ "$MODEL_NAME" == *"1.5B"* ]]; then
        echo "  - ~20GB free disk space"
        echo "  - GPU with 4GB+ VRAM (for 1.5B model)"
    elif [[ "$MODEL_NAME" == *"14B"* ]]; then
        echo "  - ~50GB free disk space"
        echo "  - GPU with 40GB+ VRAM (for 14B model)"
    else
        echo "  - Sufficient disk space for model + dependencies"
        echo "  - GPU recommended (size depends on model)"
    fi
    echo ""
    log_info "Configuration:"
    echo "  NO_SUDO=$NO_SUDO"
    echo "  USE_DOCKER_REDIS=$USE_DOCKER_REDIS"
    echo "  NUM_GPUS=$NUM_GPUS"
    echo ""
    
    read -p "Press Enter to continue, or Ctrl+C to abort..."
    echo ""
    
    # Execute phases
    install_system_deps
    setup_worker_orchestrator
    download_model
    start_services
    prepare_training
    launch_training
    
    log_section "ALL PHASES COMPLETE!"
    log_success "VulRL training setup and execution finished"
    echo ""
    log_info "Next steps:"
    echo "  - Worker Router logs: $WORKER_ORCH_DIR/logs/"
    echo "  - Training logs: $SKYRL_DIR/outputs/"
    echo "  - Monitor checkpoints: $CHECKPOINT_DIR"
    echo "  - To run again: bash $0"
    echo ""
}

# Run main function
main "$@"
