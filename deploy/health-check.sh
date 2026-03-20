#!/bin/bash
#
# KrotVPN Health Check Script
# Run on RU server to verify everything is working
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}          KrotVPN Health Check                  ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

ERRORS=0

# Check 1: AmneziaWG Server Interface
echo -e "${YELLOW}[1/8] Checking AmneziaWG server interface (awg0)...${NC}"
if ip link show awg0 &>/dev/null; then
    echo -e "${GREEN}✓ awg0 interface exists${NC}"
else
    echo -e "${RED}✗ awg0 interface not found${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 2: AmneziaWG Client Interface
echo -e "${YELLOW}[2/8] Checking AmneziaWG client interface (awg-client)...${NC}"
if ip link show awg-client &>/dev/null; then
    echo -e "${GREEN}✓ awg-client interface exists${NC}"
else
    echo -e "${RED}✗ awg-client interface not found${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 3: Tunnel to DE Server
echo -e "${YELLOW}[3/8] Checking tunnel to DE server...${NC}"
if ping -c 1 -W 2 10.200.0.1 &>/dev/null; then
    echo -e "${GREEN}✓ Tunnel to DE server working${NC}"
else
    echo -e "${RED}✗ Cannot reach DE server (10.200.0.1)${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 4: Docker containers
echo -e "${YELLOW}[4/8] Checking Docker containers...${NC}"
cd /opt/KrotVPN
for container in krotvpn-db krotvpn-redis krotvpn-backend krotvpn-frontend krotvpn-admin; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "${GREEN}✓ ${container} running${NC}"
    else
        echo -e "${RED}✗ ${container} not running${NC}"
        ERRORS=$((ERRORS+1))
    fi
done

# Check 5: Backend health
echo -e "${YELLOW}[5/8] Checking backend health...${NC}"
if curl -sf http://localhost:8000/health &>/dev/null; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${RED}✗ Backend health check failed${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 6: Database connection
echo -e "${YELLOW}[6/8] Checking database connection...${NC}"
if docker exec krotvpn-db pg_isready -U krotvpn &>/dev/null; then
    echo -e "${GREEN}✓ Database is ready${NC}"
else
    echo -e "${RED}✗ Database not ready${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 7: Redis connection
echo -e "${YELLOW}[7/8] Checking Redis connection...${NC}"
if docker exec krotvpn-redis redis-cli ping 2>/dev/null | grep -q PONG; then
    echo -e "${GREEN}✓ Redis is ready${NC}"
else
    echo -e "${RED}✗ Redis not ready${NC}"
    ERRORS=$((ERRORS+1))
fi

# Check 8: RU IPset
echo -e "${YELLOW}[8/8] Checking RU IPset...${NC}"
COUNT=$(ipset list ru_ips 2>/dev/null | grep 'Number of entries' | awk '{print $4}' || echo "0")
if [ "$COUNT" -gt 100 ]; then
    echo -e "${GREEN}✓ RU IPset has ${COUNT} entries${NC}"
else
    echo -e "${YELLOW}⚠ RU IPset has only ${COUNT} entries (run update_ru_ips.sh)${NC}"
fi

# Summary
echo ""
echo -e "${BLUE}================================================${NC}"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}        ALL CHECKS PASSED! ✓                   ${NC}"
else
    echo -e "${RED}        ${ERRORS} CHECK(S) FAILED! ✗                   ${NC}"
fi
echo -e "${BLUE}================================================${NC}"

# Show status
echo ""
echo -e "${BLUE}AmneziaWG Status:${NC}"
awg show 2>/dev/null || echo "  Not available"

echo ""
echo -e "${BLUE}Docker Status:${NC}"
docker compose ps 2>/dev/null || echo "  Not available"

exit $ERRORS
