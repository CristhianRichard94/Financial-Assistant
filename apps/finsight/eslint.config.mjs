import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const moduleExport = [
  { ignores: ["next-env.d.ts", ".next/**"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];
export default moduleExport;
