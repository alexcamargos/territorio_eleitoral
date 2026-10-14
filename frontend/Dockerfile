# syntax=docker/dockerfile:1
FROM node:22-alpine AS base

WORKDIR /app

COPY package.json package-lock.json ./

# -------------------------------------------------------------
# Target: dev (usado em desenvolvimento com docker compose up)
# -------------------------------------------------------------
FROM base AS dev

RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# -------------------------------------------------------------
# Target: build (compilação do bundle estático para produção)
# -------------------------------------------------------------
FROM base AS build

RUN npm ci

COPY . .

RUN npm run build

# -------------------------------------------------------------
# Target: prod (servidor Nginx ultra-leve servindo os estáticos)
# -------------------------------------------------------------
FROM nginx:alpine AS prod

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
