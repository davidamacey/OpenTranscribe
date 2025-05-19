#!/bin/bash

# Script to push OpenTranscribe to GitHub with proper checks
# Usage: ./scripts/push_to_github.sh

echo "🚀 Preparing to push OpenTranscribe to GitHub..."

# Set the GitHub repository URL
GITHUB_REPO="https://github.com/davidamacey/OpenTranscribe.git"

# Check if git is initialized
if [ ! -d ".git" ]; then
  echo "🔧 Initializing git repository..."
  git init
  echo "✅ Git repository initialized."
else
  echo "✅ Git repository already initialized."
fi

# Check for .env file
if [ -f ".env" ]; then
  echo "⚠️ WARNING: .env file detected with potentially sensitive data."
  echo "   This file is in .gitignore and should not be pushed, but you may want to review it."
  echo "   Continuing with push preparation..."
fi

# Check git remote
if git remote | grep -q "origin"; then
  echo "🔄 Updating 'origin' remote to point to ${GITHUB_REPO}..."
  git remote set-url origin ${GITHUB_REPO}
else
  echo "🔄 Adding 'origin' remote pointing to ${GITHUB_REPO}..."
  git remote add origin ${GITHUB_REPO}
fi

# Stage files
echo "📋 Staging files..."
git add .

# Show status
echo "📊 Current status:"
git status

# Ready for commit message
echo ""
echo "✅ Repository is ready for your commit."
echo ""
echo "🔍 Please review the staged files above to ensure no sensitive data is being committed."
echo ""
echo "📝 Commit your changes with:"
echo "   git commit -m \"Your commit message here\""
echo ""
echo "☁️ Then push to GitHub with:"
echo "   git push -u origin main"
echo ""
echo "🎉 Thank you for using OpenTranscribe!"
