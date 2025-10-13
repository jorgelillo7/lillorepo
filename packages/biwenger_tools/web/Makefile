.PHONY: dev test build push deploy clean help

# =================================================================
# DESARROLLO LOCAL
# =================================================================

dev:
	@echo "🚀 Iniciando servidor de desarrollo..."
	bazel run //web:web_dev_server

test:
	@echo "🧪 Ejecutando tests..."
	bazel test //web:web_tests

# =================================================================
# BUILD & DEPLOYMENT
# =================================================================

build:
	@echo "🏗️  Construyendo imagen (con deps pre-instaladas)..."
	bazel build //web:web_image_gcp
	@echo "✅ Imagen construida: bazel-bin/web/web_image_gcp"

push:
	@echo "📤 Subiendo imagen a GCP Artifact Registry..."
	bazel run //web:push_to_gcp

deploy: push
	@echo "☁️  Desplegando en Cloud Run..."
	gcloud run deploy biwenger-web \
		--image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/web:latest \
		--platform managed \
		--region europe-southwest1 \
		--allow-unauthenticated \
		--min-instances 0 \
		--max-instances 10 \
		--memory 512Mi \
		--cpu 1 \
		--timeout 300 \
		--set-secrets=SECRET_KEY=SECRET_KEY:latest,ADMIN_PASSWORD=ADMIN_PASSWORD:latest
	@echo "✅ Deployment completado!"

# =================================================================
# TESTING LOCAL CON DOCKER
# =================================================================

docker-load:
	@echo "🐳 Cargando imagen en Docker local..."
	bazel run //web:load_to_docker

docker-run: docker-load
	@echo "🚀 Ejecutando contenedor..."
	docker run --rm -p 8080:8080 \
		-e SECRET_KEY=test-key \
		-e ADMIN_PASSWORD=test \
		biwenger/web:latest

# =================================================================
# UTILS
# =================================================================

clean:
	@echo "🧹 Limpiando builds..."
	bazel clean

clean-all:
	@echo "🧹 Limpieza profunda (incluye cache)..."
	bazel clean --expunge

# =================================================================
# AYUDA
# =================================================================

help:
	@echo "📦 Comandos Bazel disponibles:"
	@echo ""
	@echo "Desarrollo:"
	@echo "  make dev          - Servidor de desarrollo local (Flask)"
	@echo "  make test         - Ejecutar tests unitarios"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  make build        - Construir imagen OCI (con deps instaladas)"
	@echo "  make push         - Subir imagen a GCP Artifact Registry"
	@echo "  make deploy       - Push + Deploy en Cloud Run"
	@echo ""
	@echo "Testing local:"
	@echo "  make docker-load  - Cargar imagen en Docker local"
	@echo "  make docker-run   - Ejecutar contenedor localmente"
	@echo ""
	@echo "Limpieza:"
	@echo "  make clean        - Limpiar builds de Bazel"
	@echo "  make clean-all    - Limpieza profunda (cache incluido)"
	@echo ""
	@echo "🔥 Deploy rápido: make deploy"