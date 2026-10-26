.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Release procedure — agent-cycle project

###########
Releasing
###########

Releases are decisions for the person maintaining the project. The agents
prepare and verify a release commit; they do not publish it. The ``version``
field in the ``[project]`` table of ``pyproject.toml`` is the single source
of the release version. Sphinx reads its ``version`` and ``release`` values
from that table.

****************************
Prepare the release commit
****************************

1. Add a RED test for the new release identity. It checks the project name
   and version in ``pyproject.toml`` and checks that the Sphinx values match
   them. Commit the test after confirming that exactly its declared nodes
   fail for the intended reason.
2. Add or update the project metadata, make Sphinx read it, update the
   release status and notes, and commit the result with the subject
   ``release: agent-cycle X.Y.Z``. This GREEN release commit must make the
   complete suite pass.
3. Validate each commit as its role requires. The RED has only its declared
   failures; the release commit passes all three commands::

      python3.14 -m pytest
      check_formatting --all
      git diff --check

The release commit message records the delivered work, compatibility limits
and known open notes. In particular, the Codex rollout format consumed by the
tools is undocumented and is not a compatibility promise.

***************************
Check publication content
***************************

Before tagging, run the public-content gate over the complete range that has
not been pushed. Establish the intended remote-tracking base without fetching
during the release turn, then scan through the release commit::

   tools/check-public.sh origin/main..HEAD

The scan must report a clean range. A refusal is not a clean result and stops
the release.

***********************
Create and verify tag
***********************

Tag the reviewed release commit, not an implicit moving ``HEAD``. The tag is
annotated and unsigned. Put its explanatory text in a message file, and use
the person's tagger identity explicitly. Substitute the identity placeholders,
then show the effective identity under the same configuration and confirm it
before tagging::

   git -c user.name='<tagger-name>' \
       -c user.email='<tagger-email>' \
       var GIT_COMMITTER_IDENT
   git -c user.name='<tagger-name>' \
       -c user.email='<tagger-email>' \
       tag --no-sign -a vX.Y.Z -F <message-file> <release-commit>

Verify all three parts of the local release identity before publication::

   test "$(git cat-file -t vX.Y.Z)" = tag
   test "$(git rev-parse 'vX.Y.Z^{commit}')" = \
       "$(git rev-parse <release-commit>)"
   git show vX.Y.Z:pyproject.toml | \
       python3.14 -c 'import sys, tomllib; assert tomllib.loads(sys.stdin.read())["project"]["version"] == "X.Y.Z"'

The first check distinguishes an annotated tag object from a lightweight tag;
the second proves its target; the third proves that the tagged tree carries
the matching version.

*********************
Publish and confirm
*********************

Only the person publishes a release, with one atomic push naming exactly the
branch and release tag::

   git push --atomic origin main vX.Y.Z

Never use ``--tags``. Afterwards, inspect the remote's two named refs::

   git ls-remote origin refs/heads/main refs/tags/vX.Y.Z

Confirm that the remote branch is at the intended main commit and that the
remote tag exists. For an annotated tag, its listed object is the tag object;
the local target verification above establishes the commit it names.
