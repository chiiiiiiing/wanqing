# Advanced workflows

For every branch, inspect the relevant operations in `openapi.yaml` before producing curl or code. Give the capability, when to use it, the minimum success path, and its meaningful side effects.

## Skills

For consuming a Skill, search the catalog, inspect its files/package metadata, then install an exact Version on an Agent. Carry Agent ETags and the operation’s idempotency requirements through install, upgrade, and uninstall. This path is complete when the Agent reports the intended installation and exact Version.

For authoring or publishing, separate package creation, upload, review, publication, and Agent installation. Some steps require a browser Session or Console workflow. Give curl only for operations whose security permits the available API key; use numbered Console steps for Session-only operations. This path is complete when the package reaches the requested published/review state or the developer has an exact Console handoff.

## MCP

Register the remote HTTPS server, add only the documented write-only credential when needed, activate it, and inspect discovery/activation state before attaching it to an Agent. Explain that activation contacts an external server and does not itself grant provider authorization. This path is complete when activation succeeds and the expected tools are present, or the activation error is identified.

## Custom Tools

Confirm the package contract, manifest, entrypoint, network allowlist, credential names, Version, publication state, and Agent mount sequence from the API reference and the product’s Custom Tool documentation. Custom Tool code can execute with external network and write-only secrets, so live upload, publication, or mount requires an explicit request. This path is complete when the intended Version is published and mounted, or the exact packaging/permission failure is identified.

## Managed Tools

Inspect available packages and the required Organization Auth before installation. Preserve the provider’s declared environment or JSON-file credential names; use the returned auth ID rather than inventing global Skill variables. This path is complete when the installation is visible to the intended Agent/Workspace, or the missing admin role/auth state is identified.

## Scheduler

Create a schedule only after the developer confirms its target Agent, Project, cadence, timezone, payload, and future side effect. Use the documented idempotency key and ETag rules for create/update/delete, then inspect fires as immutable execution snapshots. This path is complete when the schedule state and next execution are verified; deletion requires a separate explicit request.

## Audio Turns

Use the audio Turn operation’s multipart contract and supported media types, then consume the same NDJSON terminal flow as a text Turn. Treat the documented “ASR unavailable” response as a deployment capability gap rather than a client retry. This path is complete when the Turn reaches its terminal event or the capability gap is identified.

## Billing

Use a Workspace API Key only when the operation permits it and the key has the required Billing permission. Keep usage reads separate from spend-limit or governance mutations. This path is complete when the requested usage period/detail is returned or the missing permission is identified.

## Lark and Notion

These integrations include Console, OAuth, personal-token, or device authorization steps that cannot be completed as an ordinary User API Key curl flow. Use curl only for reads or readiness checks whose operation explicitly permits the available API key. For connect, authorize, replace, or disconnect operations that require `Agent9Session`, give numbered manual Console steps even when the developer asks for curl; keep Session cookies and provider secrets out of the API workflow. This path is complete when the developer can verify the integration’s ready state or has the exact manual action that remains.

## Full capability questions

When a requested operation falls outside the guided branches, search the full OpenAPI snapshot. Explain whether it is callable with the developer’s current identity, give raw HTTP only when authorized by the operation, and identify browser/admin-only handoffs. This path is complete when the requested operation is accurately located and its authority boundary is explicit.
