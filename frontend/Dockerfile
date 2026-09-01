FROM node:24-alpine AS build

WORKDIR /app

# Vite variables are compiled into static JS during `npm run build`.
# Changing VITE_API_BASE_URL later requires rebuilding the frontend image.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_TIMEOUT_MS=60000
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS

COPY package*.json ./
RUN npm config set registry "$NPM_CONFIG_REGISTRY" && npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

