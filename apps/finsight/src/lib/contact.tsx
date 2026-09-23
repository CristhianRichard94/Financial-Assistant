import type { ReactNode } from "react";

export const CONTACT_EMAIL = "richardcristhian94@gmail.com";

/** Rich-text tag renderer for `<contact>...</contact>` in i18n messages. */
export function renderContactLink(chunks: ReactNode) {
  return (
    <a
      href={`mailto:${CONTACT_EMAIL}`}
      className="underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] rounded-sm"
    >
      {chunks}
    </a>
  );
}
