import React, { useEffect, useMemo, useState } from "react";

const NL = String.fromCharCode(10);

const IconBase = ({ className = "", children }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    {children}
  </svg>
);

const Search = (props) => (
  <IconBase {...props}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </IconBase>
);

const Database = (props) => (
  <IconBase {...props}>
    <ellipse cx="12" cy="5" rx="8" ry="3" />
    <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
    <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
  </IconBase>
);

const GitBranch = (props) => (
  <IconBase {...props}>
    <circle cx="6" cy="6" r="3" />
    <circle cx="18" cy="18" r="3" />
    <circle cx="6" cy="18" r="3" />
    <path d="M6 9v6" />
    <path d="M9 6h3a6 6 0 0 1 6 6v3" />
  </IconBase>
);

const MousePointer2 = (props) => (
  <IconBase {...props}>
    <path d="M4 3l7.5 17 2.2-7.2 7.3-2.3L4 3z" />
  </IconBase>
);

const RotateCcw = (props) => (
  <IconBase {...props}>
    <path d="M3 12a9 9 0 1 0 3-6.7" />
    <path d="M3 4v6h6" />
  </IconBase>
);

const Layers = (props) => (
  <IconBase {...props}>
    <path d="M12 3l9 5-9 5-9-5 9-5z" />
    <path d="M3 12l9 5 9-5" />
    <path d="M3 17l9 5 9-5" />
  </IconBase>
);

const AlertTriangle = (props) => (
  <IconBase {...props}>
    <path d="M10.3 4.3 2.8 17.2A2 2 0 0 0 4.5 20h15a2 2 0 0 0 1.7-2.8L13.7 4.3a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </IconBase>
);

const CodeIcon = (props) => (
  <IconBase {...props}>
    <path d="M8 9 4 12l4 3" />
    <path d="m16 9 4 3-4 3" />
    <path d="m14 5-4 14" />
  </IconBase>
);

const DEFAULT_SQL = `with order_90 as (
  select order_date, user_id, count(order_no) as order_nos_90, sum(room_night) as room_nights_90
  from default.mdw_order_v3_international
  where dt = '20260414'
  group by 1, 2
),
no_user as (
  select distinct user_id no_user_id
  from order_90
  where room_nights_90 >= 15
),
ab_rule as (
  select ab_exp_id, ab_version, ab_rule_version, device_id as ab_exp_value
  from default.ods_abtest_rule_info rule
  join default.ods_abtest_sdk_log_endtime_hotel ab
    on ab.expid = rule.ab_exp_id
   and ab.version = rule.ab_version
   and ab.ruleversion = rule.ab_rule_version
  group by 1, 2, 3, 4
),
user_type as (
  select user_id, min(order_date) as min_order_date
  from default.mdw_order_v3_international
  where dt = '20260414'
  group by 1
),
uv as (
  select dt,
         t.ab_version,
         t.ab_rule_version,
         a.country_name as mdd,
         case when dt > b.min_order_date then '老客' else '新客' end as user_type,
         a.user_id,
         a.user_name,
         if(no_user_id is null,'正常用户','大单用户') as is_big_order_user,
         sum(search_pv) search_pv,
         sum(detail_pv) detail_pv,
         sum(booking_pv) booking_pv,
         sum(order_pv) order_pv
  from ihotel_default.mdw_user_app_log_sdbo_di_v1 a
  left join temp.temp_yiquny_zhang_ihotel_area_region_forever e on a.country_name = e.country_name
  left join user_type b on a.user_id = b.user_id
  left join no_user on a.user_id = no_user.no_user_id
  right join ab_rule t on t.ab_exp_value = a.orig_device_id
  where dt = '2026-04-14'
  group by 1,2,3,4,5,6,7,8
),
q_uv_info as (
  select dt, ab_version, ab_rule_version, is_big_order_user, count(user_id) uv
  from uv
  where is_big_order_user = '正常用户' and user_type = '新客'
  group by 1,2,3,4
),
q_order_app as (
  select order_date,
         t.ab_version,
         t.ab_rule_version,
         a.country_name as mdd,
         case when order_date = b.min_order_date then '新客' else '老客' end as user_type,
         a.user_id,
         init_gmv,
         order_no,
         room_night,
         init_commission_after as final_commission_after,
         init_commission_after_new as qyj,
         0 as zbj,
         0 as xyb,
         0 as qb,
         coupon_substract_summary,
         if(no_user_id is null,'正常用户','大单用户') is_big_order_user
  from default.mdw_order_v3_international a
  left join user_type b on a.user_id = b.user_id
  left join temp.temp_yiquny_zhang_ihotel_area_region_forever e on a.country_name = e.country_name
  left join no_user on a.user_id = no_user.no_user_id
  right join ab_rule t on t.ab_exp_value = a.user_info['orig_device_id']
  where dt = '20260414'
),
order_info_app as (
  select order_date,
         ab_version,
         ab_rule_version,
         sum(final_commission_after) as q_commission_app,
         sum(qyj) + sum(zbj) + sum(xyb) + sum(qb) as q_commission_c_view_app,
         sum(init_gmv) as q_gmv_app,
         sum(coupon_substract_summary) as q_coupon_amount_app,
         count(distinct order_no) as q_order_cnt_app,
         count(distinct user_id) as q_order_user_cnt_app,
         sum(room_night) as q_room_night_app
  from q_order_app
  where is_big_order_user = '正常用户' and user_type = '新客'
  group by 1,2,3
),
q_data_info as (
  select t1.dt,
         t1.ab_version,
         t1.ab_rule_version,
         t1.uv,
         t4.q_room_night_app,
         t4.q_order_cnt_app,
         t4.q_order_user_cnt_app,
         t4.q_gmv_app,
         t4.q_commission_app,
         t4.q_coupon_amount_app
  from q_uv_info t1
  left join order_info_app t4 on t1.dt = t4.order_date
                             and t1.ab_version = t4.ab_version
                             and t1.ab_rule_version = t4.ab_rule_version
),
qc_sdbo as (
  select a.dt,
         a.ab_version,
         a.ab_rule_version,
         count(distinct case when search_pv > 0 then a.user_id else null end) s_all_UV,
         count(distinct case when b.user_id is not null then order_no else null end) o_ds_order
  from uv a
  left join q_order_app b on a.dt = b.order_date
                         and a.user_id = b.user_id
                         and a.mdd = b.mdd
                         and a.ab_version = b.ab_version
                         and a.ab_rule_version = b.ab_rule_version
  where a.user_type = '新客'
  group by 1,2,3
),
q_app_order as (
  select order_date,
         count(distinct order_no) order_no_q
  from mdw_order_v3_international a
  left join user_type b on a.user_id = b.user_id
  group by 1
)
select q_commission_app / uv as revenue_per_uv,
       uv,
       s_all_UV,
       o_ds_order,
       q_gmv_app,
       q_commission_app,
       q_room_night_app,
       q_order_cnt_app,
       order_no_q
from q_data_info t1
left join qc_sdbo t3 on t1.dt = t3.dt
                       and t1.ab_version = t3.ab_version
                       and t1.ab_rule_version = t3.ab_rule_version
left join q_app_order t4 on t4.order_date = t1.dt;`;

