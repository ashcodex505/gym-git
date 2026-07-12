# Git Contribution Attribution

This is a core, non-optional design requirement of IronGraph.

## The philosophy

> I performed the workout. Therefore I am the author of the workout
> event. IronGraph is simply the automated mechanism that records,
> visualizes, and commits it.

The same distinction Git itself makes: the **author** is who created the
work; the **committer** is the mechanism that put it in the repository.
A CI bot merging your PR doesn't become the author of your code — and
GitHub Actions recording your workout doesn't become the author of your
training.

## How it works

1. `config/irongraph.yml` is the single source of identity:

   ```yaml
   git_author:
     name: "Ashish Kurse"
     email: "ashishkurse@gmail.com"
   ```

   This email is intentionally public and linked to the owner's GitHub
   account. It is **not** treated as a secret (no other personal data
   gets this treatment).

2. `irongraph/gitcommit.py` runs, in order:
   - `git config user.name "Ashish Kurse"`
   - `git config user.email "ashishkurse@gmail.com"`
   - `git commit --author "Ashish Kurse <ashishkurse@gmail.com>" -m …`
   - `git log -1 --format='Author: %an <%ae>%nCommitter: %cn <%ce>%nSubject: %s'`

3. The output is **verified, never assumed**. If the author line is not
   exactly `Author: Ashish Kurse <ashishkurse@gmail.com>`, the commit is
   rolled back (`git reset --soft HEAD~1`) and the workflow fails loudly.
   A mis-attributed workout commit cannot be pushed. This failure path
   has a dedicated test (`test_commit_author_mismatch_fails`).

4. Never used: `github-actions[bot]`, `*@users.noreply.github.com`
   placeholders, or any generated identity.

## What GitHub requires for a green square

Per GitHub's documented criteria, commits count as contributions when:

- the commit email is associated with the owner's GitHub account ✅ (configured above)
- the commit lands on the **default branch** ✅ (workflow pushes to it)
- the repository is standalone (not a fork) ✅

IronGraph intentionally satisfies every criterion it controls. The final
rendering of the contribution graph is GitHub's decision under GitHub's
current rules — IronGraph makes each workout commit *eligible*, and does
not claim a guaranteed square.

## Honesty of the story

The commit body says exactly what happened:

```
Recorded automatically by IronGraph (github.com actions).
Author: Ashish Kurse <ashishkurse@gmail.com>
Workout-Id: issue-42
```

Automation is disclosed; authorship is human. No implication that the
git command was typed by hand — and no bot claiming credit for 185×6.
