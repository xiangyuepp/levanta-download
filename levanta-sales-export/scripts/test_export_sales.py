import importlib.util
import csv
from datetime import date
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec=importlib.util.spec_from_file_location('export_sales',Path(__file__).with_name('export_sales.py'))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def metric(clicks=0,conversions=0,sales='0.00',commission='0.00'):
    return dict(clicks=clicks,conversions=conversions,sales=sales,commission=commission)


class FixtureClient:
    def __init__(self):self.calls=[]
    def rows(self,endpoint,params,field='rows',paginated=True):
        self.calls.append((endpoint,dict(params)))
        if endpoint=='/brands':
            return [{'id':'brand-1','name':'Example','marketplace':'amazon.com'}]
        if endpoint=='/reports/performance/date':
            return [{'date':'2026-10-01','metrics':metric(7,1,'10.00','1.00')},
                    {'date':'2026-10-02','metrics':metric(4)}]
        if params['start'].startswith('2026-10-01'):
            return [{'creator':{'id':'c1','name':'Creator One'},'metrics':metric(3,1,'10.00','1.00')},
                    {'creator':{'id':'c2','name':'Creator Two'},'metrics':metric(4)}]
        return [{'creator':{'id':'c2','name':'Creator Two'},'metrics':metric(4)}]


class ExportTests(unittest.TestCase):
    def test_exact_day_creator_and_sale_filter(self):
        client=FixtureClient()
        rows=mod.collect(client,'Account',None,date(2026,10,1),date(2026,10,2))
        self.assertEqual(rows[0]['values'],['Example / amazon.com','2026-10-01','Creator One',3,1,'10.00','1.00'])
        self.assertEqual(len(rows),1)
        self.assertEqual(len(client.calls),3)
        self.assertNotIn('/creators/active',[c[0] for c in client.calls])
        self.assertEqual(client.calls[-1][1]['end'],'2026-10-01T23:59:59.999Z')

    def test_all_activity_includes_zero_conversion_clicks(self):
        rows=mod.collect(FixtureClient(),'Account',None,date(2026,10,1),date(2026,10,2),True)
        self.assertEqual(len(rows),3)

    def test_duplicate_account_scope_is_rejected(self):
        used=set()
        mod.collect(FixtureClient(),'A',None,date(2026,10,1),date(2026,10,2),occupied=used)
        with self.assertRaises(mod.ExportError):
            mod.collect(FixtureClient(),'B',None,date(2026,10,1),date(2026,10,2),occupied=used)

    def test_mismatched_daily_totals_are_not_exported(self):
        with self.assertRaises(mod.ExportError):
            mod.reconcile([{'metrics':metric(0,1,'9.00','1.00')}],metric(0,1,'10.00','1.00'))

    def test_unknown_brand_id_rejected(self):
        with self.assertRaises(mod.ExportError):
            mod.collect(FixtureClient(),'A',['missing'],date(2026,10,1),date(2026,10,2))

    def test_init_blank_config_and_preserve_existing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'accounts.local.json'
            mod.init_config(p)
            original=p.read_bytes()
            self.assertEqual(json.loads(original)['品牌A']['api_key'],'')
            with self.assertRaises(FileExistsError):mod.init_config(p)
            self.assertEqual(p.read_bytes(),original)
            with self.assertRaises(mod.ExportError):mod.load_accounts(p)

    def test_empty_export_and_csv_literal_names(self):
        with tempfile.TemporaryDirectory() as d:
            mod.save_output(d,[],date(2026,10,1),date(2026,10,2),False)
            with (Path(d)/'sales.csv').open(encoding='utf-8-sig',newline='') as f:
                self.assertEqual(list(csv.reader(f)),[mod.HEADERS])
            rows=mod.collect(FixtureClient(),'A',None,date(2026,10,1),date(2026,10,2))
            rows[0]['values'][2]='=malicious()'
            mod.save_output(d,rows,date(2026,10,1),date(2026,10,2),False)
            self.assertIn("'=malicious()",(Path(d)/'sales.csv').read_text(encoding='utf-8-sig'))

    def test_pagination_repeated_cursor_rejected(self):
        client=mod.Client('fake-key','unused')
        with patch.object(client,'get',side_effect=[{'rows':[],'cursor':'same'},{'rows':[],'cursor':'same'}]):
            with self.assertRaises(mod.ExportError):client.rows('/example',{})

    def test_long_retry_after_stops(self):
        with tempfile.TemporaryDirectory() as d:
            client=mod.Client('fake-key',d,delay=0)
            error=HTTPError('https://app.levanta.io',429,'rate limit',{'Retry-After':'120'},None)
            with patch.object(client.opener,'open',side_effect=error):
                with self.assertRaises(mod.ExportError):client.get('/example',{})


if __name__=='__main__':unittest.main()
