# Unmissed

**Stop scrolling. Start knowing what matters.**

Unmissed turns pasted conversation text or a plain-text `.txt` export into a source-linked catch-up briefing. It runs as a loopback-only Python app and uses the local Ollama model `qwen2.5:3b`; there is no cloud model fallback.

## Run on Windows

1. Install Python 3.10 or later and Ollama.
2. Download the model once while online:

   ```powershell
   ollama pull qwen2.5:3b
   ```

3. Start Ollama if it is not already running, then start Unmissed from this folder:

   ```powershell
   $env:PORT = '8080'
   python app.py
   ```

4. Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

The application uses only the Python standard library. The browser UI is plain HTML, CSS, and JavaScript; no package install or build step is required. `PORT` can select another local port when needed. The server always binds to `127.0.0.1`.

## Use

- Paste a conversation or import a `.txt` file. CSV and platform-specific export compatibility are not claimed.
- The parser preserves message order, sender, timestamps, multiline text, system notices, and source IDs where the text format exposes them. It supports common `Name: message`, bracketed timestamps, ISO-like date/time headers, and the tested WhatsApp-style date/time header shape; see `tests/test_parser.py` for the exact examples.
- Analysis requests are chunked with message overlap. Qwen extracts evidence-linked summaries and findings; deterministic Python validates references, normalizes categories, merges duplicate findings, detects explicit mentions/commitments/meeting references, and assigns explainable priorities.
- Custom and suggested questions search every conversation chunk with the local model, then reconcile grounded answers and source IDs when the transcript spans multiple chunks.
- Select a finding or citation to jump to its original message. Original message text is retained in the current app process for evidence and is masked only when displayed; generated text and phone numbers in logs are redacted.

An unfamiliar finding category is retained as an “Other update.” If any analysis section or final synthesis fails, the app preserves successful findings and reports the incomplete coverage in the result. An empty finding list is accompanied by an uncertainty notice.

## Local processing and privacy

Conversation text and the optional identity are sent only to the configured Ollama endpoint, which must resolve to loopback (`localhost`, `127.0.0.1`, or `::1`). The app removes proxy settings from Ollama requests and rejects remote endpoints before sending transcript data. There is no analytics, database, authentication, or cloud inference path.

The app keeps recent analysis and question jobs in process memory so source navigation and follow-up questions work. Completed jobs become eligible for expiry after 24 hours and are pruned on the next job lookup or job creation. Retention is capped at 12 unreferenced completed jobs; an analysis result remains while a retained question job refers to it. Stopping the Python process clears all in-memory jobs. This is local processing, but the app does not verify that the machine's network is disconnected; initial installs, model downloads, and software updates require internet access.

The local server is intended for the presenter's own machine. Do not expose it to the public internet: it has no user authentication, and imported conversations are private. A static or ordinary hosted frontend does not provide access to a presenter's local Ollama model.

## AI prompts and model disclosure

The configured default model is **Qwen2.5 3B (`qwen2.5:3b`) through Ollama**. The exact prompt text is maintained in `analysis_prompts.py` so the application and documentation do not drift. Its active templates are:

- `SYSTEM_ANALYSIS_PROMPT` and `ANALYSIS_PROMPT` for evidence-grounded catch-up extraction; `ANALYSIS_RETRY_PROMPT` is used at most once if the model output is malformed or incomplete.
- `SYSTEM_SUMMARY_PROMPT` and `SUMMARY_PROMPT` for cross-chunk synthesis; each candidate finding and source ID is supplied, and valid chunk findings are preserved if synthesis omits them.
- `SYSTEM_QUESTION_PROMPT` and `QUESTION_PROMPT` for open-ended questions over original messages in each chunk.
- `SYSTEM_QUESTION_SYNTHESIS_PROMPT` and `QUESTION_SYNTHESIS_PROMPT` for multi-chunk question reconciliation.

The application asks the model to use only supplied conversation evidence and treats imported content as untrusted quoted data. Python does not provide semantic understanding: it checks response shape, source IDs, exact metadata grounding, duplicates, some explicit patterns, and ranking rules. Model outputs can still miss nuance or misinterpret messages; inspect cited source messages, especially when confidence is low or a conflict is shown.

## Tests and checks

Run deterministic unit tests and syntax checks:

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py product_logic.py analysis_prompts.py
node --check app.js
```

The optional test `test_real_local_analysis_and_grounded_question` calls the configured local Ollama model; it is skipped by default. To run it:

```powershell
$env:UNMISSED_RUN_OLLAMA_TESTS = '1'
python -m unittest tests.test_ollama_integration -v
Remove-Item Env:UNMISSED_RUN_OLLAMA_TESTS
```

The real-model check requires Ollama to be running with `qwen2.5:3b` already installed and may take longer than the unit suite. Mocked tests do not verify model quality or offline operation.

## Limits

- Only pasted text and `.txt` files are supported. A platform export should be called compatible only after testing a real export from that platform.
- Large conversations are processed in sequential model calls and can take several minutes. A failed chunk or truncated synthesis is surfaced as incomplete; no missing section is treated as proof that an event did not occur.
- Model availability depends on the local Ollama service and locally downloaded model. Installing or downloading those components requires internet access.
- The app is not a public multi-user service and does not persist conversations to disk.
