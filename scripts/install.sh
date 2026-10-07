#!/usr/bin/env bash
# Sets shingi up for Claude Code, OpenCode, or both: the permission rules that
# let the agent run shingi's read commands (where, context, list, kinds, version) and jq
# without prompting, while create and adopt, which change things, still ask;
# and, for OpenCode, the skill. Claude Code gets the skill from the shingi
# plugin; see the README.
#
#   scripts/install.sh                         # every agent whose CLI is on PATH
#   scripts/install.sh --claude --opencode     # just these
#   scripts/install.sh --uninstall [--claude] [--opencode]
#
# Claude Code: rules in ${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json.
# OpenCode: rules in ${XDG_CONFIG_HOME:-~/.config}/opencode/opencode.json, and
# the skill as a link, opencode/skills/shingi, to this clone's copy.
#
# The reads are allowed by name, not with one rule for all of shingi, so a
# command added later asks until this script says otherwise.
#
# Safe to rerun. A settings file is backed up (to .bak.<timestamp>, a new one
# each time) before it changes, and only shingi's rules are added or removed;
# uninstalling leaves the jq rule, which koan and sesshin rely on too. An
# opencode.jsonc, or an opencode.json jq can't parse, is never touched: the
# rules are printed to add by hand. Runs under macOS's /bin/bash 3.2. Needs jq.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd -P)
skill_src=$repo/claude/skills/shingi

claude_dir=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
claude_settings=$claude_dir/settings.json
claude_allow='["Bash(shingi where:*)", "Bash(shingi context:*)", "Bash(shingi list:*)", "Bash(shingi kinds:*)", "Bash(shingi version:*)", "Bash(jq:*)"]'
claude_ask='["Bash(shingi create:*)", "Bash(shingi adopt:*)"]'

oc_dir=${XDG_CONFIG_HOME:-$HOME/.config}/opencode
oc_json=$oc_dir/opencode.json
oc_jsonc=$oc_dir/opencode.jsonc
oc_link=$oc_dir/skills/shingi
# The last matching rule wins in OpenCode, so shingi's come after the user's.
oc_rules='{
  "shingi where*": "allow",
  "shingi context*": "allow",
  "shingi list*": "allow",
  "shingi kinds*": "allow",
  "shingi version*": "allow",
  "jq *": "allow",
  "shingi create*": "ask",
  "shingi adopt*": "ask"
}'

usage() {
	echo "usage: $0 [--claude] [--opencode] [--uninstall]" >&2
	exit 2
}

mode=install
want_claude=
want_oc=
for arg in "$@"; do
	case $arg in
	--claude) want_claude=1 ;;
	--opencode) want_oc=1 ;;
	--uninstall) mode=uninstall ;;
	*) usage ;;
	esac
done

command -v jq >/dev/null || { echo "install.sh needs jq on PATH" >&2; exit 1; }
if [[ $mode == install ]] && ! command -v shingi >/dev/null; then
	echo "shingi is not on PATH. Install it from this clone with either of:" >&2
	echo "  uv tool install $repo" >&2
	echo "  pipx install $repo" >&2
	echo "with ~/.local/bin on PATH, then rerun this script." >&2
	exit 1
fi

# Uninstalling keeps "jq": koan and sesshin rely on it too.
claude_allow_rm=$(jq -c '. - ["Bash(jq:*)"]' <<<"$claude_allow")
oc_rules_rm=$(jq -c 'del(.["jq *"])' <<<"$oc_rules")

changed=
failed=

# Which agents: the flags, or else every agent whose CLI is on PATH
# (installing) or that has something to clean up (uninstalling).
if [[ -z $want_claude$want_oc ]]; then
	if [[ $mode == install ]]; then
		if command -v claude >/dev/null; then
			want_claude=1
		else
			echo "claude: skipped, no claude on PATH"
		fi
		if command -v opencode >/dev/null; then
			want_oc=1
		else
			echo "opencode: skipped, no opencode on PATH"
		fi
	else
		if [[ -e $claude_settings ]]; then
			want_claude=1
		else
			echo "claude: skipped, no $claude_settings"
		fi
		if [[ -e $oc_json || -e $oc_jsonc || -L $oc_link ]]; then
			want_oc=1
		else
			echo "opencode: skipped, no config or skill link in $oc_dir"
		fi
	fi
fi
if [[ -z $want_claude$want_oc ]]; then
	echo "Nothing to do."
	exit 0
