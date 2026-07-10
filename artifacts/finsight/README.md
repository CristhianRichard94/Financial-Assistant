# FinSight (Next.js frontend)

FinSight's Next.js 15 App Router frontend. Talks to the Python `rag-api`
service (`services/rag-api`) for document upload/listing/deletion and
question answering, and to Supabase directly (via `@supabase/ssr`) for
Google OAuth sign-in and per-user chat history.

## Local setup

1. Copy `.env.example` to `.env.local` and fill in real values.
2. Run `rag-api` locally (see `services/rag-api/README.md`) and point
   `RAG_API_BASE_URL` at it.
3. `pnpm --filter @workspace/finsight run dev`

## Required Supabase dashboard configuration (manual, operator step)

Google OAuth sign-in requires configuration in both the Supabase dashboard
and Google Cloud Console. This cannot be done from code/CI and must be set
up once per environment (local/staging/production each point at their own
Supabase project and have their own callback URL).

1. **Google Cloud Console**: create an OAuth 2.0 Client ID (or reuse an
   existing one), and add this **Authorized redirect URI**:
   ```
   <SUPABASE_PROJECT_URL>/auth/v1/callback
   ```
   e.g. `https://your-project-ref.supabase.co/auth/v1/callback`. Note this
   is Supabase's own callback endpoint, not this app's
   `/auth/callback` route - Supabase sits in between Google and this app.

2. **Supabase Auth Providers**: in the Supabase dashboard, under
   Authentication -> Providers, enable **Google** and paste in the Client ID
   and Client Secret from step 1.

3. **Supabase Auth URL configuration**: under Authentication -> URL
   Configuration:
   - Set **Site URL** to this app's own base URL for that environment (e.g.
     `http://localhost:<PORT>` for local dev).
   - Add this app's `/auth/callback` route to **Additional Redirect URLs**
     for every environment that needs to sign in, e.g.:
     ```
     http://localhost:<PORT>/auth/callback
     https://your-production-domain.example/auth/callback
     ```
     (`<PORT>` is whatever `PORT`/`.replit-artifact/artifact.toml` configures
     for this environment - see `localPort`/`PORT` there for the default.)

Without all three of the above, `signInWithOAuth({ provider: "google" })`
will either fail outright or redirect the user to an unrecognized URL after
consenting on Google's side.

## Database migrations

This app's own schema (`chat_messages`) lives alongside `rag-pipeline`'s
migrations in `services/rag-pipeline/sql/`, since that folder is the repo's
single source of truth for the Supabase schema, even though only this
Next.js app touches that particular table. As of this writing, migrations
through `009_create_chat_messages_table.sql` have **not** been applied to
any live Supabase project - apply them (in order) via the Supabase SQL
editor or CLI before relying on multi-user auth/chat history in a given
environment.

## Auth architecture notes

- Sessions are cookie-based and verified server-side (`src/middleware.ts`,
  `src/lib/supabase/server.ts`) before any protected page renders - there is
  intentionally very little client-side "is the user logged in?" state.
- Every Route Handler under `src/app/api/**` independently verifies the
  session via `src/lib/auth/requireUser.ts`, even though `src/middleware.ts`
  already redirects unauthenticated *page* requests - a Route Handler must
  never rely on a client-side redirect alone.
- `src/lib/ragApiClient.ts` sends the verified user's id as `X-User-Id` on
  every call to `rag-api`, in addition to the existing internal shared
  secret. See `services/rag-api/rag_api/auth.py` for the corresponding
  server-side contract.
