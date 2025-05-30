import re
from playwright.sync_api import sync_playwright

def get_episode_urls_with_playwright(category_url: str) -> list[str]:
    """
    使用 Playwright 抓取所有分頁中集數的連結和集數文字，
    然后根据[...]里的数字升序排序，最后返回 href 列表。
    """
    episodes = {}  # num -> href
    next_page = category_url

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        while next_page:
            page.goto(next_page, wait_until="load")
            # 同时取所有链接和文字
            data = page.eval_on_selector_all(
                ".entry-title a",
                """els => els.map(e => ({
                    href: e.href,
                    title: e.textContent.trim()
                }))"""
            )
            print(f"[DEBUG] 抓到 {len(data)} 集於 {next_page}")
            for item in data:
                m = re.search(r'\[(\d+)\]', item["title"])
                if m:
                    num = int(m[1])
                    # 如果同集多次出现，以第一次为准
                    if num not in episodes:
                        episodes[num] = item["href"]

            # 找「上一頁」按鈕（進到更早的集數分頁）
            nxt = page.query_selector('a:has-text("上一頁")')
            if nxt:
                href = nxt.get_attribute("href")
                if href:
                    next_page = href
                    continue
            break

        browser.close()

    # 根据数字键排序
    sorted_nums = sorted(episodes.keys())
    return [episodes[n] for n in sorted_nums]

def get_video_src(page, episode_url: str) -> str:
    """
    使用同一個 Playwright page，點擊播放並取得 <video> 的 src。
    """
    page.goto(episode_url, wait_until="load")
    page.click(".vjs-big-play-centered")
    page.wait_for_function(
        "() => !!(document.querySelector('video') && document.querySelector('video').src)"
    )
    return page.evaluate("() => document.querySelector('video').src")

def main():
    category_url = (
        "https://anime1.me/category/"
        "2025%E5%B9%B4%E5%86%AC%E5%AD%A3/"
        "%E9%AD%94%E7%A5%9E%E5%89%B5%E9%80%A0%E5%82%B3"
    )
    print("[DEBUG] 開始抓取並排序所有集數連結…")
    episodes = get_episode_urls_with_playwright(category_url)
    print(f"[DEBUG] 共找到 {len(episodes)} 集，前 3 集是：{episodes[:3]}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()

        first = episodes[0]
        print(f"[DEBUG] 處理第 1 集：{first}")
        src = get_video_src(page, first)
        print(f"[DEBUG] 第 1 集影片 src：{src}")

        browser.close()

if __name__ == "__main__":
    main()
