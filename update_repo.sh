#!/bin/bash

source run_or_fail.sh

# delete the commit id of the last update (if it exists)
rm -f .commit_id

# verifies the repo we're observing exists
run_or_fail "Repository folder not found!" pushd $1 1> /dev/null

# clean up if we go out of sync
run_or_fail "Could not reset git" git reset --hard HEAD

# parse the git log to get the latest commit id
COMMIT=$(run_or_fail "Could not call 'git log' on repository" git log -n1)
if [ $? != 0 ]; then
  echo "Could not call 'git log' on repository" # we need at least one commit for this to work
  exit 1
fi
COMMIT_ID=`echo $COMMIT | awk '{ print $2 }'`

# pull the latest changes and get the new latest commit id
run_or_fail "Could not pull from repository" git pull
COMMIT=$(run_or_fail "Could not call 'git log' on repository" git log -n1)
if [ $? != 0 ]; then
  echo "Could not call 'git log' on repository"
  exit 1
fi
NEW_COMMIT_ID=`echo $COMMIT | awk '{ print $2 }'`

# if the id changed, then write it to a file
if [ $NEW_COMMIT_ID != $COMMIT_ID ]; then
  popd 1> /dev/null
  echo $NEW_COMMIT_ID > .commit_id
fi
# we only wrote the commit id of the latest changed updates
# if there were multiple commits then we would skip tests on those
