# Agent Stack Developer Kit

Everything you need to integrate **Agent Stack** — the platform for running AI agents with sessions, tools, skills, files, and artifacts — through its HTTP **Agent Service API**.

This kit is designed to work two ways:

1. **With an AI coding assistant (recommended).** The kit is packaged as a skill: point your assistant at `SKILL.md` and ask it to integrate Agent Stack into your project. The skill routes your request to the right workflow, treats the bundled OpenAPI contract as the source of truth, and produces runnable raw-HTTP calls — no SDK required.
2. **As reference documentation.** Open `references/api-reference.html` in a browser for a searchable view of every operation, or read `references/openapi.yaml` directly for exact wire-level detail.

## What's inside

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Entry point for AI assistants: request routing, contract discipline, security rules. |
| `references/core-workflows.md` | First call, workspace bootstrap, project integration, files and artifacts. |
| `references/reliability.md` | Idempotency, ETags, retries, NDJSON streaming, pagination, failure diagnosis. |
| `references/advanced-workflows.md` | Skills, MCP, Custom Tools, Managed Tools, Scheduler, audio, Billing, integrations. |
| `references/openapi.yaml` | The complete Agent Service API contract. The single source of truth. |
| `references/api-reference.html` | The same contract rendered for humans. |
| `agents/openai.yaml` | Skill interface metadata. |

## Prerequisites

- **`AGENT_STACK_BASE_URL`** — the service root of your Agent Stack deployment.
- **`AGENT_STACK_USER_API_KEY`** — a User API Key. If you only hold a Workspace API Key, follow the *workspace bootstrap* route in `references/core-workflows.md` to mint a service-user key.
- Optionally **`AGENT_STACK_PROJECT_ID`** — a fixed project; otherwise list projects and pick one at runtime.

Treat every key as one-time secret material: store it in a secret manager, never in code, logs, or chat.

## Your first turn in five steps

1. **List projects** and select a `projectId`.
2. **List or create an agent** and note its `agentId`.
3. **Create a session** in that project, bound to the agent.
4. **Submit a turn** with your input. The response streams as **NDJSON** — one JSON event per line. Skip blank heartbeat lines, keep event order, collect the `assistant_message`, and stop at `turn_finished`.
5. **Fetch session or turn history** to confirm what happened.

The exact methods, paths, headers, schemas, and error codes for each step live in `references/openapi.yaml`; the sequencing rules live in `references/core-workflows.md`.

## Core concepts

- **Project** — the working scope for sessions and files.
- **Agent** — a configured worker: model, capabilities, skills, memory.
- **Session** — a conversation with an agent inside a project.
- **Turn** — one request/response exchange in a session, streamed as NDJSON.
- **Artifact** — a durable output (documents, media, files) with revisions, preview, and download.
- **Skill** — a versioned package that extends what an agent can do, installable per agent.

## Coverage

- **Build**: custom Skills (consume and publish), Custom Tools, MCP servers, Managed Tools.
- **Run**: sessions, text and audio turns, file uploads, artifact retrieval, schedulers.
- **Operate**: retries, idempotency, concurrency control, stream recovery, billing usage reads, failure diagnosis.

Some administrative operations require a browser Console session rather than an API key; the workflows mark these explicitly and provide step-by-step Console handoffs instead.

## Reliability rules worth knowing up front

- Mutations that accept an `Idempotency-Key` are safely retryable with the **same** key; everything else is not.
- Concurrent updates use ETags: carry the latest ETag into `If-Match`, and refetch after a precondition failure.
- Consume turn streams line by line to a terminal event; after a dropped connection, inspect session state before resubmitting.

## Security model in one paragraph

Operation-level `security` in the OpenAPI contract is authoritative: a User API Key covers ordinary product calls, a Workspace API Key only the operations that explicitly allow it, and anything marked session-only is a Console workflow. Third-party credentials are write-only: send them once to the documented endpoint and reference them afterwards. Nothing in this kit ever requires pasting a secret into a conversation.
