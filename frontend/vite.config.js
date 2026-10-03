import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Enable the React transform and Vite's fast development server.
export default defineConfig({
  plugins: [react()],
});
