
# MandarinOS Family Engine Memory Rules v1

Purpose:
Define how the runtime should use known family information to guide the Family engine naturally.

The goal is to avoid redundant questions and activate the most relevant branch automatically.

---

# 1. Core Family Memory Fields

Recommended fields:

- family_size
- siblings_status
- sibling_type
- only_child
- parents_location
- parents_job
- married_status
- partner_exists
- partner_job
- partner_hometown
- children_status
- children_count
- children_age
- children_school
- grandparents_status
- grandparents_location
- living_arrangement

---

# 2. Basic Runtime Rule

Known memory should change question selection.

The Family engine should not behave like a fixed checklist.
It should behave like a conditional branch system.

---

# 3. Siblings Rules

If:
siblings_status = yes

Then:
- activate Sibling branch
- ask about older/younger sibling
- ask sibling work / location

If:
siblings_status = none

Then:
- skip sibling-detail questions
- activate Only-Child branch

Example:
If learner says:
我没有兄弟姐妹。
I don’t have siblings.

Store:
siblings_status = none
only_child = probable

Then ask:
你是独生子女吗？
Are you an only child?

---

# 4. Marriage / Partner Rules

If:
children_status = yes

Then:
- skip 你结婚了吗？
- assume partner branch is likely relevant
- ask partner question directly if natural

Example:
你爱人做什么？
What does your partner do?

If:
partner_exists = yes

Then:
- skip 你有对象吗？
- skip 你结婚了吗？ if already known
- ask follow-up:
  - 你爱人做什么？
  - 你们住在哪儿？
  - 你爱人是哪儿人？ (P2)

If:
married_status = no
and partner_exists = unknown

Then:
- 你有对象吗？
Do you have a partner?

---

# 5. Children Rules

If:
children_status = yes

Then activate Children branch:
- 你的孩子多大？
- 他们在哪儿上学？
- 他们喜欢什么？

If:
children_status = no

Then skip children questions.

If:
children_count known

Then ask a more specific follow-up rather than re-asking existence.

---

# 6. Parents Rules

If:
parents_location known

Then do not re-ask:
你的父母在哪儿？

Instead ask:
- 你常回家吗？
- 他们住得远吗？
- 你多久回一次家？

If:
parents_job known

Then ask:
- 他们忙吗？
- 他们退休了吗？ (if age-appropriate)

---

# 7. Grandparents Rules

If:
grandparents_status = yes

Then activate Grandparent branch:
- 他们住在哪儿？
- 你常见他们吗？

If:
grandparents_status = none / no longer living

Then skip these questions unless context makes it meaningful.

---

# 8. Living Arrangement Rules

If:
living_arrangement known = with parents

Then skip:
你跟父母住吗？

And ask follow-ups like:
- 你喜欢跟父母住吗？
- 他们住得远吗？ (if not together, skip)

If:
living_arrangement known = alone

Then ask:
- 你喜欢自己住吗？
- 你多久回家一次？

If:
living_arrangement known = with friends

Then this may bridge later to social / place discussions.

---

# 9. Priority Rule

When multiple branches are possible, prefer this order:

1. missing high-value family anchor
2. obvious branch activated by recent answer
3. non-redundant follow-up
4. bridge to next engine

This keeps the conversation feeling natural.

---

# 10. Example Conditional Flows

Example A:
Learner says:
我有两个孩子。
I have two children.

Store:
children_status = yes
children_count = 2

Runtime should:
- skip 你结婚了吗？
- ask child detail or partner detail

Possible next:
你的孩子多大？
How old are your children?

or:
你爱人做什么？
What does your partner do?

---

Example B:
Learner says:
我没有兄弟姐妹。
I don’t have siblings.

Store:
siblings_status = none

Runtime should:
- skip sibling-detail questions
- ask:
你是独生子女吗？
Are you an only child?

---

Example C:
Learner says:
我跟父母住。
I live with my parents.

Store:
living_arrangement = with_parents

Runtime should:
- not re-ask living arrangement
- ask:
你喜欢跟父母住吗？
Do you like living with your parents?

---

# 11. Key Design Principle

Family memory should work like intelligent branch control.

The system should sound like:
“I heard what you said, so I’ll ask the next natural question.”

Not like:
“I’m following a checklist.”

---

# 12. Implementation Summary

The Family engine should:
- capture family anchors
- check them before choosing next question
- skip redundant questions
- activate sibling / only-child / partner / children / grandparents branches intelligently

This is enough to make the Family conversation feel much smarter even with simple runtime logic.
