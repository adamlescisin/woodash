FROM node:22-slim AS build
WORKDIR /web
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM node:22-slim
WORKDIR /web
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
