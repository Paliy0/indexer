#!/bin/bash
set -e

PROJECT_DIR="/home/ubuntu/indexer"
cd "$PROJECT_DIR"

echo "=== Site Search Platform - Ralph Autonomous Loop ==="
echo ""

# Step 1: Set up Python virtual environment
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating Python virtual environment..."
    rm -rf venv
    sudo apt-get install -y python3-venv python3-pip > /dev/null 2>&1
    python3 -m venv venv
fi
source venv/bin/activate
echo "Python venv activated: $(which python)"
echo "pip: $(pip --version)"
echo ""

# Step 2: Initialize git repo if needed
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
    git add -A
    git commit --author="Ralph AI <pabloguliasprats@gmail.com>" -m "Initial commit: project documentation and web-parser"
    echo ""
fi

# Step 3: Create GitHub repo and push if no remote exists
if ! git remote get-url origin &>/dev/null; then
    echo "Creating GitHub repository Paliy0/indexer..."
    gh repo create Paliy0/indexer --public --source=. --remote=origin --push
    echo ""
else
    echo "Remote 'origin' already configured: $(git remote get-url origin)"
    # Ensure main branch is pushed
    git push origin main 2>/dev/null || git push -u origin main 2>/dev/null || true
    echo ""
fi

echo "=== Starting Ralph Loop ==="
echo "Provider:       openrouter"
echo "Model:          deepseek/deepseek-v3.2"
echo "Max iterations: 30"
echo "Task promise:   READY_FOR_NEXT_TASK"
echo "Log file:       $PROJECT_DIR/ralph.log"
echo ""

# Step 4: Run Ralph
ralph --prompt-file "$PROJECT_DIR/ralph-executor-prompt.txt" \
  --agent opencode \
  --model openrouter/deepseek/deepseek-v3.2 \
  --tasks \
  --task-promise READY_FOR_NEXT_TASK \
  --max-iterations 30 \
  --no-commit \
  2>&1 | tee "$PROJECT_DIR/ralph.log"
