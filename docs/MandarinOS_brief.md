1. **Product intent**



I am redesigning the app from a character-learning app into a conversation-first Mandarin operating system.

The core unit of learning is now the word (not the character), and the goal is real-world conversational ability through structured conversation engines, spaced repetition, and visual-semantic reinforcement using radicals and handwriting.



**2. The new learning model**



The app now follows a layered language acquisition model:



Words → Sentence Frames → Conversation Engines → Real Conversations → Daily Life



Words are the unit of utility.

Frames are the unit of fluency.

Conversation engines are recursive social loops.

Characters and radicals are visual reinforcement, not the primary unit.



**3. Phase system (capability-based, not level-based)**



This is no longer “levels”.



The app is now organised into capability phases:



Phase 1 — Survival Conversation

Phase 2 — Daily Life \& Social Independence

Phase 3 — Social \& Work Fluency (future)



Each phase has:



* a word spine
* sentence frames
* conversation engines
* diagnostics
* spaced repetition schedule



Progression is based on conversational capability, not lesson completion.



**4. Conversation engine model (core innovation)**



This is the heart of your product.



The app uses six permanent conversation engines:



* Identity
* Place
* Family
* Work
* Hobby
* Travel



These are recursive topic loops that create natural repetition and real conversation.

They never disappear — they only deepen across phases.



**5. Sentence frame system (fluency engine)**



This replaces static sentences.



The app no longer uses fixed sentences.

It uses recombinable sentence frames with slots.



Example:

* 你周末有什么计划？
* 我打算{ACTION}



Frames are linked to words so every word is learned in real usage.



**6. Word-centric architecture**



This is a big change.



The primary learning object is now the word (mostly compound words), not the character.

Characters are attached to words as visual-semantic support.



Each word includes:

* frequency
* characters
* radicals/components
* handwriting support
* linked frames
* SRS scheduling



**7. Diagnostic model (real-world tasks)**



this is not a quiz system.



The app now uses task-based diagnostics:

* introduce yourself
* plan a weekend
* tell a short story
* express an opinion
* solve a simple problem



Placement and progression are based on real conversational performance.



**8) Spaced repetition engine (memory layer)**



this is now systematic.



The app uses an SM-2 spaced repetition engine (Anki-style) with:

* learning steps
* lapse handling
* word+frame bundles
* 10-minute session policy
* backlog protection



Characters and radicals are scheduled only when confusion is detected.



**9) Visual language system (differentiation - most functionality already exists)**



Chinese is treated as a visual-semantic language.

Radicals and components are used to explain meaning.

Handwriting is used to encode memory.

Characters are grouped into semantic families.



This solves pinyin saturation and homophone overload.



**10) Data-driven content packs**



Content is now loaded as structured JSON packs:

* words
* frames
* fillers (names, cities, jobs, hobbies)
* engines
* diagnostics
* SRS config

The app dynamically generates conversations from these packs.



Core Pack



* pack\_meta.json
* content\_manifest.json
* import\_order.json
* import\_validation\_rules.json
* runtime\_indexes.json
* id\_map.json (optional)



Learning System



* srs\_config.json (SM-2 + 10-minute sessions)
* P1 + P2 engines
* P1 + P2 frames
* P1 + P2 fillers
* P1 + P2 diagnostics
* P1 + P2 word spines



Visual Language Layer



* radicals\_core.json
* characters\_1200.json
* word\_character\_links.json



MandarinOS\_Content/

│

├── content\_manifest.json

├── srs\_config.json

├── id\_map.json              (optional)

│

├── p1\_words.json

├── p1\_frames.json

├── p1\_fillers.json

├── p1\_engines.json

├── diagnostic\_p1.json

│

├── p2\_words.json

├── p2\_frames.json

├── p2\_fillers.json

├── p2\_engines.json

├── diagnostic\_p2.json

│

├── characters\_1200.json

└── radicals\_core.json



* content\_manifest.json

1. p1\_words.json
2. p1\_frames.json
3. p1\_fillers.json
4. p1\_engines.json
5. p2\_words.json
6. p2\_frames.json
7. p2\_fillers.json
8. p2\_engines.json
9. diagnostic\_p1.json
10. diagnostic\_p2.json
11. srs\_config.json
12. sm2\_reference\_pseudocode.txt
13. characters\_1200.json (your existing dataset)
14. radicals\_core.json (your 25 radicals + 25 base components list)



