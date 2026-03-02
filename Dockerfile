# ./Dockerfile
FROM docker/compose:2.20.2

WORKDIR /app
COPY . .

CMD ["docker-compose", "up"]