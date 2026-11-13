#!/usr/bin/env bash
# Tests develop_merged.sh on small throwaway repositories.
#   .github/scripts/test_develop_merged.sh <directory that does not exist yet>
set -eu
script="$(cd "$(dirname "$0")" && pwd)/develop_merged.sh"
work=$1
[ ! -e "$work" ] || { echo "$work exists; give a new directory"; exit 2; }
mkdir -p "$work" && cd "$work" && git init -q -b main
git config user.email t@example.org && git config user.name test
commit() { echo "$1" > "file_$1" && git add "file_$1" && git commit -q -m "$1"; }
fail=0
check() {   # name, expected, develop, head, before
    got=$(bash "$script" "$3" "$4" "$5")
    if [ "$got" = "$2" ]; then echo "ok    $1 -> $got"; else echo "FAIL  $1: expected $2, got $got"; fail=1; fi
}
commit c0
git checkout -q -b develop && commit c1
dev1=$(git rev-parse HEAD)
git checkout -q main
check "develop not yet merged (push of an unrelated main commit)" false "$dev1" "$(git rev-parse main)" "$(git rev-parse main)"
before=$(git rev-parse main); git merge -q --ff-only develop; head=$(git rev-parse main)
check "fast-forward merge of develop" true "$dev1" "$head" "$before"
before=$(git rev-parse main); commit c2; head=$(git rev-parse main)
check "direct commit to main after the merge" false "$dev1" "$head" "$before"
git checkout -q develop && commit c3 && dev2=$(git rev-parse HEAD)
git checkout -q main; before=$(git rev-parse main); git merge -q --no-ff -m merge develop; head=$(git rev-parse main)
check "merge commit of develop" true "$dev2" "$head" "$before"
git checkout -q develop && commit c4 && dev3=$(git rev-parse HEAD)
git checkout -q main; before=$(git rev-parse main); commit c5; head=$(git rev-parse main)
check "main commit while develop is ahead and unmerged" false "$dev3" "$head" "$before"
check "first push of a branch (before is all zeros), develop contained" true "$dev2" "$(git rev-parse main~1)" 0000000000000000000000000000000000000000
check "before commit unknown to the clone (force push)" true "$dev2" "$(git rev-parse main~1)" 1111111111111111111111111111111111111111
exit $fail
