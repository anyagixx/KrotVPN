#!/bin/bash
#
# KrotVPN Interactive Installer
# Run this command to install:
#   curl -fsSL https://raw.githubusercontent.com/anyagixx/KrotVPN/main/install.sh | bash
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Credentials (will be set during installation)
RU_IP=""
RU_USER="root"
RU_PASS=""
DE_IP=""
DE_USER="root"
DE_PASS=""

# Print functions
print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║                         K R O T V P N                        ║"
    echo "║                                                              ║"
    echo "║              Interactive Installer v2.1.2                    ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Read input from terminal (works with curl | bash)
ask() {
    local prompt="$1"
    local default="$2"
    local var="$3"
    
    if [ -n "$default" ]; then
        echo -ne "${YELLOW}${prompt} [${default}]: ${NC}"
    else
        echo -ne "${YELLOW}${prompt}: ${NC}"
    fi
    
    read -r value < /dev/tty
    
    if [ -z "$value" ] && [ -n "$default" ]; then
        value="$default"
    fi
    
    eval "$var='$value'"
}

# Read password with asterisks
ask_password() {
    local prompt="$1"
    local var="$2"
    
    echo -ne "${YELLOW}${prompt}: ${NC}"
    
    local password=""
    local char=""
    
    while IFS= read -r -n1 -s char < /dev/tty; do
        if [[ -z "$char" ]]; then
            # Enter pressed
            echo ""
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\x08' ]]; then
            # Backspace
            if [ -n "$password" ]; then
                password="${password%?}"
                echo -ne "\b \b"
            fi
        else
            password+="$char"
            echo -n "*"
        fi
    done
    
    eval "$var='$password'"
}

ask_yesno() {
    local prompt="$1"
    local default="$2"
    local var="$3"
    
    if [ "$default" = "y" ]; then
        echo -ne "${YELLOW}${prompt} [Y/n]: ${NC}"
    else
        echo -ne "${YELLOW}${prompt} [y/N]: ${NC}"
    fi
    
    read -r value < /dev/tty
    
    value=$(echo "$value" | tr '[:upper:]' '[:lower:]')
    
    if [ -z "$value" ]; then
        value="$default"
    fi
    
    if [ "$value" = "y" ] || [ "$value" = "yes" ]; then
        eval "$var='y'"
    else
        eval "$var='n'"
    fi
}

# SSH command with password
ssh_cmd() {
    local host="$1"
    local user="$2"
    local pass="$3"
    shift 3
    local cmd="$@"
    
    sshpass -p "$pass" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o LogLevel=ERROR "$user@$host" "$cmd"
}

# SCP with password
scp_cmd() {
    local src="$1"
    local host="$2"
    local user="$3"
    local pass="$4"
    local dst="$5"
    
    sshpass -p "$pass" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o LogLevel=ERROR "$src" "$user@$host:$dst"
}

# Check environment
check_environment() {
    print_step "Step 1: Checking environment"
    
    # Check if we're on Linux
    if [ "$(uname -s)" != "Linux" ]; then
        print_error "This installer only works on Linux"
        print_info "If you're on Windows/Mac, use WSL2 or a Linux VM"
        exit 1
    fi
    print_success "Running on Linux"
    
    # Check if we have SSH
    if ! command -v ssh &> /dev/null; then
        print_error "SSH client not found"
        print_info "Install with: sudo apt install openssh-client"
        exit 1
    fi
    print_success "SSH client available"
    
    # Check if we have curl/wget
    if command -v curl &> /dev/null; then
        print_success "curl available"
        DOWNLOADER="curl"
    elif command -v wget &> /dev/null; then
        print_success "wget available"
        DOWNLOADER="wget"
    else
        print_error "Neither curl nor wget found"
        print_info "Install with: sudo apt install curl"
        exit 1
    fi
    
    # Check/install sshpass
    if ! command -v sshpass &> /dev/null; then
        print_info "Installing sshpass..."
        if command -v sudo &> /dev/null; then
            sudo apt update -qq && sudo apt install -y -qq sshpass
        else
            apt update -qq && apt install -y -qq sshpass
        fi
    fi
    print_success "sshpass available"
}

# Get server information
get_server_info() {
    print_step "Step 2: Server configuration"
    
    echo -e "${BLUE}KrotVPN requires two servers:${NC}"
    echo -e "  ${CYAN}• RU Server (Russia)${NC} - Entry node, hosts the application"
    echo -e "  ${CYAN}• DE Server (Germany/EU)${NC} - Exit node, provides internet access"
    echo ""
    
    ask "Enter RU Server IP address" "" RU_IP
    if [ -z "$RU_IP" ]; then
        print_error "RU Server IP is required"
        exit 1
    fi
    
    ask "Enter DE Server IP address" "" DE_IP
    if [ -z "$DE_IP" ]; then
        print_error "DE Server IP is required"
        exit 1
    fi
    
    echo ""
    echo -e "${GREEN}Configuration:${NC}"
    echo -e "  RU Server: ${CYAN}${RU_IP}${NC}"
    echo -e "  DE Server: ${CYAN}${DE_IP}${NC}"
    echo ""
    
    ask_yesno "Is this correct?" "y" CONFIRM
    if [ "$CONFIRM" != "y" ]; then
        print_error "Installation cancelled"
        exit 1
    fi
}

