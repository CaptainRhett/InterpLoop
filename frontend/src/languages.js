export const LANGUAGE_DIRECTIONS = [
  { value: "日→中", label: "日语 → 中文", sourceLang: "ja-JP", targetLang: "zh-CN" },
  { value: "中→日", label: "中文 → 日语", sourceLang: "zh-CN", targetLang: "ja-JP" },
  { value: "英→中", label: "英语 → 中文", sourceLang: "en-US", targetLang: "zh-CN" },
  { value: "中→英", label: "中文 → 英语", sourceLang: "zh-CN", targetLang: "en-US" },
];

export const SPOKEN_LANGUAGES = [
  { value: "ja-JP", label: "日语" },
  { value: "zh-CN", label: "中文" },
  { value: "en-US", label: "英语" },
];

const directionMap = new Map(LANGUAGE_DIRECTIONS.map((item) => [item.value, item]));

export function languagePairForDirection(direction) {
  return directionMap.get(direction) || LANGUAGE_DIRECTIONS[0];
}
