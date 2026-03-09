#### design reasoning flow ####
1. What problems are we solving?
- to split cpu usage and gpu usage
- to untangle reward-calculating workers from model trainers
- to manage and monitor state of workers
- to allow worker to use llm


2. What modules do we need?
- trainer module -> skyrl skeleton
- worker router
- workers
- LLM server (init by skyrl)


3. How do modules communicate?
- trainer calls workder-router to init worker with a event-key, and request reward & rollout pair from workder-router with the same key; use http protocal
- worker-router invokes worker with input [vulhub case path + unique id] with a pre-defined bash script? or by threading?; records the network info, container names, and etc.; at this stage, we can consider workers and worker-router are always on the same machine (no budget for load balance)
- within workders, they must inherit a model-steping skeleton, to produce reward
- the worker inherit a GeneratorInterface to use the LLM server init by skyrl


4. What tech should be adapted?
- trainer: skyrl framework until custom generator, generator calls HTTP protocal to request rollout
- worker router: FastAPI HTTP server + Redis for state management
- worker: Python subprocess with Docker SDK (manages docker-compose environments)
- LLM server: init by skyrl, accessed via HTTP endpoint by workers

5. Technical Details (see WORKER_MANAGEMENT_TECH_SPEC.md)
- Worker Router: FastAPI async server with WorkerPool class
  - Spawns/manages worker subprocesses
  - Exposes REST API: POST /api/rollout/execute, GET /api/rollout/status/{task_id}
  - Uses Redis for worker state tracking and task queuing
- Worker Unit: Python subprocess
  - Polls Redis queue for tasks
  - Manages docker-compose up/down for each rollout
  - Queries LLM via HTTP (http://127.0.0.1:8001/v1/chat/completions)
  - Executes exploitation in Docker containers
  - Computes rewards and returns trajectory
- Communication Flow:
  SkyRL Generator → Worker Router (HTTP) → Redis Queue → Worker Unit (polls) → LLM Server (HTTP)




#### design reasoning flow end ####
