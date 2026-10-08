import {defineConfig, globalIgnores} from 'eslint/config';
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
export default defineConfig([
  js.configs.recommended,...tseslint.configs.recommended,
  {files:['**/*.{ts,tsx}'],...reactHooks.configs.flat.recommended},
  {files:['**/*.tsx'],...jsxA11y.flatConfigs.recommended},
  globalIgnores(['.next/**','playwright-report/**','test-results/**','next-env.d.ts']),
]);
