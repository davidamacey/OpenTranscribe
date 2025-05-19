import { writable } from 'svelte/store';

// Immediately apply theme before DOM is fully loaded to prevent flash
if (typeof window !== 'undefined') {
  // Get theme from localStorage or system preference
  const savedTheme = localStorage.getItem('theme');
  let initialTheme;
  
  if (savedTheme) {
    initialTheme = savedTheme;
  } else {
    // Check for system preference
    initialTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches 
      ? 'dark' 
      : 'light';
  }
  
  // Apply theme to document immediately - this helps prevent flicker
  document.documentElement.setAttribute('data-theme', initialTheme);
  
  // Also add class to body - helps with transition handling
  document.body.classList.add(`theme-${initialTheme}`);
}

// Check for saved theme preference or use system preference
const getInitialTheme = () => {
  if (typeof window !== 'undefined') {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      return savedTheme;
    }
    
    // Check for system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
  }
  
  // Default to light theme
  return 'light';
};

// Create the theme store
export const theme = writable(getInitialTheme());

// Subscribe to theme changes and update localStorage and document attribute
if (typeof window !== 'undefined') {
  theme.subscribe(value => {
    localStorage.setItem('theme', value);
    document.documentElement.setAttribute('data-theme', value);
    
    // Update body class for additional styling hooks
    document.body.classList.remove('theme-light', 'theme-dark');
    document.body.classList.add(`theme-${value}`);
  });
}

// Function to toggle theme
export const toggleTheme = () => {
  theme.update(currentTheme => {
    return currentTheme === 'light' ? 'dark' : 'light';
  });
};
