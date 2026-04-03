#!/bin/bash

# Campaign Retry Chain Migration Script
# This script migrates old retry campaigns to use the new parent-child chain structure

echo "🚀 Starting campaign retry chain migration..."
echo ""

cd apps/backend || exit 1

# Check if we're in a virtual environment or have the dependencies
if ! python -c "import motor" 2>/dev/null; then
    echo "⚠️  Warning: motor package not found. Make sure you have the backend dependencies installed."
    echo "   Run: pip install -r requirements.txt"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Run the migration
python -m scripts.migrate_retry_campaigns

echo ""
echo "✅ Migration complete!"
echo ""
echo "Next steps:"
echo "1. Check the output above to verify campaigns were linked correctly"
echo "2. Refresh your dashboard to see the updated effective reach metric"
echo "3. The effective reach should now reflect the true reach across retry chains"
