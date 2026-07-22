.PHONY: help dev build up down test lint clean init-db seed-kb

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev:  ## 启动开发环境
	docker-compose -f infrastructure/docker-compose.yml up -d postgres redis
	@echo "等待数据库就绪..."
	@sleep 3
	cd shared && pip install -e .
	@echo "开发环境就绪，运行: make run-gateway / make run-cs / ..."

build:  ## 构建所有镜像
	docker-compose -f infrastructure/docker-compose.yml build

up:  ## 启动全部服务
	docker-compose -f infrastructure/docker-compose.yml up -d

down:  ## 停止全部服务
	docker-compose -f infrastructure/docker-compose.yml down

test:  ## 运行测试
	pytest tests/ -v --tb=short

lint:  ## 代码检查
	ruff check services/ shared/
	mypy services/ shared/ --ignore-missing-imports

clean:  ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

init-db:  ## 初始化数据库
	python scripts/init_db.py

seed-kb:  ## 初始化知识库数据
	python scripts/seed_knowledge.py

# --- 各 Agent 独立启动 ---
run-gateway:
	uvicorn services.gateway.main:app --reload --port 8000

run-supervisor:
	uvicorn services.supervisor.main:app --reload --port 8001

run-telemarketing:
	uvicorn services.telemarketing.main:app --reload --port 8002

run-live:
	uvicorn services.live.main:app --reload --port 8003

run-cs:
	uvicorn services.customer-service.main:app --reload --port 8004

run-operations:
	uvicorn services.operations.main:app --reload --port 8005

run-content:
	uvicorn services.content.main:app --reload --port 8006

run-office:
	uvicorn services.office.main:app --reload --port 8007
