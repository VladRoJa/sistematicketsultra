#frontend-angular\Dockerfile

# Etapa 1: build de la app Angular
FROM node:18 AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build -- --configuration=production --project=frontend-angular


# Etapa 2: Servir con Nginx
FROM nginx:1.25
COPY --from=build /app/dist/frontend-angular /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
