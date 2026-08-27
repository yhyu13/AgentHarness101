# Goal Loop Template

> Write your goal as a document like this, then hand it to the goal loop runner or a
> maker agent. The more specific and verifiable, the higher the loop quality.

## Goal

<!-- One sentence describing what to do -->

Implement the XX feature with complete unit test coverage.

## Acceptance Criteria

<!-- Machine-verifiable completion conditions. Append `@verify <command>` to make a
     criterion machine-checked; without it, the independent checker decides. -->

- [ ] Unit tests pass fully @verify python -m pytest -q
- [ ] Coverage report shows goal_loop coverage ≥ 80% @verify python -m pytest --cov=goal_loop --cov-report=term-missing
- [ ] The package imports cleanly @verify python -c "import goal_loop"

## Scope

<!-- Be explicit about what NOT to touch -->

### Fair game

- All files under `goal_loop/`
- Test files under `tests/`
- Related type definition files

### Hands off

- `goal_persistence/` (the durable core)
- Database schema migrations
- Dependency versions in `pyproject.toml` (unless explicitly needed)
- CI/CD config files

## Verification Method

<!-- How to verify after each step -->

1. After implementation, run these commands in order:
   1. `python -m pytest -q` — unit tests
   2. `python -m pytest --cov=goal_loop --cov-report=term-missing` — coverage check
2. Fix any failures before moving to the next step.
3. When everything passes, run the full end-to-end demo (`python examples/goal_loop_demo.py`).

## Stop Conditions

- Max turns reached: 20
- No progress for 3 consecutive rounds (same error keeps appearing)
- Blocking issue that cannot be resolved independently (e.g., missing dependency, environment problem)

## How to Work

1. Read the project structure and existing features before writing code.
2. Write out the design approach before touching code.
3. Verify after each sub-task is done.
4. If stuck for more than 2 rounds, switch approach or simplify.
5. Update progress at the end of each round.
