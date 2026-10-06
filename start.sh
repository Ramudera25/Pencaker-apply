#!/bin/bash
# Start AutoLamar — http://127.0.0.1:8010
# Log: ./autolamar.log | Stop: pkill -f "autolamar.*uvicorn"
set -e
cd "$HOME/autolamar"

# Penting: bersihkan PYTHONHOME/PYTHONPATH milik runtime Hermes (python 3.14).
# Jika tidak, uvicorn mengambil paket dari venv Hermes dan .so pydantic_core
# tidak cocok dengan interpreter venv ini (python 3.12).
unset PYTHONHOME
unset PYTHONPATH

export no_proxy="localhost,127.0.0.1"
export NO_PROXY="localhost,127.0.0.1"
exec "$HOME/autolamar/venv/bin/uvicorn" autolamar.app.main:app \
  --host 127.0.0.1 --port 8010 >> ./autolamar.log 2>&1
