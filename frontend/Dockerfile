# T_SEC.2 — multi-stage production build.
# Stage 1 compiles TypeScript + Vite. Stage 2 serves the static bundle with
# a tiny nginx. No dev-server, no HMR, no StrictMode double-effect in prod.

FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ─────────────────────────────────────────────────────────────

FROM nginx:1.27-alpine AS server

# SPA-friendly nginx: try_files for client-side routing.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Bundled dist from the builder — no source code, no node_modules in prod.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
