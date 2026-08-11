FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./
# Frozen, so the image can never resolve different versions than the committed
# lockfile, which is the whole reason that lockfile is tracked.
RUN pnpm install --frozen-lockfile

COPY . .

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_TIMEOUT_MS=5000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS

RUN pnpm build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
