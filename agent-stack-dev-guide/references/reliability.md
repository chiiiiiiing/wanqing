# Reliability and troubleshooting

Apply only the rules relevant to the selected OpenAPI operation.

## Prepare a request

Before constructing or retrying a request, verify:

1. The operation explicitly permits the caller’s security scheme.
2. The selected Project header is present when the operation requires it.
3. Required `Idempotency-Key` and `If-Match` headers are present.
4. Content type, content length, digest, and streaming response type match the operation.

Preparation is complete when every required request field comes from the operation or a referenced schema rather than inference.

## Idempotency and concurrency

For a mutation that explicitly accepts `Idempotency-Key`, generate one key per logical action and reuse that same key when retrying the action. A new logical action gets a new key.

Carry an ETag unchanged into `If-Match`. After a precondition failure, fetch the current resource, reconsider the intended change, and use its new ETag. Concurrency handling is complete when the request either commits against the observed version or reports the conflict without overwriting newer state.

## Retry decisions

- Retry a connection failure, `429`, or server error only when the request is read-only or the mutation is protected by its documented idempotency mechanism.
- Honor `Retry-After` when present; otherwise use bounded exponential backoff with jitter.
- Surface validation, authentication, authorization, conflict, and precondition errors immediately with their `error.code`.
- Treat credential writes, Turn creation without a documented replay guarantee, and destructive operations as non-replayable unless the specific operation states otherwise.

Retry handling is complete when the code has a finite attempt bound and cannot duplicate an unsafe action.

## NDJSON and interruption

Consume the Turn response line by line. Empty lines are heartbeats. Parse each non-empty line independently, preserve order, and stop only on a terminal event or a documented transport failure.

A closed connection may interrupt the active Turn. Before submitting another Turn, inspect the Session/Turn state and history. Stream recovery is complete when the client either recovers the terminal outcome or presents an explicit unresolved state without duplicating work.

## Pagination

Use the operation’s documented cursor or page token. Preserve filters and sort choices between pages. Pagination is complete when the terminal page is observed, the requested result is found, or the caller’s explicit result limit is reached.

## Diagnose an API failure

1. Remove secrets, then record status, error envelope, `error.code`, request method/path, response headers, and relevant stream events.
2. Locate the exact operation and error code in `openapi.yaml`.
3. Compare security, Project selection, headers, content type, body schema, ETag, and idempotency requirements.
4. Use the operation-detail endpoint when the response provides an operation identifier and the caller has permission.
5. Give one root cause and the smallest corrective request or code change; label uncertainty when evidence remains incomplete. If the contract omits an error description or code, report the omission and rely only on the observed response.

Diagnosis is complete when the conclusion is supported by the observed response and the documented contract. A successful live retry is additional evidence, not a prerequisite unless the developer asked for execution.
