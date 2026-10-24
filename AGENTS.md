# Repository Guidance

## Graphify
- For codebase or architecture questions, check `graphify-out/graph.json` from the repository root first. If it exists, use the installed `/graphify` skill to query it, then verify behavior-sensitive conclusions against source.
- If no graph exists, answer from the source and documentation. Do not create or rebuild a graph unless the user explicitly requests `/graphify` or graph generation.

## Project Map
- This is an asynchronous Python client for Quotex. Start with `api_quotex/client.py` for public operations and `api_quotex/websocket_client.py` for transport and protocol handling.
- Login and session handling are in `api_quotex/login.py` and `api_quotex/config.py`; domain types and errors are in `api_quotex/models.py`, `api_quotex/constants.py`, and `api_quotex/exceptions.py`.
- Follow [README.md](README.md) for API usage and [setup.md](setup.md) for installation. The documented setup is `pip install .` followed by `python -m playwright install chromium`.
- `test1.py` is a network smoke script that logs in and submits demo orders. Do not run it unless the user asks to exercise that workflow.