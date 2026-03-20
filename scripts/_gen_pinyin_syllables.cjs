const fs = require("fs");
const path = require("path");
const raw = `a ai an ang ao ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu cai can cang cao ce ceng cha chai chan chang chao che chen cheng chi chong chou chu chua chuai chuan chuang chui chun chuo ci cong cou cu cuan cui cun cuo da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan dui dun duo e ei en er fa fan fang fei fen feng fo fou fu ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo ha hai han hang hao he hei hen heng hm hong hou hu hua huai huan huang hui hun huo ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun ka kai kan kang kao ke ken keng kong kou ku kua kuai kuan kuang kui kun kuo la lan lang lao le lei leng li lia lian liang liao lie lin ling liu long lou lu luan lue lun luo lv ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu nong nou nu nuan nue nv o ou pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun ran rang rao re ren reng ri rong rou ru ruan rui run ruo sa sai san sang sao se sen seng sha shai shan shang shao she shei shen sheng shi shou shu shua shuai shuan shuang shui shun shuo si song sou su suan sui sun suo ta tai tan tang tao te tei teng ti tian tiao tie ting tong tou tu tuan tui tun tuo wa wai wan wang wei wen weng wo wu xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo`;
const s = raw.split(/\s+/);
s.sort((a, b) => b.length - a.length || a.localeCompare(b));
const out = path.join(__dirname, "..", "ui", "pinyinAlign.js");
const body = `/** Greedy pinyin segmentation (toneless base syllables). Used to align compact headword pinyin to Hanzi graphemes. */
export const PINYIN_SYLLABLES_DESC = ${JSON.stringify(s)};

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
  const partsBySpace = py.split(/\\s+/).filter(Boolean);
  if (partsBySpace.length === graph.length) return partsBySpace;
  if (partsBySpace.length === 1 && graph.length > 1) {
    const plain = pinyinStripTonesForMatch(py.toLowerCase());
    const syls = splitPlainPinyinToSyllables(plain);
    if (!syls || syls.length !== graph.length) return null;
    return sliceTonedPinyin(py, syls);
  }
  return null;
}
`;
fs.writeFileSync(out, body, "utf8");
console.log("wrote", out, "syllables", s.length);
