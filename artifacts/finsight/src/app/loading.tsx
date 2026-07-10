import { Spinner } from "@/components/ui/spinner";
import { BrandLockup } from "@/components/auth/BrandLockup";

/**
 * Full-screen fallback shown by Next.js while any route segment below the
 * root is still resolving on the server (e.g. `/login` or
 * `(protected)/layout.tsx` awaiting `supabase.auth.getUser()`).
 *
 * This is what prevents a flash of `/login`'s sign-in form or of protected
 * `AppLayout` content before auth status is known: since this app resolves
 * the session server-side before rendering either of those, Next shows this
 * neutral screen for the (typically brief) window while that resolution is
 * in flight, instead of rendering a "wrong" state and then swapping it out.
 */
export default function RootLoading() {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[hsl(var(--background))] px-4 py-12">
      <div className="w-full max-w-sm flex flex-col items-center gap-8">
        <BrandLockup />
        <Spinner className="size-5 text-[hsl(var(--muted-foreground))]" />
      </div>
    </div>
  );
}
