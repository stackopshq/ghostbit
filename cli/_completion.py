"""Shell completion templates (bash, zsh, fish).

Kept in its own module so the main cli.py stays focused on the command
logic — this file is 90% string literals. `LANGUAGES` is injected at
render time via a placeholder so adding a language to the list in
_languages requires no change here.
"""

from __future__ import annotations

_COMPLETION_BASH = r"""
# Ghostbit bash completion
# Usage: eval "$(gbit completion bash)"  or add to ~/.bashrc

_gb_completion() {
    local cur prev words cword
    _init_completion 2>/dev/null || {
        COMPREPLY=()
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    }

    local langs="LANGS_PLACEHOLDER"
    local main_opts="--lang --expires --burn --max-views --password --server --quiet --json -l -e -b -m -p -s -q"

    # Option argument completions
    case "$prev" in
        --lang|-l)    COMPREPLY=($(compgen -W "$langs" -- "$cur")); return ;;
        --server|-s)  COMPREPLY=($(compgen -W "http:// https://" -- "$cur")); return ;;
        --expires|-e|--max-views|-m|--password|-p) return ;;
    esac

    local subcmd="${words[1]}"

    case "$subcmd" in
        config)
            case "$cword" in
                2) COMPREPLY=($(compgen -W "show set unset" -- "$cur")) ;;
                3) [[ "${words[2]}" == "set" || "${words[2]}" == "unset" ]] \
                    && COMPREPLY=($(compgen -W "server" -- "$cur")) ;;
            esac
            return ;;
        completion)
            COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur"))
            return ;;
        view) return ;;
    esac

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "config view delete list completion $main_opts" -- "$cur"))
        COMPREPLY+=($(compgen -f -- "$cur"))
    else
        COMPREPLY=($(compgen -W "$main_opts" -- "$cur"))
        COMPREPLY+=($(compgen -f -- "$cur"))
    fi
}

complete -o filenames -F _gb_completion gbit
complete -o filenames -F _gb_completion ghostbit
"""

_COMPLETION_ZSH = r"""
#compdef gbit ghostbit
# Ghostbit zsh completion
# Usage: eval "$(gbit completion zsh)"  or add to ~/.zshrc

_gb() {
    local langs=(LANGS_PLACEHOLDER)
    local main_opts=(
        '(-l --lang)'{-l,--lang}'[language hint]:language:('"${langs[*]}"')'
        '(-e --expires)'{-e,--expires}'[TTL in seconds]:seconds:'
        '(-b --burn)'{-b,--burn}'[delete after first view]'
        '(-m --max-views)'{-m,--max-views}'[delete after N views]:count:'
        '(-p --password)'{-p,--password}'[encrypt with password]:password:'
        '(-s --server)'{-s,--server}'[server URL]:url:'
        '(-q --quiet)'{-q,--quiet}'[print URL only]'
        '--json[print full JSON response]'
    )

    local state
    _arguments -C \
        '1: :->first' \
        '*: :->rest' && return 0

    case $state in
        first)
            _alternative \
                'subcommands:subcommand:((config\:"manage config" view\:"view a paste" delete\:"delete a paste" list\:"list local history" completion\:"shell completion"))' \
                "options: :_arguments ${main_opts[*]}" \
                'files:file:_files'
            ;;
        rest)
            case $words[2] in
                config)
                    case $CURRENT in
                        3) _values 'action' show set unset ;;
                        4) [[ $words[3] == (set|unset) ]] && _values 'key' server ;;
                    esac ;;
                view)      _nothing ;;
                completion) _values 'shell' bash zsh fish ;;
                *)         _arguments "${main_opts[@]}" && _files ;;
            esac
            ;;
    esac
}

_gb
"""

_COMPLETION_FISH = """
# Ghostbit fish completion
# Usage: gbit completion fish | source  or save to ~/.config/fish/completions/gbit.fish

set -l langs LANGS_PLACEHOLDER

# Disable file completion when a subcommand is active and not needed
function __gb_no_subcommand
    not __fish_seen_subcommand_from config view delete list completion
end

# Subcommands
complete -c gbit -f -n '__gb_no_subcommand' -a config     -d 'Manage configuration'
complete -c gbit -f -n '__gb_no_subcommand' -a view       -d 'View and decrypt a paste'
complete -c gbit -f -n '__gb_no_subcommand' -a delete     -d 'Delete a paste'
complete -c gbit -f -n '__gb_no_subcommand' -a list       -d 'List local paste history'
complete -c gbit -f -n '__gb_no_subcommand' -a completion -d 'Output shell completion script'

# config actions
complete -c gbit -f -n '__fish_seen_subcommand_from config' -a show  -d 'Show current config'
complete -c gbit -f -n '__fish_seen_subcommand_from config' -a set   -d 'Set a value'
complete -c gbit -f -n '__fish_seen_subcommand_from config' -a unset -d 'Remove a value'

# completion shells
complete -c gbit -f -n '__fish_seen_subcommand_from completion' -a bash -d 'Bash completion'
complete -c gbit -f -n '__fish_seen_subcommand_from completion' -a zsh  -d 'Zsh completion'
complete -c gbit -f -n '__fish_seen_subcommand_from completion' -a fish -d 'Fish completion'

# Main options
complete -c gbit -n '__gb_no_subcommand' -s l -l lang       -d 'Language hint'         -a "$langs"
complete -c gbit -n '__gb_no_subcommand' -s e -l expires    -d 'TTL in seconds'
complete -c gbit -n '__gb_no_subcommand' -s b -l burn       -d 'Delete after first view'
complete -c gbit -n '__gb_no_subcommand' -s m -l max-views  -d 'Delete after N views'
complete -c gbit -n '__gb_no_subcommand' -s p -l password   -d 'Encrypt with password'
complete -c gbit -n '__gb_no_subcommand' -s s -l server     -d 'Server URL'
complete -c gbit -n '__gb_no_subcommand' -s q -l quiet      -d 'Print URL only'
complete -c gbit -n '__gb_no_subcommand'      -l json       -d 'Print full JSON response'
"""


def cmd_completion(shell: str, languages: list[str]) -> None:
    langs_str = " ".join(languages)
    templates = {
        "bash": _COMPLETION_BASH,
        "zsh": _COMPLETION_ZSH,
        "fish": _COMPLETION_FISH,
    }
    script = templates[shell].replace("LANGS_PLACEHOLDER", langs_str)
    print(script.strip())
