# Working together on this project

This guide is for everyone on the team.

## First day

1. Ask the project owner to add you to the GitHub repo.
2. Install Docker Desktop, Python and Git.
3. Clone the repo and run `./scripts/setup.sh`.
4. Run `python -m unittest discover tests`. All tests should pass.

## How we pick work

- All work lives in the **Issues** tab on GitHub.
- Pick an issue, then assign it to yourself so nobody doubles up.
- If you have a new idea or find a bug, open a new issue first.

## How we make changes

1. Get the latest code: `git checkout main` then `git pull`.
2. Make a branch for your work: `git checkout -b short-name-of-task`.
3. Make your change. Keep it small.
4. Run the tests: `python -m unittest discover tests`.
5. Save and send it:
   ```sh
   git add .
   git commit -m "Say what you changed"
   git push -u origin short-name-of-task
   ```
6. On GitHub, open a **Pull Request**. Fill in the short form.
7. One teammate reviews it. When they approve, merge it.

GitHub runs the tests on every Pull Request automatically.

## Rules that keep the walls safe

- Never give an agent a network that is not `internal: true`.
- Never put two agents on the same network.
- Never mount one agent's notes into another agent.
- Never commit the `.env` file. It holds the secret tokens.
- Any change to `policy.json` needs a second person to review it.

## Suggested team roles

- **Coordinator lead**: routing, policy and logging.
- **Agent lead**: agent roles, prompts and notes.
- **Security lead**: wall checks and Docker settings.
- **Docs and testing lead**: README, guides and tests.

People can share or swap roles. The point is that every area has an owner.
