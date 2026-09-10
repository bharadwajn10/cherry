# Project Cherry — Architecture Spec (v2)

## 1. What Cherry actually is

Not an always-on server bot. It's a **local, on-demand personal assistant**:

- You open your laptop, run one script.
- It starts a local LLM via Ollama (Qwen or DeepSeek — interchangeable, just a config value).
- It **catches up** on everything posted across the whole server since it last ran.
- It figures out, per message, whether that's a **task to schedule**, a **question about your existing tasks/plans**, or **just casual chat** — and responds accordingly.
- While the laptop stays open, it keeps listening live and doing the same thing in real time.
- Everything is free: local model (Ollama), Google Calendar API (free tier is plenty for personal use), file-based state (no database, no hosting).

## 2. Goals

- Works across **all channels** in the server, not one designated channel.
- No task/chat command syntax — intent is inferred from the message itself.
- Casual conversation mode has access to your calendar/task context, so it can answer "what do I have this week?" for real instead of guessing.
- All state is **plain files in the project directory** — light, human-readable, easy to inspect or wipe.
- A memory file gives the chat mode continuity across sessions, but is actively pruned so it never grows unbounded.
- Swapping the local model (Qwen ↔ DeepSeek ↔ anything else in Ollama) is a one-line config change.

## 3. Non-goals (v1)

- Multi-server support (single Discord server).
- Multi-user calendars (your calendar only).
- Always-on hosting / uptime guarantees — it's fine that it only runs when your laptop is open and the script is started.

## 4. Module layout

```
cherry/
  config.py            # loads & validates .env, exposes typed settings (model name, discord token, etc.)
  models.py            # Pydantic models: ParsedEvent, Intent, ChatTurn
  llm_client.py         # wraps Ollama HTTP calls; model name is a config value, not hardcoded
  intent_router.py      # one LLM call: classifies a message as task / task_query / general_chat
  calendar_client.py    # wraps Google Calendar API
  state_store.py        # last_read.json — tracks last processed message ID PER CHANNEL
  memory_store.py        # memory.txt — rolling notes from chat mode, pruned to stay small
  discord_bot.py         # discord.py client: catch-up pass + live on_message, across all channels
  pipeline.py            # orchestrates: classify -> route -> (schedule | answer | chat) -> reply
  main.py                 # entrypoint: run catch-up phase, then start live listener
  logging_config.py
tests/
  test_intent_router.py
  test_llm_client.py
  test_pipeline.py
```

Keep `pipeline.py` free of Discord-specific or Ollama-specific code — it should take a plain message string + channel context and return an action, so it's testable without either dependency running.

## 5. State files (all in project root, not a database)

### `last_read.json`
```json
{
  "1234567890": "998877665544",
  "1234567891": "998877665599"
}
```
Maps `channel_id → last processed message_id`. Updated **after each message is successfully handled**, not in a batch at the end — so a crash mid-catch-up doesn't reprocess or lose messages.

### `memory.txt`
Free-form rolling notes from chat mode — not a full transcript. Think "things worth remembering," e.g.:
```
- User is working on a hackathon project due Oct 12, team of 3.
- Prefers evening study blocks after 7pm.
- Mentioned wanting to reduce Discord notifications from #general.
```
- Chat mode reads this file and injects it into the system prompt for context.
- After each chat exchange, a lightweight LLM call decides whether anything new is worth appending.
- **Pruning:** before writing, check file size (e.g. cap at ~4–8 KB). If over the cap, run one LLM call: "compress this memory file to under X characters, keep the important facts, drop stale/completed items." This keeps memory useful without letting it balloon.

This is intentionally simple text, not JSON — you said it's fine as a lightweight "thinking" file, so keep it human-readable and easy to hand-edit or clear yourself if needed.

## 6. Intent routing (the key new piece)

Every incoming message goes through one classification call before anything else:

```python
class Intent(BaseModel):
    type: Literal["task", "task_query", "general_chat"]
    reasoning: str  # short, for debugging/logs — not shown to user
```

Prompt sketch:
> "Classify this Discord message as one of: `task` (something to schedule — an event, deadline, assignment), `task_query` (a question about existing plans/schedule — 'what do I have this week', 'when's my hackathon meeting'), or `general_chat` (anything else — casual conversation, brainstorming, venting). Message: {text}"

Routing:
- `task` → existing parse-to-`ParsedEvent` → validate → create calendar event → reply with confirmation + link (this part is basically your original pipeline).
- `task_query` → pipeline fetches relevant data from `calendar_client` (e.g. `list_upcoming_events(days=7)`) and/or `memory.txt`, injects it into a prompt, and replies conversationally with the real answer.
- `general_chat` → chat mode: load `memory.txt` + recent conversation turns, respond conversationally, then decide whether to append anything to memory.

This one router call is what lets you mix "schedule my chem lab report for Friday" and "hey, been slammed lately lol" in the same channel with no special syntax.

