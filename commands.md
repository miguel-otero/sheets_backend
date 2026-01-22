## 1) Ayuda y versión

* `docker --version` → versión
* `docker info` → info del daemon (storage, runtimes, etc.)
* `docker <comando> --help` → ayuda, ej. `docker run --help`

## 2) Imágenes

* `docker pull <imagen>:<tag>` → descargar

  * Ej: `docker pull nginx:latest`
* `docker images` → listar imágenes locales
* `docker rmi <imagen|id>` → borrar imagen
* `docker build -t <nombre>:<tag> .` → construir desde Dockerfile

  * Ej: `docker build -t miapp:1.0 .`
* `docker tag <src> <dest>` → etiquetar

  * Ej: `docker tag miapp:1.0 miusuario/miapp:1.0`

## 3) Contenedores (correr / parar / ver)

* `docker run [opciones] <imagen> [cmd]` → crear y ejecutar

  * `-d` (detached/background), `--name`, `-p host:container`, `-e`, `-v`
  * Ej: `docker run -d --name web -p 8080:80 nginx:latest`
* `docker ps` → contenedores corriendo
* `docker ps -a` → todos (incluye detenidos)
* `docker stop <nombre|id>` → detener
* `docker start <nombre|id>` → arrancar uno detenido
* `docker restart <nombre|id>` → reiniciar
* `docker rm <nombre|id>` → eliminar contenedor (detenido)
* `docker rm -f <nombre|id>` → eliminar forzando (lo detiene)

## 4) Entrar al contenedor / ejecutar comandos

* `docker exec -it <contenedor> <cmd>` → ejecutar dentro

  * Ej: `docker exec -it web sh` (o `bash` si existe)
* `docker logs <contenedor>` → ver logs
* `docker logs -f <contenedor>` → seguir logs en vivo
* `docker inspect <contenedor|imagen>` → JSON con detalles
* `docker top <contenedor>` → procesos dentro

## 5) Puertos, variables y volúmenes (lo más común)

* Publicar puertos:

  * `-p 8080:80` → host 8080 → contenedor 80
* Variables de entorno:

  * `-e KEY=VAL` → ej: `-e NODE_ENV=production`
* Montar volumen/carpeta:

  * `-v /ruta/host:/ruta/container`
  * Ej: `docker run -v $(pwd):/app -w /app node:20 node index.js`

## 6) Copiar archivos

* `docker cp <contenedor>:/ruta/origen /ruta/destino`
* `docker cp /ruta/origen <contenedor>:/ruta/destino`

## 7) Redes (básico)

* `docker network ls` → listar redes
* `docker network create <red>` → crear red
* `docker network inspect <red>` → ver detalles
* `docker network rm <red>` → borrar red
* Usar red al correr:

  * `docker run --network <red> ...`

## 8) Volúmenes (básico)

* `docker volume ls`
* `docker volume create <vol>`
* `docker volume inspect <vol>`
* `docker volume rm <vol>`
* Montar volumen nombrado:

  * `docker run -v <vol>:/data ...`

## 9) Limpieza (cuidado)

* `docker system df` → uso de espacio
* `docker system prune` → limpia *cache/containers/redes* no usados
* `docker system prune -a` → también borra imágenes no usadas (más agresivo)
* `docker volume prune` → borra volúmenes no usados

## 10) Docker Compose (muy usado)

* `docker compose up -d` → levantar servicios
* `docker compose down` → bajar y limpiar red por defecto
* `docker compose ps` → ver estado
* `docker compose logs -f` → logs
* `docker compose build` → construir imágenes del compose
