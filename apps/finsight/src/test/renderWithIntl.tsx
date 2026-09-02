import type { ReactElement } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/en.json";

/** Renders with the app's real English messages loaded via
 * `NextIntlClientProvider`, so components using `useTranslations` work in
 * tests exactly like they do in the browser (with `NEXT_LOCALE=en`), letting
 * existing assertions keep matching the English copy. */
export function renderWithIntl(ui: ReactElement, options?: RenderOptions) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
    options
  );
}

export * from "@testing-library/react";
