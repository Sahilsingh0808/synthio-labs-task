FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Empty defaults mean "use same-origin via nginx proxy". Override at build
# time with --build-arg VITE_API_BASE=https://my.api.example.com if you are
# deploying the frontend and backend on different domains.
ARG VITE_API_BASE=""
ARG VITE_WS_BASE=""
# Frontend-only soft auth gate. When VITE_AUTH_USERNAME + VITE_AUTH_PASSWORD
# are non-empty at build time, the SPA shows a login page and only loads the
# app after the credentials match. Empty = open access.
ARG VITE_AUTH_USERNAME=""
ARG VITE_AUTH_PASSWORD=""
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_WS_BASE=${VITE_WS_BASE}
ENV VITE_AUTH_USERNAME=${VITE_AUTH_USERNAME}
ENV VITE_AUTH_PASSWORD=${VITE_AUTH_PASSWORD}

RUN npm run build


FROM nginx:1.27-alpine AS runtime

RUN apk add --no-cache curl \
    && rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
