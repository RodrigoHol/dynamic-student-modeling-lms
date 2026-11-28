FROM node:22-alpine AS builder

WORKDIR /app
COPY frontend/dashboard/package.json ./
RUN npm install

COPY frontend/dashboard/index.html frontend/dashboard/tsconfig.json frontend/dashboard/vite.config.ts ./
COPY frontend/dashboard/src ./src
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
