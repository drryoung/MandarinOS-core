<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as a historical report on counter-reply matrix content or behaviour.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current reply-selection code, phrase or content banks, current tests, and `docs/ANSWER_SOURCE_CONTRACT.md`.
> - **Principal caution:** Matrix entries, coverage, and behaviour may have changed since this report. Verify current reply sources and routing before relying on any reported result.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Pass 1 — Counter-Reply Coverage Matrix

Persona: **xiaoyun**  |  Server: http://localhost:8765/api/run_turn


### Persona: xiaoyun

| ID | Question | Expect | Status | counter_reply |
|---|---|---|---|---|
| A1 | 你呢？ | reply | ✓ | 我呢，我叫晓云。 |
| A2 | 我是新西兰人，你呢？ | reply | ✓ | 我呢，我是成都人。 |
| A3 | 你做什么工作？ | reply | ✓ | 我做旅行博主已经三年了。 |
| A4 | 你是做什么的 | reply | ✓ | 我是旅行博主，经常出去拍照写文章。 |
| A5 | 有意思，你呢 | reply | ✓ | 我呢，我是旅行博主，经常出去拍照写文章。 |
| A6 | 生活不错 | silent | ✓ |  |
| B1 | 你叫什么名字？ | reply | ✓ | 我呢，你可以叫我晓云。 |
| B2 | 你的名字是什么意思？ | reply | ✓ | 晓云这个名字有点特别。 |
| B3 | 谁给你取的名字？ | reply | ✓ | 是我外婆取的。 |
| B4 | 你是哪里人？ | reply | ✓ | 我是成都人，从小在那里长大。 |
| B5 | 你做什么工作？ | reply | ✓ | 我做旅行博主已经三年了。 |
| B6 | 你做这份工作多久了？ | reply | ✓ | 现在在小红书上有大概十万粉丝。 |
| B7 | 你家里有几个人？ | reply | ✓ | 我爸妈都在成都。 |
| B8 | 你有兄弟姐妹吗？ | reply | ✓ | 我是独生女。 |
| B9 | 你喜欢做什么？ | reply | ✓ | 我的相机是我最重要的东西。 |
| B10 | 你去过哪里？ | reply | ✓ | 我去过西藏。 |
| B11 | 你最喜欢吃什么？ | reply | ✓ | 我觉得云南的菜最有特色。 |
| C1 | 你是做什么的？ | reply | ✓ | 我是旅行博主，经常出去拍照写文章。 |
| C2 | 你老家在哪儿？ | reply | ✓ | 我是成都人。 |
| C3 | 你妈妈在哪儿？ | reply | ✓ | 我爸妈都在成都。 |
| C4 | 你在哪个平台发内容？ | reply | ✓ | 现在在小红书上有大概十万粉丝。 |
| C5 | 你最难忘的旅行是哪次？ | reply | ✓ | 最难忘的是在西藏看星星那一晚。 |
| C6 | 你吉他学多久了？ | reply | ✓ | 走到哪里都带着。 |
| D1 | 你喜欢什么颜色？ | deflect | ✓ (deflect) | 这个……我不太好说，不好意思！ |
| D2 | 你有没有宠物？ | deflect | ✓ (deflect) | 嗯，好问题！我得好好想想。 |
| D3 | 你多大了？ | deflect | ✓ (deflect) | 哈，年龄这种事……说多少都不准！反正我不老就是了。 |
| D4 | 你结婚了吗？ | deflect | ✓ (deflect) | 哈，这个嘛……还是个秘密！ |
| D5 | 你的电话号码是什么？ | deflect | ✓ (deflect) | 哎，这个嘛……说来话长，有空再聊！ |

### Persona: xiaoming

| ID | Question | Expect | Status | counter_reply |
|---|---|---|---|---|
| E1 | 你做什么工作？ | reply | ✓ | 我在一家做人工智能的公司工作。 |
| E2 | 你家里有几个人？ | reply | ✓ | 我有一个姐姐。 |
| E3 | 你妈妈在哪儿？ | reply | ✓ | 我有一个姐姐。 |

## Summary

31 tests, 0 gap(s).