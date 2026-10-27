FROM node:22-alpine AS build
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/ui/package.json packages/ui/package.json
RUN pnpm install --frozen-lockfile --filter @argus/ui...
COPY packages/ui packages/ui
ARG VITE_ARGUS_API_URL=http://localhost:8000
ARG VITE_ARGUS_API_TOKEN=
ENV VITE_ARGUS_API_URL=$VITE_ARGUS_API_URL
ENV VITE_ARGUS_API_TOKEN=$VITE_ARGUS_API_TOKEN
RUN pnpm --filter @argus/ui build

FROM nginx:alpine
COPY packages/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/packages/ui/dist /usr/share/nginx/html
EXPOSE 80
