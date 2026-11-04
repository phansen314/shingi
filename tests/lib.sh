# shellcheck shell=bash
# Shared by the test files: a scratch HOME per test, a real koan, assertions.

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
# shellcheck disable=SC2034 # the test files use these
start=$repo/recipes/start/start.sh
# shellcheck disable=SC2034
claim=$repo/recipes/claim/claim.sh
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
real_path=$PATH
tests=0
failures=0
home_n=0

# fresh: a new HOME with its own koan root, and nothing inherited.
fresh() {
	home_n=$((home_n + 1))
	export HOME=$scratch/home$home_n
	export PATH=$real_path
	unset SESSHIN_JOB
	mkdir -p "$HOME"
	koan init >/dev/null
}

# new_task TITLE [KOAN-TASK-CREATE-OPTIONS...]: prints the ID.
new_task() {
	koan task create "$@" | jq -r .result.id
}

# run SCRIPT ARGS...: sets $out and $rc.
run() {
	out=$("$@" 2>&1)
	rc=$?
}

fail() {
	failures=$((failures + 1))
	printf 'FAIL %s: %s\n--- output:\n%s\n---\n' "$current" "$1" "${out:-}"
}

# test_case NAME: a new test, on a fresh HOME.
test_case() {
	current=$1
	tests=$((tests + 1))
	fresh
}

has() {
	case $out in
	*"$1"*) ;;
	*) fail "expected to find: $1" ;;
	esac
}

lacks() {
	case $out in
	*"$1"*) fail "expected not to find: $1" ;;
	esac
}

exit_is() {
	[ "$rc" -eq "$1" ] || fail "exit $rc, expected $1"
}

# refused: exit 0, and a first line that says don't start.
refused() {
	exit_is 0
	case $out in
	"DON'T START:"*) ;;
	*) fail "expected a first line beginning DON'T START:" ;;
	esac
}

# not_refused: exit 0, and no refusal.
not_refused() {
	exit_is 0
	lacks "DON'T START:"
}

# claim_extra ID: the claim's extra, compact; null when unclaimed.
claim_extra() {
	koan show "$1" | jq -c '.result.task.claim.extra'
}

equals() {
	[ "$1" = "$2" ] || fail "got $1, expected $2"
}

# only_tools NAME...: a PATH holding just these tools, and what the scripts always need.
only_tools() {
	local bin=$scratch/bin$home_n tool
	mkdir -p "$bin"
	for tool in bash cat dirname env "$@"; do
		ln -s "$(PATH=$real_path command -v "$tool")" "$bin/$tool"
	done
	export PATH=$bin
}

finish() {
	printf '%s: %d tests, %d failures\n' "$(basename "$0")" "$tests" "$failures"
	[ "$failures" -eq 0 ]
}
