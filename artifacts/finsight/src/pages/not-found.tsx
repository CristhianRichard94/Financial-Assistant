import type { GetServerSideProps } from "next";
import { NextIntlClientProvider } from "next-intl";
import { Card, CardContent } from "@/components/ui/card";
import { AlertCircle } from "lucide-react";
import esMessages from "../../messages/es.json";
import enMessages from "../../messages/en.json";
import { DEFAULT_LOCALE, LOCALE_COOKIE_NAME, type Locale } from "../../i18n/locales";

const MESSAGES_BY_LOCALE: Record<Locale, typeof esMessages> = {
  es: esMessages,
  en: enMessages,
};

interface NotFoundProps {
  locale: Locale;
}

/**
 * This lives under `src/pages/` (Pages Router), outside the App Router tree
 * that `src/app/layout.tsx` wraps in `NextIntlClientProvider` - Next.js uses
 * it as the fallback for routes that don't match any App Router segment, so
 * it needs its own locale resolution and provider rather than relying on
 * `useTranslations` picking up ambient context from the App Router layout.
 */
export default function NotFound({ locale }: NotFoundProps) {
  const t = MESSAGES_BY_LOCALE[locale].notFound;

  return (
    <NextIntlClientProvider locale={locale} messages={MESSAGES_BY_LOCALE[locale]}>
      <div className="min-h-screen w-full flex items-center justify-center bg-gray-50">
        <Card className="w-full max-w-md mx-4">
          <CardContent className="pt-6">
            <div className="flex mb-4 gap-2">
              <AlertCircle className="h-8 w-8 text-red-500" />
              <h1 className="text-2xl font-bold text-gray-900">{t.title}</h1>
            </div>

            <p className="mt-4 text-sm text-gray-600">{t.description}</p>
          </CardContent>
        </Card>
      </div>
    </NextIntlClientProvider>
  );
}

export const getServerSideProps: GetServerSideProps<NotFoundProps> = async ({ req }) => {
  const cookieLocale = req.cookies[LOCALE_COOKIE_NAME];
  const locale: Locale = cookieLocale === "es" || cookieLocale === "en" ? cookieLocale : DEFAULT_LOCALE;

  return { props: { locale } };
};
