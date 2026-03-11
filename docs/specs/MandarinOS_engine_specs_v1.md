# MandarinOS Engine Specs v1

Purpose: Capture the current engine designs in a compact,
implementation-facing format.

This document reflects the current stable design direction: - spoken
Chinese - short, memorable questions - curiosity-driven conversation -
reciprocity via 你呢？ - bridges between engines

------------------------------------------------------------------------

# ENGINE: Identity

Purpose: Establish who the person is and open paths to place, family,
and study/work.

Role: Entry\
Likely next engines: Place, Family, Study/Work

## Core Questions

\[?\] 你叫什么名字？\
nǐ jiào shénme míngzi\
What is your name?

\[?\] 你呢？\
nǐ ne\
And you?

## Treasure Questions

\[T\] 你的名字是什么意思？\
nǐ de míngzi shì shénme yìsi\
What does your name mean?

\[T\] 谁给你取的名字？\
shéi gěi nǐ qǔ de míngzi\
Who gave you your name?

\[T\] 你多大？\
nǐ duō dà\
How old are you?

\[T\] 你是哪一年出生的？\
nǐ shì nǎ yì nián chūshēng de\
What year were you born?

\[T\] 属什么？\
shǔ shénme\
What is your zodiac animal?

\[T\] 你结婚了吗？\
nǐ jiéhūn le ma\
Are you married?

\[T\] 你有孩子吗？\
nǐ yǒu háizi ma\
Do you have children?

\[T\] 你做什么？\
nǐ zuò shénme\
What do you do?

## Loop Questions

\[L\] 大家一般怎么叫你？\
dàjiā yìbān zěnme jiào nǐ\
What do people usually call you?

\[L\] 这个名字是谁想的？\
zhège míngzi shì shéi xiǎng de\
Who came up with this name?

\[L\] 你的朋友怎么叫你？\
nǐ de péngyou zěnme jiào nǐ\
What do your friends call you?

\[L\] 你的家人怎么叫你？\
nǐ de jiārén zěnme jiào nǐ\
What do your family call you?

\[L\] 你喜欢你的名字吗？\
nǐ xǐhuan nǐ de míngzi ma\
Do you like your name?

\[L\] 为什么？\
wèishénme\
Why?

\[L\] 你有中文名字吗？\
nǐ yǒu Zhōngwén míngzi ma\
Do you have a Chinese name?

## Trigger Patterns

-   Name origin → family
-   Age → birth year → zodiac
-   Age / life stage → study/work
-   Marriage → children → family

## Bridges

\[B→Place\] 你是哪里人？\
Where are you from?

\[B→Place\] 你老家在哪儿？\
Where is your hometown?

\[B→Family\] 你家里有几个人？\
How many people are in your family?

\[B→Family\] 你有兄弟姐妹吗？\
Do you have siblings?

\[B→StudyWork\] 你在哪儿工作？\
Where do you work?

## Typical Paths

-   name → meaning → place
-   name origin → family
-   age → work/study
-   marriage → children → family

## Example Mini Conversation

你叫什么名字？\
What is your name?

我叫 Raymond。\
My name is Raymond.

你呢？\
And you?

## Notes

-   Identity is a strong entry engine.
-   It should include reciprocity early.
-   Questions should stay short and spoken.

------------------------------------------------------------------------

# ENGINE: Place

Purpose: Establish where someone is from or lives and expand toward
food, travel, family, and daily life.

Role: Entry + Hub\
Likely next engines: Food, Travel, Family

## Core Questions

\[?\] 你是哪里人？\
nǐ shì nǎlǐ rén\
Where are you from?

\[?\] 你老家在哪儿？\
nǐ lǎojiā zài nǎr\
Where is your hometown?

\[?\] 你住哪儿？\
nǐ zhù nǎr\
Where do you live?

## Treasure Questions

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

## Trigger Patterns

-   City answer → orientation + description + food
-   Country answer → distance from China + travel
-   Food mention → Food engine
-   Travel mention → Travel engine

## Bridges

\[B→Food\] 那儿有什么好吃的？\
What good food is there?

