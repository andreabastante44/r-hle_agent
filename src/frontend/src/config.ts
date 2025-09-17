// Frontend Configuration
// Erstelle eine .env Datei im Frontend-Ordner mit diesen Werten:

export const config = {
  // API Base URL - ändere dies entsprechend deiner API
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  
  // Mock Mode - setze auf false um echte API zu verwenden
  USE_MOCK: import.meta.env.VITE_USE_MOCK === 'true',
  
  // Development Mode
  DEV_MODE: import.meta.env.VITE_DEV_MODE === 'true' || import.meta.env.DEV,
};

// Für .env Datei erstelle folgende Datei: src/frontend/.env
// VITE_API_BASE_URL=http://localhost:8000
// VITE_USE_MOCK=false
// VITE_DEV_MODE=true
