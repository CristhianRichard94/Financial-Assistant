import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function RootPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Check the session directly here instead of unconditionally redirecting
  // to /dashboard first: that would otherwise bounce a signed-out visitor
  // through /dashboard -> (middleware redirect) -> /login, a needless
  // double redirect.
  redirect(user ? "/dashboard" : "/login");
}
