# frontend

Одно SPA для обоих кабинетов, кандидата и работодателя. Vite, React, TypeScript, shadcn/ui на Radix,
Tailwind v4, TanStack Query, React Router, react-hook-form + zod. В контейнере nginx только отдаёт
статику (`nginx.conf`), запросы к API идут через общий gateway.

## Устройство

| Каталог                  | Что в нём                                                                                      |
| ------------------------ | ---------------------------------------------------------------------------------------------- |
| `src/api/generated/`     | клиент API и хуки TanStack Query, сгенерированные orval из OpenAPI бэкенда; руками не правится |
| `src/api/http-client.ts` | мутатор: на не-2xx бросает `ApiError` со статусом и кодом ошибки бэкенда                       |
| `src/features/<фича>/`   | логика и компоненты фич: тест, профиль, подбор, приглашения, вакансии, ФСП ID                  |
| `src/pages/`             | страницы; маршруты в `src/app/router.tsx`                                                      |
| `src/components/ui/`     | компоненты shadcn/ui                                                                           |
| `src/index.css`          | токены темы и палитра ФСП                                                                      |

Права проверяет бэкенд; `RequireRole` во фронте только скрывает чужой кабинет.

## Запуск и проверки

```sh
pnpm install
pnpm dev             # dev-сервер, /api проксируется на gateway (http://localhost:8080)
pnpm typecheck && pnpm lint && pnpm format:check
pnpm api:generate    # обновить клиент после изменения API бэкенда
pnpm build
```
