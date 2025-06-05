import { existsSync, mkdirSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import fetch from 'node-fetch';
import https from 'https';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const fontsDir = join(__dirname, '../public/fonts');

// Create fonts directory if it doesn't exist
if (!existsSync(fontsDir)) {
  mkdirSync(fontsDir, { recursive: true });
}

const fontWeights = {
  300: { name: 'Light', url: 'https://fonts.gstatic.com/s/poppins/v20/pxiByp8kv8JHgFVrLDz8Z1xlEQ.woff2' },
  400: { name: 'Regular', url: 'https://fonts.gstatic.com/s/poppins/v20/pxiEyp8kv8JHgFVrJJfecg.woff2' },
  500: { name: 'Medium', url: 'https://fonts.gstatic.com/s/poppins/v20/pxiByp8kv8JHgFVrLGT9Z1xlEQ.woff2' },
  600: { name: 'SemiBold', url: 'https://fonts.gstatic.com/s/poppins/v20/pxiByp8kv8JHgFVrLEj6Z1xlEQ.woff2' },
  700: { name: 'Bold', url: 'https://fonts.gstatic.com/s/poppins/v20/pxiByp8kv8JHgFVrLCz7Z1xlEQ.woff2' }
};

// Download a file from URL
async function downloadFile(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to download ${url}: ${response.status} ${response.statusText}`);
    }
    const buffer = await response.buffer();
    return buffer;
  } catch (error) {
    console.error(`Error downloading ${url}:`, error.message);
    throw error;
  }
}

// Download all font files
async function downloadFonts() {
  try {
    // Create a CSS file with @font-face rules
    let cssContent = '/* Google Fonts - Poppins */\n';
    
    // Download each font file directly from Google Fonts
    for (const [weight, fontInfo] of Object.entries(fontWeights)) {
      const fontFileName = `Poppins-${fontInfo.name}.woff2`;
      const localPath = join(fontsDir, fontFileName);
      
      console.log(`Downloading ${fontFileName}...`);
      try {
        const fontData = await downloadFile(fontInfo.url);
        writeFileSync(localPath, fontData);
        
        // Add @font-face rule
        cssContent += `\n@font-face {\n`;
        cssContent += `  font-family: 'Poppins';\n`;
        cssContent += `  font-style: normal;\n`;
        cssContent += `  font-weight: ${weight};\n`;
        cssContent += `  font-display: swap;\n`;
        cssContent += `  src: local('Poppins ${fontInfo.name}'), local('Poppins-${fontInfo.name}'), `;
        cssContent += `url('/fonts/${fontFileName}') format('woff2');\n`;
        cssContent += `  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+2074, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;\n`;
        cssContent += `}\n`;
        
        console.log(`Downloaded ${fontFileName}`);
      } catch (error) {
        console.error(`Error downloading ${fontFileName}:`, error.message);
        // Continue with other fonts even if one fails
      }
    }
    
    // Write the CSS file
    writeFileSync(join(fontsDir, 'poppins.css'), cssContent);
    console.log('Generated poppins.css with @font-face rules');
    console.log('All fonts downloaded successfully!');
  } catch (error) {
    console.error('Error in font download process:', error);
    process.exit(1);
  }
}

// Main function
async function main() {
  await downloadFonts();
}

main();
