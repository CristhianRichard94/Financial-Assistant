"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import { BrandLockup } from "@/components/auth/BrandLockup";
import { createClient } from "@/lib/supabase/browser";
import { safeRedirect } from "@/lib/safeRedirect";

export type LoginErrorReason = "cancelled" | "failed";

const ERROR_COPY: Record<LoginErrorReason, { title: string; description: string }> = {
  cancelled: {
    title: "Sign-in was cancelled",
    description: "You can try again whenever you're ready.",
  },
  failed: {
    title: "Something went wrong",
    description: "We couldn't sign you in. Please try again.",
  },
};

interface LoginFormProps {
  error?: LoginErrorReason;
  redirectTo?: string;
}

export function LoginForm({ error: initialError, redirectTo }: LoginFormProps) {
  const [isRedirecting, setIsRedirecting] = useState(false);
  // Starts from the `?error=` query param (set by the OAuth callback route),
  // but can also be set locally if `signInWithOAuth` itself fails before the
  // browser ever navigates away (misconfigured provider, network failure,
  // etc.) - see the catch block below.
  const [error, setError] = useState<LoginErrorReason | undefined>(initialError);
  const errorCopy = error ? ERROR_COPY[error] : null;

  async function handleSignIn() {
    setIsRedirecting(true);
    setError(undefined);

    try {
      const callbackUrl = new URL("/auth/callback", window.location.origin);
      // Only ever forward an already-validated, same-origin path onward to
      // the OAuth callback - never an attacker-controlled value straight
      // from the query string.
      const safeTarget = safeRedirect(redirectTo, "");
      if (safeTarget) {
        callbackUrl.searchParams.set("redirect", safeTarget);
      }

      const supabase = createClient();
      // Full-page redirect (not a popup) - this is `signInWithOAuth`'s
      // default browser behavior.
      const { error: signInError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: callbackUrl.toString() },
      });

      if (signInError) {
        throw signInError;
      }
      // On success the browser is about to navigate away entirely, so there
      // is no further state to update here.
    } catch (err) {
      console.error("Failed to start Google sign-in:", err);
      // Without this, a failure here (e.g. a misconfigured provider or a
      // network error) before the browser navigates away would otherwise
      // leave the button disabled and spinning forever, with no way to
      // retry short of a full page reload.
      setIsRedirecting(false);
      setError("failed");
    }
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[hsl(var(--background))] px-4 py-12">
      <h1 className="sr-only">Sign in to FinSight</h1>
      <div className="w-full max-w-sm flex flex-col items-center gap-8">
        <BrandLockup />

        {errorCopy && (
          <Alert variant="destructive">
            <AlertTitle>{errorCopy.title}</AlertTitle>
            <AlertDescription>{errorCopy.description}</AlertDescription>
          </Alert>
        )}

        <Button
          size="lg"
          className="w-full gap-2"
          autoFocus
          onClick={handleSignIn}
          disabled={isRedirecting}
          aria-busy={isRedirecting}
        >
          {isRedirecting ? (
            <>
              <Spinner className="size-4" />
              Redirecting…
            </>
          ) : (
            <>
              <img src="/google-logo.svg" alt="" width={18} height={18} />
              Sign in with Google
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