function isSpace(ch) {
  if (!ch) return true;
  const c = ch.charCodeAt(0);
  return c === 32 || c === 10 || c === 13 || c === 9;
}

function isNameStart(ch) {
  if (!ch) return false;
  const c = ch.charCodeAt(0);
  return ch === "_" || (c >= 65 && c <= 90) || (c >= 97 && c <= 122);
}

function isNamePart(ch) {
  if (!ch) return false;
  const c = ch.charCodeAt(0);
  return isNameStart(ch) || (c >= 48 && c <= 57) || ch === "$";
}

function isTablePart(ch) {
  return isNamePart(ch) || ch === ".";
}

function cleanSpaces(str) {
  let out = "";
  let lastSpace = false;
  for (const ch of str) {
    if (isSpace(ch)) {
      if (!lastSpace) out += " ";
      lastSpace = true;
    } else {
      out += ch;
      lastSpace = false;
    }
  }
  return out.trim();
}

function lower(str) {
  return String(str || "").toLowerCase();
}

function isBoundary(ch) {
  return !ch || !(isNamePart(ch) || ch === ".");
}

function containsWord(text, word) {
  const t = lower(text);
  const w = lower(word);
  let idx = t.indexOf(w);
  while (idx >= 0) {
    if (isBoundary(t[idx - 1]) && isBoundary(t[idx + w.length])) return true;
    idx = t.indexOf(w, idx + 1);
  }
  return false;
}

function startsWithWord(text, pos, word) {
  const part = lower(text.slice(pos, pos + word.length));
  return part === lower(word) && isBoundary(text[pos - 1]) && isBoundary(text[pos + word.length]);
}

function indexOfWord(text, word) {
  const t = lower(text);
  const w = lower(word);
  let idx = t.indexOf(w);
  while (idx >= 0) {
    if (isBoundary(t[idx - 1]) && isBoundary(t[idx + w.length])) return idx;
    idx = t.indexOf(w, idx + 1);
  }
  return -1;
}

