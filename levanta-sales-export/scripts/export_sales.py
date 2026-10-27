#!/usr/bin/env python3
"""Read-only Levanta daily creator export. Python 3.10+, standard library only."""
import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = 'https://app.levanta.io/api/seller/v2'
HEADERS = ['Marketplace Program', 'Date', 'Creator', 'Clicks', 'Conversions', 'Sales', 'Commission']


class ExportError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    temporary.chmod(0o600)
    temporary.replace(path)


def init_config(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).resolve().parents[1] / 'assets/accounts.example.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(template.read_text(encoding='utf-8'))
    ignore = path.parent / '.gitignore'
    existing = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    additions = [x for x in (path.name, '.levanta-cache/', 'outputs/') if x not in existing.splitlines()]
    if additions:
        with ignore.open('a', encoding='utf-8') as stream:
            stream.write(('\n' if existing and not existing.endswith('\n') else '') + '\n'.join(additions) + '\n')
    print(f'请填写并保存：{path}')


def load_accounts(path, selected=None):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not data:
        raise ExportError('密钥配置必须是非空 JSON 对象。')
    if selected is not None:
        if selected not in data:
            raise ExportError('找不到指定的账号名称。')
        data = {selected: data[selected]}
    for name, account in data.items():
        if not name.strip() or not isinstance(account, dict):
            raise ExportError('账号名称或配置格式无效。')
        key = account.get('api_key', '')
        if not isinstance(key, str) or not key.strip():
            raise ExportError('有账号尚未填写 api_key；请填写后再下载。')
        key = key.strip()
        if not key.isascii() or any(c.isspace() for c in key) or key.lower().startswith('bearer'):
            raise ExportError('api_key 格式无效，请只填写密钥本身。')
        account['api_key'] = key
        ids = account.get('brand_ids')
        if ids is not None and (not isinstance(ids, list) or not ids or any(not isinstance(x,str) or not x for x in ids)):
            raise ExportError('brand_ids 必须是非空品牌 ID 字符串数组，或省略此字段。')
    return data


