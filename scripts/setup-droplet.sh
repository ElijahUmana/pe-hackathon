#!/bin/bash
# DigitalOcean Droplet Setup Script
# CentOS 9 Stream x64
# Run as root: bash setup-droplet.sh

set -euo pipefail

echo "=== DigitalOcean Droplet Setup ==="
echo "=== MLH PE Hackathon 2026 ==="

# 1. Update system
echo ">>> Updating system packages..."
dnf update -y
dnf install -y git curl wget vim

# 2. Set up swap (2GB) — critical for 1GB RAM droplet
echo ">>> Setting up 2GB swap file..."
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile swap swap defaults 0 0' >> /etc/fstab

# Verify swap
echo ">>> Swap status:"
free -h

# 3. Install Docker
echo ">>> Installing Docker..."
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl start docker
systemctl enable docker

# Verify Docker
docker --version
docker compose version

# 4. Configure firewall
echo ">>> Configuring firewall..."
firewall-cmd --permanent --add-port=80/tcp    # HTTP (Nginx)
firewall-cmd --permanent --add-port=3000/tcp  # Grafana
firewall-cmd --permanent --add-port=9090/tcp  # Prometheus
firewall-cmd --permanent --add-port=9093/tcp  # Alertmanager
firewall-cmd --reload

# 5. Clone the repository
echo ">>> Cloning repository..."
cd /root
if [ -d "pe-hackathon" ]; then
    cd pe-hackathon
    git pull
else
    git clone https://github.com/ElijahUmana/pe-hackathon.git
    cd pe-hackathon
fi

# 6. Create .env from example
echo ">>> Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    # Update for Docker internal networking
    sed -i 's/DATABASE_HOST=localhost/DATABASE_HOST=db/' .env
    sed -i 's/REDIS_URL=redis:\/\/localhost/REDIS_URL=redis:\/\/redis/' .env
fi

# 7. Build and start all services
echo ">>> Building and starting services..."
docker compose build
docker compose up -d

# 8. Wait for services to be healthy
echo ">>> Waiting for services to start..."
sleep 15

# 9. Seed the database
echo ">>> Seeding database..."
docker compose exec app1 uv run python -m app.seed

# 10. Verify everything works
echo ">>> Verifying deployment..."
echo "Health check:"
curl -s http://localhost/health | python3 -m json.tool

echo ""
echo "=== Setup Complete ==="
echo "Services running:"
docker compose ps
echo ""
echo "Access points:"
echo "  App:          http://$(curl -s ifconfig.me)"
echo "  Grafana:      http://$(curl -s ifconfig.me):3000 (admin/hackathon2026)"
echo "  Prometheus:   http://$(curl -s ifconfig.me):9090"
echo "  Alertmanager: http://$(curl -s ifconfig.me):9093"
