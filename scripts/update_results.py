#!/usr/bin/env python3
"""Refresh LottoVision360 from public Missouri Lottery past-numbers tables."""
import json, re, sys, time
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent.parent
PAGE=ROOT/'index.html'
URLS={3:'https://www.molottery.com/pick3/past-numbers.do',4:'https://www.molottery.com/pick4/past-numbers.do'}
DATE_FORMATS=('%Y-%m-%d','%A, %b %d, %Y','%b %d, %Y','%m/%d/%Y')

def parse_date(s):
    s=' '.join(s.split())
    for fmt in DATE_FORMATS:
        try:return datetime.strptime(s,fmt).strftime('%Y-%m-%d')
        except ValueError:pass
    return None

def parse_table(html,game):
    soup=BeautifulSoup(html,'html.parser')
    records=[]
    for tr in soup.select('tr'):
        cols=[' '.join(td.stripped_strings) for td in tr.find_all(['td','th'])]
        if len(cols)<3:continue
        date=parse_date(cols[0]); draw=cols[1].strip().title()
        if not date or draw not in ('Midday','Evening'):continue
        # Digits can be spaced, in individual nested elements, or concatenated.
        digits=''.join(re.findall(r'\d',cols[2]))
        if len(digits)!=game:continue
        records.append([date,draw,digits])
    return records

def main():
    content=PAGE.read_text(encoding='utf-8')
    match=re.search(r'const DATA=(\{.*?\});',content,re.S)
    if not match:raise RuntimeError('Cannot locate embedded DATA in index.html')
    data=json.loads(match.group(1)); changed=False
    session=requests.Session();session.headers.update({'User-Agent':'LottoVision360-public-results-check/1.0'})
    for game,url in URLS.items():
        try:
            response=session.get(url,timeout=35);response.raise_for_status()
            rows=parse_table(response.text,game)
            if not rows:raise ValueError('No valid draw rows found; page format may have changed')
            key=str(game); existing=data[key]
            known={(r[0],r[1]) for r in existing}
            added=0
            for row in rows:
                ident=(row[0],row[1])
                if ident not in known:
                    existing.append(row);known.add(ident);added+=1
                else:
                    old=next(r for r in existing if (r[0],r[1])==ident)
                    if old[2]!=row[2]:
                        print(f'WARNING Pick {game} conflicting official result for {ident}: existing={old[2]}, fetched={row[2]}; manual review required',file=sys.stderr)
            if added:
                existing.sort(key=lambda r:(r[0],0 if r[1]=='Midday' else 1));changed=True
            print(f'Pick {game}: {len(rows)} fetched, {added} new, {len(existing)} stored')
        except Exception as exc:
            print(f'WARNING Pick {game}: fetch failed: {exc}',file=sys.stderr)
    if changed:
        replacement='const DATA='+json.dumps(data,separators=(',',':'))+';'
        PAGE.write_text(content[:match.start()]+replacement+content[match.end():],encoding='utf-8')
        print('Updated index.html')
    else:print('No new results; index.html unchanged')

if __name__=='__main__':main()
