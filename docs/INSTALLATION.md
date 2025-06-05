# OpenTranscribe One-Line Installation Guide

## 🚀 Quick Installation (Any Platform)

**Copy and paste this single command on any operating system:**

```bash
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

**That's it!** The script will:
- ✅ Detect your hardware automatically (NVIDIA GPU, Apple Silicon, CPU)
- ✅ Configure optimal settings for your platform
- ✅ Set up Docker with proper runtime
- ✅ Download all necessary files
- ✅ Create management scripts
- ✅ Generate secure configuration

## 🌍 Platform Compatibility

### ✅ **Linux (All Distributions)**
```bash
# Ubuntu, Debian, CentOS, Fedora, Arch, etc.
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

### ✅ **macOS (Intel & Apple Silicon)**
```bash
# Works on both Intel Macs and Apple Silicon (M1/M2)
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

### ✅ **Windows (WSL2)**
```bash
# In WSL2 terminal
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

### ✅ **Windows (Git Bash/Cygwin)**
```bash
# In Git Bash or Cygwin terminal
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

## 📋 Prerequisites

**Required (automatically checked):**
- Docker (with daemon running)
- Docker Compose v2+
- `curl` command
- Internet connection

**Optional (auto-detected):**
- NVIDIA GPU + NVIDIA Container Toolkit (for GPU acceleration)
- HuggingFace account (for speaker diarization)

## 🔧 What Happens During Installation

1. **Platform Detection**: Identifies your OS and architecture
2. **Hardware Detection**: Scans for NVIDIA GPU, Apple Silicon, or CPU
3. **Docker Validation**: Checks Docker installation and runtime capabilities
4. **Configuration Download**: Downloads optimized docker-compose and config files
5. **Environment Setup**: Creates secure `.env` with hardware-specific settings
6. **Script Creation**: Generates management script for daily operations
7. **Validation**: Confirms everything is properly configured

## 🎯 Hardware-Specific Optimizations

| Platform | Device | Precision | Batch Size | Recommended Model |
|----------|--------|-----------|------------|-------------------|
| Linux + NVIDIA RTX 40x0 | `cuda` | `float16` | `16` | `large-v2` |
| Linux + NVIDIA RTX 30x0 | `cuda` | `float16` | `8-12` | `large-v2` |
| Linux + NVIDIA GTX/older | `cuda` | `float32` | `4-8` | `medium` |
| macOS + M2 Max/Ultra | `mps` | `float32` | `8` | `medium` |
| macOS + M1/M2 | `mps` | `float32` | `4-6` | `small` |
| Intel Mac | `cpu` | `int8` | `2-4` | `base` |
| Any CPU (16+ cores) | `cpu` | `int8` | `4` | `small` |
| Any CPU (8+ cores) | `cpu` | `int8` | `2` | `base` |
| Any CPU (4 cores) | `cpu` | `int8` | `1` | `base` |

## 🚀 After Installation

**Start OpenTranscribe:**
```bash
cd opentranscribe
./opentranscribe.sh start
```

**Access the application:**
- Web Interface: http://localhost:5173
- API Documentation: http://localhost:8080/docs
- Task Monitor: http://localhost:5555/flower

## 🛠️ Edge Cases & Troubleshooting

### **Issue: Permission Denied**
```bash
# If you get permission denied, run with explicit bash:
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh -o setup.sh
chmod +x setup.sh
./setup.sh
```

### **Issue: No curl Command**
```bash
# On older systems without curl, use wget:
wget -qO- https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash

# Or download manually:
wget https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh
bash setup-opentranscribe.sh
```

### **Issue: Corporate Firewall/Proxy**
```bash
# Set proxy environment variables:
export http_proxy=http://proxy.company.com:8080
export https_proxy=http://proxy.company.com:8080
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

### **Issue: Docker Not Running**
```bash
# Start Docker daemon:
sudo systemctl start docker      # Linux (systemd)
sudo service docker start       # Linux (service)
open -a Docker                  # macOS
# Or start Docker Desktop manually
```

### **Issue: NVIDIA GPU Not Detected**
```bash
# Check GPU availability:
nvidia-smi

# Install NVIDIA Container Toolkit:
# Ubuntu/Debian:
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Test GPU in Docker:
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi
```

### **Issue: Apple Silicon Docker Issues**
```bash
# Ensure Docker Desktop is set to use Apple Silicon emulation:
# Docker Desktop > Settings > General > "Use Rosetta for x86/amd64 emulation" (disabled)
# Docker Desktop > Settings > Features in Development > "Use containerd for pulling and storing images" (enabled)
```

### **Issue: Low Memory/Storage**
```bash
# Check available space (needs ~10GB):
df -h

# Check available memory (needs ~4GB):
free -h  # Linux
vm_stat  # macOS

# Clean Docker if needed:
docker system prune -a
```

### **Issue: Windows Subsystem for Linux (WSL2)**
```bash
# Ensure WSL2 is properly configured:
wsl --list --verbose  # Should show version 2
wsl --set-default-version 2

# Install WSL2 Docker integration:
# Install Docker Desktop for Windows with WSL2 backend
```

### **Issue: Slow Internet/Timeouts**
```bash
# Increase timeout and retry:
curl -fsSL --max-time 300 --retry 3 https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

### **Issue: Different Architecture**
```bash
# For ARM64 systems (Raspberry Pi, etc.):
export TARGETPLATFORM=linux/arm64
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

## 🔄 Manual Installation (Alternative)

If the one-line installation doesn't work, you can install manually:

```bash
# 1. Create directory and download
mkdir opentranscribe && cd opentranscribe
curl -O https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh
chmod +x setup-opentranscribe.sh

# 2. Run setup
./setup-opentranscribe.sh

# 3. Start application
./opentranscribe.sh start
```

## 📞 Support

If you encounter any issues:

1. **Check Prerequisites**: Ensure Docker is installed and running
2. **Review Logs**: Look at the setup script output for error messages
3. **Hardware Validation**: Run `docker run --rm hello-world` to test Docker
4. **GPU Testing**: Run `nvidia-smi` (NVIDIA) or check system info (Apple Silicon)
5. **Create Issue**: Open a GitHub issue with your platform details and error logs

## 🔐 Security Notes

- The setup script downloads files from GitHub using HTTPS
- JWT secrets are automatically generated using secure random methods
- No sensitive data is transmitted during installation
- All containers run with non-root users where possible

## 🌟 Advanced Usage

**Custom Installation Directory:**
```bash
export PROJECT_DIR="my-transcribe-app"
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

**Force Specific Hardware:**
```bash
export TORCH_DEVICE=cpu  # Force CPU mode
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

**Skip Interactive Prompts:**
```bash
export HUGGINGFACE_TOKEN=your_token_here
export WHISPER_MODEL=base
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```

---

**Ready to transcribe on any platform with one command! 🎉**