## 7. Multi-channel catch-up + live flow

**On startup (`main.py`):**
1. Load `last_read.json`.
2. For every text channel the bot can read in the server:
   - Fetch messages after the stored last-read ID (`channel.history(after=..., oldest_first=True)`).
   - If no entry exists for that channel yet, either skip backlog (start fresh) or fetch a bounded window (e.g. last 24h) — decide once and keep it consistent; don't backfill the entire channel history on first run.
   - Run each message through the pipeline in order, updating `last_read.json` after each one.
3. Once caught up on all channels, start the live `on_message` listener, which runs the same pipeline on new messages as they arrive.

**Filtering rules (apply in both phases):**
- Ignore messages from the bot itself.
- Ignore other bots' messages (configurable).
- Optionally ignore channels by name/category (e.g. skip `#announcements`) via a simple allow/deny list in config — since "all channels" may still want a couple of exclusions.

## 8. LLM client — model-agnostic by design

```python
# .env
OLLAMA_MODEL=qwen2.5        # or deepseek-r1, or anything else pulled locally
OLLAMA_HOST=http://localhost:11434
```

`llm_client.py` should never hardcode "qwen" or "deepseek" — it reads the model name from config and passes it straight into the Ollama `/api/chat` payload. This means:
- You can `ollama pull deepseek-r1` and switch by changing one env var.
- You could even route different steps to different models later (e.g. a smaller/faster model for intent classification, a larger one for chat) without touching the rest of the codebase — worth designing the client to accept a model override per call, even if v1 only uses one model everywhere.

## 9. Calendar client

Same as before, but now also needs a **read path** for `task_query`:
```python
def create_event(event: ParsedEvent) -> CalendarEventResult: ...
def list_upcoming_events(days: int = 7) -> list[CalendarEventResult]: ...
```
Both wrap `google-api-python-client` with your existing service account credentials — no new setup needed there, just an added read method.

## 10. Pipeline flow (end to end)

1. Message arrives (catch-up or live) → skip if bot/self/excluded channel.
2. Skip if `message_id <= last_read[channel_id]` (safety net alongside the catch-up range).
3. `intent_router.classify(text)` → `task` / `task_query` / `general_chat`.
4. Branch:
   - **task** → parse → validate (`ParsedEvent`) → on failure, retry once with error feedback, then ask for clarification in-channel if still failing → on success, create calendar event → reply with confirmation + link.
   - **task_query** → fetch calendar data (+ memory if relevant) → reply conversationally.
   - **general_chat** → load memory → reply conversationally → maybe update memory (pruned if oversized).
5. Update `last_read.json` for that channel with this message's ID.
6. Log the outcome (see §11).

## 11. Error handling & logging

- Wrap every Ollama call, Discord call, and Google API call in try/except with timeouts — none should crash the process.
- Log to a rotating file (e.g. `cherry.log`) with message ID, channel, intent, and outcome — enough to debug "why didn't it schedule that" after the fact, without needing a database.
- If Ollama isn't running when the script starts, fail fast with a clear message ("Ollama not reachable at localhost:11434 — is it running?") rather than failing per-message later.

## 12. Config & secrets

`.env`:
```
DISCORD_TOKEN=...
OLLAMA_MODEL=qwen2.5
OLLAMA_HOST=http://localhost:11434
GOOGLE_CALENDAR_ID=...
EXCLUDED_CHANNELS=announcements,rules   # optional, by name
```
`credentials.json` and `.env` stay out of version control. `config.py` validates all required fields at startup and fails immediately with a clear message if anything's missing.

## 13. Suggested build order for the coding agent

Since you have working `bot.py` code already, this should be a **refactor+extend**, not a rewrite from zero:

1. `config.py` + `models.py` — pull settings/env logic out first.
2. `state_store.py` — replace the current single-file/single-channel `last_read.txt` logic with the per-channel JSON version.
3. `intent_router.py` — new; test with a handful of sample messages (task / task_query / general_chat) before wiring anything else.
4. `llm_client.py` — generalize the existing Ollama call to take model name from config; keep your existing parsing prompt for the `task` branch.
5. `calendar_client.py` — keep `create_event` as-is, add `list_upcoming_events`.
6. `memory_store.py` — new; simple read/append/prune functions, tested in isolation.
7. `pipeline.py` — wire steps 3–6 together with injected dependencies.
8. `discord_bot.py` + `main.py` — extend to all channels, add the catch-up phase, then the live listener using the same pipeline.

## 14. Open questions worth deciding before/during build

- **First-run behavior per channel:** skip backlog entirely, or backfill a bounded window (e.g. last 24–48h)? Recommend the bounded window so a first run on an old server doesn't try to process years of history.
- **Excluded channels:** decide the initial list now (e.g. announcement/rules channels) so the agent doesn't have to guess.
- **Memory size cap:** pick a concrete number (e.g. 4KB) so pruning behavior is deterministic rather than "roughly."
