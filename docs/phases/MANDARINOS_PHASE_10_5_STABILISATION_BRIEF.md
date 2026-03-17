MANDARINOS — PHASE 10.5 STABILISATION BRIEF
Purpose: Stabilise conversation architecture before Phase 11 (Alpha expansion)
Author: Dr Raymond Young + ChatGPT Strategist
Status: Pre-implementation (architecture only — no code yet)

---------------------------------------------------------------------
CONTEXT
---------------------------------------------------------------------

MandarinOS has completed:

Phase 7  Learning Interaction Layer
Phase 8  Conversation Loop UI
Phase 9  Conversation Engine Integration
Phase 10 Memory + Persona Foundations

Alpha testing shows:

• Conversations are functional but not fully natural
• Response options sometimes feel mismatched
• Hint system is strong for vocabulary but weak for conversation recovery
• Conversation flow feels slightly mechanical
• Advanced design concepts (curiosity engine, loop questions, etc.) are not fully expressed

Conclusion:

The issue is NOT missing features.
The issue is a missing **conversation operating layer**.

---------------------------------------------------------------------
CORE DIAGNOSIS
---------------------------------------------------------------------

Current system models:

→ sentences
→ vocabulary
→ frame routing

But natural conversation requires:

→ conversation moves
→ interaction strategies
→ conversational rhythm

Missing layer:

>>> CONVERSATION STRUCTURE <<<

This must be added WITHOUT breaking existing architecture.

---------------------------------------------------------------------
PHASE 10.5 OBJECTIVE
---------------------------------------------------------------------

Introduce a lightweight structural layer that enables:

• natural conversation flow
• reusable interaction patterns
• scalable adaptive behaviour (Phase 11+)
• better use of existing infrastructure

DO NOT:
• hard-code conversations
• rewrite content
• introduce heavy logic

FOCUS ON:
• structure
• tagging
• minimal extensions

---------------------------------------------------------------------
KEY CONCEPTS TO INTRODUCE
---------------------------------------------------------------------

1) CONVERSATION MOVE TYPES

Each frame must represent a **conversation role**, not just a sentence.

Add field:

move_type

Allowed values:

ASK
ANSWER_MIN
ANSWER_EXTEND
REACTION
LOOP_QUESTION
BRIDGE_QUESTION
RECIPROCITY
REPAIR
CLARIFY

Example:

"你叫什么名字？" → ASK  
"我叫Raymond" → ANSWER_MIN  
"我叫Raymond，我来自新西兰" → ANSWER_EXTEND  
"真的吗？" → REACTION  
"你呢？" → RECIPROCITY  

---------------------------------------------------------------------

2) QUESTION TYPES (CURIOSITY ENGINE)

Add field:

question_type

Values:

core       → basic factual
treasure   → interesting / deeper
loop       → follow-up on user answer
bridge     → topic shift

IMPORTANT:

These were already conceptual ([?][T][L][B→X])  
They must now become **runtime-visible structure**.

---------------------------------------------------------------------

3) RESPONSE OPTION ROLES

Options must represent **conversation strategies**, not just variations.

Add to each option:

option_role

Values:

minimal        → short safe answer
extend         → adds information
reciprocate    → returns question
repair         → asks for help / repeat
clarify        → checks understanding
react          → emotional response

Example:

Question: 你叫什么名字？

Options should include:

• 我叫Raymond (minimal)
• 我叫Raymond，我来自新西兰 (extend)
• 我叫Raymond，你呢？ (reciprocate)
• 不好意思，可以再说一次吗？ (repair)

---------------------------------------------------------------------

4) OXYGEN VOCABULARY LAYER

Define a new tagging concept:

oxygen_tags

These are high-frequency conversational operators:

Question oxygen:
谁 / 什么 / 哪儿 / 怎么 / 为什么 / 哪个

Connection oxygen:
也 / 还 / 都 / 就 / 因为 / 所以 / 但是 / 然后

Interaction oxygen:
吗 / 呢 / 吧 / 啊 / 哦 / 对 / 是吗 / 真的

