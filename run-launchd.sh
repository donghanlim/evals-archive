#!/bin/zsh
set -e
ENV_FILE="/Users/justimmacbook/Documents/_personal/my_brain_files/50_private-admin/credentials/evals-archive/groq.env"
if [[ -r "$ENV_FILE" ]]; then
  source "$ENV_FILE"
fi
exec /Users/justimmacbook/.local/share/mise/installs/python/3.12/bin/python3 evals.py run --db evals.db
