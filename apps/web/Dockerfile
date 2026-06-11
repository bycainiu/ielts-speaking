FROM node:22-alpine AS deps

WORKDIR /app
RUN corepack enable

COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --filter @ielts-speaking/web --frozen-lockfile=false

FROM node:22-alpine AS builder

WORKDIR /app
RUN corepack enable

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-workspace.yaml ./
COPY apps/web ./apps/web

# These vars are read by next.config.mjs rewrites() at build time.
# They must point to Docker-internal service hostnames so the Next.js
# server-side proxy can reach the backend containers at runtime.
ARG API_INTERNAL_URL=http://api-go:8080
ARG SPEECH_ASSESSMENT_URL=http://speech-assessment:8010
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
ENV SPEECH_ASSESSMENT_URL=${SPEECH_ASSESSMENT_URL}

WORKDIR /app/apps/web
RUN pnpm build

FROM node:22-alpine AS runtime

WORKDIR /app/apps/web
ENV NODE_ENV=production

RUN corepack enable
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/pnpm-workspace.yaml /app/pnpm-workspace.yaml
COPY --from=builder /app/node_modules /app/node_modules
COPY --from=builder /app/apps/web/package.json ./package.json
COPY --from=builder /app/apps/web/node_modules ./node_modules
COPY --from=builder /app/apps/web/.next ./.next
COPY --from=builder /app/apps/web/public ./public

EXPOSE 3000

CMD ["pnpm", "start"]
