"""FastAPI application for Worker Router."""

from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

from .config import Config
from .redis_client import RedisClient
from .worker_pool import WorkerPool
from .utils.logger import setup_logger
from .routes import rollout, workers


# Global instances
config: Config = None
redis_client: RedisClient = None
worker_pool: WorkerPool = None
logger: logging.Logger = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    global config, redis_client, worker_pool, logger
    
    # Load config
    config = Config("config.yaml")
    
    # Setup logger
    logger = setup_logger(
        log_dir=config.get("logging.log_dir", "logs"),
        log_file=config.get("logging.log_file", "worker_router.log"),
        level=config.get("logging.level", "INFO"),
    )
    
    logger.info("Starting Worker Router...")
    
    # Initialize Redis client
    redis_config = config.redis
    redis_client = RedisClient(
        host=redis_config.get("host", "localhost"),
        port=redis_config.get("port", 6379),
        db=redis_config.get("db", 0),
        password=redis_config.get("password"),
    )
    
    # Test Redis connection
    redis_client.ping()
    logger.info("Redis connection established")
    
    # Initialize worker pool
    worker_pool = WorkerPool(
        redis_client=redis_client,
        max_workers=config.get("worker_router.max_workers", 10),
    )
    logger.info(f"Worker pool initialized (max_workers={config.get('worker_router.max_workers', 10)})")
    
    # Inject dependencies into routes
    rollout.set_dependencies(redis_client, worker_pool, logger)
    workers.set_dependencies(redis_client, worker_pool, logger)
    
    logger.info("Worker Router started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Worker Router...")
    worker_pool.shutdown_all()
    logger.info("All workers shutdown")


# Create FastAPI app
app = FastAPI(
    title="VulRL Worker Router",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(rollout.router)
app.include_router(workers.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "VulRL Worker Router",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "redis": redis_client.ping() if redis_client else False,
    }
