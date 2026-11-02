# Etapa 1: compilar con Node. Etapa 2: servir solo los estáticos con nginx (la imagen final no lleva Node).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# "/api" relativo: el navegador habla con nginx (mismo origen) y nginx reenvía al backend. Así no hace falta CORS
# ni conocer la dirección del backend al compilar. El valor se hornea en el JS (Vite lo resuelve en build).
ENV VITE_API_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
