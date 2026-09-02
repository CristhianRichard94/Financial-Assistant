import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { safeRedirect } from "@/lib/safeRedirect";
import { LoginForm, type LoginErrorReason } from "./LoginForm";

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parseErrorReason(value: string | undefined): LoginErrorReason | undefined {
  return value === "cancelled" || value === "failed" ? value : undefined;
}

interface LoginPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const redirectParam = firstValue(params.redirect);
  const errorParam = firstValue(params.error);

  // An already-signed-in user hitting /login directly must never see the
  // sign-in form - send them straight to where they were headed (or
  // /dashboard).
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    redirect(safeRedirect(redirectParam));
  }

  return <LoginForm error={parseErrorReason(errorParam)} redirectTo={redirectParam} />;
}
