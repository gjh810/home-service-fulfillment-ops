import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 全部参数均为个人项目的演示假设，不代表任何企业的实际业务水平。
const SEED = 20261011;
const COUNT = 600;
const OUTPUT = path.join(path.dirname(fileURLToPath(import.meta.url)), '03_模拟工单.csv');
const MINUTE = 60_000;
const fields = [
  'order_id', 'city', 'service_type', 'site_id', 'created_at', 'dispatched_at',
  'appointment_deadline', 'arrived_at', 'completion_deadline', 'completed_at',
  'order_status', 'primary_exception', 'exception_detected_at',
  'exception_closed_at', 'complaint_flag', 'rating',
];

function rng(seed) {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let x = state;
    x = Math.imul(x ^ (x >>> 15), x | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}
const random = rng(SEED);
const integer = (low, high) => low + Math.floor(random() * (high - low + 1));
const choice = (items, weights) => {
  let remaining = random() * weights.reduce((a, b) => a + b, 0);
  for (let i = 0; i < items.length; i++) {
    remaining -= weights[i];
    if (remaining < 0) return items[i];
  }
  return items.at(-1);
};
const add = (date, minutes) => new Date(date.getTime() + minutes * MINUTE);
const dateAt = (day, hour, minute = 0) => new Date(Date.UTC(2026, 7, day, hour, minute));
const stamp = (date) => date ? date.toISOString().slice(0, 16).replace('T', ' ') : '';

function scenarioFor(site, service) {
  const names = ['正常', '派单晚', '未派单', '上门晚', '未上门', '完工晚', '上门后未完工'];
  const weights = [72, 5, 3, 8, 3, 7, 2];
  if (site === 'WH02') { weights[0] -= 6; weights[3] += 6; }
  if (site === 'CQ01') { weights[0] -= 6; weights[5] += 6; }
  if (service === '维修') { weights[0] -= 3; weights[5] += 3; }
  return choice(names, weights);
}

function makeOrder() {
  const city = choice(['北京', '武汉', '重庆'], [40, 35, 25]);
  const service_type = choice(['安装', '维修', '拆旧'], [45, 40, 15]);
  const site_id = choice({北京:['BJ01','BJ02'],武汉:['WH01','WH02'],重庆:['CQ01','CQ02']}[city], [1, 1]);
  const created_at = dateAt(integer(1, 28), integer(8, 18), integer(0, 11) * 5);
  const leadDays = choice([1, 2, 3], [60, 30, 10]);
  const appointment_deadline = dateAt(created_at.getUTCDate() + leadDays, choice([10, 12, 15, 17], [25, 25, 30, 20]));
  const completion_deadline = add(appointment_deadline, {安装:240,维修:300,拆旧:180}[service_type]);
  const scenario = scenarioFor(site_id, service_type);
  let dispatched_at = null;
  let arrived_at = null;
  let completed_at = null;

  if (scenario !== '未派单') {
    dispatched_at = scenario === '派单晚'
      ? add(appointment_deadline, integer(15, 120))
      : add(created_at, integer(30, 240));
  }
  if (dispatched_at && scenario !== '未上门') {
    arrived_at = ['派单晚', '上门晚'].includes(scenario)
      ? add(scenario === '派单晚' ? dispatched_at : appointment_deadline, integer(15, 120))
      : add(appointment_deadline, -integer(10, 75));
    if (arrived_at < add(dispatched_at, 10)) arrived_at = add(dispatched_at, 10);
  }
  if (arrived_at && scenario !== '上门后未完工') {
    completed_at = scenario === '完工晚'
      ? add(completion_deadline, integer(15, 180))
      : add(arrived_at, integer(50, 150));
    if (scenario === '正常' && completed_at > add(completion_deadline, -10)) {
      completed_at = add(completion_deadline, -10);
    }
  }

  const primary_exception = !dispatched_at || dispatched_at > appointment_deadline ? '派单超时'
    : !arrived_at || arrived_at > appointment_deadline ? '上门超时'
    : !completed_at || completed_at > completion_deadline ? '完工超时' : '无';
  const exception_detected_at = primary_exception === '无' ? null
    : primary_exception === '完工超时' ? completion_deadline : appointment_deadline;
  const exception_closed_at = primary_exception !== '无' && completed_at && random() < 0.68
    ? add(new Date(Math.max(exception_detected_at, completed_at)), integer(30, 360)) : null;
  const complaintChance = primary_exception === '无' ? 0.025 : completed_at ? 0.14 : 0.24;
  const complaint_flag = random() < complaintChance ? 1 : 0;
  const rating = !completed_at || random() < 0.18 ? '' : complaint_flag
    ? choice([1, 2, 3], [25, 45, 30])
    : primary_exception === '无'
      ? choice([3, 4, 5], [10, 35, 55])
      : choice([2, 3, 4, 5], [20, 35, 35, 10]);

  return {
    city, service_type, site_id, created_at, dispatched_at, appointment_deadline,
    arrived_at, completion_deadline, completed_at,
    order_status: completed_at ? '已完工' : '未完工',
    primary_exception, exception_detected_at, exception_closed_at, complaint_flag, rating,
  };
}

const orders = Array.from({length: COUNT}, makeOrder)
  .sort((a, b) => a.created_at - b.created_at || a.site_id.localeCompare(b.site_id));
orders.forEach((order, index) => { order.order_id = `HS202608${String(index + 1).padStart(4, '0')}`; });
const quote = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`;
const csv = '\ufeff' + fields.join(',') + '\r\n' + orders.map(order => fields.map(field => {
  const value = order[field];
  return quote(value instanceof Date ? stamp(value) : value);
}).join(',')).join('\r\n') + '\r\n';
await fs.writeFile(OUTPUT, csv, 'utf8');
console.log(JSON.stringify({output: OUTPUT, seed: SEED, rows: orders.length}, null, 2));
