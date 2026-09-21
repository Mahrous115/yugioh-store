import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Variables the app cannot boot without. supabase-js calls createClient() during
// module evaluation — before React renders — so a missing one is a blank page and
// an uncaught "supabaseUrl is required", not anything the UI can catch and show.
// Failing the build instead turns that into a red deploy with a named cause.
const REQUIRED = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY']

// Vercel sets VERCEL=1 on its builders. It is the difference between "this build
// will be served to other people" and "this build is for the machine it was made
// on", which is exactly the line VITE_API_URL's correctness depends on.
const ON_VERCEL = Boolean(process.env.VERCEL)

// Hostnames that resolve to whoever is *loading* the page, not to a server. The
// check is on a parsed hostname rather than a substring, so it cannot be fooled by
// a legitimate host that merely contains one of these words — api.localhost-cdn.net
// is a real remote host, and https://localhost.example.com is someone's subdomain.
const LOOPBACK_HOSTNAMES = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]'])

// Anchored to this file rather than process.cwd(), so the check still reads the
// right directory if the build is ever invoked from the repo root.
const ENV_DIR = fileURLToPath(new URL('.', import.meta.url))

/**
 * Why VITE_API_URL is fatal on a Vercel builder and only a warning locally.
 *
 * Returns a reason string, or null when the value is fit to ship. The reason never
 * includes the value: build logs get pasted into issues and chat.
 */
function apiUrlProblem(raw) {
  const value = String(raw ?? '').trim()
  if (!value) return 'is not set'

  let parsed
  try {
    parsed = new URL(value)
  } catch {
    return 'is not a parseable absolute URL (it needs a scheme, e.g. https://…)'
  }

  if (LOOPBACK_HOSTNAMES.has(parsed.hostname.toLowerCase())) {
    return 'points at a loopback host, which is each visitor\'s own machine rather than your API'
  }

  if (parsed.protocol !== 'https:') {
    return 'is not https, so a page served over https will block the request as mixed content'
  }

  return null
}

/**
 * Fail the build when a required VITE_ variable is missing or unusable.
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

      const problem = apiUrlProblem(env.VITE_API_URL)

      // On a builder this is fatal. A warning is not enough: Vercel reports a build
      // with warnings as a green "Ready" deploy, and nobody reads the log of a
      // build that succeeded — so the failure surfaces in the visitor's browser
      // instead, which is the same shape as the blank-page bug this guard exists
      // to prevent.
      if (ON_VERCEL && problem) {
        throw new Error(
          `VITE_API_URL ${problem}.\n\n` +
          '  This build is running on a Vercel builder (VERCEL is set), so the\n' +
          '  bundle will be served to other people. services/api.js falls back to\n' +
          '  http://localhost:8000 when the variable is absent, which would point\n' +
          '  every visitor\'s browser at their own machine.\n\n' +
          '  Set VITE_API_URL to the https URL of the deployed backend in\n' +
          '  Settings -> Environment Variables. Production and Preview are separate\n' +
          '  tick-boxes; set both, then redeploy.\n\n' +
          '  Only the variable name and the reason are shown; the value is not printed.'
        )
      }

      // Locally the localhost fallback is correct, so absence is worth a note and
      // nothing more.
      if (!ON_VERCEL && problem === 'is not set') {
        console.warn(
          '[require-vite-env] VITE_API_URL is not set. The app will fall back to ' +
          'http://localhost:8000, which is correct for local use but not for any ' +
          'deployed build.'
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
