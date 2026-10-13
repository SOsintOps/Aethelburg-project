# Aethelburg - Project Startup Script
# Starts Docker services and runs the application

Write-Host "Starting Aethelburg..." -ForegroundColor Cyan

# Start Docker services
docker compose up -d db
Write-Host "Waiting for PostgreSQL..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Run migrations
python -m alembic upgrade head

# Start application
python -m src.main