# Get SSH credentials
get_credentials() {
    print_step "Step 3: SSH credentials"
    
    echo -e "${BLUE}Enter SSH credentials for your servers:${NC}"
    echo ""
    
    # RU Server credentials
    echo -e "${CYAN}RU Server (${RU_IP}):${NC}"
    ask "  SSH username" "root" RU_USER
    ask_password "  SSH password" RU_PASS
    
    if [ -z "$RU_PASS" ]; then
        print_error "Password is required"
        exit 1
    fi
    echo ""
    
    # DE Server credentials
    echo -e "${CYAN}DE Server (${DE_IP}):${NC}"
    ask "  SSH username" "root" DE_USER
    ask_password "  SSH password" DE_PASS
    
    if [ -z "$DE_PASS" ]; then
        print_error "Password is required"
        exit 1
    fi
    echo ""
    
    # Test connections
    print_info "Testing connection to RU server..."
    if ssh_cmd "$RU_IP" "$RU_USER" "$RU_PASS" "echo ok" 2>/dev/null | grep -q "ok"; then
        print_success "RU server connection OK"
    else
        print_error "Cannot connect to RU server. Check credentials."
        exit 1
    fi
    
    print_info "Testing connection to DE server..."
    if ssh_cmd "$DE_IP" "$DE_USER" "$DE_PASS" "echo ok" 2>/dev/null | grep -q "ok"; then
        print_success "DE server connection OK"
    else
        print_error "Cannot connect to DE server. Check credentials."
        exit 1
    fi
}

# Clone repository
clone_repo() {
    print_step "Step 4: Downloading KrotVPN"
    
    INSTALL_DIR="${INSTALL_DIR:-/opt/KrotVPN}"
    
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Directory $INSTALL_DIR already exists"
        ask_yesno "Remove and reinstall?" "y" REINSTALL
        if [ "$REINSTALL" = "y" ]; then
            rm -rf "$INSTALL_DIR"
        else
            cd "$INSTALL_DIR"
            print_info "Using existing installation"
            return
        fi
    fi
    
    print_info "Cloning KrotVPN repository..."
    git clone https://github.com/anyagixx/KrotVPN.git "$INSTALL_DIR"
    print_success "Cloned from GitHub"
    
    cd "$INSTALL_DIR"
}

# Run deployment
run_deployment() {
    print_step "Step 5: Starting deployment"
    
    echo -e "${BLUE}This will:${NC}"
    echo -e "  1. Install dependencies on both servers"
    echo -e "  2. Install and configure AmneziaWG"
    echo -e "  3. Set up VPN tunnel between servers"
    echo -e "  4. Install Docker and run KrotVPN containers"
    echo -e "  5. Generate SSL certificates for HTTPS"
    echo ""
    
    ask_yesno "Start deployment?" "y" START_DEPLOY
    if [ "$START_DEPLOY" != "y" ]; then
        print_error "Deployment cancelled"
        exit 1
    fi
    
    print_info "This will take 10-15 minutes. Please wait..."
    echo ""
    
    # Run deploy-all.sh with credentials
    cd "$INSTALL_DIR"
    chmod +x deploy/deploy-all.sh
    
    # Export credentials for deploy script
    export RU_IP RU_USER RU_PASS DE_IP DE_USER DE_PASS
    
    ./deploy/deploy-all.sh
    
    DEPLOY_EXIT=$?
    
    if [ $DEPLOY_EXIT -ne 0 ]; then
        print_error "Deployment failed with exit code $DEPLOY_EXIT"
        print_info "Check the logs above for errors"
        exit 1
    fi
}

# Final instructions
show_complete() {
    print_step "Installation Complete!"
    
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║              🎉 KrotVPN is now installed! 🎉                ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo -e "${CYAN}Access your VPN service:${NC}"
    echo ""
    echo -e "  ${GREEN}Frontend:${NC}    https://${RU_IP}"
    echo -e "  ${GREEN}Admin Panel:${NC} https://${RU_IP}:8443"
    echo -e "  ${GREEN}Backend API:${NC} https://${RU_IP}:8000"
    echo ""
    echo -e "${YELLOW}Note: Your browser will warn about self-signed certificate.${NC}"
    echo -e "${YELLOW}This is normal - click 'Advanced' → 'Proceed' to continue.${NC}"
    echo ""
    echo -e "${CYAN}Create your first VPN client:${NC}"
    echo ""
    echo -e "  ssh root@${RU_IP} \"/opt/KrotVPN/deploy/create-client.sh my_client\""
    echo ""
    echo -e "${CYAN}Configure in /opt/KrotVPN/.env:${NC}"
    echo ""
    echo -e "  • YOOKASSA_SHOP_ID     - for payments"
    echo -e "  • YOOKASSA_SECRET_KEY  - for payments"
    echo -e "  • TELEGRAM_BOT_TOKEN   - for Telegram bot"
    echo -e "  • ADMIN_PASSWORD       - change default password!"
    echo ""
    echo -e "${CYAN}Support:${NC}"
    echo ""
    echo -e "  GitHub: https://github.com/anyagixx/KrotVPN"
    echo ""
}

# Main
main() {
    print_banner
    check_environment
    get_server_info
    get_credentials
    clone_repo
    run_deployment
    show_complete
}

main "$@"
