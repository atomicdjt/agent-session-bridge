# Independent Reproduction Guide

This guide allows any developer to independently reproduce the ablation experiments disproving the efficacy of `transcript.jsonl` imports in the Antigravity CLI.

### Step 1: Prove `transcript.jsonl` is ignored
1. Generate a UUID (e.g. `test-ablation-2222`).
2. Create the directory:
   ```bash
   mkdir -p ~/.gemini/antigravity/brain/test-ablation-2222/.system_generated/logs/
   ```
3. Synthesize a mock transcript:
   ```bash
   echo '{"step_index":1,"source":"USER_EXPLICIT","type":"USER_INPUT","status":"DONE","created_at":"2026-08-21T10:00:00Z","content":"Hello world!"}' > ~/.gemini/antigravity/brain/test-ablation-2222/.system_generated/logs/transcript.jsonl
   ```
4. Attempt to resume it:
   ```bash
   agy --conversation test-ablation-2222 --print "What did I say?"
   ```
5. **Expected Result:** `warning: conversation "test-ablation-2222" not found`. 

### Step 2: Inspect Authoritative State
1. Force a clean, isolated conversation creation:
   ```cmd
   cmd.exe /c "set AGY_CONVERSATION_ID= && set AGY_WORKSPACE= && agy --new-project --print \"The verification phrase is DELTA-99991.\""
   ```
2. Locate the generated SQLite database:
   ```powershell
   Get-ChildItem -Path ~/.gemini/antigravity/conversations/*.db | Sort-Object LastWriteTime -Descending | Select-Object -First 1
   ```
3. Inspect the schema to observe the proprietary binary blobs preventing safe external synthesis:
   ```python
   import sqlite3
   import sys
   
   db_path = sys.argv[1]
   conn = sqlite3.connect(db_path)
   print(conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())
   ```
4. **Expected Result:** Tables like `steps`, `trajectory_meta`, `gen_metadata` populated with opaque `blob` fields.
