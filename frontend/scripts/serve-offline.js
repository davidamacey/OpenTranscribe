const express = require('express');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

const PORT = 3000;
const DIST_DIR = path.join(__dirname, '../dist');

// Build the production version
console.log('Building production version...');
try {
  execSync('npm run build', { stdio: 'inherit' });
  console.log('Build completed successfully');
} catch (error) {
  console.error('Build failed:', error);
  process.exit(1);
}

// Create a simple HTTP server to serve the built files
const app = express();

// Serve static files from the dist directory
app.use(express.static(DIST_DIR, { extensions: ['html'] }));

// Handle client-side routing - return index.html for all other requests
app.get('*', (req, res) => {
  res.sendFile(path.join(DIST_DIR, 'index.html'));
});

// Start the server
app.listen(PORT, () => {
  console.log(`\nOffline server running at http://localhost:${PORT}`);
  console.log('Press Ctrl+C to stop the server');
  console.log('\nTo test offline functionality:');
  console.log('1. Open Chrome DevTools (F12)');
  console.log('2. Go to Application > Service Workers');
  console.log('3. Check "Offline" to simulate offline mode');
  console.log('4. Refresh the page to see offline behavior');
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down server...');
  process.exit(0);
});
