# Core workflows

Read the relevant OpenAPI operations and schemas while following these routes. The workflow supplies the sequence; `openapi.yaml` supplies every wire detail.

## First call

1. Confirm `AGENT_STACK_BASE_URL` and a User API Key are available through the environment. If the developer has only a Workspace API Key, use the bootstrap route below. This step is complete when the acting identity is unambiguous and no secret value has entered the conversation.
2. List the User’s available Projects. Use `AGENT_STACK_PROJECT_ID` when it matches an available Project; otherwise let the developer select from the response. This step is complete when one `projectId` is selected for the run.
3. List Agents and select one, or create the minimum Agent the request needs. Follow the operation’s idempotency and ETag requirements. This step is complete when an `agentId` is available or the default-Agent behavior is confirmed from the contract.
4. Create a Session in the selected Project and bind the intended Agent when required. This step is complete when the response provides a Session ID.
5. Create a Turn and consume the response as NDJSON, not one JSON document. Ignore blank heartbeat lines, retain event order, collect the assistant message, and wait for the terminal event. If a clarification item appears, carry its source Turn ID into the next Turn as documented. This step is complete when `assistant_message` and `turn_finished` are observed, or a documented terminal error is identified.
6. Show the smallest follow-up request needed to retrieve the Session or Turn history. The first-call route is complete when the developer has a reproducible request sequence and knows the success signal for each request. Execute it only when the developer explicitly asks and the live inputs are available.

## Workspace bootstrap

Use this route only when the caller needs a machine-managed identity and the selected operations explicitly allow a Workspace API Key.

1. Create or identify the Service User that represents the customer or application. Keep the durable customer-to-Service-User mapping in the application’s data store. This step is complete when the Service User ID is known.
2. Create a User API Key for that Service User. Treat the returned plaintext as one-time secret material. This step is complete when the secret has been handed directly to the developer’s secret manager.
3. Switch to `AGENT_STACK_USER_API_KEY` for Project, Agent, Session, and Turn work. This route is complete when an ordinary User-authenticated request succeeds or its documented error is identified.

## Existing-project integration

1. Inspect the application’s existing configuration and HTTP client. Reuse them rather than adding a new client dependency. This step is complete when the base URL, key, project selection, timeout, and streaming mechanism each have one existing home.
2. Implement the smallest end-to-end vertical slice: select Project and Agent, create or resume a Session, submit a Turn, and parse NDJSON. This step is complete when every documented terminal event and error path has an explicit outcome in code.
3. Run the project’s existing focused checks. A live call is optional and requires explicit authority. This route is complete when the code passes those checks and either an observed service response or a clearly labelled unexecuted curl reproducer is available.

## Files and Artifacts

Choose one upload path from the contract:

- Use the Session file operation for its documented small/simple input case.
- Use User File upload capabilities for general uploads, checksums, multipart transfer, and later selection through `userFileIds`.

Read the upload capability before building the request. Preserve content length, digest, upload IDs, part ETags, and completion state exactly as the contract requires. This step is complete when the uploaded file ID is accepted by the intended Turn.

For Artifacts, prefer search, read, revision inspection, preview, and download. Treat publish or delete as separate authorized mutations. The Artifact route is complete when the requested content is retrieved or the exact missing permission/state is identified.

## Core troubleshooting

Capture the HTTP status, response body, request method/path, relevant response headers, and stream events with secret values removed. Then read [reliability.md](reliability.md). Diagnosis is complete when the evidence maps to a documented error or contract mismatch and the smallest corrective request or code change is identified.