fi

# is_our_link PATH: PATH is a symlink to this clone's skill.
is_our_link() {
	local target
	[[ -L $1 ]] || return 1
	target=$(cd "$1" 2>/dev/null && pwd -P) || return 1
	[[ $target == "$skill_src" ]]
}

if [[ -n $want_claude && -e $claude_settings ]] && ! jq empty "$claude_settings" 2>/dev/null; then
	echo "claude: $claude_settings isn't valid JSON; fix it and rerun. Nothing was changed." >&2
	exit 1
fi

# write_json LABEL FILE JSON: backs FILE up if it exists, then replaces it.
# Each backup gets its own timestamp, so an install then an uninstall doesn't
# overwrite the original with the installed version.
write_json() {
	local bak n
	mkdir -p "$(dirname "$2")"
	if [[ -e $2 ]]; then
		bak=$2.bak.$(date +%Y%m%d-%H%M%S)
		# Two runs in the same second: don't overwrite the first's.
		if [[ -e $bak ]]; then
			n=2
			while [[ -e $bak.$n ]]; do n=$((n + 1)); done
			bak=$bak.$n
		fi
		cp -p "$2" "$bak"
		echo "$1: backed up to $bak"
	fi
	printf '%s\n' "$3" >"$2.tmp"
	mv "$2.tmp" "$2"
	changed=1
	echo "$1: updated $2"
}

