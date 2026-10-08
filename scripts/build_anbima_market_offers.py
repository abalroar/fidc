#!/usr/bin/env python3
"""Refresh the official ANBIMA market bulletin for the consolidated monthly cut."""
from __future__ import annotations
import argparse
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from urllib.request import Request, urlopen
if __package__ in {None,''}:sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.industry_comparative_period import ComparisonCut
from services.industry_anbima_market_source import resolve_market_bulletin,build_anbima_market_snapshot

def main(argv: list[str]|None=None)->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('data/industry_study'))
    parser.add_argument('--cache-dir',type=Path,default=Path('.cache/anbima'))
    parser.add_argument('--workbook',type=Path)
    parser.add_argument('--source-url')
    parser.add_argument('--source-as-of-date',default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--latest-complete')
    args=parser.parse_args(argv)
    cut=ComparisonCut.from_competence(args.latest_complete) if args.latest_complete else ComparisonCut.from_data_dir(args.data_dir)
    source=resolve_market_bulletin() if args.workbook is None else {'url':args.source_url,'published_at':''}
    if not source['url']:raise ValueError('--source-url é obrigatório com --workbook')
    if args.workbook is None:
        args.cache_dir.mkdir(parents=True,exist_ok=True)
        args.workbook=args.cache_dir/source['file_name']
        with urlopen(Request(source['url'],headers={'User-Agent':'FIDC-industry-audit/1.0'}),timeout=120) as response:payload=response.read()
        args.workbook.write_bytes(payload)
    frame,manifest=build_anbima_market_snapshot(args.workbook,comparison_cut=cut,source_url=source['url'],source_as_of_date=args.source_as_of_date,source_published_at=source['published_at'])
    args.data_dir.mkdir(parents=True,exist_ok=True)
    output_path=args.data_dir/'industry_anbima_market_offers.csv'
    frame.to_csv(output_path,index=False)
    manifest["output_sha256"]=sha256(output_path.read_bytes()).hexdigest()
    (args.data_dir/'industry_anbima_market_offers_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
