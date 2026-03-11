# MandarinOS Conversation Engine

## ENGINE: Place

Purpose: Establish where someone is from or lives and expand
conversation toward food, travel, family, and daily life.

Role: Entry + Hub\
Likely next engines: Food, Travel, Family, Daily Life

------------------------------------------------------------------------

## Core Questions

\[?\] 你是哪里人？\
nǐ shì nǎlǐ rén\
Where are you from?

Alternative spoken entry:

\[?\] 你老家在哪儿？\
nǐ lǎojiā zài nǎr\
Where is your hometown?

Possible answers

我是{CITY}人\
I am from {CITY}

我是{COUNTRY}人\
I am from {COUNTRY}

------------------------------------------------------------------------

\[?\] 你住哪儿？\
nǐ zhù nǎr\
Where do you live?

Answer

我住在{CITY}。\
I live in {CITY}.

------------------------------------------------------------------------

## Treasure Questions

### Orientation

\[T\] 在哪儿？\
zài nǎr\
Where is it?

\[T\] 在北京附近吗？\
zài Běijīng fùjìn ma\
Is it near Beijing?

\[T\] 在上海附近吗？\
zài Shànghǎi fùjìn ma\
Is it near Shanghai?

\[T\] 在广州附近吗？\
zài Guǎngzhōu fùjìn ma\
Is it near Guangzhou?

\[T\] 是大城市吗？\
shì dà chéngshì ma\
Is it a big city?

\[T\] 离这儿远吗？\
lí zhèr yuǎn ma\
Is it far from here?

\[T\] 怎么去？\
zěnme qù\
How do you get there?

------------------------------------------------------------------------

### Description

\[T\] 那儿怎么样？\
nàr zěnmeyàng\
What is it like there?

\[T\] 那儿好玩吗？\
nàr hǎowán ma\
Is it fun there?

\[T\] 天气怎么样？\
tiānqì zěnmeyàng\
How is the weather?

\[T\] 你喜欢那儿吗？\
nǐ xǐhuan nàr ma\
Do you like it there?

------------------------------------------------------------------------

## Loop Questions

\[L\] 为什么？\
wèishénme\
Why?

\[L\] 那儿有什么好吃的？\
nàr yǒu shénme hǎochī de\
What good food is there?

\[L\] 那儿有什么好玩的？\
nàr yǒu shénme hǎowán de\
What fun things are there?

\[L\] 你最喜欢那儿什么？\
nǐ zuì xǐhuan nàr shénme\
What do you like most there?

\[L\] 你常去哪儿玩？\
nǐ cháng qù nǎr wán\
Where do you often go for fun?

\[L\] 你家人也在那儿吗？\
nǐ jiārén yě zài nàr ma\
Is your family there too?

\[L\] 要多久？\
yào duōjiǔ\
How long does it take?

------------------------------------------------------------------------

## Trigger Patterns

City answer → orientation + description + food discussion

Country answer → distance from China + travel discussion

Food mention → transition to Food engine

Travel mention → transition to Travel engine

------------------------------------------------------------------------

## Bridges

\[B→Food\] 那儿有什么好吃的？\
What good food is there?

\[B→Travel\] 你去过北京吗？\
Have you been to Beijing?

\[B→Travel\] 你去过中国吗？\
Have you been to China?

\[B→Family\] 你家人也在那儿吗？\
Is your family there too?

\[B→DailyLife\] 天气怎么样？\
How is the weather?

------------------------------------------------------------------------

## Example Mini Conversation

你是哪里人？\
Where are you from?

我是苏州人。\
I'm from Suzhou.

苏州在哪儿？\
Where is Suzhou?

在上海附近。\
Near Shanghai.

离这儿远吗？\
Is it far from here?

开车一个小时。\
One hour by car.

那儿有什么好吃的？\
What good food is there?

有很多面。\
There are many noodles.