class Client:
    def __init__(self, key, cache, refresh=False, delay=2.5):
        self.key, self.cache, self.refresh, self.delay = key, Path(cache), refresh, delay
        self.opener = build_opener(NoRedirect())
        self.last_request = 0.0

    def get(self, endpoint, params):
        query = urlencode(sorted(params.items()))
        fingerprint = hashlib.sha256((self.key + '\n' + endpoint + '?' + query).encode()).hexdigest()
        file = self.cache / (fingerprint + '.json')
        if file.exists() and not self.refresh:
            return json.loads(file.read_text(encoding='utf-8'))
        for attempt in range(5):
            time.sleep(max(0.0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = Request(BASE + endpoint + '?' + query, headers={
                'Authorization': 'Bearer ' + self.key, 'Accept': 'application/json'})
            try:
                with self.opener.open(request, timeout=60) as response:
                    value = json.load(response)
                if not isinstance(value, dict):
                    raise ExportError('接口返回格式异常。')
                private_json(file, value)
                return value
            except HTTPError as error:
                if error.code not in (429,500,502,503,504) or attempt == 4:
                    raise ExportError(f'接口失败（HTTP {error.code}）。请核对权限，或稍后重试。') from None
                delay = min(15 * (attempt + 1), 45)
                retry_after = error.headers.get('Retry-After')
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                        except (TypeError, ValueError):
                            pass
                if delay > 60:
                    raise ExportError('服务要求等待超过一分钟，请稍后重新运行以复用进度。') from None
                print(f'接口暂时繁忙，{max(0,delay):.0f} 秒后重试。', flush=True)
                time.sleep(max(0,delay))
            except (URLError, TimeoutError):
                if attempt == 4:
                    raise ExportError('网络异常或超时；请稍后重试。') from None
                time.sleep(min(5 * (attempt + 1), 20))
        raise ExportError('接口重试耗尽。')

    def rows(self, endpoint, params, field='rows', paginated=True):
        params = dict(params)
        if paginated:
            params['limit'] = 100
        rows, seen = [], set()
        while True:
            data = self.get(endpoint, params)
            if data.get('currency', 'USD') != 'USD' or not isinstance(data.get(field), list):
                raise ExportError('接口币种或数据字段异常。')
            rows.extend(data[field])
            cursor = data.get('cursor')
            if not cursor:
                return rows
            if not isinstance(cursor,str) or cursor in seen:
                raise ExportError('分页游标异常。')
            seen.add(cursor)
            params['cursor'] = cursor


def number(metrics, field):
    try:
        value = Decimal(str(metrics[field]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        raise ExportError('报表指标字段缺失或不是有效数值。') from None
    if not value.is_finite():
        raise ExportError('报表指标不是有限数值。')
    return value


def activity(metrics):
    return any(number(metrics, key) != 0 for key in ('clicks','conversions','sales','commission'))


def reconcile(rows, expected):
    for field in ('conversions','sales','commission'):
        actual = sum((number(r['metrics'],field) for r in rows), Decimal(0))
        tolerance = Decimal(0) if field == 'conversions' else Decimal('0.02')
        if abs(actual-number(expected,field)) > tolerance:
            raise ExportError('逐日红人数据与日期汇总不一致；请使用 --refresh 更新数据后重试。')


def collect(client, account, brand_ids, start, end, all_activity=False, occupied=None):
    result = []
    brands = client.rows('/brands', {'marketplace':'all'}, 'brands')
    if brand_ids is not None:
        if not set(brand_ids).issubset({b['id'] for b in brands}):
            raise ExportError('配置包含当前密钥不可访问的 brand_ids。')
        brands = [b for b in brands if b['id'] in brand_ids]
    occupied = occupied if occupied is not None else set()
    for brand in brands:
        identity = (brand['id'],brand['marketplace'])
        if identity in occupied:
            raise ExportError('多个账号覆盖同一品牌站点；请用 brand_ids 限定范围，避免重复。')
        occupied.add(identity)
        cursor = start
        dates_seen = set()
        while cursor <= end:
            stop = min(end,cursor+timedelta(days=30))
            params = {'start':cursor.isoformat()+'T00:00:00.000Z',
                      'end':stop.isoformat()+'T23:59:59.999Z', 'currency':'USD',
                      'brandIds':brand['id'], 'marketplaces':brand['marketplace']}
            dates = client.rows('/reports/performance/date', params, paginated=False)
            for day in dates:
                day_date = date.fromisoformat(day['date'])
                if not cursor <= day_date <= stop or day['date'] in dates_seen:
                    raise ExportError('日期报表范围或日期重复异常。')
                dates_seen.add(day['date'])
                if not (activity(day['metrics']) if all_activity else number(day['metrics'],'conversions')>0):
                    continue
                daily = dict(params,start=day['date']+'T00:00:00.000Z',end=day['date']+'T23:59:59.999Z')
                creators = client.rows('/reports/performance/creator', daily)
                reconcile(creators,day['metrics'])
                ids = set()
                for row in creators:
                    creator = row.get('creator')
                    creator_id = creator['id'] if creator else None
                    if creator_id in ids:
                        raise ExportError('同一天返回重复红人行。')
                    ids.add(creator_id)
                    metrics = row['metrics']
                    if not (activity(metrics) if all_activity else number(metrics,'conversions')>0):
                        continue
                    clicks, conversions = number(metrics,'clicks'), number(metrics,'conversions')
                    if clicks != clicks.to_integral_value() or conversions != conversions.to_integral_value():
                        raise ExportError('点击数或转化数不是整数。')
                    result.append({'account':account,'brandId':brand['id'],'marketplace':brand['marketplace'],
                        'creatorId':creator_id,'values':[
                            brand['name'].strip()+' / '+brand['marketplace'],day['date'],creator['name'] if creator else 'Unattributed',
                            int(clicks),int(conversions),str(number(metrics,'sales')),str(number(metrics,'commission'))]})
                print(f"已读取 {brand['marketplace']} {day['date']}。",flush=True)
            cursor = stop + timedelta(days=1)
    return result


def cell(value):
    # Protect literal names when CSV is opened in spreadsheet software.
    return "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r','\n')) else value


def save_output(output, records, start, end, all_activity):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    records.sort(key=lambda r:(r['values'][1],r['values'][0],r['values'][2],r['account']))
    rows = [r['values'] for r in records]
    meta = {'start':start.isoformat(),'end':end.isoformat(),'timezone':'UTC','currency':'USD',
            'filter':'all activity' if all_activity else 'Conversions > 0',
            'downloadedAt':datetime.now(timezone.utc).isoformat(),'rowCount':len(rows),
            'conversions':sum(r[4] for r in rows),
            'sales':str(sum((Decimal(r[5]) for r in rows),Decimal(0))),
            'commission':str(sum((Decimal(r[6]) for r in rows),Decimal(0))),
            'records':[{'account':r['account'],'brandId':r['brandId'],'marketplace':r['marketplace'],
                        'date':r['values'][1],'creatorId':r['creatorId']} for r in records]}
    temporary = output/'sales.csv.tmp'
    fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows([[cell(v) if i in (0,2) else v for i,v in enumerate(row)] for row in rows])
    temporary.chmod(0o600)
    temporary.replace(output/'sales.csv')
    private_json(output/'sales.json',{'headers':HEADERS,'rows':rows,'metadata':meta})
    private_json(output/'metadata.json',meta)
    print(f"导出完成：{len(rows)} 行，{meta['conversions']} 次转化。CSV：{(output/'sales.csv').resolve()}")
    return meta


def main():
    parser=argparse.ArgumentParser(description='Levanta 每日红人七列业绩导出')
    parser.add_argument('--init-config',metavar='PATH')
    parser.add_argument('--config',default='levanta/accounts.local.json')
    parser.add_argument('--account')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--output',default='outputs/levanta')
    parser.add_argument('--all-activity',action='store_true')
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    try:
        if args.init_config:
            init_config(args.init_config)
            return 0
        if not args.start or not args.end:
            raise ExportError('请提供 --start 和 --end（YYYY-MM-DD）。')
        start,end=date.fromisoformat(args.start),date.fromisoformat(args.end)
        if start>end:
            raise ExportError('开始日期不能晚于结束日期。')
        accounts=load_accounts(args.config,args.account)
        records,occupied=[],set()
        for account,settings in accounts.items():
            client=Client(settings['api_key'],Path(args.output)/'.levanta-cache',args.refresh)
            records.extend(collect(client,account,settings.get('brand_ids'),start,end,args.all_activity,occupied))
        save_output(args.output,records,start,end,args.all_activity)
        return 0
    except FileExistsError:
        print('配置已存在，未覆盖；请直接打开已有文件。',file=sys.stderr)
    except (ExportError,OSError,ValueError,KeyError,TypeError) as error:
        # Do not print arbitrary exception strings: a bad API response may contain secrets.
        print(str(error) if isinstance(error,ExportError) else '配置、网络或返回数据格式异常，请检查后重试。',file=sys.stderr)
    return 1


if __name__=='__main__':
    sys.exit(main())
