# Multi-stage build: Node.js build → nginx:alpine serve
# DOCS_BASE_URL=/docs/ ensures all internal Docusaurus links use /docs/ prefix
# so the site works correctly when proxied by the frontend at /docs/

FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first (layer caching)
COPY package*.json ./
RUN npm ci

# Copy source and build with /docs/ base URL
COPY . .
ARG DOCS_BASE_URL=/docs/
ENV DOCS_BASE_URL=$DOCS_BASE_URL
RUN npm run build

# Production image: nginx:alpine (~25MB) serving static files
FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
