#!/usr/bin/env bash
# Prints "true" when a push to main brought the tip of develop into main, else "false".
#
#   develop_merged.sh <develop-sha> <new-main-sha> <main-sha-before-the-push>
#
# True for a fast-forward or merge-commit merge of develop. False for a direct
# commit to main, for any push after the merge, and while develop is not yet in main.
# Run it inside a clone that has the full history.
set -u
develop=$1
head=$2
before=$3

# develop must be part of main after the push ...
if ! git merge-base --is-ancestor "$develop" "$head"; then
    echo false
    exit 0
fi
# ... and must not have been part of it before the push.
zeros=0000000000000000000000000000000000000000
if [ "$before" = "$zeros" ] || ! git cat-file -e "${before}^{commit}" 2>/dev/null; then
    echo true
    exit 0
fi
if git merge-base --is-ancestor "$develop" "$before"; then
    echo false
else
    echo true
fi
