// Supabase browser client.
//
// This uses the anon / publishable key, which is meant to be public: it ships in
// the JS bundle and is constrained by Row Level Security. The service-role key
// bypasses RLS and must never appear in this directory.
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY

// createClient() already throws "supabaseUrl is required" on its own, but this
// module is evaluated before React mounts, so that surfaces as a blank page with
// a message naming neither the variable nor the fact that it is a *build-time*
// value. Someone reading it reasonably goes looking for a runtime config problem.
//
// Only names are reported here, never values: this message reaches the browser
// console, where anything printed is readable by whoever is looking at the page.
const missing = [
  ['VITE_SUPABASE_URL', supabaseUrl],
  ['VITE_SUPABASE_ANON_KEY', supabaseKey],
]
  .filter(([, value]) => !String(value ?? '').trim())
  .map(([name]) => name)

if (missing.length > 0) {
  throw new Error(
    `Supabase client cannot start: missing ${missing.join(' and ')}. ` +
    'These are VITE_ variables, so they are inlined into the bundle at build ' +
    'time — setting them after a deploy has no effect until the project is ' +
    'rebuilt. In Vercel they must be ticked for the environment being built ' +
    '(Production and Preview are configured separately), then redeployed. ' +
    'No values are read or logged by this check.'
  )
}

export const supabase = createClient(supabaseUrl, supabaseKey)
