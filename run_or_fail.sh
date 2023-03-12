# helper method for providing error messages for a command
run_or_fail() {
  local explanation=$1
  shift 1
  # run the command
  "$@"
  # if the command failed, exit with an error message
  if [ $? != 0 ]; then
    # echo the error message to stderr
    echo $explanation 1>&2
    exit 1
  fi
}