## Summary
- 

## Linked Work
- Closes #
- Related PRs:

## Scope
- [ ] Backend
- [ ] LangGraph service
- [ ] Frontend
- [ ] Infrastructure / deployment
- [ ] Documentation

## Architecture and Product Decisions
- Decision(s) reviewed with user:
  - 
- Tradeoffs considered:
  - 

## Validation Checklist
### Core Quality Gates
- [ ] `./.venv/bin/ruff check backend langgraph_service`
- [ ] `./.venv/bin/pytest -q`
- [ ] `cd frontend && bun run lint`
- [ ] `cd frontend && bun run test`
- [ ] `cd frontend && bun run build`
- [ ] `cd frontend && bun run typecheck`
- [ ] `cd frontend && bun run check` (single command proof of `lint -> test -> build -> typecheck`)
- [ ] `scripts/check-repo-hygiene`

### Runtime / Integration Gates
- [ ] `scripts/stack up`
- [ ] `scripts/stack smoke`
- [ ] WebSocket chat flow manually validated (user->user, user->AI, group, direct)
- [ ] Streaming validated (reasoning + output deltas)
- [ ] Checklist API and UI sync validated (`/v1/sessions/{application_id}/checklist`)

### Deployment Gates (when infra changes)
- [ ] `scripts/publish-ecr` dry run or execution notes added
- [ ] ECS/EC2 deploy path documented/validated for changed services
- [ ] `docker compose -f compose.yaml config` succeeds

## Evidence
- Key command outputs / screenshots / notes:
  - 

## Risks and Rollback
- Known risks:
  - 
- Rollback plan:
  - 

## Docs Updated
- [ ] README
- [ ] `docs/DEPLOYMENT_WORKFLOW.md`
- [ ] API/event contract docs
- [ ] Runbooks / phase plan / architecture decisions
