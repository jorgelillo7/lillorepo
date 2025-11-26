```
docker build -f docker/Dockerfile.base -t bazel/python-base-all:latest .
docker tag bazel/python-base-all:latest \
  europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest
docker push europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest
```


docker buildx create --name mi_builder --driver docker-container --use
docker buildx ls


docker buildx build --platform linux/amd64,linux/arm64 \
-f docker/Dockerfile.base \
-t europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest \
--push .