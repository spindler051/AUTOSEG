# AUTOSEG `main` — branch-protection owner handoff

**Status: NOT APPLIED.** No settings were changed on GitHub by the patch author.
The owner of `spindler051/AUTOSEG` must configure these in GitHub's
Settings → Rules → Rulesets (or Settings → Branches → Branch protection rules).

## Required protection for `main`

1. Target `main` (and optionally `develop`/`dev` separately once their intended
   lifecycle is confirmed), enable **Require a pull request before merging**;
   require at least **one approval** (`approvals`), dismiss stale approvals on
   new commits and require review of the most recent push by someone other
   than the author. Do not allow direct pushes to protected branches.
2. Enable **Require status checks to pass** on up-to-date code before merge.
   The workflow currently triggered by PRs against `main` is
   `.github/workflows/estabilidade-main.yml`; its job identifier is `validar`
   and the human display name is `AUTOSEG main - testes atuais`. Select the
   exact **validar** status check reported by an actual successful PR run,
   not a guessed check name. Require the independent security checks in the
   remediation checklist (full Python tests, `surface_divergence.py --check`,
   `audit_comments.py --strict`, patch whitespace validation). Update CI to
   publish those checks before marking them mandatory.
3. Enable **Block force pushes** (force push disabled) and **restrict deletions**.
   Enable **Do not allow bypassing** for privileged roles if supported.
4. Consider **Require signed commits** after verifying every intended maintainer
   and automation signer is configured; existing historical commits are unsigned,
   so activation must be coordinated rather than silently forced.
5. Restrict creation of matching refs where appropriate, and verify that the
   ruleset is **Active**, has no bypass actors and applies to `main`.

## Owner verification (mandatory)

- Open a pull request into `main` from a non-protected test branch. Check that
  it cannot be merged before the required review and green `validar` check.
- Try a direct push and a force push to `main` from a non-bypass actor; both
  must be rejected. Check that deleting the branch is rejected.
- Record the ruleset ID, enforced check names and verification timestamp in
  the repository's operational security evidence. **Do not** copy secrets.

This documentation is the handoff, not proof that the GitHub settings were
changed. It does not alter GitHub remotely.
