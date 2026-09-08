# OptiTrade frontend - production build served by a small non-root
# nginx container, reverse-proxied by the host's existing Algorix
# system nginx under /optitrade/ (see /etc/nginx/sites-available/
# algorixstudio). No .env, no secrets, no backend credentials belong in
# this image - it only ever ships static, publicly-servable assets.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Baked into the static bundle at build time, not read at container
# runtime - a static SPA has no server-side process to read env vars
# from. Defaults match the Algorix integrated deployment path; override
# with --build-arg for a different mount point.
ARG VITE_BASE_PATH=/optitrade/
ARG VITE_API_BASE_URL=/optitrade/api
ENV VITE_BASE_PATH=$VITE_BASE_PATH
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=5s \
    CMD wget -q -O- http://127.0.0.1:8080/health || exit 1
