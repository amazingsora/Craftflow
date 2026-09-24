// CharacterTab 共用 helper／常數

import { request } from '../api/client'

export const GENRES = ['玄幻', '奇幻', '現代都市', '科幻', '古風', 'BL/GL', '輕小說', '其他']
export const STATUSES = ['構思中', '撰寫中', '修稿中', '完稿']

export async function apiFetch(path, opts = {}) {
  return request(path, opts).then((r) => r.json())
}
