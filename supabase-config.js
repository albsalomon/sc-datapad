/**
 * VetDose — Configuración de Supabase
 * ─────────────────────────────────────
 * Rellena SUPABASE_URL y SUPABASE_ANON_KEY con los valores de tu proyecto.
 * Los encuentras en: Supabase Dashboard → Settings → API
 *
 * Para Vercel: define estas variables de entorno en el dashboard de Vercel
 * y usa un build step para inyectarlas aquí, o ponlas directamente si el
 * repo es privado (la anon key es pública por diseño).
 *
 * Variables de entorno recomendadas (.env):
 *   SUPABASE_URL=https://xxxxxxxxxxxxxxxxxxxx.supabase.co
 *   SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
 */

const SUPABASE_URL      = 'https://xmsknhqfuufluenqzstq.supabase.co';   // ← cambia esto
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhtc2tuaHFmdXVmbHVlbnF6c3RxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMDk4NTYsImV4cCI6MjA5MDc4NTg1Nn0.jv8-_2J8htPoqaNyadh9Vx1z380WDoLHfhysXK36vgQ';                  // ← cambia esto

/* No toques lo que hay debajo ───────────────────────────── */
const SUPABASE_CONFIGURED =
  SUPABASE_URL      !== 'https://your-project.supabase.co' &&
  SUPABASE_ANON_KEY !== 'your-anon-key-here';
