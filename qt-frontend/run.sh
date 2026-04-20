#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
case "${QT_IM_MODULE:-}" in
	""|fcitx|fcitx5)
		export QT_IM_MODULE=ibus
		;;
esac
cd "$SCRIPT_DIR"
python main.py "$@"
