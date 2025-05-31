import subprocess
import os

def download_m3u8_with_custom_headers(m3u8_url: str, output_ts: str):
    """
    直接把預先知道的那些 HTTP header 一次性打包，並傳給 ffmpeg 下載 HLS (.m3u8 → 多個 .ts)
    然後把所有 .ts 串起來，輸出成單一的 .ts 檔。
    """

    # ──────────────────────────────────────────────────
    # 1. 把你列出的每一個 Header 組成 ffmpeg 所需的 “-headers” 單行字串
    #    ffmpeg 要求是 Key: Value\r\n 這樣一行行串起，最後再給 -headers
    # ──────────────────────────────────────────────────
    header_lines = (
        "accept: */*\r\n"
        "accept-language: zh-TW,zh-CN;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6\r\n"
        "dnt: 1\r\n"
        "origin: https://ani.gamer.com.tw\r\n"
        "priority: u=1, i\r\n"
        "referer: https://ani.gamer.com.tw/animeVideo.php?sn=43390\r\n"
        "sec-ch-ua: \"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"\r\n"
        "sec-ch-ua-mobile: ?0\r\n"
        "sec-ch-ua-platform: \"Windows\"\r\n"
        "sec-fetch-dest: empty\r\n"
        "sec-fetch-mode: cors\r\n"
        "sec-fetch-site: cross-site\r\n"
        "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36\r\n"
    )

    # ──────────────────────────────────────────────────
    # 2. 確認輸出資料夾存在
    # ──────────────────────────────────────────────────
    folder = os.path.dirname(output_ts)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)

    # ──────────────────────────────────────────────────
    # 3. 組裝 ffmpeg 命令
    #    -allowed_extensions ALL：允許 ffmpeg 處理具 querystring 的 .ts 段
    #    -headers "<header_lines>"：把我們準備好的所有 headers 一次塞給 ffmpeg
    #    -i "<m3u8_url>"：告訴 ffmpeg 直接讀這條 HLS 清單
    #    -c copy：不重新編碼，純粹拷貝每個 ts 片段
    #    "<output_ts>"：下載並合併完後的最終 .ts 檔案
    # ──────────────────────────────────────────────────
    cmd = [
        "ffmpeg",
        "-y",
        "-allowed_extensions", "ALL",
        "-headers", header_lines,
        "-i", m3u8_url,
        "-c", "copy",
        output_ts
    ]

    print("執行 ffmpeg，命令如下：")
    print("  " + " \\\n  ".join(cmd))

    # ──────────────────────────────────────────────────
    # 4. 執行 ffmpeg
    # ──────────────────────────────────────────────────
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        print(">>> ffmpeg stderr:")
        print(proc.stderr.decode(errors="ignore"))
        raise RuntimeError("ffmpeg 下載/合併 TS 失敗，請檢查上面錯誤訊息。")

    print(f"[OK] 下載完成，已輸出成 TS：{output_ts}")
    return output_ts


if __name__ == "__main__":
    # 你給的 m3u8 範例
    m3u8_url = "https://bahamut.akamaized.net/ad/welcome_to_anigamer/540p/chunklist_b1200000.m3u8"
    # 最終要輸出的 TS 檔案
    output_ts = "downloads/anigamer_video.ts"

    try:
        final_ts = download_m3u8_with_custom_headers(m3u8_url, output_ts)
        print("最終 TS 檔位置：", final_ts)
    except Exception as e:
        print("發生錯誤：", e)
