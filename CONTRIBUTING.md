# Contributing

1. Fork, branch, PR.
2. Keep business logic in `services/`, not in cogs.
3. All commands must use `@is_guild_admin()` or `@is_moderator()`.
4. Never store secrets in the DB.
5. Run `pytest` before opening a PR.
