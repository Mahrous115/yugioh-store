import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Variables the app cannot boot without. supabase-js calls createClient() during
// module evaluation — before React renders — so a missing one is a blank page and
// an uncaught "supabaseUrl is required", not anything the UI can catch and show.
// Failing the build instead turns that into a red deploy with a named cause.
const REQUIRED = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY']

// Not required: services/api.js falls back to http://localhost:8000. That default
// is right locally and silently wrong in any deployed build, where it points the
// browser at the visitor's own machine — so it warns rather than failing.
const RECOMMENDED = ['VITE_API_URL']

// Anchored to this file rather than process.cwd(), so the check still reads the
// right directory if the build is ever invoked from the repo root.
const ENV_DIR = fileURLToPath(new URL('.', import.meta.url))

/**
 * Fail the build when a required VITE_ variable is missing.
 *
 * Deliberately a Vite plugin rather than a prebuild npm script: loadEnv() resolves
 * exactly what the build itself will inline — .env files locally, real environment
 * variables on a CI or Vercel builder — using the same mode and prefix rules. A
 * separate prebuild process sees only process.env, so it would pass on a Vercel
 * builder and false-alarm locally, where the values live in frontend/.env.
 *
 * `apply: 'build'` keeps `npm run dev` unaffected.
 */
function requireViteEnv() {
  return {
    name: 'require-vite-env',
    apply: 'build',
    config(_userConfig, { mode }) {
      const env = loadEnv(mode, ENV_DIR, 'VITE_')
      const isBlank = name => !String(env[name] ?? '').trim()

      const missing = REQUIRED.filter(isBlank)
      if (missing.length > 0) {
        // Names only. Build logs are frequently pasted into issues and chat.
        throw new Error(
          'Missing required build-time environment variable(s):\n' +
          missing.map(name => `    - ${name}`).join('\n') + '\n\n' +
          '  VITE_ variables are inlined into the bundle at BUILD time, so setting\n' +
          '  them after a deploy changes nothing until the project is rebuilt.\n\n' +
          '  Local builds:  add them to frontend/.env (see frontend/.env.example)\n' +
          '  Vercel:        Settings -> Environment Variables. Production and Preview\n' +
          '                 are separate tick-boxes; set both, then redeploy.\n\n' +
          '  Only variable names are shown above; no values are read or printed.'
        )
      }

      for (const name of RECOMMENDED.filter(isBlank)) {
        console.warn(
          `[require-vite-env] ${name} is not set. The app will fall back to ` +
          'http://localhost:8000, which is not reachable from a deployed frontend.'
        )
      }
    },
  }
}

export default defineConfig({
  plugins: [requireViteEnv(), react()],
  server: {
    port: 5173,
  },
})
