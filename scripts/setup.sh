#!/usr/bin/env bash
set -e

echo "🤖 Engineering AI Assistant — Setup"
echo "======================================"

# -------------------------
# Detect Python command
# -------------------------
if command -v python3 &>/dev/null; then
  PYTHON=python3
elif command -v python &>/dev/null; then
  PYTHON=python
elif command -v py &>/dev/null; then
  PYTHON=py
else
  echo "❌ Python is required. Install from https://python.org"
  exit 1
fi

echo "✓ Using Python: $($PYTHON --version 2>&1)"

# -------------------------
# Check Node
# -------------------------
if ! command -v node &>/dev/null; then
  echo "❌ Node.js 18+ is required. Install from https://nodejs.org"
  exit 1
fi

echo "✓ Node.js $(node --version) found"

# -------------------------
# Create .env if missing
# -------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✓ Created .env from .env.example"
  echo ""
  echo "⚠️  Add at least one API key in .env:"
  echo "   ANTHROPIC_API_KEY=..."
  echo "   OPENAI_API_KEY=..."
  echo "   GEMINI_API_KEY=..."
  echo ""
fi

# -------------------------
# Backend setup
# -------------------------
echo "Setting up Python backend..."
cd backend

# Create venv if not exists
if [ ! -d "venv" ]; then
  $PYTHON -m venv venv
fi

# Activate venv (cross-platform)
if [ -f "venv/Scripts/activate" ]; then
  source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

# Upgrade pip + install dependencies
$PYTHON -m pip install --upgrade pip
pip install -r requirements.txt

echo "✓ Backend dependencies installed"
cd ..

# -------------------------
# Frontend setup
# -------------------------
echo "Setting up frontend..."
cd frontend
npm install
echo "✓ Frontend dependencies installed"
cd ..

# -------------------------
# Data directory
# -------------------------
mkdir -p data/chroma
echo "✓ Data directory ready"

# -------------------------
# Done
# -------------------------
echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the application:"
echo ""
echo "Backend:"
echo "  cd backend"
echo "  source venv/bin/activate   # Linux/macOS"
echo "  venv\\Scripts\\activate    # Windows"
echo "  uvicorn backend.api.main:app --reload --port 8000"
echo ""
echo "Frontend:"
echo "  cd frontend"
echo "  npm run dev"
echo ""
echo "Then open:"
echo "  http://localhost:5173"
echo ""