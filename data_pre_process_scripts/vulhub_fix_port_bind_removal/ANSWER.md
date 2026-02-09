# Answer to Question 2

## Question: If a folder has docker-compose.yml and docker-compose-original.yml, which would docker compose up use?

**Answer: `docker-compose.yml`**

### Explanation:

By default, Docker Compose looks for the following files in order:
1. `docker-compose.yml`
2. `docker-compose.yaml` (alternative extension)

If you want to use a different file, you must explicitly specify it with the `-f` flag:
```bash
docker compose -f docker-compose-original.yml up
```

Since we're using the standard `docker compose up` command (without the `-f` flag), it will always use `docker-compose.yml` when present.

### Our Strategy:

This is perfect for our use case:
1. We keep the original file as `docker-compose-original.yml` (backup)
2. We modify `docker-compose.yml` to remove fixed port bindings
3. Docker Compose automatically uses the modified `docker-compose.yml`
4. Users can still reference the original file if needed
