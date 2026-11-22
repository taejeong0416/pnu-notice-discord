import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0"}
MAX_PAGES = 5

# (이름, 목록 주소, 페이지 요청 방식, 날짜 셀 선택자, 제목 링크 선택자)
BOARDS = [
    ("학부 공지", "https://cse.pusan.ac.kr/bbs/cse/2055/artclList.do", "post", "td.td-date", "td.td-title a"),
    ("부산대 공지", "https://www.pusan.ac.kr/kor/CMS/Board/Board.do?mCode=MN095&mgr_seq=3", "get", "td.date", "td.subject a"),
    ("학부 채용", "https://cse.pusan.ac.kr/bbs/cse/2060/artclList.do", "post", "td.td-date", "td.td-title a"),
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


def collect(board, day):
    """그 날짜에 올라온 글. 고정 공지는 날짜가 맞을 때만 포함."""
    _, url, method, date_sel, link_sel = board
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
                posts[href] = link.get_text(" ", strip=True)
            elif posted < day and not pinned:
                older_found = True
        if older_found:
            break
    return [(title, href) for href, title in posts.items()]


def build_messages(day, results):
    lines = [f"**부산대 공지 브리핑** ({day:%m/%d} 게시분)"]
    for name, posts in results:
        if not posts:
            continue
        lines.append("")
        lines.append(f"**{name}** {len(posts)}건")
        for title, href in posts:
            lines.append(f"- [{title}](<{href}>)")

    # 디스코드 메시지 한도 2000자
    messages, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > 1900:
            messages.append(cur)
            cur = ""
        cur += line + "\n"
    messages.append(cur)
    return messages


def send_dm(messages):
    token = os.environ["DISCORD_BOT_TOKEN"]
    user_id = os.environ["DISCORD_USER_ID"]
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "DiscordBot (https://github.com/taejeong0416/pnu-notice-discord, 1.0)",
    }
    api = "https://discord.com/api/v10"
    res = requests.post(f"{api}/users/@me/channels", json={"recipient_id": user_id}, headers=headers, timeout=20)
    res.raise_for_status()
    channel_id = res.json()["id"]
    for content in messages:
        # flags 4: 링크 미리보기 끄기
        res = requests.post(f"{api}/channels/{channel_id}/messages",
                            json={"content": content, "flags": 4}, headers=headers, timeout=20)
        res.raise_for_status()


def main():
    dry_run = "--dry-run" in sys.argv
    day = datetime.now(KST).date() - timedelta(days=1)

    results, total = [], 0
    for board in BOARDS:
        posts = collect(board, day)
        results.append((board[0], posts))
        total += len(posts)

    if total == 0:
        print(f"{day} 게시분 없음")
        return

    messages = build_messages(day, results)
    if dry_run:
        for m in messages:
            print(m)
        return
    send_dm(messages)
    print(f"{total}건 전송")


if __name__ == "__main__":
    main()