Repair oxygen:
什么？ / 不好意思 / 再说一次 / 听不清

These are NOT normal vocabulary.

They are:

>>> CONVERSATION INFRASTRUCTURE <<<

System should:

• prioritise their visibility
• reuse them across engines
• ensure early and repeated exposure

---------------------------------------------------------------------

5) CONVERSATION SKELETONS

Introduce reusable interaction patterns.

New concept:

conversation_skeleton

Each skeleton defines a pattern of moves.

Examples:

Skeleton A — Basic exchange
ASK → ANSWER_MIN → REACTION

Skeleton B — Reciprocity
ASK → ANSWER_MIN → RECIPROCITY

Skeleton C — Extension
ASK → ANSWER_MIN → ANSWER_EXTEND

Skeleton D — Loop
ASK → ANSWER_MIN → LOOP_QUESTION

Skeleton E — Repair
ASK → REPAIR → REPEAT → ANSWER

These are NOT hard-coded flows.

They are:

>>> TEMPLATES <<<

Runtime selects skeleton → fills with frames.

---------------------------------------------------------------------
RUNTIME BEHAVIOUR (TARGET)
---------------------------------------------------------------------

Instead of:

frame → option → next frame

System should behave as:

1) Select skeleton
2) Select move type
3) Select frame matching move
4) Select options matching role
5) Advance based on conversation state

Example:

Step 1: ASK (core question)
Step 2: user selects ANSWER_MIN
Step 3: system chooses:
        → REACTION OR LOOP_QUESTION
Step 4: if loopable → ask follow-up
Step 5: optionally allow reciprocity

---------------------------------------------------------------------
HINT SYSTEM UPGRADE
---------------------------------------------------------------------

Current hints:

Level 1 → pinyin  
Level 2 → translation  
Level 3 → etymology  

Problem:

Only supports comprehension.

Upgrade to include conversation support:

Level 1 → minimal answer (how to reply)
Level 2 → extended answer (add detail)
Level 3 → translation / meaning
Level 4 → etymology (optional)

Goal:

>>> HELP USER CONTINUE CONVERSATION <<<

not just understand words.

---------------------------------------------------------------------
PHASE 10.5 IMPLEMENTATION SCOPE
---------------------------------------------------------------------

DO NOT CHANGE:

• existing runtime APIs
• card system
• token system
• SRS / memory system

ADD ONLY:

1) move_type to frames
2) question_type to frames
3) option_role to options
4) oxygen_tags (light tagging)
5) skeleton definitions (new file or structure)

NO heavy refactor.

---------------------------------------------------------------------
EXPECTED OUTCOME
---------------------------------------------------------------------

After Phase 10.5:

• Conversations feel more natural
• Options feel purposeful
• Loop questions appear organically
• “你呢？” and reciprocity become structured
• Repair paths exist
• Oxygen vocabulary becomes visible and reused

Most importantly:

>>> SYSTEM BEHAVES LIKE A CONVERSATION, NOT A QUIZ <<<

---------------------------------------------------------------------
SUCCESS CRITERIA
---------------------------------------------------------------------

1) Same content produces better conversations (no content expansion required)

2) At least 3 distinct response strategies appear per question:
   - minimal
   - extend
   - reciprocate or repair

3) Loop questions occur naturally in ≥30% of exchanges

4) User can recover from confusion without breaking flow

5) Conversations feel:
   - less mechanical
   - more human
   - more interactive

---------------------------------------------------------------------
IMPORTANT DESIGN PRINCIPLE
---------------------------------------------------------------------

DO NOT hard-code dialogue.

Instead:

• define structure
• tag content
• let runtime assemble conversations dynamically

---------------------------------------------------------------------
NEXT STEP
---------------------------------------------------------------------

Architect (Cursor) should:

1) Map current frames → move_type
2) Map options → option_role
3) Identify oxygen vocabulary coverage
4) Propose minimal schema extension
5) Suggest where skeleton layer lives (no code yet)

Then return for strategist review before implementation.