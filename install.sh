#!/bin/bash
#
# KrotVPN Interactive Installer v2.4.8
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

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║                         K R O T V P N                        ║"
    echo "║                                                              ║"
    echo "║              Interactive Installer v2.4.8                    ║"
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

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

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

ask_password() {
    local prompt="$1"
    local var="$2"
    
    echo -ne "${YELLOW}${prompt}: ${NC}"
    
    local password=""
    local char=""
    
    while IFS= read -r -n1 -s char < /dev/tty; do
        if [[ -z "$char" ]]; then
            echo ""
            break
        elif [[ "$char" == $'\x7f' ]] || [[ "$char" == $'\x08' ]]; then
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

check_prerequisites() {
    print_step "Step 1: Checking prerequisites"
    
    if ! command -v sshpass &> /dev/null; then
        print_info "Installing sshpass..."
        if command -v sudo &> /dev/null; then
            sudo apt update -qq && sudo apt install -y -qq sshpass
        else
            apt update -qq && apt install -y -qq sshpass
        fi
    fi
    print_success "sshpass available"
    
    if ! command -v ssh &> /dev/null; then
        print_error "SSH client not found"
        exit 1
    fi
    print_success "SSH client available"
}

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

get_credentials() {
    print_step "Step 3: SSH credentials"
    
    echo -e "${BLUE}Enter SSH credentials:${NC}"
    echo ""
    
    echo -e "${CYAN}RU Server (${RU_IP}):${NC}"
    ask "  SSH username" "root" RU_USER
    ask_password "  SSH password" RU_PASS
    if [ -z "$RU_PASS" ]; then
        print_error "Password is required"
        exit 1
    fi
    echo ""
    
    echo -e "${CYAN}DE Server (${DE_IP}):${NC}"
    ask "  SSH username" "root" DE_USER
    ask_password "  SSH password" DE_PASS
    if [ -z "$DE_PASS" ]; then
        print_error "Password is required"
        exit 1
    fi
    echo ""
    
    print_info "Testing connection to RU server..."
    if sshpass -p "$RU_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o LogLevel=ERROR "$RU_USER@$RU_IP" "echo ok" 2>/dev/null | grep -q "ok"; then
        print_success "RU server connection OK"
    else
        print_error "Cannot connect to RU server. Check credentials."
        exit 1
    fi
    
    print_info "Testing connection to DE server..."
    if sshpass -p "$DE_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o LogLevel=ERROR "$DE_USER@$DE_IP" "echo ok" 2>/dev/null | grep -q "ok"; then
        print_success "DE server connection OK"
    else
        print_error "Cannot connect to DE server. Check credentials."
        exit 1
    fi
}

deploy() {
    print_step "Step 4: Starting deployment"
    
    echo -e "${BLUE}This will:${NC}"
    echo -e "  1. Clone KrotVPN on RU server"
    echo -e "  2. Install dependencies on both servers"
    echo -e "  3. Configure AmneziaWG VPN tunnel"
    echo -e "  4. Start Docker containers with HTTPS"
    echo ""
    
    ask_yesno "Start deployment?" "y" START
    if [ "$START" != "y" ]; then
        print_error "Deployment cancelled"
        exit 1
    fi
    
    print_info "Deploying... This will take 10-15 minutes."
    echo ""
    
    # Encode passwords in base64 (handles ALL special characters)
    RU_PASS_B64=$(echo -n "$RU_PASS" | base64 -w0)
    DE_PASS_B64=$(echo -n "$DE_PASS" | base64 -w0)
    
    # Create config file on RU server with base64 encoded passwords
    print_info "Creating configuration on RU server..."
    sshpass -p "$RU_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR "$RU_USER@$RU_IP" "cat > /tmp/krotvpn_deploy.conf" << EOF
DE_IP='${DE_IP}'
DE_USER='${DE_USER}'
DE_PASS_B64='${DE_PASS_B64}'
RU_IP='${RU_IP}'
RU_USER='${RU_USER}'
RU_PASS_B64='${RU_PASS_B64}'
EOF
    
    if [ $? -ne 0 ]; then
        print_error "Failed to create config file"
        exit 1
    fi
    print_success "Config created"
    
    # Clone repository
    print_info "Cloning KrotVPN repository..."
    sshpass -p "$RU_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR "$RU_USER@$RU_IP" "
        cd /opt
        rm -rf KrotVPN 2>/dev/null || true
        git clone https://github.com/anyagixx/KrotVPN.git
        chmod +x /opt/KrotVPN/deploy/*.sh
    "
    
    if [ $? -ne 0 ]; then
        print_error "Failed to clone repository"
        exit 1
    fi
    print_success "Repository cloned"
    
    # Run deployment script
    print_info "Running deployment script on RU server..."
    echo ""
    
    sshpass -p "$RU_PASS" ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR "$RU_USER@$RU_IP" "cd /opt/KrotVPN && ./deploy/deploy-on-server.sh"
}

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
    echo -e "${YELLOW}Note: Browser will warn about self-signed certificate.${NC}"
    echo -e "${YELLOW}Click 'Advanced' → 'Proceed' to continue.${NC}"
    echo ""
    echo -e "${CYAN}Create VPN client:${NC}"
    echo ""
    echo -e "  ssh root@${RU_IP} \"/opt/KrotVPN/deploy/create-client.sh my_client\""
    echo ""
    echo -e "${CYAN}Configure in /opt/KrotVPN/.env:${NC}"
    echo ""
    echo -e "  • YOOKASSA_SHOP_ID     - for payments"
    echo -e "  • YOOKASSA_SECRET_KEY  - for payments"
    echo -e "  • TELEGRAM_BOT_TOKEN   - for Telegram bot"
    echo -e "  • ADMIN_PASSWORD       - ${RED}change default!${NC}"
    echo ""
}

main() {
    print_banner
    check_prerequisites
    get_server_info
    get_credentials
    deploy
    show_complete
}

main "$@"