\[B→Travel\] 你去过北京吗？\
Have you been to Beijing?

\[B→Travel\] 你去过中国吗？\
Have you been to China?

\[B→Family\] 你家人也在那儿吗？\
Is your family there too?

## Typical Paths

-   place → orientation → food
-   place → country → travel
-   place → family location → family

## Example Mini Conversation

你是哪里人？\
Where are you from?

我是苏州人。\
I'm from Suzhou.

苏州在哪儿？\
Where is Suzhou?

在上海附近。\
Near Shanghai.

## Notes

-   Place is the main hub engine.
-   Must support both city and country answers.
-   Use spoken Chinese.

------------------------------------------------------------------------

# ENGINE: Food

Purpose: Talk about food associated with a place and expand toward
personal taste, daily eating habits, and travel.

Role: Secondary\
Likely next engines: Place, Travel

## Core Questions

\[?\] 那儿有什么好吃的？\
nàr yǒu shénme hǎochī de\
What good food is there?

\[?\] 你们那儿最有名的菜是什么？\
nǐmen nàr zuì yǒumíng de cài shì shénme\
What dish is your place most famous for?

## Treasure Questions

\[T\] 你最喜欢那里的什么菜？\
nǐ zuì xǐhuan nàlǐ de shénme cài\
What dish from there do you like most?

\[T\] 那个菜好吃吗？\
nàge cài hǎochī ma\
Is that dish tasty?

\[T\] 辣吗？\
là ma\
Is it spicy?

\[T\] 甜吗？\
tián ma\
Is it sweet?

\[T\] 贵不贵？\
guì bú guì\
Is it expensive?

\[T\] 你喜欢吃辣吗？\
nǐ xǐhuan chī là ma\
Do you like spicy food?

## Loop Questions

\[L\] 为什么？\
wèishénme\
Why?

\[L\] 你常吃吗？\
nǐ cháng chī ma\
Do you eat it often?

\[L\] 跟谁一起吃？\
gēn shéi yìqǐ chī\
Who do you eat it with?

\[L\] 什么时候吃？\
shénme shíhou chī\
When do you eat it?

\[L\] 你会做吗？\
nǐ huì zuò ma\
Can you cook it?

## Trigger Patterns

-   Place mentions local food → Food starts
-   Dish mention → taste / preference loop
-   Cooking mention → cooking sub-branch

## Bridges

\[B→Place\] 这是什么地方的菜？\
Where is this dish from?

\[B→Travel\] 你在哪儿吃过最好吃的火锅？\
Where have you eaten the best hotpot?

## Typical Paths

-   local food → favourite dish
-   dish → taste → price
-   dish → frequency → travel memory

## Example Mini Conversation

那儿有什么好吃的？\
What good food is there?

有很多火锅。\
There is a lot of hotpot.

贵不贵？\
Is it expensive?

不贵。\
Not expensive.

## Notes

-   Food should begin from place, then move to personal taste.
-   Keep adjectives simple and reusable.

------------------------------------------------------------------------

# ENGINE: Family

Purpose: Talk about family members, relationships, and connected
personas.

Role: Secondary\
Likely next engines: Place, Study/Work, Persona-linked conversations

## Core Questions

\[?\] 你家有几个人？\
nǐ jiā yǒu jǐ gè rén\
How many people are in your family?

\[?\] 你有兄弟姐妹吗？\
nǐ yǒu xiōngdì jiěmèi ma\
Do you have siblings?

\[?\] 你有孩子吗？\
nǐ yǒu háizi ma\
Do you have children?

## Treasure Questions

\[T\] 你爸爸做什么？\
nǐ bàba zuò shénme\
What does your father do?

\[T\] 你妈妈在哪儿？\
nǐ māma zài nǎr\
Where is your mother?

\[T\] 他们在哪儿？\
tāmen zài nǎr\
Where are they?

\[T\] 他们做什么？\
tāmen zuò shénme\
What do they do?

## Loop Questions

\[L\] 他们喜欢什么？\
tāmen xǐhuan shénme\
What do they like?

\[L\] 你常见他们吗？\
nǐ cháng jiàn tāmen ma\
Do you see them often?

