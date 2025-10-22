#!/bin/bash
# Exit on error is removed to allow graceful error handling
# set -e  # DO NOT use - we need to handle partial download failures

# OpenTranscribe Model Downloader
# Downloads all required AI models before application startup
# Usage: ./scripts/download-models.sh [model_cache_dir]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
MODEL_CACHE_DIR="${1:-./models}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

print_header() {
    echo -e "\n${CYAN}================================================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}================================================================${NC}\n"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Calculate directory size
get_dir_size() {
    du -sh "$1" 2>/dev/null | cut -f1 || echo "0"
}

check_models_exist() {
    print_info "Checking for existing models in $MODEL_CACHE_DIR..."

    # Check if models directory exists and has content
    if [ -d "$MODEL_CACHE_DIR/huggingface" ] && [ -d "$MODEL_CACHE_DIR/torch" ]; then
        local hf_size=$(du -sb "$MODEL_CACHE_DIR/huggingface" 2>/dev/null | cut -f1)
        local torch_size=$(du -sb "$MODEL_CACHE_DIR/torch" 2>/dev/null | cut -f1)

        # If both directories have substantial content (>100MB combined), assume models exist
        if [ "$((hf_size + torch_size))" -gt 100000000 ]; then
            local total_size=$(get_dir_size "$MODEL_CACHE_DIR")
            print_success "Found existing models ($total_size)"
            echo -e "${YELLOW}Do you want to skip model download and use existing models? (Y/n)${NC}"
            read -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                print_info "Skipping model download - using existing models"
                return 0
            else
                print_info "Re-downloading models as requested"
            fi
        fi
    fi

    return 1
}

check_huggingface_token() {
    print_info "Checking for HuggingFace token..."

    # Check environment variable first
    if [ -n "$HUGGINGFACE_TOKEN" ]; then
        print_success "HuggingFace token found in environment"
        return 0
    fi

    # Check .env file
    if [ -f "$REPO_ROOT/.env" ]; then
        local token=$(grep "^HUGGINGFACE_TOKEN=" "$REPO_ROOT/.env" | cut -d'=' -f2 | tr -d ' ')
        if [ -n "$token" ]; then
            export HUGGINGFACE_TOKEN="$token"
            print_success "HuggingFace token loaded from .env file"
            return 0
        fi
    fi

    print_error "HUGGINGFACE_TOKEN not found!"
    echo ""
    echo -e "${YELLOW}A HuggingFace token is required to download speaker diarization models.${NC}"
    echo ""
    echo "To get your FREE token:"
    echo "1. Go to: https://huggingface.co/settings/tokens"
    echo "2. Click 'New token'"
    echo "3. Give it a name (e.g., 'OpenTranscribe')"
    echo "4. Select 'Read' permissions"
    echo "5. Copy the token"
    echo ""
    echo "Then either:"
    echo "  • Export it: export HUGGINGFACE_TOKEN=your_token_here"
    echo "  • Add it to .env file: HUGGINGFACE_TOKEN=your_token_here"
    echo ""
    exit 1
}

download_models_docker() {
    print_header "Downloading AI Models"

    print_info "This will download approximately 2.5GB of AI models:"
    print_info "  • WhisperX transcription models (~1.5GB)"
    print_info "  • PyAnnote speaker diarization models (~500MB)"
    print_info "  • Wav2Vec2 alignment model (~360MB)"
    echo ""
    print_warning "This may take 10-30 minutes depending on your internet speed..."
    echo ""

    # Create model cache directories
    mkdir -p "$MODEL_CACHE_DIR/huggingface"
    mkdir -p "$MODEL_CACHE_DIR/torch"

    print_info "Starting model download using Docker..."
    echo ""

    # Get Whisper model from .env or use default
    local whisper_model="large-v2"
    if [ -f "$REPO_ROOT/.env" ]; then
        local env_model=$(grep "^WHISPER_MODEL=" "$REPO_ROOT/.env" | cut -d'=' -f2 | tr -d ' ')
        if [ -n "$env_model" ]; then
            whisper_model="$env_model"
        fi
    fi

    # Determine if GPU is available
    local use_gpu="false"
    local gpu_args=""
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        use_gpu="true"
        # Use specific GPU if GPU_DEVICE_ID is set, otherwise use all GPUs
        if [ -n "$GPU_DEVICE_ID" ]; then
            gpu_args="--gpus device=${GPU_DEVICE_ID}"
            print_info "GPU detected - using GPU ${GPU_DEVICE_ID} for model initialization"
        else
            gpu_args="--gpus all"
            print_info "GPU detected - using GPU for faster model initialization"
        fi
    else
        print_info "No GPU detected - using CPU (this is fine, just slower)"
    fi

    # Run model download in Docker container with progress output
    print_info "Downloading models (progress shown below)..."
    echo ""

    # Run the download with real-time output
    # IMPORTANT: Backend runs as 'appuser' (UID 1000), so mount to /home/appuser/.cache
    # Note: When using --gpus device=X, Docker remaps that GPU to index 0 inside container
    # So we always use CUDA_VISIBLE_DEVICES=0 inside the container, regardless of host GPU index
    docker run --rm \
        $gpu_args \
        -e CUDA_VISIBLE_DEVICES=0 \
        -e HUGGINGFACE_TOKEN="${HUGGINGFACE_TOKEN}" \
        -e WHISPER_MODEL="${whisper_model}" \
        -e USE_GPU="${use_gpu}" \
        -e COMPUTE_TYPE="${COMPUTE_TYPE:-float16}" \
        -e DIARIZATION_MODEL="${DIARIZATION_MODEL:-pyannote/speaker-diarization-3.1}" \
        -v "$(realpath "$MODEL_CACHE_DIR/huggingface"):/home/appuser/.cache/huggingface" \
        -v "$(realpath "$MODEL_CACHE_DIR/torch"):/home/appuser/.cache/torch" \
        -v "$SCRIPT_DIR/download-models.py:/app/download-models.py:ro" \
        davidamacey/opentranscribe-backend:latest \
        python /app/download-models.py

    local docker_exit_code=$?

    echo ""

    # Check if download succeeded
    if [ $docker_exit_code -eq 0 ]; then
        local total_size=$(get_dir_size "$MODEL_CACHE_DIR")
        print_success "Models downloaded successfully ($total_size)"

        # Create marker file to indicate successful download
        echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "$MODEL_CACHE_DIR/.download_complete"

        return 0
    else
        # Download failed - provide detailed error information
        print_error "Model download failed (exit code: $docker_exit_code)"
        echo ""

        # Check if any models were partially downloaded
        local hf_size=$(du -sb "$MODEL_CACHE_DIR/huggingface" 2>/dev/null | cut -f1 || echo "0")
        local torch_size=$(du -sb "$MODEL_CACHE_DIR/torch" 2>/dev/null | cut -f1 || echo "0")
        local partial_size=$(get_dir_size "$MODEL_CACHE_DIR")

        if [ "$((hf_size + torch_size))" -gt 1000000 ]; then
            print_warning "Partial download detected ($partial_size)"
            echo "Some models may have been downloaded successfully."
            echo "Remaining models will be downloaded on first application use."
        else
            print_error "No models were downloaded"
        fi

        echo ""
        echo -e "${YELLOW}Common causes:${NC}"
        echo "  • Network connectivity issues"
        echo "  • Docker image not available"
        echo "  • Insufficient disk space"
        echo "  • Invalid HuggingFace token"
        echo ""
        echo -e "${YELLOW}Next steps:${NC}"
        echo "  1. Check your internet connection"
        echo "  2. Verify HuggingFace token is valid"
        echo "  3. Try running this script again: bash scripts/download-models.sh models"
        echo "  4. Or continue setup - models will download automatically on first use"
        echo ""

        return 1
    fi
}

download_models_local() {
    print_header "Downloading AI Models (Local Python)"

    print_info "Checking for Python and required packages..."

    if ! command -v python3 &> /dev/null; then
        print_error "Python3 not found. Using Docker method instead..."
        download_models_docker
        return $?
    fi

    # Check for required packages
    local missing_packages=()
    python3 -c "import whisperx" 2>/dev/null || missing_packages+=("whisperx")
    python3 -c "import pyannote.audio" 2>/dev/null || missing_packages+=("pyannote-audio")

    if [ ${#missing_packages[@]} -gt 0 ]; then
        print_warning "Missing Python packages: ${missing_packages[*]}"
        print_info "Using Docker method instead (recommended)..."
        download_models_docker
        return $?
    fi

    # Set environment variables for model cache
    export HF_HOME="$MODEL_CACHE_DIR/huggingface"
    export TORCH_HOME="$MODEL_CACHE_DIR/torch"

    # Run Python download script
    print_info "Running model download script..."
    python3 "$SCRIPT_DIR/download-models.py"
}

show_summary() {
    print_header "Model Download Summary"

    local total_size=$(get_dir_size "$MODEL_CACHE_DIR")
    local hf_size=$(get_dir_size "$MODEL_CACHE_DIR/huggingface")
    local torch_size=$(get_dir_size "$MODEL_CACHE_DIR/torch")

    echo -e "${GREEN}✅ Model cache ready!${NC}"
    echo ""
    echo "Cache location: $MODEL_CACHE_DIR"
    echo "Total size: $total_size"
    echo "  • HuggingFace models: $hf_size"
    echo "  • Torch models: $torch_size"
    echo ""
    print_info "Models are cached and will be available immediately when Docker starts"
    echo ""
}

#######################
# MAIN
#######################

main() {
    print_header "OpenTranscribe Model Downloader"

    print_info "Model cache directory: $MODEL_CACHE_DIR"
    echo ""

    # Check if models already exist
    if check_models_exist; then
        show_summary
        exit 0
    fi

    # Check for HuggingFace token
    check_huggingface_token

    # Download models using Docker (recommended)
    if download_models_docker; then
        show_summary
        exit 0
    else
        print_error "Model download failed"
        echo ""
        print_info "Models will be downloaded automatically when you first run the application,"
        print_info "but this will cause a delay on first use."
        echo ""
        exit 1
    fi
}

# Run main function
main
