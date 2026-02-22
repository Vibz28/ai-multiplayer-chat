FROM oven/bun:1.2.23 AS build

WORKDIR /app

COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ .

ARG VITE_BACKEND_HTTP_URL=http://localhost:18000
ARG VITE_BACKEND_WS_URL=ws://localhost:18000
ENV VITE_BACKEND_HTTP_URL=${VITE_BACKEND_HTTP_URL}
ENV VITE_BACKEND_WS_URL=${VITE_BACKEND_WS_URL}

RUN bun run build

FROM nginx:1.29-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
