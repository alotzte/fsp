FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable pnpm

# Зависимости отдельным слоем: переустанавливаются только при изменении lock-файла.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
# Префикс публикации (/fsp) вшивается в сборку: пути ассетов, basename роутера, адреса API.
ARG BASE_PATH=""
ENV BASE_PATH=$BASE_PATH
RUN pnpm build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
