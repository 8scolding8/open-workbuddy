# Security policy

## Scope

The project is a local proxy. By default it binds only to `127.0.0.1` and
management routes reject non-loopback requests.

## Report a vulnerability

Please do not open a public issue containing credentials, session data, private
gateway URLs, or a working exploit. Contact the repository maintainer through
GitHub's private security reporting channel when it is enabled, or open a
minimal issue asking for a private contact path.

When reporting, include the affected version, operating system, transport,
reproduction steps that do not contain secrets, and the expected versus actual
behavior.

## Local handling rules

- Treat `config.json`, `.workbuddy` data, session stores, and runtime logs as
  sensitive.
- Do not expose an unauthenticated wildcard bind to a LAN or the public
  internet.
- Use the official WorkBuddy/CodeBuddy ACP client instead of reproducing
  private authentication flows.
