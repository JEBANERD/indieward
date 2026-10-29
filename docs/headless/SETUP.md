# Turn on the headless build loop (Jasper, about 20–40 minutes, once)

Everything here uses free GitHub Actions minutes for public repos and your own Claude subscription. Don't use employer cloud credits without written approval.

1. **Create the repo.** New public repo on GitHub, then from the unzipped `indieward/` folder:
   ```
   git init -b main && git add -A && git commit -m "IndieWard v0.1.0"
   git remote add origin https://github.com/<you>/indieward.git && git push -u origin main
   ```
2. **Let Actions open PRs.** Repo Settings → Actions → General → Workflow permissions: *Read and write*, and tick *Allow GitHub Actions to create and approve pull requests*.
3. **Connect Claude.** On your PC run `claude setup-token`, copy the token, and add it as a repo secret named `CLAUDE_CODE_OAUTH_TOKEN` (Settings → Secrets and variables → Actions). Or run `/install-github-app` inside Claude Code, which installs the Claude GitHub App and sets the secret for you.
4. **(Recommended) Bot token so headless PRs trigger CI.** Create a fine-grained personal access token limited to this repo with *Contents: read/write* and *Pull requests: read/write*, and save it as secret `IW_BOT_TOKEN`. Without it, PRs still open but CI won't start on them until you press "Re-run" or push a commit.
5. **Kick it off.** Actions → *claude-headless* → Run workflow (leave card blank). After that it runs on weekdays around 3 am New York.

**Your loop:** review each PR (the body says what changed, how it was tested, and anything you must do by hand), merge it, and set its row in `docs/headless/QUEUE.md` to `done`. You can also comment `@claude set P1-01 to done` on the PR. Comment `@claude …` on any issue or PR to ask for changes from your phone.

**Usage:** each run uses your Claude plan's usage, typically one card per run. Change the schedule in `.github/workflows/claude-headless.yml` (the `cron` line) if it competes with your other projects.
