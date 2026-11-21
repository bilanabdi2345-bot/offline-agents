# Adding a new agent

Example: adding `agent_d`.

1. In `docker-compose.yml`, copy the `agent_c` block and rename it `agent_d`.
   Give it its own role, its own notes volume `notes_d`, and its own network `net_d`.
2. Add `net_d: { internal: true }` under `networks`.
3. Add `notes_d:` under `volumes`.
4. Add `net_d` to the coordinator's list of networks.
5. Add `TOKEN_AGENT_D: ${AGENT_D_TOKEN}` to the coordinator's environment.
6. Add `AGENTS: agent_a=http://agent_a:9000,...,agent_d=http://agent_d:9000`
   to the coordinator's environment.
7. Add `AGENT_D_TOKEN=<a long random string>` to your `.env` file.
8. Add `agent_d` to `coordinator/policy.json`.
9. Add `agent_d` to the list in `agents/check_walls.py`.
10. Run `docker compose up -d --build`, then run the wall check.
