"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  MessageSquare,
  TrendingUp,
  Menu,
  X,
  Sun,
  Moon,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { createClient } from "@/lib/supabase/browser";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/chat", label: "Chat", icon: MessageSquare },
];

export interface SidebarUser {
  email: string;
  displayName: string | null;
  avatarUrl: string | null;
}

function getInitials(label: string): string {
  const words = label.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

function IdentityMenu({ user }: { user: SidebarUser }) {
  const router = useRouter();
  const identityLabel = user.displayName || user.email;
  const initials = getInitials(identityLabel);

  async function handleLogout() {
    const supabase = createClient();
    await supabase.auth.signOut();
    toast("Signed out");
    router.push("/login");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`${identityLabel} account menu`}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-[hsl(var(--sidebar-foreground))] hover:bg-white/10 hover:text-white transition-all motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--sidebar-primary))] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar))] mb-3"
        >
          <Avatar className="h-8 w-8 shrink-0">
            <AvatarImage src={user.avatarUrl ?? undefined} alt="" />
            <AvatarFallback className="bg-[hsl(var(--sidebar-muted))] text-[hsl(var(--sidebar-foreground))] text-xs font-medium">
              {initials}
            </AvatarFallback>
          </Avatar>
          <span className="flex-1 min-w-0 text-left truncate">{identityLabel}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-56">
        <DropdownMenuItem onClick={handleLogout}>
          <LogOut className="mr-2" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ThemeToggle({ variant }: { variant: "desktop" | "mobile" }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (variant === "desktop") {
    if (!mounted) {
      return (
        <div
          aria-hidden="true"
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-[hsl(var(--sidebar-foreground))] mb-3"
        >
          <span className="invisible flex items-center gap-3">
            <Moon className="w-4 h-4 shrink-0" />
            Dark mode
          </span>
        </div>
      );
    }

    const isDark = resolvedTheme === "dark";
    return (
      <button
        type="button"
        onClick={() => setTheme(isDark ? "light" : "dark")}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-[hsl(var(--sidebar-foreground))] hover:bg-white/10 hover:text-white transition-all motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--sidebar-primary))] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar))] mb-3"
      >
        {isDark ? (
          <Moon className="w-4 h-4 shrink-0" />
        ) : (
          <Sun className="w-4 h-4 shrink-0" />
        )}
        {isDark ? "Dark mode" : "Light mode"}
      </button>
    );
  }

  // mobile
  if (!mounted) {
    return (
      <div aria-hidden="true" className="ml-auto p-2 rounded-lg">
        <Sun className="w-5 h-5 invisible" />
      </div>
    );
  }

  const isDark = resolvedTheme === "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="ml-auto p-2 rounded-lg hover:bg-[hsl(var(--muted))] transition-colors motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--background))]"
    >
      {isDark ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
    </button>
  );
}

function Sidebar({ onClose, user }: { onClose?: () => void; user: SidebarUser }) {
  const pathname = usePathname();
  return (
    <aside className="flex flex-col h-full w-64 bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))]">
      <div className="flex items-center gap-3 px-6 py-5 border-b border-[hsl(var(--sidebar-border))]">
        <div className="w-8 h-8 rounded-lg bg-[hsl(var(--primary))] flex items-center justify-center">
          <TrendingUp className="w-4 h-4 text-white" />
        </div>
        <span className="font-semibold text-lg tracking-tight text-white">FinSight</span>
        {onClose && (
          <button
            onClick={onClose}
            className="ml-auto p-1 rounded hover:bg-white/10 transition-colors lg:hidden"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname?.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ease-out",
                active
                  ? "bg-[hsl(var(--primary))] text-white shadow-sm"
                  : "text-[hsl(var(--sidebar-foreground))] hover:bg-white/10 hover:text-white"
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 border-t border-[hsl(var(--sidebar-border))]">
        <IdentityMenu user={user} />
        <ThemeToggle variant="desktop" />
        <p className="text-xs text-[hsl(var(--sidebar-foreground))] opacity-60">
          AI-powered finance assistant
        </p>
      </div>
    </aside>
  );
}

export function AppLayout({
  children,
  user,
}: {
  children: React.ReactNode;
  user: SidebarUser;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-[hsl(var(--background))] transition-colors duration-200">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex shrink-0">
        <Sidebar user={user} />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
          />
          <div className="relative z-50 flex h-full">
            <Sidebar onClose={() => setMobileOpen(false)} user={user} />
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 flex-col min-w-0 overflow-hidden">
        {/* Mobile header */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-[hsl(var(--border))] lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="p-2 rounded-lg hover:bg-[hsl(var(--muted))] transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-[hsl(var(--primary))] flex items-center justify-center">
              <TrendingUp className="w-3 h-3 text-white" />
            </div>
            <span className="font-semibold text-sm">FinSight</span>
          </div>
          <ThemeToggle variant="mobile" />
        </header>

        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