\[L\] 为什么？\
wèishénme\
Why?

## Trigger Patterns

-   Sibling mention → study/work
-   Child mention → persona network bridge
-   Parent location → Place

## Bridges

\[B→Place\] 他们在哪儿？\
Where are they?

\[B→StudyWork\] 她做什么？\
What does she do?

\[B→Identity\] 她叫什么名字？\
What is her name?

## Typical Paths

-   family size → siblings
-   children → school / student persona
-   parent job → work

## Example Mini Conversation

你有兄弟姐妹吗？\
Do you have siblings?

我有一个妹妹。\
I have a younger sister.

她做什么？\
What does she do?

她是学生。\
She is a student.

## Notes

-   Family is highly memorable and bridges naturally to connected
    personas.
-   Keep kinship vocabulary simple at P1.

------------------------------------------------------------------------

# ENGINE: Study / Work

Purpose: Talk about what someone does, what they study, and their life
stage.

Role: Secondary\
Likely next engines: Place, Family

## Core Questions

\[?\] 你做什么？\
nǐ zuò shénme\
What do you do?

\[?\] 你学什么？\
nǐ xué shénme\
What do you study?

## Treasure Questions

\[T\] 在哪儿学？\
zài nǎr xué\
Where do you study?

\[T\] 在哪儿工作？\
zài nǎr gōngzuò\
Where do you work?

\[T\] 忙不忙？\
máng bù máng\
Are you busy?

## Loop Questions

\[L\] 为什么？\
wèishénme\
Why?

\[L\] 你喜欢吗？\
nǐ xǐhuan ma\
Do you like it?

\[L\] 什么时候毕业？\
shénme shíhou bìyè\
When will you graduate?

## Trigger Patterns

-   Student → major / city
-   Worker → workplace / place
-   Job mention → family or city follow-up

## Bridges

\[B→Place\] 在哪儿？\
Where?

\[B→Family\] 你家人也在那儿吗？\
Is your family there too?

## Typical Paths

-   student → major → city
-   worker → workplace → busy/not busy

## Example Mini Conversation

你做什么？\
What do you do?

我是学生。\
I am a student.

你学什么？\
What do you study?

我学计算机。\
I study computer science.

## Notes

-   Keep "你做什么？" as the most natural short question.
-   Student and work sub-branches should both be supported.

------------------------------------------------------------------------

# ENGINE: Travel

Purpose: Talk about places visited and create curiosity-driven story
branches.

Role: Secondary\
Likely next engines: Place, Food

## Core Questions

\[?\] 你去过中国吗？\
nǐ qùguo Zhōngguó ma\
Have you been to China?

\[?\] 你去过北京吗？\
nǐ qùguo Běijīng ma\
Have you been to Beijing?

## Treasure Questions

\[T\] 你去过哪个国家？\
nǐ qùguo nǎge guójiā\
Which country have you been to?

\[T\] 好玩吗？\
hǎowán ma\
Was it fun?

\[T\] 什么时候去的？\
shénme shíhou qù de\
When did you go?

\[T\] 跟谁一起去的？\
gēn shéi yìqǐ qù de\
Who did you go with?

## Loop Questions

\[L\] 为什么？\
wèishénme\
Why?

\[L\] 你最喜欢哪个地方？\
nǐ zuì xǐhuan nǎge dìfang\
Which place do you like most?

\[L\] 那儿有什么好吃的？\
nàr yǒu shénme hǎochī de\
What good food is there?

## Trigger Patterns

-   Country mention → place orientation
-   Positive experience → curiosity chain
-   Food mention → Food engine

## Bridges

\[B→Place\] 那个地方在哪儿？\
Where is that place?

\[B→Food\] 那儿有什么好吃的？\
What good food is there?

## Typical Paths

-   travel place → fun → food
-   travel place → time → companions

## Example Mini Conversation

你去过中国吗？\
Have you been to China?

去过。\
Yes, I have.

好玩吗？\
Was it fun?

很好玩。\
Very fun.

## Notes

-   Travel should rely on short trigger statements and follow-up
    curiosity.
-   Avoid long narrative pressure at P1.
