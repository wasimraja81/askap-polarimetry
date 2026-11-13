#!/bin/bash
# Fail if a tracked (or staged) file holds something that must not be published:
# absolute home paths, e-mail addresses other than example.org, key or token
# patterns.
# Usage: bash .github/scripts/check_private_info.sh   (run from the repository root)
cd "$(git rev-parse --show-toplevel)" || exit 2
status=0
check() {
    label=$1; pattern=$2
    hits=$(git grep --untracked -nIiE -e "$pattern" -- . ':!.github/scripts/check_private_info.sh' | grep -v 'example\.org' | cut -c1-120)
    if [ -n "$hits" ]; then
        echo "FOUND ($label):"; echo "$hits"; status=1
    fi
}
check "absolute home path" '(/Users/|/home/)[A-Za-z0-9._-]+'
check "e-mail address" '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
check "password or token" '(password|passwd|secret|api[_-]?key|access[_-]?token|authorization:|bearer )[[:space:]]*[=:]'
check "private key" '-----BEGIN [A-Z ]*PRIVATE KEY'
if [ $status -eq 0 ]; then echo "No private information found."; fi
exit $status
