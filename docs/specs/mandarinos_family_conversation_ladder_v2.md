
# MandarinOS Family Conversation Ladder v2

Purpose:
Provide a natural progression path for Family conversations while allowing the runtime to skip redundant questions based on known information.

---

# Level 1 — Family Structure

Goal: establish basic family facts

你家有几个人？  
How many people are in your family?

你有兄弟姐妹吗？  
Do you have siblings?

你有孩子吗？  
Do you have children?

Branch logic:

- If siblings = yes → go to Sibling branch
- If siblings = none → go to Only-Child branch

---

# Level 2 — Sibling Branch

你有哥哥还是弟弟？  
Do you have older or younger brothers?

你有姐姐还是妹妹？  
Do you have older or younger sisters?

他 / 她做什么？  
What does he / she do?

他 / 她住在哪儿？  
Where does he / she live?

---

# Level 3 — Only-Child Branch

你是独生子女吗？  
Are you an only child?

你的父母在哪儿？  
Where are your parents?

你常回家吗？  
Do you often go home?

---

# Level 4 — Marriage / Partner Branch

Conditional entry:

If children are already known:
- Skip 你结婚了吗？
- Go directly to partner questions

If children are not known:
- Ask 你结婚了吗？ first

Core questions:

你结婚了吗？  
Are you married?

你爱人做什么？  
What does your partner do?

你们住在哪儿？  
Where do you live?

你有对象吗？  
Do you have a partner / boyfriend / girlfriend?

---

# Level 5 — Children Branch

If children exist:

你的孩子多大？  
How old are your children?

他们在哪儿上学？  
Where do they study?

他们喜欢什么？  
What do they like?

---

# Level 6 — Grandparents Branch

你爷爷奶奶还在吗？  
Are your grandparents still living?

他们住在哪儿？  
Where do they live?

你常见他们吗？  
Do you see them often?

---

# Level 7 — Living Arrangement Branch

你跟父母住吗？  
Do you live with your parents?

你自己住吗？  
Do you live alone?

你跟朋友住吗？  
Do you live with friends?

---

# Level 8 — Deeper P2 Conversation

你跟谁最像？  
Who are you most like?

你更像爸爸还是妈妈？  
Are you more like your father or mother?

你家在城市还是农村？  
Is your family in the city or the countryside?

---

# Typical Natural Flow

Family structure
→ siblings / only child
→ marriage / partner
→ children
→ grandparents
→ living arrangement
→ deeper discussion

---

# Key Design Rule

Skip redundant questions.

Examples:
- If children = yes, skip 你结婚了吗？
- If siblings = none, go to only-child branch
- If partner already known, go directly to partner follow-ups
