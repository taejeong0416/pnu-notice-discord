import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0"}
MAX_PAGES = 5
WEEKDAYS = "월화수목금토일"

# (이름, 목록 주소, 페이지 요청 방식, 날짜 셀 선택자, 제목 링크 선택자, 디스코드 채널 ID)
BOARDS = [
    ("학부 공지", "https://cse.pusan.ac.kr/bbs/cse/2055/artclList.do", "post",
     "td.td-date", "td.td-title a", "1574093799498453135"),
    ("부산대 공지", "https://www.pusan.ac.kr/kor/CMS/Board/Board.do?mCode=MN095&mgr_seq=3", "get",
     "td.date", "td.subject a", "1574093875604099167"),
    ("학부 채용", "https://cse.pusan.ac.kr/bbs/cse/2060/artclList.do", "post",
     "td.td-date", "td.td-title a", "1574093917857775748"),
]


def fetch_page(url, method, page):
    if method == "post":
        res = requests.post(url, data={"page": str(page)}, headers=UA, timeout=20)
    else:
        res = requests.get(f"{url}&page={page}", headers=UA, timeout=20)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def parse_date(text):
    return datetime.strptime(text.strip().replace("-", "."), "%Y.%m.%d").date()


def full_title(row, link):
    """목록에서 잘린 제목은 첨부파일 아이콘의 alt에서 전체 제목을 가져옴."""
    title = re.sub(r"\s*새글$", "", link.get_text(" ", strip=True))
    img = row.select_one("img[alt$='의 첨부파일']")
    if title.endswith("...") and img:
        m = re.match(r"'(.*)'의 첨부파일$", img["alt"])
        if m:
            return m.group(1)
    return title


def collect(board, day):
    """그 날짜에 올라온 글. 고정 공지는 날짜가 맞을 때만 포함."""
    _, url, method, date_sel, link_sel, _ = board
    posts = {}
    for page in range(1, MAX_PAGES + 1):
        soup = fetch_page(url, method, page)
        older_found = False
        for row in soup.select("table tbody tr"):
            date_cell = row.select_one(date_sel)
            link = row.select_one(link_sel)
            if not date_cell or not link:
                continue
            posted = parse_date(date_cell.get_text())
            pinned = bool(set(row.get("class") or []) & {"notice", "isnotice"})
            if posted == day:
                href = urljoin(url, link.get("href", ""))
                posts[href] = full_title(row, link)
            elif posted < day and not pinned:
                older_found = True
        if older_found:
            break
    return [(title, href) for href, title in posts.items()]


def format_line(title, href):
    # 맨 앞 [부서명]은 라벨로 분리
    label = ""
    m = re.match(r"\s*\[([^\]]+)\]\s*(.*)", title)
    if m:
        label, title = m.group(1), m.group(2)
    # 링크 텍스트 안의 대괄호는 마크다운을 깨뜨림
    title = title.replace("[", "(").replace("]", ")")
    line = f"[{title}]({href})"
    return f"`{label}` {line}" if label else line


def build_embeds(name, day, posts):
    header = f"{day.month}월 {day.day}일 ({WEEKDAYS[day.weekday()]}) {name} {len(posts)}건"
    lines = [format_line(t, h) for t, h in posts]

    # embed 설명 한도 4096자
    chunks, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 2 > 4000:
            chunks.append(cur)
            cur = ""
        cur += line + "\n\n"
    chunks.append(cur)

    embeds = [{"description": c.strip()} for c in chunks]
    embeds[0]["title"] = header
    return embeds


def send(channel_id, embeds):
    headers = {
        "Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}",
        "User-Agent": "DiscordBot (https://github.com/taejeong0416/pnu-notice-discord, 1.0)",
    }
    # 한 메시지에 embed 최대 10개
    for i in range(0, len(embeds), 10):
        res = requests.post(f"https://discord.com/api/v10/channels/{channel_id}/messages",
                            json={"embeds": embeds[i:i + 10]}, headers=headers, timeout=20)
        res.raise_for_status()


def main():
    dry_run = "--dry-run" in sys.argv
    day = datetime.now(KST).date() - timedelta(days=1)
    # --date YYYY-MM-DD: 지난 날짜 다시 보내기
    if "--date" in sys.argv:
        day = datetime.strptime(sys.argv[sys.argv.index("--date") + 1], "%Y-%m-%d").date()

    for board in BOARDS:
        name, channel_id = board[0], board[5]
        posts = collect(board, day)
        if not posts:
            print(f"{name}: {day} 게시분 없음")
            continue
        embeds = build_embeds(name, day, posts)
        if dry_run:
            for e in embeds:
                print(e.get("title", ""))
                print(e["description"])
            continue
        send(channel_id, embeds)
        print(f"{name}: {len(posts)}건 전송")


if __name__ == "__main__":
    main()
