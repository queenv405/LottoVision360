#!/usr/bin/env python3
"""Refresh LottoVision360 and export Pick 4 history/statistics."""
import csv, json, re, sys
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
        digits=''.join(re.findall(r'\d',cols[2]))
        if len(digits)!=game:continue
        records.append([date,draw,digits])
    return records

def export_pick4(rows):
    """Export history and per-draw overdue stats, using prior draws only."""
    rows=sorted((r for r in rows if len(r)==3 and re.fullmatch(r'\d{4}',str(r[2]))),
                key=lambda r:(r[0],0 if r[1]=='Midday' else 1))
    output=ROOT/'data'
    output.mkdir(exist_ok=True)
    seen_sums={};seen_roots={}
    history=[]
    for i,(date,draw,number) in enumerate(rows):
        total=sum(map(int,number))
        root=total%9 or 9 if total else 0
        history.append({'date':date,'draw':draw,'number':number,'sum':total,'root':root,
                        'sum_gap_before':i-seen_sums[total]-1 if total in seen_sums else None,
                        'root_gap_before':i-seen_roots[root]-1 if root in seen_roots else None})
        seen_sums[total]=i;seen_roots[root]=i
    with (output/'pick4_history.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['date','draw','number','sum','root','sum_gap_before','root_gap_before'])
        writer.writeheader();writer.writerows(history)
    n=len(history)
    summary={'draw_count':n,'last_draw':history[-1]['date']+' '+history[-1]['draw'] if history else None,
             'sum_overdue':{str(s):n-1-seen_sums[s] if s in seen_sums else None for s in range(37)},
             'root_overdue':{str(r):n-1-seen_roots[r] if r in seen_roots else None for r in range(10)}}
    (output/'pick4_stats.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(f'Exported {n} Pick 4 draws to data/pick4_history.csv and data/pick4_stats.json')

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
    export_pick4(data['4'])

if __name__=='__main__':main()
