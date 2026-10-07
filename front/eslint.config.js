import js from '@eslint/js';
import globals from 'globals';

export default [
  { ignores: ['node_modules/**', 'playwright-report/**', 'test-results/**'] },
  js.configs.recommended,
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.node },
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always'],
      'prefer-const': 'error',
      'no-var': 'error',
    },
  },
  {
    files: ['public/js/**/*.js'],
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      // XSS guard: user data must go through textContent/createElement.
      'no-restricted-properties': [
        'error',
        { property: 'innerHTML', message: 'Use textContent/createElement.' },
        { property: 'outerHTML', message: 'Use textContent/createElement.' },
      ],
      'no-restricted-syntax': [
        'error',
        {
          selector: "MemberExpression[object.name='localStorage']",
          message: 'Não armazene dados no localStorage.',
        },
      ],
    },
  },
];
