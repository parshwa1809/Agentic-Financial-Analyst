# Multi-stage Dockerfile for building and serving the React (Vite) client

# Build stage
FROM node:18-alpine AS builder
WORKDIR /app

# Install deps
COPY package.json package-lock.json* ./
# Use npm ci when package-lock.json is present for deterministic installs,
# otherwise fall back to npm install so builds without a lockfile still work.
RUN if [ -f package-lock.json ]; then \
			npm ci --silent; \
		else \
			npm install --silent; \
		fi

# Copy source
COPY . .

# Allow build-time override of API base URL
ARG VITE_API_BASE=http://localhost:8000/api
# Create a .env file Vite will pick up at build time (optional)
RUN printf 'VITE_API_BASE=%s\n' "$VITE_API_BASE" > .env

# Build production assets
RUN npm run build

# Production stage: nginx
FROM nginx:stable-alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Use custom nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy runtime entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
