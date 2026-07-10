/**
 * Shared env var accessors for the Supabase client helpers
 * (`src/lib/supabase/browser.ts`, `server.ts`, `middleware.ts`).
 *
 * Both of these are intentionally `NEXT_PUBLIC_*` - the Supabase anon key is
 * safe to ship to the browser by design (it only ever grants access subject
 * to Postgres Row Level Security policies - see
 * services/rag-pipeline/sql/007_add_user_scoping.sql and
 * 009_create_chat_messages_table.sql). No Supabase service-role key is used
 * anywhere in this Next.js app.
 */

export function getSupabaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!url) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL is not set. Copy artifacts/finsight/.env.example to " +
        ".env.local and set it to your Supabase project's URL."
    );
  }
  return url;
}

export function getSupabaseAnonKey(): string {
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!key) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_ANON_KEY is not set. Copy artifacts/finsight/.env.example to " +
        ".env.local and set it to your Supabase project's anon/public key."
    );
  }
  return key;
}
