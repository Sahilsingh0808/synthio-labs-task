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
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_WS_BASE=${VITE_WS_BASE}

RUN npm run build


FROM nginx:1.27-alpine AS runtime

# ``apache2-utils`` provides ``htpasswd`` which the entrypoint helper uses to
# generate the BASIC_AUTH credentials file at container start.
RUN apk add --no-cache curl apache2-utils \
    && rm /etc/nginx/conf.d/default.conf

# The template is copied into place on every boot by the entrypoint helper so
# BASIC_AUTH changes are picked up on restart.
COPY nginx.conf /etc/nginx/conf.d/default.conf.template
COPY docker-entrypoint.d/40-voiceslide-auth.sh /docker-entrypoint.d/40-voiceslide-auth.sh
RUN chmod +x /docker-entrypoint.d/40-voiceslide-auth.sh \
    && cp /etc/nginx/conf.d/default.conf.template /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