function stripComments(sql) {
  let out = "";
  let i = 0;
  while (i < sql.length) {
    const ch = sql[i];
    const next = sql[i + 1];
    if (ch === "-" && next === "-") {
      while (i < sql.length && sql.charCodeAt(i) !== 10) i += 1;
      out += " ";
      continue;
    }
    if (ch === "/" && next === "*") {
      i += 2;
      while (i < sql.length && !(sql[i] === "*" && sql[i + 1] === "/")) i += 1;
      i += 2;
      out += " ";
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

function skipSpaces(sql, pos) {
  let i = pos;
  while (i < sql.length && isSpace(sql[i])) i += 1;
  return i;
}

function readName(sql, pos, allowDot = false) {
  let i = skipSpaces(sql, pos);
  if (!isNameStart(sql[i])) return null;
  let start = i;
  i += 1;
  while (i < sql.length && (allowDot ? isTablePart(sql[i]) : isNamePart(sql[i]))) i += 1;
  return { value: sql.slice(start, i), end: i };
}

function isQuoteChar(ch) {
  const c = ch ? ch.charCodeAt(0) : 0;
  return c === 39 || c === 34 || c === 96;
}

function skipQuoted(sql, pos) {
  const quote = sql[pos];
  let i = pos + 1;
  while (i < sql.length) {
    if (sql[i] === quote) {
      if (quote === "'" && sql[i + 1] === "'") {
        i += 2;
        continue;
      }
      return i + 1;
    }
    i += 1;
  }
  return sql.length;
}

function skipLineComment(sql, pos) {
  let i = pos + 2;
  while (i < sql.length && sql.charCodeAt(i) !== 10) i += 1;
  return i;
}

function skipBlockComment(sql, pos) {
  let i = pos + 2;
  while (i < sql.length && !(sql[i] === "*" && sql[i + 1] === "/")) i += 1;
  return Math.min(sql.length, i + 2);
}

function findMatchingParen(sql, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < sql.length; i += 1) {
    const ch = sql[i];
    const next = sql[i + 1];
    if (isQuoteChar(ch)) {
      i = skipQuoted(sql, i) - 1;
      continue;
    }
    if (ch === "-" && next === "-") {
      i = skipLineComment(sql, i) - 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      i = skipBlockComment(sql, i) - 1;
      continue;
    }
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (depth === 0) return i;
  }
  return -1;
}

function parseCtes(sql) {
  const withIdx = indexOfWord(sql, "with");
  if (withIdx < 0) {
    return { ctes: [], finalSql: sql.trim(), warnings: ["未识别到 WITH 子句，仅生成 final_select 节点。"] };
  }
  let pos = withIdx + 4;
  const ctes = [];
  const warnings = [];
  while (pos < sql.length) {
    pos = skipSpaces(sql, pos);
    if (sql[pos] === ",") pos = skipSpaces(sql, pos + 1);
    const nameToken = readName(sql, pos, false);
    if (!nameToken) break;
    const name = nameToken.value;
    pos = skipSpaces(sql, nameToken.end);
    if (sql[pos] === "(") {
      const columnListCloseIdx = findMatchingParen(sql, pos);
      if (columnListCloseIdx < 0) throw new Error(`CTE ${name} 的列名列表括号未闭合。`);
      pos = skipSpaces(sql, columnListCloseIdx + 1);
    }
    if (!startsWithWord(sql, pos, "as")) {
      warnings.push(`在 ${name} 附近未识别到 AS (...)，CTE 解析提前停止。`);
      break;
    }
    pos = skipSpaces(sql, pos + 2);
    if (sql[pos] !== "(") {
      warnings.push(`CTE ${name} 的 AS 后面不是左括号。`);
      break;
    }
    const closeIdx = findMatchingParen(sql, pos);
    if (closeIdx < 0) throw new Error(`CTE ${name} 的括号未闭合。`);
    const body = sql.slice(pos + 1, closeIdx).trim();
    const fullSql = `${name} as (${NL}${body}${NL})`;
    ctes.push({ name, body, fullSql });
    pos = skipSpaces(sql, closeIdx + 1);
    if (sql[pos] !== ",") break;
  }
  return { ctes, finalSql: sql.slice(pos).trim(), warnings };
}

function pushUnique(list, value) {
  if (value && !list.includes(value)) list.push(value);
}

function readQuotedIdentifier(sql, pos) {
  const quote = sql[pos];
  if (!isQuoteChar(quote)) return null;
  const end = skipQuoted(sql, pos);
  const value = sql.slice(pos + 1, Math.max(pos + 1, end - 1));
  return { value, end };
}

function readRelationName(sql, pos) {
  let p = skipSpaces(sql, pos);
  const quoted = readQuotedIdentifier(sql, p);
  if (quoted) return quoted;
  return readName(sql, p, true);
}

function scanRelations(sql, names, depth = 0) {
  let i = 0;
  while (i < sql.length) {
    const ch = sql[i];
    const next = sql[i + 1];

    if (isQuoteChar(ch)) {
      i = skipQuoted(sql, i);
      continue;
    }
    if (ch === "-" && next === "-") {
      i = skipLineComment(sql, i);
      continue;
    }
    if (ch === "/" && next === "*") {
      i = skipBlockComment(sql, i);
      continue;
    }

    const token = readName(sql, i, false);
    if (!token) {
      i += 1;
      continue;
    }

    const word = lower(token.value);
    if (word === "from" || word === "join") {
      let p = skipSpaces(sql, token.end);

      if (sql[p] === "(") {
        const closeIdx = findMatchingParen(sql, p);
        if (closeIdx > p) {
          const innerSql = sql.slice(p + 1, closeIdx);
          scanRelations(innerSql, names, depth + 1);
          i = closeIdx + 1;
          continue;
        }
        i = p + 1;
        continue;
      }

      const relationToken = readRelationName(sql, p);
      if (relationToken) {
        const relationName = relationToken.value;
        const relationLower = lower(relationName);
        if (!["select", "with", "lateral", "values", "unnest"].includes(relationLower)) {
          pushUnique(names, relationName);
        }
        i = relationToken.end;
        continue;
      }
    }

    i = token.end;
  }
}

function extractRelationNames(sql) {
  const names = [];
  scanRelations(sql, names, 0);
  return names;
}

function extractBaseTables(sql, cteNameSet) {
  return extractRelationNames(sql).filter((name) => !cteNameSet.has(lower(name)));
}

function extractDependencies(sql, cteNameMap, selfName) {
  const relations = extractRelationNames(sql).map((name) => lower(name));
  const deps = [];
  Object.entries(cteNameMap).forEach(([lowerName, originalName]) => {
    if (lowerName !== lower(selfName) && relations.includes(lowerName)) {
      deps.push(originalName);
    }
  });
  return deps;
}

function findTopLevelWord(sql, word, start = 0) {
  let depth = 0;
  let squareDepth = 0;
  for (let i = start; i < sql.length; i += 1) {
    const ch = sql[i];
    const next = sql[i + 1];
    if (isQuoteChar(ch)) {
      i = skipQuoted(sql, i) - 1;
      continue;
    }
    if (ch === "-" && next === "-") {
      i = skipLineComment(sql, i) - 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      i = skipBlockComment(sql, i) - 1;
      continue;
    }
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (ch === "[") squareDepth += 1;
    if (ch === "]") squareDepth -= 1;
    if (depth === 0 && squareDepth === 0 && startsWithWord(sql, i, word)) return i;
  }
  return -1;
}

function findTopLevelGroupBy(sql, start = 0) {
  let groupIdx = findTopLevelWord(sql, "group", start);
  while (groupIdx >= 0) {
    const byPos = skipSpaces(sql, groupIdx + 5);
    if (startsWithWord(sql, byPos, "by")) {
      return { groupIdx, afterBy: byPos + 2 };
    }
    groupIdx = findTopLevelWord(sql, "group", groupIdx + 5);
  }
  return null;
}

function findTopLevelClauseEnd(sql, start) {
  const stops = ["where", "group", "having", "order", "limit", "union", "qualify", "distribute", "sort", "cluster"];
  let end = sql.length;
  stops.forEach((word) => {
    const idx = findTopLevelWord(sql, word, start);
    if (idx >= 0 && idx < end) end = idx;
  });
  return end;
}

function splitTopLevelComma(text) {
  const parts = [];
  let start = 0;
  let depth = 0;
  let squareDepth = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (isQuoteChar(ch)) {
      i = skipQuoted(text, i) - 1;
      continue;
    }
    if (ch === "-" && next === "-") {
      i = skipLineComment(text, i) - 1;
      continue;
    }
    if (ch === "/" && next === "*") {
      i = skipBlockComment(text, i) - 1;
      continue;
    }
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (ch === "[") squareDepth += 1;
    if (ch === "]") squareDepth -= 1;
    if (ch === "," && depth === 0 && squareDepth === 0) {
      const part = text.slice(start, i).trim();
      if (part) parts.push(part);
      start = i + 1;
    }
  }
  const last = text.slice(start).trim();
  if (last) parts.push(last);
  return parts;
}

function stripDistinctPrefix(selectPart) {
  let text = selectPart.trim();
  if (startsWithWord(text, 0, "distinct")) text = text.slice(8).trim();
  return text;
}

function findTopLevelAs(item) {
  let idx = findTopLevelWord(item, "as", 0);
  let latest = -1;
  while (idx >= 0) {
    latest = idx;
    idx = findTopLevelWord(item, "as", idx + 2);
  }
  return latest;
}

function parseSelectItem(raw, index) {
  const text = cleanSpaces(raw);
  const asIdx = findTopLevelAs(text);
  if (asIdx >= 0) {
    const expr = text.slice(0, asIdx).trim();
    const alias = text.slice(asIdx + 2).trim();
    return { index, raw: text, expression: expr || text, alias, display: alias ? `${expr} as ${alias}` : expr };
  }
  let end = text.length;
  while (end > 0 && isSpace(text[end - 1])) end -= 1;
  let start = end - 1;
  while (start >= 0 && isNamePart(text[start])) start -= 1;
  const alias = text.slice(start + 1, end);
  const beforeAlias = text[start];
  const expr = text.slice(0, start + 1).trim();
  if (alias && expr && isSpace(beforeAlias) && !startsWithWord(text, 0, "case")) {
    return { index, raw: text, expression: expr, alias, display: `${expr} as ${alias}` };
  }
  if (alias && expr && isSpace(beforeAlias) && startsWithWord(text, 0, "case")) {
    return { index, raw: text, expression: expr, alias, display: `${expr} as ${alias}` };
  }
  return { index, raw: text, expression: text, alias: "", display: text };
}

function extractSelectItems(sql) {
  const cleaned = stripComments(sql);
  const selectIdx = findTopLevelWord(cleaned, "select", 0);
  if (selectIdx < 0) return [];
  const fromIdx = findTopLevelWord(cleaned, "from", selectIdx + 6);
  const end = fromIdx >= 0 ? fromIdx : findTopLevelClauseEnd(cleaned, selectIdx + 6);
  const selectPart = stripDistinctPrefix(cleaned.slice(selectIdx + 6, end));
  return splitTopLevelComma(selectPart).map((item, idx) => parseSelectItem(item, idx + 1));
}

function extractGroupByItems(sql) {
  const cleaned = stripComments(sql);
  const group = findTopLevelGroupBy(cleaned, 0);
  if (!group) return [];
  let end = cleaned.length;
  ["having", "order", "limit", "union", "qualify", "distribute", "sort", "cluster"].forEach((word) => {
    const idx = findTopLevelWord(cleaned, word, group.afterBy);
    if (idx >= 0 && idx < end) end = idx;
  });
  return splitTopLevelComma(cleaned.slice(group.afterBy, end)).map((item) => cleanSpaces(item).replace(";", ""));
}

function isIntegerText(text) {
  const s = cleanSpaces(text);
  if (!s) return false;
  for (const ch of s) {
    const c = ch.charCodeAt(0);
    if (c < 48 || c > 57) return false;
  }
  return true;
}

function resolveGroupByItems(sql) {
  const selectItems = extractSelectItems(sql);
  const groupItems = extractGroupByItems(sql);
  return groupItems.map((item) => {
    if (isIntegerText(item)) {
      const idx = Number(item);
      const selectItem = selectItems[idx - 1];
      if (selectItem) {
        return {
          raw: item,
          position: idx,
          isOrdinal: true,
          resolved: selectItem.expression,
          alias: selectItem.alias,
          display: selectItem.alias ? `${item} -> ${selectItem.expression} as ${selectItem.alias}` : `${item} -> ${selectItem.expression}`
        };
      }
      return { raw: item, position: idx, isOrdinal: true, resolved: `无法解析第${idx}列`, alias: "", display: `${item} -> 无法解析第${idx}列` };
    }
    return { raw: item, position: null, isOrdinal: false, resolved: item, alias: "", display: item };
  });
}

function inferGrain(sql) {
  const resolved = resolveGroupByItems(sql);
  if (resolved.length) {
    const text = resolved.map((item) => item.display).join(" + ");
    return text.length > 120 ? `group by ${text.slice(0, 120)}...` : `group by ${text}`;
  }
  const cleaned = stripComments(sql);
  if (lower(cleaned).includes("select distinct")) {
    const items = extractSelectItems(sql).map((item) => item.display).join(" + ");
    return items ? `distinct ${items}` : "distinct 去重粒度";
  }
  return "未显式聚合 / 明细或派生粒度";
}

function layoutGraph(rawNodes, edges) {
  const ids = rawNodes.map((n) => n.id);
  const incoming = Object.fromEntries(ids.map((id) => [id, []]));
  const outgoing = Object.fromEntries(ids.map((id) => [id, []]));
  edges.forEach((e) => {
    if (incoming[e.to]) incoming[e.to].push(e.from);
    if (outgoing[e.from]) outgoing[e.from].push(e.to);
  });
  const level = {};
  const visit = (id, stack = new Set()) => {
    if (level[id] !== undefined) return level[id];
    if (stack.has(id)) return 0;
    stack.add(id);
    const parents = incoming[id] || [];
    level[id] = parents.length ? Math.max(...parents.map((p) => visit(p, stack))) + 1 : 0;
    stack.delete(id);
    return level[id];
  };
  ids.forEach((id) => visit(id));
  const groups = {};
  rawNodes.forEach((n) => {
    const l = level[n.id] || 0;
    if (!groups[l]) groups[l] = [];
    groups[l].push(n);
  });
  const maxLevel = Math.max(1, ...Object.keys(groups).map(Number));
  const width = 1420;
  const height = 680;
  const xGap = Math.max(180, (width - 180) / Math.max(maxLevel, 1));
  const positioned = [];
  Object.entries(groups).forEach(([levelKey, arr]) => {
    const l = Number(levelKey);
    const yGap = height / (arr.length + 1);
    arr.forEach((n, idx) => {
      positioned.push({
        ...n,
        x: Math.min(width - 90, 90 + l * xGap),
        y: Math.min(height - 55, Math.max(55, yGap * (idx + 1))),
        level: l,
        indegree: incoming[n.id]?.length || 0,
        outdegree: outgoing[n.id]?.length || 0
      });
    });
  });
  return positioned;
}

function buildGraphFromSql(sql) {
  const { ctes, finalSql, warnings } = parseCtes(sql);
  const cteNameMap = Object.fromEntries(ctes.map((c) => [lower(c.name), c.name]));
  const cteNameSet = new Set(Object.keys(cteNameMap));
  const nodes = [];
  const edges = [];
  ctes.forEach((cte) => {
    const deps = extractDependencies(cte.body, cteNameMap, cte.name);
    const baseTables = extractBaseTables(cte.body, cteNameSet);
    const selectItems = extractSelectItems(cte.body);
    const groupByItems = extractGroupByItems(cte.body);
    const resolvedGrainFields = resolveGroupByItems(cte.body);
    nodes.push({
      id: cte.name,
      label: cte.name,
      type: baseTables.length ? "source_cte" : "cte",
      sql: cte.fullSql,
      baseTables,
      grain: inferGrain(cte.body),
      selectItems,
      groupByItems,
      resolvedGrainFields,
      desc: baseTables.length ? `直接读取 ${baseTables.length} 张底表，并依赖 ${deps.length} 个上游 CTE。` : `不直接读取底表，主要依赖 ${deps.length} 个上游 CTE。`,
      deps
    });
    deps.forEach((dep) => edges.push({ from: dep, to: cte.name, label: "CTE依赖" }));
  });
  const finalDeps = extractDependencies(finalSql, cteNameMap, "final_select");
  const finalSelectItems = extractSelectItems(finalSql);
  const finalGroupByItems = extractGroupByItems(finalSql);
  const finalResolvedGrainFields = resolveGroupByItems(finalSql);
  nodes.push({
    id: "final_select",
    label: "final_select",
    type: "final",
    sql: finalSql || "未识别到最终 select",
    baseTables: extractBaseTables(finalSql, cteNameSet),
    grain: inferGrain(finalSql),
    selectItems: finalSelectItems,
    groupByItems: finalGroupByItems,
    resolvedGrainFields: finalResolvedGrainFields,
    desc: `最终查询。识别到 ${finalDeps.length} 个 CTE 输入。`,
    deps: finalDeps
  });
  finalDeps.forEach((dep) => edges.push({ from: dep, to: "final_select", label: "最终输出" }));
  if (!ctes.length && finalSql.trim()) {
    nodes[0].baseTables = extractBaseTables(finalSql, new Set());
    nodes[0].desc = "普通 SELECT 查询，未拆出 CTE。";
  }
  const seen = new Set();
  const uniqueEdges = edges.filter((e) => {
    const key = `${e.from}->${e.to}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return {
    nodes: layoutGraph(nodes, uniqueEdges),
    edges: uniqueEdges,
    warnings,
    stats: {
      cteCount: ctes.length,
      edgeCount: uniqueEdges.length,
      baseTableCount: new Set(nodes.flatMap((n) => n.baseTables)).size,
      sqlLength: sql.length
    }
  };
}

function detectRiskNotes(graph) {
  const notes = [];
  const finalNode = graph.nodes.find((n) => n.id === "final_select");
  if (finalNode && !containsWord(finalNode.sql, "ab_version") && graph.nodes.some((n) => containsWord(n.sql, "ab_version"))) {
    notes.push("final_select 未显式输出 ab_version，但上游存在 AB 维度；如果结果多行，验数定位会比较困难。 ");
  }
  graph.edges.forEach((e) => {
    const child = graph.nodes.find((n) => n.id === e.to);
    if (!child) return;
    const text = lower(child.sql);
    if (text.includes(`join ${lower(e.from)}`) && text.includes("ab_version") && !text.includes(`${lower(e.from)}.ab_version`)) {
      notes.push(`${e.to} 引用 ${e.from} 时建议核查 join 条件是否包含 ab_version、ab_rule_version。`);
    }
  });
  return [...new Set(notes)].slice(0, 8);
}

function edgeKey(edge) {
  return `${edge.from}->${edge.to}`;
}

function runParserTests() {
  const cases = [
    {
      name: "字段名和CTE同名不应误连边",
      sql: `with uv as (select id from db.source_a), q as (select uv from db.source_b) select uv from q`,
      expectEdges: ["q->final_select"],
      rejectEdges: ["uv->q", "uv->final_select"]
    },
    {
      name: "final_select中的子查询应递归识别CTE依赖",
      sql: `with a as (select id from db.t1), b as (select * from a) select * from (select * from b) t`,
      expectEdges: ["a->b", "b->final_select"],
      rejectEdges: ["a->final_select"]
    },
    {
      name: "group by序号应还原为select实际字段",
      sql: `with a as (select dt, user_id, sum(gmv) as gmv from mart.order_detail group by 1,2) select * from a`,
      expectEdges: ["a->final_select"],
      expectResolvedGrain: { node: "a", values: ["dt", "user_id"] }
    },
    {
      name: "注释和字符串里的from join不应产生依赖",
      sql: `with a as (select id from db.t1), b as (select '-- from a' as txt from db.t2) select * from b`,
      expectEdges: ["b->final_select"],
      rejectEdges: ["a->b", "a->final_select"]
    },
    {
      name: "底表识别不应把CTE当底表",
      sql: `with a as (select * from db.real_table), b as (select * from a join dim.city d on a.city_id = d.id) select * from b`,
      expectEdges: ["a->b", "b->final_select"],
      expectBaseTables: { node: "b", values: ["dim.city"] },
      rejectBaseTables: { node: "b", values: ["a"] }
    }
  ];

  return cases.map((item) => {
    try {
      const graph = buildGraphFromSql(item.sql);
      const edges = new Set(graph.edges.map(edgeKey));
      const failures = [];
      (item.expectEdges || []).forEach((edge) => {
        if (!edges.has(edge)) failures.push(`缺少边 ${edge}`);
      });
      (item.rejectEdges || []).forEach((edge) => {
        if (edges.has(edge)) failures.push(`不应出现边 ${edge}`);
      });
      if (item.expectResolvedGrain) {
        const node = graph.nodes.find((n) => n.id === item.expectResolvedGrain.node);
        const resolvedText = (node?.resolvedGrainFields || []).map((x) => x.resolved).join(" ");
        item.expectResolvedGrain.values.forEach((value) => {
          if (!resolvedText.includes(value)) failures.push(`group by未解析出 ${value}`);
        });
      }
      if (item.expectBaseTables) {
        const node = graph.nodes.find((n) => n.id === item.expectBaseTables.node);
        item.expectBaseTables.values.forEach((value) => {
          if (!node?.baseTables?.includes(value)) failures.push(`底表未识别 ${value}`);
        });
      }
      if (item.rejectBaseTables) {
        const node = graph.nodes.find((n) => n.id === item.rejectBaseTables.node);
        item.rejectBaseTables.values.forEach((value) => {
          if (node?.baseTables?.includes(value)) failures.push(`不应把 ${value} 识别为底表`);
        });
      }
      return { name: item.name, pass: failures.length === 0, failures, graph };
    } catch (e) {
      return { name: item.name, pass: false, failures: [e?.message || String(e)], graph: null };
    }
  });
}

function wrapText(str, max = 24) {
  if (!str) return [];
  const chars = Array.from(str);
  const lines = [];
  for (let i = 0; i < chars.length; i += max) lines.push(chars.slice(i, i + max).join(""));
  return lines.slice(0, 2);
}

function getNodeColor(node) {
  if (node.type === "final") return "#7c3aed";
  if (node.type === "source_cte") return "#2563eb";
  if (node.indegree === 0) return "#0891b2";
  return "#059669";
}

export default function SqlLineageInteractiveGraph() {
  const initialGraph = useMemo(() => buildGraphFromSql(DEFAULT_SQL), []);
  const [sqlText, setSqlText] = useState(DEFAULT_SQL);
  const [graph, setGraph] = useState(initialGraph);
  const [lastGoodGraph, setLastGoodGraph] = useState(initialGraph);
  const [nodes, setNodes] = useState(initialGraph.nodes);
  const [parseError, setParseError] = useState("");
  const [autoParse, setAutoParse] = useState(true);
  const [editorOpen, setEditorOpen] = useState(true);
  const [hoverId, setHoverId] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [dragId, setDragId] = useState(null);
  const [query, setQuery] = useState("");
  const [showSql, setShowSql] = useState(true);
  const [showRisk, setShowRisk] = useState(true);

  const parseAndApply = (text = sqlText) => {
    try {
      const next = buildGraphFromSql(text);
      setGraph(next);
      setLastGoodGraph(next);
      setNodes(next.nodes);
      setParseError("");
      if (selectedId && !next.nodes.some((n) => n.id === selectedId)) setSelectedId(null);
    } catch (e) {
      setParseError(e?.message || String(e));
      setGraph(lastGoodGraph);
      setNodes(lastGoodGraph.nodes);
    }
  };

  useEffect(() => {
    if (!autoParse) return;
    const timer = setTimeout(() => parseAndApply(sqlText), 450);
    return () => clearTimeout(timer);
  }, [sqlText, autoParse]);

  const nodeMap = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const selectedNode = selectedId ? nodeMap[selectedId] : null;
  const hoverNode = hoverId ? nodeMap[hoverId] : null;
  const previewNode = hoverNode || selectedNode;
  const riskNotes = useMemo(() => detectRiskNotes({ ...graph, nodes }), [graph, nodes]);
  const testResults = useMemo(() => runParserTests(), []);
  const testPassedCount = testResults.filter((item) => item.pass).length;

  const filteredNodes = useMemo(() => {
    const q = lower(query.trim());
    if (!q) return new Set(nodes.map((n) => n.id));
    return new Set(nodes.filter((n) => lower([n.id, n.grain, n.desc, n.baseTables.join(" "), n.sql].join(" ")).includes(q)).map((n) => n.id));
  }, [query, nodes]);

  const onPointerMove = (e) => {
    if (!dragId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 1420;
    const y = ((e.clientY - rect.top) / rect.height) * 680;
    setNodes((prev) => prev.map((n) => (n.id === dragId ? { ...n, x: Math.max(45, Math.min(1375, x)), y: Math.max(45, Math.min(635, y)) } : n)));
  };

  const resetLayout = () => {
    const sourceGraph = parseError ? lastGoodGraph : graph;
    const relayoutedNodes = layoutGraph(sourceGraph.nodes, sourceGraph.edges);
    const next = { ...sourceGraph, nodes: relayoutedNodes };
    setGraph(next);
    setNodes(relayoutedNodes);
    if (!parseError) setLastGoodGraph(next);
  };

  const dependencyRows = graph.edges.filter((e) => e.to === selectedNode?.id || e.from === selectedNode?.id);
  const allBaseTables = useMemo(() => [...new Set(nodes.flatMap((n) => n.baseTables))], [nodes]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-5">
      <div className="max-w-[1900px] mx-auto space-y-4">
        <header className="rounded-2xl bg-slate-900/80 border border-slate-700 p-5 shadow-2xl">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <GitBranch className="w-7 h-7 text-cyan-300" />
                <h1 className="text-2xl font-bold tracking-tight">SQL CTE 血缘交互图 · 可编辑版</h1>
              </div>
              <p className="mt-2 text-slate-300 text-sm">在 SQL 面板中修改或整体替换 SQL，页面会解析 CTE、底表、依赖关系，并动态刷新点线图。</p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 min-w-[420px]">
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3"><div className="text-xs text-slate-500">CTE 数</div><div className="text-xl font-bold text-cyan-200">{graph.stats.cteCount}</div></div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3"><div className="text-xs text-slate-500">依赖边</div><div className="text-xl font-bold text-purple-200">{graph.stats.edgeCount}</div></div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3"><div className="text-xs text-slate-500">底表数</div><div className="text-xl font-bold text-emerald-200">{graph.stats.baseTableCount}</div></div>
              <div className="rounded-xl bg-slate-950 border border-slate-800 p-3"><div className="text-xs text-slate-500">SQL长度</div><div className="text-xl font-bold text-amber-200">{graph.stats.sqlLength}</div></div>
            </div>
          </div>
        </header>

        <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl overflow-hidden">
          <div className="p-4 border-b border-slate-700 flex flex-col lg:flex-row gap-3 lg:items-center lg:justify-between">
            <div className="flex items-center gap-2">
              <CodeIcon className="w-5 h-5 text-cyan-300" />
              <h2 className="text-lg font-bold">可编辑 SQL 面板</h2>
              <span className={`ml-2 text-xs px-2 py-1 rounded-full border ${parseError ? "text-red-200 border-red-700 bg-red-950/50" : "text-emerald-200 border-emerald-700 bg-emerald-950/40"}`}>{parseError ? "解析失败，保留上一次图" : "解析正常"}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setEditorOpen((v) => !v)} className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm">{editorOpen ? "收起面板" : "展开面板"}</button>
              <button onClick={() => setAutoParse((v) => !v)} className={`px-3 py-2 rounded-xl border text-sm ${autoParse ? "bg-cyan-900/50 border-cyan-600 text-cyan-100" : "bg-slate-800 hover:bg-slate-700 border-slate-600"}`}>{autoParse ? "实时解析：开" : "实时解析：关"}</button>
              <button onClick={() => parseAndApply(sqlText)} className="px-3 py-2 rounded-xl bg-cyan-700 hover:bg-cyan-600 border border-cyan-500 text-sm font-semibold">解析并生成图</button>
              <button onClick={resetLayout} className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm flex items-center gap-2"><RotateCcw className="w-4 h-4" />重新布局</button>
              <button onClick={() => setSqlText(DEFAULT_SQL)} className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm">加载示例SQL</button>
            </div>
          </div>
          {editorOpen && (
            <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-0">
              <textarea value={sqlText} onChange={(e) => setSqlText(e.target.value)} spellCheck={false} className="min-h-[360px] xl:min-h-[460px] w-full resize-y bg-slate-950 text-slate-100 p-4 font-mono text-sm leading-6 outline-none border-0 focus:ring-2 focus:ring-cyan-500" placeholder="在这里粘贴或修改完整 SQL。支持 WITH CTE 解析、FROM/JOIN 底表识别、CTE 依赖识别。" />
              <div className="border-t xl:border-t-0 xl:border-l border-slate-700 p-4 bg-slate-950/50 space-y-3">
                <div className="text-sm text-slate-300 leading-6"><div className="font-semibold text-slate-100 mb-1">解析能力</div><div>1. 识别 WITH 后的多个 CTE。</div><div>2. 只基于 FROM / JOIN 关系判断 CTE 依赖。</div><div>3. 递归扫描 from 子查询内部依赖。</div><div>4. 从 FROM / JOIN 中抽取底表。</div><div>5. 将 group by 1,2,3 还原为 select 实际字段。</div><div>6. 内置单元测试覆盖误边、漏边、底表和序号分组。</div></div>
                {parseError && <div className="rounded-xl bg-red-950/40 border border-red-700 p-3 text-sm text-red-100 leading-6"><div className="font-semibold mb-1">错误信息</div>{parseError}</div>}
                {!!graph.warnings.length && <div className="rounded-xl bg-amber-950/40 border border-amber-700 p-3 text-sm text-amber-100 leading-6"><div className="font-semibold mb-1">解析提示</div>{graph.warnings.map((w, i) => <div key={i}>{i + 1}. {w}</div>)}</div>}
                <div className="rounded-xl bg-slate-900 border border-slate-800 p-3 text-xs text-slate-400 leading-5">当前是前端轻量级解析器，适合快速画 SQL 血缘图。遇到复杂宏、动态 SQL、极深嵌套或方言特殊语法时，建议先格式化 SQL 后再粘贴。</div>
              </div>
            </div>
          )}
        </section>

        <div className="grid grid-cols-1 2xl:grid-cols-[1fr_470px] gap-4">
          <main className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-slate-700 flex flex-col lg:flex-row gap-3 lg:items-center lg:justify-between">
              <div className="flex items-center gap-2 text-sm text-slate-300"><MousePointer2 className="w-4 h-4 text-cyan-300" />拖拽节点调整布局；悬浮节点临时预览 SQL；双击节点固定预览，点击空白处取消。</div>
              <div className="relative w-full lg:w-[420px]"><Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索子查询、底表、SQL关键字..." className="w-full bg-slate-950 border border-slate-700 rounded-xl pl-9 pr-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-500" /></div>
            </div>
            <div className="relative h-[720px] bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.08),transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(168,85,247,0.10),transparent_36%)]">
              <svg viewBox="0 0 1420 680" className="w-full h-full select-none" onPointerMove={onPointerMove} onPointerUp={() => setDragId(null)} onPointerLeave={() => setDragId(null)} onClick={() => { setSelectedId(null); setHoverId(null); }}>
                <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#94a3b8" /></marker><filter id="glow"><feGaussianBlur stdDeviation="3.5" result="coloredBlur" /><feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
                {graph.edges.map((edge, idx) => {
                  const s = nodeMap[edge.from];
                  const t = nodeMap[edge.to];
                  if (!s || !t) return null;
                  const dx = t.x - s.x;
                  const dy = t.y - s.y;
                  const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
                  const sx = s.x + (dx / dist) * 54;
                  const sy = s.y + (dy / dist) * 34;
                  const tx = t.x - (dx / dist) * 66;
                  const ty = t.y - (dy / dist) * 38;
                  const mx = (sx + tx) / 2;
                  const my = (sy + ty) / 2;
                  const active = selectedId === edge.from || selectedId === edge.to || hoverId === edge.from || hoverId === edge.to;
                  const visible = filteredNodes.has(edge.from) || filteredNodes.has(edge.to);
                  return <g key={`${edge.from}-${edge.to}-${idx}`} opacity={visible ? 1 : 0.13}><path d={`M ${sx} ${sy} C ${mx} ${sy}, ${mx} ${ty}, ${tx} ${ty}`} fill="none" stroke={active ? "#22d3ee" : "#64748b"} strokeWidth={active ? 3 : 1.8} markerEnd="url(#arrow)" />{active && <g><rect x={mx - 56} y={my - 14} width="112" height="25" rx="8" fill="#0f172a" stroke="#334155" /><text x={mx} y={my + 4} textAnchor="middle" fontSize="11" fill="#cbd5e1">{edge.label}</text></g>}</g>;
                })}
                {nodes.map((node) => {
                  const active = selectedId === node.id;
                  const hover = hoverId === node.id;
                  const visible = filteredNodes.has(node.id);
                  const color = getNodeColor(node);
                  const lines = wrapText(node.label, 18);
                  return <g key={node.id} transform={`translate(${node.x}, ${node.y})`} opacity={visible ? 1 : 0.18} className="cursor-grab active:cursor-grabbing" onPointerDown={(e) => { e.stopPropagation(); e.currentTarget.setPointerCapture(e.pointerId); setDragId(node.id); }} onMouseEnter={() => setHoverId(node.id)} onMouseLeave={() => setHoverId(null)} onClick={(e) => { e.stopPropagation(); }} onDoubleClick={(e) => { e.stopPropagation(); setSelectedId(node.id); }}><rect x="-78" y="-34" width="156" height="68" rx="18" fill="#0f172a" stroke={active || hover ? "#22d3ee" : color} strokeWidth={active || hover ? 3 : 2} filter={active || hover ? "url(#glow)" : undefined} /><circle cx="-55" cy="0" r="11" fill={color} />{lines.map((line, i) => <text key={i} x="8" y={lines.length === 1 ? 5 : -4 + i * 15} textAnchor="middle" fontSize="14" fontWeight="700" fill="#e2e8f0">{line}</text>)}<text x="0" y="50" textAnchor="middle" fontSize="11" fill="#94a3b8">{node.grain.length > 34 ? node.grain.slice(0, 34) + "..." : node.grain}</text></g>;
                })}
              </svg>
              </div>
            {previewNode && <div className="border-t border-slate-700 bg-slate-950/80 p-4" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}><div className="rounded-2xl bg-slate-950/95 border border-cyan-500/40 shadow-2xl p-4"><div className="flex items-center justify-between gap-3 mb-2"><div className="font-bold text-cyan-200">{previewNode.label}</div><div className="flex items-center gap-2"><div className="text-xs text-slate-400">{selectedId === previewNode.id ? "双击固定预览" : "悬浮临时预览"}</div>{selectedId === previewNode.id && <button onClick={() => setSelectedId(null)} className="text-xs px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200">关闭</button>}</div></div><div className="text-xs text-slate-300 mb-2">输出粒度：{previewNode.grain}</div><pre className="max-h-[360px] overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-200 bg-slate-900 rounded-xl p-3 border border-slate-800">{previewNode.sql || "暂无 SQL"}</pre></div></div>}
          </main>

          <aside className="space-y-4">
            <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl p-4"><div className="flex items-center gap-2 mb-3"><Layers className="w-5 h-5 text-cyan-300" /><h2 className="text-lg font-bold">子查询详情</h2></div>{selectedNode ? <div className="space-y-3"><div><div className="text-xs text-slate-400 mb-1">节点名</div><div className="text-xl font-bold text-cyan-200 break-all">{selectedNode.label}</div></div><div className="grid grid-cols-3 gap-2 text-center"><div className="rounded-xl bg-slate-950 border border-slate-800 p-2"><div className="text-xs text-slate-500">入边</div><div className="font-bold">{selectedNode.indegree || 0}</div></div><div className="rounded-xl bg-slate-950 border border-slate-800 p-2"><div className="text-xs text-slate-500">出边</div><div className="font-bold">{selectedNode.outdegree || 0}</div></div><div className="rounded-xl bg-slate-950 border border-slate-800 p-2"><div className="text-xs text-slate-500">底表</div><div className="font-bold">{selectedNode.baseTables.length}</div></div></div><div><div className="text-xs text-slate-400 mb-1">推断输出粒度</div><div className="text-sm text-slate-100 bg-slate-950 rounded-xl p-3 border border-slate-800 break-all">{selectedNode.grain}</div></div>{selectedNode.resolvedGrainFields?.length > 0 && <div><div className="text-xs text-slate-400 mb-1">Group By 序号还原</div><div className="space-y-1">{selectedNode.resolvedGrainFields.map((item, idx) => <div key={idx} className="text-xs text-cyan-100 bg-slate-950 rounded-lg p-2 border border-slate-800 break-all">{item.display}</div>)}</div></div>}<div><div className="text-xs text-slate-400 mb-1">作用说明</div><div className="text-sm text-slate-300 leading-6">{selectedNode.desc}</div></div></div> : <div className="text-sm text-slate-400">暂无节点</div>}</section>
            <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl p-4"><div className="flex items-center gap-2 mb-3"><Database className="w-5 h-5 text-emerald-300" /><h2 className="text-lg font-bold">对应底表</h2></div>{selectedNode?.baseTables?.length ? <div className="space-y-2">{selectedNode.baseTables.map((t) => <div key={t} className="rounded-xl bg-slate-950 border border-slate-800 p-3 text-sm text-emerald-200 break-all">{t}</div>)}</div> : <div className="rounded-xl bg-slate-950 border border-slate-800 p-3 text-sm text-slate-400">当前节点不直接读取底表，主要依赖上游 CTE，或底表未被轻量解析器识别。</div>}</section>
            <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl p-4"><h2 className="text-lg font-bold mb-3">上下游依赖</h2><div className="space-y-2 max-h-[300px] overflow-auto pr-1">{dependencyRows.length ? dependencyRows.map((e, idx) => <div key={idx} className="rounded-xl bg-slate-950 border border-slate-800 p-3 text-sm"><div className="text-slate-300"><span className="text-cyan-300 font-semibold break-all">{e.from}</span> → <span className="text-purple-300 font-semibold break-all">{e.to}</span></div><div className="text-xs text-slate-500 mt-1">{e.label}</div></div>) : <div className="text-sm text-slate-400">无依赖信息</div>}</div></section>
            {showRisk && <section className="rounded-2xl bg-amber-950/40 border border-amber-700/60 shadow-2xl p-4"><div className="flex items-center gap-2 mb-3"><AlertTriangle className="w-5 h-5 text-amber-300" /><h2 className="text-lg font-bold text-amber-100">自动风险提示</h2></div><div className="space-y-2 max-h-[260px] overflow-auto pr-1">{riskNotes.length ? riskNotes.map((note, i) => <div key={i} className="text-sm text-amber-100/90 leading-6 bg-slate-950/40 rounded-xl p-3 border border-amber-900/60">{i + 1}. {note}</div>) : <div className="text-sm text-amber-100/80 leading-6 bg-slate-950/40 rounded-xl p-3 border border-amber-900/60">暂未识别到明显粒度风险。该结果只代表轻量规则扫描，不等价于 SQL 编译器校验。</div>}</div></section>}
          </aside>
        </div>

        <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl overflow-hidden"><div className="p-4 border-b border-slate-700 flex flex-col md:flex-row md:items-center md:justify-between gap-3"><div><h2 className="text-lg font-bold">SQL 详情：{selectedNode?.label || "未选择"}</h2><p className="text-sm text-slate-400 mt-1">双击图中任意节点，可固定查看该节点解析出的 SQL 片段；点击画布空白处取消固定。</p></div><div className="flex gap-2"><button onClick={() => setShowSql((v) => !v)} className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm">{showSql ? "隐藏SQL详情" : "显示SQL详情"}</button><button onClick={() => setShowRisk((v) => !v)} className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-sm">{showRisk ? "隐藏风险提示" : "显示风险提示"}</button></div></div>{showSql && <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-slate-200 bg-slate-950 p-5">{selectedNode?.sql || "暂无 SQL"}</pre>}</section>

        <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl p-4"><div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-3"><div><h2 className="text-lg font-bold">解析器单元测试</h2><p className="text-sm text-slate-400 mt-1">用于验证点线血缘依赖规则、group by序号还原、底表识别和字段同名误判。</p></div><div className={`text-sm px-3 py-2 rounded-xl border ${testPassedCount === testResults.length ? "text-emerald-200 border-emerald-700 bg-emerald-950/40" : "text-red-200 border-red-700 bg-red-950/40"}`}>{testPassedCount}/{testResults.length} 通过</div></div><div className="grid grid-cols-1 xl:grid-cols-2 gap-3">{testResults.map((item, idx) => <div key={idx} className={`rounded-xl border p-3 ${item.pass ? "bg-emerald-950/20 border-emerald-800" : "bg-red-950/20 border-red-800"}`}><div className="flex items-center justify-between gap-2"><div className="font-semibold text-sm text-slate-100">{item.name}</div><div className={`text-xs px-2 py-1 rounded-lg ${item.pass ? "bg-emerald-900/50 text-emerald-100" : "bg-red-900/50 text-red-100"}`}>{item.pass ? "PASS" : "FAIL"}</div></div>{!item.pass && <div className="mt-2 space-y-1">{item.failures.map((f, i) => <div key={i} className="text-xs text-red-100 bg-slate-950/60 rounded-lg p-2">{f}</div>)}</div>}</div>)}</div></section>

        <section className="rounded-2xl bg-slate-900/80 border border-slate-700 shadow-2xl p-4"><h2 className="text-lg font-bold mb-3">全局底表索引</h2>{allBaseTables.length ? <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">{allBaseTables.map((t) => { const owners = nodes.filter((n) => n.baseTables.includes(t)).map((n) => n.label); return <div key={t} className="rounded-xl bg-slate-950 border border-slate-800 p-3"><div className="text-sm text-emerald-200 break-all font-semibold">{t}</div><div className="text-xs text-slate-500 mt-2">使用节点：{owners.join("、")}</div></div>; })}</div> : <div className="rounded-xl bg-slate-950 border border-slate-800 p-4 text-sm text-slate-400">暂未识别到底表。请确认 SQL 中存在 FROM / JOIN 表名。</div>}</section>
      </div>
    </div>
  );
}
