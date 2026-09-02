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
# T_OPS.2 — the SSR process for `/rules` and `/rules/*`.
#
# Built `FROM builder` rather than from a bare node image: the SSR bundle
# imports React and the router as externals, so it needs the same
# `node_modules` the build used. Copying a curated subset would be a second
# dependency list to keep in step with the first, and the drift would show up
# as a page that renders in the build and crashes in production.
#
# Nothing is exposed publicly: the frontend's nginx proxies to it over the
# compose network, and it answers two path shapes and a health probe.
FROM builder AS ssr
ENV NODE_ENV=production
CMD ["node", "scripts/ssr-server.mjs"]

# ─────────────────────────────────────────────────────────────

FROM nginx:1.27-alpine AS server

# SPA-friendly nginx: try_files for client-side routing.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Bundled dist from the builder — no source code, no node_modules in prod.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
