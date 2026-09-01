# Build Stage
# Node 18 reached end-of-life in April 2025 and no longer receives security fixes.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# `npm ci` installs exactly what package-lock.json pins and fails if the lockfile
# and package.json disagree. `npm install` silently resolves new versions, so two
# builds of the same commit could ship different dependency trees.
RUN npm ci
COPY . .
RUN npm run build

# Production Stage
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
