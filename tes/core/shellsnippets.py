"""Shell code that goes into ~/.bashrc, kept as raw strings so nothing is double-escaped.

Placeholders: @CFG@ (config dir expression), @AC@ (accent colour index), @BIN@ (path of the `tes` launcher).
Files these snippets read (greetings.txt, roasts.txt) hold `FACE<TAB>TEXT` lines. They are only printed, never evaluated.
"""

PACK_SH = r"""  if [[ -r "@CFG@/greetings.txt" ]]; then
    mapfile -t _tes_g < "@CFG@/greetings.txt"
    if (( ${#_tes_g[@]} )); then
      _tes_l=${_tes_g[RANDOM % ${#_tes_g[@]}]}
      if [[ -n ${_tes_l%%$'\t'*} ]]; then
        printf '%s%s%s  %s%s%s\n' "$_tes_c" "${_tes_l%%$'\t'*}" "$_tes_r" "$_tes_d" "${_tes_l#*$'\t'}" "$_tes_r"
      else
        printf '%s%s%s\n' "$_tes_d" "${_tes_l#*$'\t'}" "$_tes_r"
      fi
    fi
  fi"""

# Roasts hook Bash's command-not-found handler. Ubuntu's own handler ("did you mean...?") is wrapped, not replaced.
ROAST_SH = r"""  if [[ -z ${_TES_CNF:-} ]]; then
    _TES_CNF=1
    if declare -F command_not_found_handle >/dev/null 2>&1; then
      eval "_tes_orig_cnf$(declare -f command_not_found_handle | sed '1s/^command_not_found_handle//')"
    fi
  fi
  command_not_found_handle() {
    local f="@CFG@/roasts.txt" c="${1//[[:cntrl:]]/}" l face text
    local -a r
    if [[ -r $f ]]; then
      mapfile -t r < "$f"
      if (( ${#r[@]} )); then
        l=${r[RANDOM % ${#r[@]}]}
        face=${l%%$'\t'*}; text=${l#*$'\t'}
        text=${text//'{cmd}'/"$c"}
        if [[ -n $face ]]; then printf '%s%s%s  %s\n' $'\e[1;38;5;@AC@m' "$face" $'\e[0m' "$text" >&2
        else printf '%s\n' "$text" >&2; fi
      fi
    fi
    if declare -F _tes_orig_cnf >/dev/null 2>&1; then _tes_orig_cnf "$@"; return $?; fi
    printf 'bash: %s: command not found\n' "$c" >&2
    return 127
  }"""

SHORTCUTS_SH = r"""  _TES_BIN="@BIN@"
  if [[ -x $_TES_BIN ]]; then
    type tes >/dev/null 2>&1 || tes() { "$_TES_BIN" "$@"; }
    type ask >/dev/null 2>&1 || ask() { "$_TES_BIN" ask "$@"; }
    type reply >/dev/null 2>&1 || reply() { "$_TES_BIN" reply "$@"; }
    type howto >/dev/null 2>&1 || howto() { "$_TES_BIN" cmd "$@"; }
    type fix >/dev/null 2>&1 || fix() { local ec=$?; "$_TES_BIN" fix "$ec" "$(fc -ln -2 -2 2>/dev/null)"; }
  fi"""
