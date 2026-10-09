//MY PROMPT
Here
This is my ps, I have make a website so that I can summarize the important stuff
I can run it locally when I'm presenting, so I can use some local llms
I don't have any local llms installed rn, let's discuss what all can we do before we write the prompt
expand your intelligence and creativity
and remember everything we have discussed for this hackathon
you are an expert ai prompt engineer 
give me a ultimate prompt regarding this
dont miss any any evaluating parameter and write me a website which doesnt have any unnecesaary feature which can take my time and use mroe tokens



//PROMPT FROM CHATGPT
UNMISSED — FINAL HACKATHON BUILD, POLISH AND VERIFICATION
Act as a senior full-stack engineer, local-AI engineer, product designer, application security engineer and QA lead. Your task is to finish the existing Unmissed application to a high, submission-ready standard within the current project and environment.
This is the final comprehensive implementation pass. Inspect the existing workspace and previous changes first, preserve working code, identify unfinished requirements, implement the missing pieces, run meaningful tests, and fix the most important defects. Do not waste time repeatedly planning, rewriting working components, adding unnecessary features, or producing lengthy progress reports.
Do not stop after making a plan. Execute the work in priority order. Ask me a question only if a genuinely blocking decision cannot be resolved safely from the existing requirements.
1. PRODUCT VISION AND CHALLENGE
Product: Unmissed
Tagline: Stop scrolling. Start knowing what matters.
Challenge: The Unread Problem — “What Did I Miss?”
Unmissed is a privacy-first AI catch-up application that transforms overwhelming chat conversations into a concise, prioritized briefing.
It must help users answer:
- What happened while I was away?
- What matters to me?
- What did the group actually decide?
- What tasks, deadlines, meetings or requests require attention?
- What else interesting or useful did I miss?
- Can I ask an arbitrary question about the conversation and find the actual supporting messages?
This is not merely a generic summarizer. The differentiator is broad information discovery, explainable prioritization, open-ended conversation Q&A, and clickable evidence linking every finding to its original messages.
2. PRESERVE THE EXISTING WORKING APP
The project is in:
C:\Users\Charan\OneDrive\Desktop\hacakton
The app uses Python, HTML, CSS and JavaScript. Its local inference path uses Ollama and qwen2.5:3b. It has been run at:
http://127.0.0.1:8080/
Existing modules include app.py, app.js, index.html, styles.css, analysis_prompts.py, product_logic.py, a README, and tests.
Existing functionality includes paste/TXT import, transcript parsing, chunked analysis, structured output validation, summaries, categorized findings, question shortcuts, source-message references, phone-number masking and local-model integration.
Earlier checks reported a passing real-model integration and passing unit tests, but problems have also occurred with real exports, parser warnings, incorrect classifications and general questions. Verify the current code before trusting previous reports.
Rules:
- Do not delete or rebuild the application.
- Do not undo working changes.
- Preserve existing tests and add regression tests.
- Keep port 8080 as the documented default unless there is a demonstrated reason to change it.
- Do not remove local AI inference.
- Do not repeat old parser work if the existing implementation already handles it.
- Spend time on actual defects, missing requirements and visible product quality.
3. HIGHEST PRIORITY: MAKE OPEN-ENDED QUESTIONS WORK
This is a critical feature.
The current user may import a conversation successfully, yet ask something like:
- “Were there any jokes?”
- “What funny things happened?”
- “Did someone share an interesting link?”
- “Was the venue changed?”
- “What did people say about the internet?”
- “Did anyone cancel something?”
- “What did they say after the speech?”
- “Were there any complaints?”
- “What was the last important update?”
- Or any other reasonable question about the original conversation.
The application must not answer “No jokes found” or “Nothing mentioned” merely because a finding was not extracted into the initial dashboard.
Required Q&A architecture
The original parsed conversation is the source of truth. Extracted findings and the summary are useful indexes, not the complete knowledge base.
For every custom question and suggested question:
1. Interpret the user's question using the local AI.
2. Search/analyze the original messages, not only the already-extracted findings.
3. Preserve relevant source-message IDs and context.
4. Use chunk-wise local inference and a final synthesis when the full conversation cannot fit safely in one model context.
5. Cover every relevant chunk within the supported input limits. Use efficient context selection where reliable, but do not let keyword-only filtering silently exclude semantically relevant messages.
6. Merge duplicate answers, related evidence and information found across chunks.
7. Return a concise, natural-language answer grounded in the actual messages.
8. Include clickable citations to original messages, including sender and timestamp when available.
9. If the conversation contains no evidence answering the question after it has actually been checked, say so honestly.
10. If analysis was incomplete, timed out or could not cover every relevant chunk, report that limitation instead of presenting an unsupported negative answer.
For example, when asked about jokes, examine the messages themselves for jokes, playful banter, teasing, humorous remarks, memes, stickers, laughter and funny exchanges. Do not search only for the literal word “joke.” Do not force every amusing message into a single hardcoded joke category. Use contextual interpretation and display the actual supporting messages.
The same broad-recall approach must apply to links, warnings, announcements, shared resources, complaints, cancellations, changes of plan, contextual details, and unfamiliar topics.
Do not build a separate fixed rule or hardcoded answer for every possible question. The AI must interpret the user's wording and reason over the original conversation.
Keep this functionality local through Ollama. Avoid sending the entire conversation repeatedly when an efficient, validated chunk workflow can answer the question reliably. Measure the resulting latency.
4. BROAD INFORMATION DISCOVERY — DO NOT MISS UNUSUAL FINDINGS
The first analysis must discover meaningful information even when it does not fit a predefined category.
Ask the model to look for:
- Action items and commitments.
- Confirmed decisions and changes of plan.
- Meetings and events.
- Direct mentions and requests.
- Deadlines and time-sensitive information.
- Important announcements and status updates.
- Problems, warnings and complaints.
- Shared links, files, resources and information.
- Cancellations or changed arrangements.
- Unresolved questions or conflicting statements.
- Interesting conversations and notable moments.
- Unexpected but useful information a returning participant should know.
Support an OTHER_UPDATE category for meaningful findings that do not fit the standard types.
Prioritize findings rather than suppressing them. Lower-priority but potentially useful information must remain accessible in All highlights or Other updates.
Do not claim that nothing important was missed merely because the initial extraction returned few results.
5. CORRECTNESS, SOURCE EVIDENCE AND PRIORITIZATION
Classification
Distinguish these categories accurately:
- ACTION_ITEM: a concrete task, with an assignee and deadline only when supported.
- DECISION: an actual agreement, selection, resolution or confirmed change of plan.
- MEETING_EVENT: an event or meeting with evidence-supported details.
- MENTION_REQUEST: a direct mention, question or request addressed to a participant.
- NOTABLE_MOMENT: an actually interesting or memorable exchange.
- OTHER_UPDATE: useful information that does not fit the categories above.
A request, announcement or proposal is not automatically a decision. A suggestion is not a confirmed agreement. A task mentioned in a group is not automatically assigned to the user.
When an item is ambiguous, preserve uncertainty rather than confidently inventing a classification.
Evidence grounding
Every finding and Q&A answer must retain valid source-message IDs.
- Validate IDs against messages actually parsed from the conversation.
- Keep message order, sender identity, timestamps and original text.
- Allow users to click citations and inspect the exact source.
- Distinguish original quoted text from AI-generated paraphrases.
- If evidence conflicts, show the conflict instead of guessing.
- Do not invent messages, names, owners, dates, meetings or decisions.
Summary consistency
The summary must agree with the final validated findings. Do not claim that there are no decisions while displaying a confirmed decision card.
Synthesize validated evidence across all chunks rather than letting one chunk's summary replace the rest.
Priority
Use the AI to interpret relevance and meaning. Use deterministic code for transparent checks and priority rules.
Consider:
- Explicit approaching or overdue deadlines.
- Tasks genuinely assigned to the user.
- Direct requests or questions that require attention.
- Major decisions and plan changes.
- Explicit urgency and relevant unresolved commitments.
Explain every important priority. Do not make everything high priority. Missing deadlines must remain missing. Do not discard unfamiliar categories or low-priority information simply because the ranking system does not recognize them.
6. REAL EXPORTED CHAT PARSING
The user's chat contains headers such as:
[10/9/26, 10:48:04 AM] +91 63662 36404: We are in the class room
Continue supporting realistic variations:
- Sender followed by a colon.
- Bracketed timestamps.
- ISO timestamps.
- AM/PM timestamps with seconds.
- Phone-number sender identifiers containing spaces.
- Unicode sender names.
- Message text containing colons or URLs.
- Multiline messages.
- System notifications.
- Deleted-message notices and media placeholders.
- Missing timestamps and genuinely malformed lines.
Preserve all content where possible. Do not silently discard unfamiliar lines. Avoid warnings for formats the parser actually supports.
Support TXT export and pasted text reliably. Add other formats only when their actual structure is understood and tested.
Do not claim full compatibility with a messaging platform without testing a real export from it.
7. LOCAL AI PIPELINE AND RELIABILITY
Continue using the installed Ollama model qwen2.5:3b.
Expected pipeline:
Input → parser → normalized messages with source IDs → context-aware chunking → local AI structured extraction → validation → deduplication and conflict handling → final synthesis → evidence-grounded priorities and Q&A → dashboard.
Use Ollama's supported JSON Schema response format and application-side validation. Each analysis result must have the required summary and findings array, including when that array is empty.
Constrain evidence IDs to those actually belonging to the chunk or relevant message set. Handle invalid IDs, missing fields, malformed JSON, truncation, duplicate findings, timeouts and model unavailability.
Use at most one controlled repair retry when appropriate, then report a useful error. Never replace failed inference with mock results.
Keep diagnostics useful but privacy-safe: log stages, chunk indexes, durations, output lengths and error types when appropriate. Never log entire conversations, phone numbers, private model responses or user identities.
Make the initial summary and follow-up questions reliable without adding a complicated framework or multiple agents.
8. FINAL UI/UX REDESIGN
The existing warm ivory, forest-green and editorial typography direction is a good foundation. Preserve that identity, but make the website look like a polished, distinctive hackathon product rather than a simple form.
Do not redesign only the import page and leave the results screen plain. Implement a coherent design across the whole application.
Navigation
Add a compact, useful results navigation—not a generic marketing navbar.
Include:
- Overview.
- Needs your attention.
- Action items.
- Decisions.
- Meetings & events.
- Mentions & requests.
- Other updates.
- All highlights.
- Conversation Q&A.
Navigation must filter or navigate to actual content. Counts must be derived from current analysis results. Do not invent findings or counts. Use a compact sidebar on desktop and an accessible responsive equivalent on mobile.
Import experience
Keep paste/TXT import as the easiest route. Improve the input card, supported-format guidance, clear primary action and upload state. Preserve useful whitespace without leaving the page visually empty.
The optional user-identity input should remain secondary.
Remove the model-selection dropdown because the initial product has one configured model. Instead display a truthful model-status indicator for Qwen2.5 3B through Ollama.
Replace the tiny privacy text with a proper local/offline information bar
Create a prominent, well-designed “Local & Offline” information bar or expandable panel near the import area. It must explain:
- The conversation is processed using a local application and local AI.
- Which prerequisites must be installed before first use.
- How to run Ollama and start the local application.
- That the model and Python dependencies must be downloaded/installed before offline use.
- That analysis can run without internet once the model, dependencies and required assets are available locally, subject to verification.
- What an internet connection is still needed for, such as initial installation, model download or updates.
- How the UI behaves when Ollama is unavailable.
- That no cloud AI fallback is used.
Provide concise, step-by-step expandable instructions and useful copyable commands where practical.
The bar must distinguish verified live status from general instructions. Use the actual backend health/status response where available. Do not claim “offline ready” or “your chat never leaves this device” unless the current configuration supports that claim.
Bundle or locally serve frontend assets where practical, so external fonts, scripts or analytics do not unexpectedly break offline use or leak metadata.
Results dashboard
Make this the strongest visual part of the application.
Build a clear hierarchy:
1. Catch-up summary.
2. A compact overview of actual finding counts.
3. Needs your attention.
4. Confirmed decisions.
5. Action items and deadlines.
6. Meetings and events.
7. Mentions and requests.
8. Other updates and all highlights.
9. Conversation Q&A.
Use polished finding cards with category, evidence-based description, priority reason, and source link. Visually distinguish confirmed decisions, proposals, announcements, tasks and uncertain findings.
Include filters that actually work, accessible selected/hover/focus states, responsive layout, source-message navigation/highlighting, and concise progress indicators.
General visual quality
- Strong typography, spacing, alignment and hierarchy.
- Consistent icons and visual language.
- Restrained, intentional use of color and semantic status styles.
- Clean responsive desktop/mobile behavior.
- Keyboard accessibility, readable contrast, semantic HTML and accessible controls.
- Polished loading, errors, success, empty and partial-result states.
- No decorative features that obscure real functionality.
- Every button and menu must work.
Do not add dependencies purely for appearance. Retain the current backend and application logic wherever possible.
9. LOCAL-FIRST PRIVACY AND SECURITY
The challenge explicitly requires local-first processing. Keep AI inference on the user's device.
- No cloud LLM or silent cloud fallback.
- No external transmission of conversation content, summaries, findings, identities or question text.
- Require a loopback Ollama endpoint, bypass environment proxies for its requests, and reject remote endpoints before sending transcript data.
- No login, database, account system or unnecessary persistent storage.
- Preserve original message content and sender IDs internally for source evidence.
- Mask phone numbers in generated findings, answers, visible source panels and diagnostic logs by default without corrupting original evidence data.
- Use an optional supplied identity only for appropriate matching; do not expose it in public job metadata or logs.
- Avoid analytics or telemetry that collect conversation content.
- Validate inputs and file sizes.
- Use safe HTML rendering and prevent unsafe file/path handling and injection.
- Do not expose the local server or Ollama to the public internet merely to make the hosted link appear to work.
Verify privacy behavior rather than relying on text in the UI. Document limitations honestly.
10. OFFLINE USE VERSUS PUBLIC DEPLOYMENT
Our local app and a public deployed website are different runtime environments. A hosted URL cannot automatically reach Ollama running on the developer's laptop.
Keep the locally working application functional first.
The hackathon requires a deployed project link, so investigate the simplest genuine approach that also preserves local-first privacy. Evaluate existing hosting/environment constraints before changing the architecture. Browser-local inference may be considered only if its model size, browser/hardware requirements, offline operation and reliability are demonstrated to be feasible.
Do not add cloud AI, expose the backend publicly, or use a tunnel without a deliberate security review. Do not pretend that the public URL has working AI when it does not.
Provide a realistic solution and accurately document which functionality works locally, which works on the hosted URL, and what the judge must do. Do not claim deployment is complete until the live URL is opened and tested.
11. PERFORMANCE AND TOKEN EFFICIENCY
- Avoid redundant model calls.
- Use bounded, overlapping chunks where needed.
- Reuse validated analysis where possible.
- For broad questions, cover the original conversation and merge relevant results without unbounded repeated calls.
- Do not use keyword-only filters to exclude potentially relevant semantic evidence.
- Clearly surface incomplete analysis if a limit, failure or timeout prevents complete coverage.
- Measure actual latency on the real test conversation.
- Keep dependencies minimal.
- Avoid repeated full-code rewrites and huge output dumps.
12. ALL PROTOCOLX EVALUATION CRITERIA
Treat every criterion as important; the deck does not give exact numerical weights for all parameters.
- Code quality: clean, readable, maintainable and testable implementation.
- Security: safe inputs, privacy, no unintended data transmission or exposed local services.
- Efficiency: bounded analysis, appropriate chunking, caching and minimal dependencies.
- Testing: meaningful unit/integration tests and a demonstrated real workflow.
- UI/UX polish: distinctive, polished, responsive experience with strong hierarchy and accessible states.
- Innovation and engineering uniqueness: broad catch-up discovery, source-grounded findings, explainable priority and arbitrary conversation Q&A.
- Modular structure: separate parsing, prompts, inference, validation, prioritization, privacy and presentation logically.
- Accessibility: keyboard operation, focus states, semantic markup, contrast and usable responsive layout.
- Documentation: clear setup, architecture, supported formats, prompts, limitations and AI disclosure.
- Git history: meaningful commits and a clean repository.
- Problem-statement alignment: solve “What did I miss?” with useful, trustworthy, locally processed findings.
Do not invent numerical weights or scoring results.
13. TESTING AND VERIFICATION
Expand and preserve tests for:
Parser
- The user's bracketed date/AM-PM export format with seconds and phone-number senders.
- Unicode and multiline messages.
- Messages containing URLs/colons.
- System messages and media placeholders.
- Unknown lines, malformed input, duplicates and long transcripts.
AI and prioritization
- Required JSON fields, empty findings, invalid JSON and truncated output.
- Real source-ID constraints and evidence validation.
- Requests versus confirmed decisions.
- Tasks assigned to other participants versus the user.
- Unknown categories and preservation of low-priority findings.
- Conflicting deadlines or changed plans.
- Summary/findings consistency.
- Phone-number/identity masking.
- Prompt-injection attempts embedded in imported chat content.
Open-ended Q&A
- Jokes and playful conversation, including examples where humour is implied rather than the word “joke” appearing.
- Shared links, venue changes, warnings and unexpected updates.
- Queries whose answers occur in different chunks.
- Queries with evidence and queries with genuinely insufficient evidence.
- Citations that open the correct source messages.
- Incomplete chunk/question analysis never presented as a definitive negative answer.
Integration and operation
- Genuine local Ollama inference.
- Full import-to-dashboard workflow.
- Each of the five question shortcuts.
- Custom question grounded in the original messages.
- Ollama unavailable, invalid response and timeout.
- Local-only endpoint enforcement.
- Privacy behavior and offline-ready status correctness.
Mocks are acceptable for deterministic unit tests but must never masquerade as real AI results. Run the genuine integration tests when the model is available.
Run all existing tests, new tests, Python compilation, JavaScript syntax checks and configured build/lint checks. Review the actual page in a browser where possible. If preview access is blocked, explain that honestly and use available HTTP/API checks.
Use the exact real exported chat if it is accessible. If it is not available, use representative synthetic tests and explicitly state that limitation. Never claim to have tested data that was unavailable.
14. README, ACTUAL AI PROMPTS, AND GITHUB
Complete the root README.md with the actual shipped implementation:
- Product overview and primary features.
- Supported input formats and limitations.
- Architecture and data flow.
- Installation, Ollama setup, model setup, startup and test commands.
- Actual system, extraction and Q&A prompts used by the code.
- Structured output schema, source grounding and chunk-merging design.
- Deterministic prioritization explanation.
- Privacy and offline behavior.
- Difference between local operation and the public deployment.
- Known limitations and honest demo instructions.
- Exact generative-AI/model disclosure: which model is used and where.
- Results of real checks, not invented claims.
The prompt documentation must match the real code; do not insert fictional or unused prompts.
Keep the repository clean:
- Add/update .gitignore.
- Exclude secrets, model weights, private chats, virtual environments and build artifacts.
- Use meaningful commits at coherent milestones if Git is configured, without rewriting history or force-pushing.
- Verify setup instructions against actual commands where practical.
15. SCOPE RESTRICTIONS
Do not build:
- Login, profiles or account management.
- A database or cloud synchronization.
- Social/team features.
- Direct integrations requiring OAuth.
- An unnecessary mobile app.
- A vector database, complex RAG framework or multi-agent system.
- Unrelated settings, billing, analytics or admin pages.
- Unnecessary model-selection controls.
- Fake demo output or decorative nonfunctional buttons.
Every feature must support the core task, reliability, privacy or evaluation quality.
16. EXECUTION ORDER
Work through the following sequence without asking me to approve each ordinary step:
1. Inspect the current workspace and identify existing progress.
2. Fix the biggest correctness/parser/accuracy issues without destabilizing working code.
3. Make open-ended Q&A inspect original source messages, not just pre-extracted highlights.
4. Improve broad-recall extraction, source grounding and category consistency.
5. Finish the UI redesign, results navigation and Local & Offline information bar.
6. Add meaningful tests for the changed behavior.
7. Run a genuine local-model check and measure a real conversation when available.
8. Complete README prompt documentation, privacy review and repository hygiene.
9. Evaluate a feasible, honest deployment route.
10. Report concrete results and remaining blockers.
Do not stop after describing this plan. Make the changes in coherent stages and continue until the practical work is complete.
17. DEFINITION OF DONE
Unmissed is ready only when:
- A real supported chat can be imported and analyzed through local AI.
- The UI gives an accurate, useful catch-up summary.
- Important information outside predefined categories is preserved.
- Custom questions can find evidence anywhere in the original conversation, including across chunks.
- Negative answers are not returned merely because extraction missed something.
- Every important result links to real source messages.
- Decisions, requests, announcements and tasks are classified correctly.
- All five quick questions and custom Q&A work.
- Privacy and masking protections are tested.
- Local/offline requirements and the setup bar are accurate.
- The UI is polished, responsive and accessible.
- Tests, syntax checks and available build checks pass, or outstanding failures are clearly explained.
- The README documents actual prompts, setup and AI usage.
- The repository is clean.
- The deployment story is honest, feasible and verified to the extent possible.
At completion, provide a concise report with implemented features, files changed, actual verification commands/results, latency observations, exact launch instructions, and remaining limitations. Do not call something finished unless it has been tested.
Final objective: a polished, distinctive, privacy-respecting AI catch-up product that makes users confident they understand what they missed, including details they didn't know to ask about, with trustworthy evidence behind every answer.