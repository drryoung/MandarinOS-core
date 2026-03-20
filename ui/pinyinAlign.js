/** Greedy pinyin segmentation (toneless base syllables). Used to align compact headword pinyin to Hanzi graphemes. */
export const PINYIN_SYLLABLES_DESC = ["chuang","shuang","zhuang","chang","cheng","chong","chuai","chuan","guang","huang","jiang","jiong","kuang","liang","niang","qiang","qiong","shang","sheng","shuai","shuan","xiang","xiong","zhang","zheng","zhong","zhuai","zhuan","bang","beng","bian","biao","bing","cang","ceng","chai","chan","chao","chen","chou","chua","chui","chun","chuo","cong","cuan","dang","deng","dian","diao","ding","dong","duan","fang","feng","gang","geng","gong","guai","guan","hang","heng","hong","huai","huan","jian","jiao","jing","juan","kang","keng","kong","kuai","kuan","lang","leng","lian","liao","ling","long","luan","mang","meng","mian","miao","ming","nang","neng","nian","niao","ning","nong","nuan","pang","peng","pian","piao","ping","qian","qiao","qing","quan","rang","reng","rong","ruan","sang","seng","shai","shan","shao","shei","shen","shou","shua","shui","shun","shuo","song","suan","tang","teng","tian","tiao","ting","tong","tuan","wang","weng","xian","xiao","xing","xuan","yang","ying","yong","yuan","zang","zeng","zhai","zhan","zhao","zhei","zhen","zhou","zhua","zhui","zhun","zhuo","zong","zuan","ang","bai","ban","bao","bei","ben","bie","bin","cai","can","cao","cha","che","chi","chu","cou","cui","cun","cuo","dai","dan","dao","dei","den","dia","die","diu","dou","dui","dun","duo","fan","fei","fen","fou","gai","gan","gao","gei","gen","gou","gua","gui","gun","guo","hai","han","hao","hei","hen","hou","hua","hui","hun","huo","jia","jie","jin","jiu","jue","jun","kai","kan","kao","ken","kou","kua","kui","kun","kuo","lan","lao","lei","lia","lie","lin","liu","lou","lue","lun","luo","mai","man","mao","mei","men","mie","min","miu","mou","nai","nan","nao","nei","nen","nie","nin","niu","nou","nue","pai","pan","pao","pei","pen","pie","pin","pou","qia","qie","qin","qiu","que","qun","ran","rao","ren","rou","rui","run","ruo","sai","san","sao","sen","sha","she","shi","shu","sou","sui","sun","suo","tai","tan","tao","tei","tie","tou","tui","tun","tuo","wai","wan","wei","wen","xia","xie","xin","xiu","xue","xun","yan","yao","yin","you","yue","yun","zai","zan","zao","zei","zen","zha","zhe","zhi","zhu","zou","zui","zun","zuo","ai","an","ao","ba","bi","bo","bu","ce","ci","cu","da","de","di","du","ei","en","er","fa","fo","fu","ga","ge","gu","ha","he","hm","hu","ji","ju","ka","ke","ku","la","le","li","lu","lv","ma","me","mi","mo","mu","na","ne","ni","nu","nv","ou","pa","pi","po","pu","qi","qu","re","ri","ru","sa","se","si","su","ta","te","ti","tu","wa","wo","wu","xi","xu","ya","ye","yi","yo","yu","za","ze","zi","zu","a","e","o"];

export function pinyinStripTonesForMatch(str) {
  let out = "";
  for (const ch of str.toLowerCase()) {
    switch (ch) {
      case "ā": case "á": case "ǎ": case "à": out += "a"; break;
      case "ē": case "é": case "ě": case "è": out += "e"; break;
      case "ī": case "í": case "ǐ": case "ì": out += "i"; break;
      case "ō": case "ó": case "ǒ": case "ò": out += "o"; break;
      case "ū": case "ú": case "ǔ": case "ù": out += "u"; break;
      case "ǖ": case "ǘ": case "ǚ": case "ǜ": case "ü": out += "v"; break;
      default:
        if (ch >= "a" && ch <= "z") out += ch;
        break;
    }
  }
  return out;
}

function splitPlainPinyinToSyllables(plain) {
  const out = [];
  let i = 0;
  while (i < plain.length) {
    let found = null;
    for (const syl of PINYIN_SYLLABLES_DESC) {
      if (plain.startsWith(syl, i)) {
        found = syl;
        break;
      }
    }
    if (!found) return null;
    out.push(found);
    i += found.length;
  }
  return out;
}

function sliceTonedPinyin(raw, plainSyllables) {
  const t = raw.trim();
  const lower = t.toLowerCase();
  const fullPlain = pinyinStripTonesForMatch(lower);
  const joined = plainSyllables.join("");
  if (fullPlain !== joined) return null;
  let li = 0;
  const out = [];
  for (const ps of plainSyllables) {
    const start = li;
    let got = 0;
    while (got < ps.length && li < lower.length) {
      const ch = lower[li];
      if ((ch >= "a" && ch <= "z") || "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü".includes(ch)) got++;
      li++;
    }
    if (got !== ps.length) return null;
    out.push(t.substring(start, li));
  }
  if (li !== lower.length) return null;
  return out;
}

/**
 * Align headword pinyin to Hanzi graphemes (one reading per 字).
 * Handles spaced pinyin ("nǐ hǎo") and compact ("zěnmeyàng") via greedy syllable split.
 * @returns {string[]|null}
 */
export function splitHeadwordPinyinToGraphemes(hanzi, pinyinStr) {
  if (!hanzi || pinyinStr == null) return null;
  const graph = [...String(hanzi).trim()];
  if (graph.length === 0) return null;
  const py = String(pinyinStr).trim();
  const partsBySpace = py.split(/\s+/).filter(Boolean);
  if (partsBySpace.length === graph.length) return partsBySpace;
  if (partsBySpace.length === 1 && graph.length > 1) {
    const plain = pinyinStripTonesForMatch(py.toLowerCase());
    const syls = splitPlainPinyinToSyllables(plain);
    if (!syls || syls.length !== graph.length) return null;
    return sliceTonedPinyin(py, syls);
  }
  return null;
}