if [[ -n $want_claude ]]; then
	if [[ $mode == install ]]; then
		allow=$claude_allow
		# shellcheck disable=SC2016 # $allow and $ask are jq variables
		filter='
			.permissions.allow = ((.permissions.allow // []) + ($allow - (.permissions.allow // [])))
			| .permissions.ask = ((.permissions.ask // []) + ($ask - (.permissions.ask // [])))'
	else
		allow=$claude_allow_rm
		# shellcheck disable=SC2016
		filter='
			if .permissions then
				.permissions.allow = ((.permissions.allow // []) - $allow)
				| .permissions.ask = ((.permissions.ask // []) - $ask)
				| if .permissions.allow == [] then del(.permissions.allow) else . end
				| if .permissions.ask == [] then del(.permissions.ask) else . end
				| if .permissions == {} then del(.permissions) else . end
			else . end'
	fi
	if [[ -e $claude_settings ]]; then
		cur=$(<"$claude_settings")
	else
		cur='{}'
	fi
	new=$(jq --argjson allow "$allow" --argjson ask "$claude_ask" "$filter" <<<"$cur")
	# Order doesn't matter to Claude Code's rules, so compare sorted.
	if [[ $(jq -S . <<<"$cur") == "$(jq -S . <<<"$new")" ]]; then
		echo "claude: $claude_settings already up to date"
	elif [[ $mode == uninstall && ! -e $claude_settings ]]; then
		:
	else
		write_json claude "$claude_settings" "$new"
	fi
fi

# oc_by_hand: prints the rules to add to, or remove from, a config this script
# won't edit.
oc_by_hand() {
	echo "opencode: $1"
	echo "  so it was left alone."
	if [[ $mode == install ]]; then
		echo "  Add these rules by hand, in this order, at the end of"
		echo "  \"permission\": { \"bash\": { ... } } (in OpenCode the last matching rule"
		echo "  wins, so they must come after any rule matching shingi):"
		jq -r 'to_entries[] | "    \(.key | tojson): \(.value | tojson),"' <<<"$oc_rules"
		echo "  If \"bash\" is a string, such as \"ask\", make it an object with \"*\" set to"
		echo "  that value first."
	else
		echo "  Remove these rules from \"permission\": { \"bash\": { ... } } by hand:"
		jq -r 'keys_unsorted[] | "    \(tojson)"' <<<"$oc_rules_rm"
	fi
}

if [[ -n $want_oc ]]; then
	oc_cur=
	if [[ -e $oc_jsonc ]]; then
		oc_by_hand "$oc_jsonc is JSONC, which jq can't edit without losing comments,"
	elif [[ -e $oc_json ]] && ! jq empty "$oc_json" 2>/dev/null; then
		oc_by_hand "$oc_json isn't plain JSON (comments or trailing commas?),"
	elif [[ -e $oc_json ]]; then
		oc_cur=$(<"$oc_json")
	elif [[ $mode == install ]]; then
		# shellcheck disable=SC2016 # "$schema" is a JSON key
		oc_cur='{"$schema": "https://opencode.ai/config.json"}'
	else
		echo "opencode: no $oc_json, no rules to remove"
	fi

	if [[ -n $oc_cur ]]; then
		if [[ $mode == install ]]; then
			rules=$oc_rules
			# Drop shingi's rules wherever they are, then append them, so they
			# end up last and in order. A string default ("bash": "ask")
			# becomes the "*" rule, so it still covers everything else.
			# shellcheck disable=SC2016 # $rules is a jq variable
			filter='
				.permission = (.permission // {} | if type == "string" then {"*": .} else . end)
				| .permission.bash = (
					.permission.bash // {}
					| if type == "string" then {"*": .} else . end
					| with_entries(select(.key as $k | $rules | has($k) | not))
					| . + $rules)'
		else
			rules=$oc_rules_rm
			# shellcheck disable=SC2016
			filter='
				if (.permission | type) == "object" and (.permission.bash | type) == "object" then
					.permission.bash |= with_entries(select(.key as $k | $rules | has($k) | not))
					| if .permission.bash == {} then del(.permission.bash) else . end
					| if .permission == {} then del(.permission) else . end
				else . end'
		fi
		new=$(jq --argjson rules "$rules" "$filter" <<<"$oc_cur")
		# Order matters here, so don't sort: a reorder is a change.
		if [[ -e $oc_json && $(jq -c . <<<"$oc_cur") == "$(jq -c . <<<"$new")" ]]; then
			echo "opencode: $oc_json already up to date"
		else
			write_json opencode "$oc_json" "$new"
		fi
		if [[ $mode == install ]]; then
			# shellcheck disable=SC2016
			others=$(jq -r --argjson rules "$oc_rules" '
				.permission.bash | keys_unsorted[]
				| select(. as $k | startswith("shingi") and ($rules | has($k) | not))' <<<"$new")
			if [[ -n $others ]]; then
				echo "opencode: warning: these rules of yours match shingi commands, but come"
				echo "  before shingi's, so where both match, shingi's win:"
				printf '    %s\n' "$others"
			fi
		fi
	fi

	if [[ $mode == install ]]; then
		if is_our_link "$oc_link"; then
			echo "opencode: skill link $oc_link already in place"
		elif [[ -e $oc_link || -L $oc_link ]]; then
			echo "opencode: $oc_link exists and isn't a link to $skill_src; left alone." >&2
			echo "  Move it out of the way and rerun to install the skill." >&2
			failed=1
		else
			mkdir -p "$(dirname "$oc_link")"
			ln -s "$skill_src" "$oc_link"
			changed=1
			echo "opencode: linked the skill, $oc_link -> $skill_src"
		fi
	else
		if is_our_link "$oc_link"; then
			rm "$oc_link"
			changed=1
			echo "opencode: removed the skill link $oc_link"
		elif [[ -e $oc_link || -L $oc_link ]]; then
			echo "opencode: $oc_link isn't a link to $skill_src; left in place"
		fi
	fi
fi

if [[ $mode == install ]]; then
	if ! command -v koan >/dev/null; then
		echo
		echo "koan, which shingi runs for every unit's tasks, is not on PATH. Install it with:"
		echo "  GOBIN=~/.local/bin go install github.com/phansen314/koan/cmd/koan@latest"
	fi
	# kinds reads the rules and nothing else, so its failing means they're
	# missing or wrong.
	if ! kinds=$(shingi kinds 2>/dev/null) && [[ $(jq -r '.error.kind // empty' <<<"$kinds" 2>/dev/null) == invalid-rules ]]; then
		echo
		echo "shingi has no usable rules file yet: $(jq -r '.error.message' <<<"$kinds")"
		echo "  See \"The rules file\" in $repo/README.md for an example."
	fi
	if [[ -n $want_claude ]] && command -v claude >/dev/null &&
		! claude plugin list --json 2>/dev/null | jq -e 'any(.[]; .id == "shingi@shingi" and .enabled)' >/dev/null; then
		echo
		echo "The shingi plugin, which gives Claude Code the skill, is not installed. Install it with:"
		echo "  claude plugin marketplace add phansen314/shingi"
		echo "  claude plugin install shingi@shingi"
	fi
fi

[[ -n $changed ]] || echo "Nothing changed."
[[ -z $failed ]]
