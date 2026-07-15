import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AppLayout, type SidebarUser } from "@/components/AppLayout";

/**
 * Shared server-side layout for the protected routes (`/dashboard`, `/chat`,
 * `/documents`) - fetches the verified user once and hands it down to
 * `AppLayout`'s sidebar (desktop + mobile share the same `Sidebar`
 * component, so both get the identity row for free).
 *
 * `src/middleware.ts` already redirects a signed-out request to `/login`
 * before it ever reaches this layout, but that must never be the only
 * check: a Server Component/Route Handler always re-verifies the session
 * itself (defense in depth - see `src/lib/auth/requireUser.ts`).
 */
export default async function ProtectedLayout({ children }: { children: ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const sidebarUser: SidebarUser = {
    email: user.email ?? "",
    displayName: (user.user_metadata?.full_name as string | undefined) ?? null,
    avatarUrl: (user.user_metadata?.avatar_url as string | undefined) ?? null,
  };

  return <AppLayout user={sidebarUser}>{children}</AppLayout>;
}
