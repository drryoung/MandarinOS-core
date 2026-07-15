
# MandarinOS Conversation Steering Engine v1

Purpose:
Control how the conversation moves between engines so dialogue feels natural rather than scripted.

Core idea:
Conversation should move toward the most interesting information rather than follow a fixed lesson order.

--------------------------------------------------

CORE PRINCIPLE

Conversation flow:

New information
→ curiosity
→ follow-up
→ new topic opportunity
→ bridge to another engine

--------------------------------------------------

TRIGGER TYPES

Location signals
Example: 我在上海工作 (I work in Shanghai)
→ Trigger Place engine

Family signals
Example: 我有两个孩子 (I have two children)
→ Trigger Family engine

Work signals
Example: 我在银行工作 (I work in a bank)
→ Trigger Study/Work engine

Food signals
Example: 我是四川人 (I am from Sichuan)
→ Trigger Food engine

Travel signals
Example: 我去过日本 (I have been to Japan)
→ Trigger Travel engine

Opportunity signals
Example: 工作压力很大 (Work pressure is high)
→ Trigger Entrepreneurship branch

--------------------------------------------------

STEERING LOOP

User answer
↓
Extract signals
↓
Evaluate curiosity triggers
↓
Select next engine
↓
Ask next question

--------------------------------------------------

PRIORITY RULE

Choose the most interesting branch:

New information
→ Personal information
→ Emotional signals
→ Curiosity opportunities
→ Neutral questions

--------------------------------------------------

EXAMPLE FLOW

Identity:
你叫什么名字？

User:
我叫李明，我在深圳工作

Detected signal:
Location → Shenzhen

Next engine:
Place

Next question:
深圳怎么样？
