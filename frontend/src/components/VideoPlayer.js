import React, { useRef, useEffect } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

function VideoPlayer({ url, onClose }) {
  const videoRef = useRef();
  const hlsRef = useRef(null);

  useEffect(() => {
    console.log('VideoPlayer useEffect 執行, url:', url);
    
    // 清理上一個 Hls 實例
    if (hlsRef.current) {
      console.log('正在銷毀上一個 HLS 實例');
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    
    // 確保 videoRef 有效後再繼續
    if (!videoRef.current) {
      console.error('videoRef.current 為 undefined，等待下一次渲染');
      return;
    }
    
    const video = videoRef.current;
    console.log('videoRef.current 已找到:', video);
  
    // 只針對 m3u8 用 Hls.js
    if (url && url.endsWith(".m3u8") && Hls.isSupported()) {
      console.log('正在為以下 URL 設定新的 HLS 實例:', url);
      const hls = new Hls({
        debug: true,
        enableWorker: true,
        lowLatencyMode: true
      });

      hls.on(Hls.Events.MANIFEST_LOADING, () => {
        console.log('開始載入 HLS manifest');
      });

      hls.on(Hls.Events.MANIFEST_LOADED, (event, data) => {
        console.log('HLS manifest 已載入:', data);
      });

      hls.on(Hls.Events.MANIFEST_PARSED, (event, data) => {
        console.log('HLS manifest 解析完成:', {
          levels: data.levels,
          firstLevel: data.firstLevel,
          stats: data.stats
        });
        if (videoRef.current) {
          videoRef.current.play().catch(e => console.error('自動播放失敗:', e));
        }
      });

      hls.on(Hls.Events.ERROR, function (event, data) {
        console.error('HLS.js ERROR:', {
          type: data.type,
          details: data.details,
          fatal: data.fatal,
          url: data.url,
          response: data.response,
          error: data.error
        });

        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              console.error('致命網絡錯誤:', {
                details: data.details,
                response: data.response,
                url: data.url
              });
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              console.error('致命媒體錯誤:', {
                details: data.details,
                error: data.error
              });
              hls.recoverMediaError();
              break;
            default:
              console.error('無法恢復的錯誤:', data);
              hls.destroy();
              break;
          }
        }
      });

      try {
        console.log('正在載入來源:', url);
        hls.loadSource(url);
        
        console.log('正在附加到媒體元素, videoRef.current:', videoRef.current);
        hls.attachMedia(video);
        hlsRef.current = hls;
      } catch (error) {
        console.error('Hls.js 初始化過程中發生錯誤:', error);
      }
    }

    // 清理
    return () => {
      console.log('VideoPlayer useEffect 清理函式執行, url:', url);
      if (hlsRef.current) {
        console.log('正在於清理函式中銷毀 HLS 實例');
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [url]);

  // 若是 m3u8 不設 src，其餘直接設
  const isHls = url && url.endsWith(".m3u8");
  const videoSrc = isHls ? undefined : url || "";

  return (
    <Dialog open={!!url} onClose={onClose} fullWidth maxWidth="md">
      <div style={{ position: "relative", background: "#000" }}>
        <video
          ref={videoRef}
          src={videoSrc}
          style={{ width: "100%", height: "100%" }}
          controls
          autoPlay
        >
          不支援此格式
        </video>
        <IconButton
          style={{ position: "absolute", top: 0, right: 0, color: "#fff" }}
          onClick={onClose}
        >
          <CloseIcon />
        </IconButton>
      </div>
    </Dialog>
  );
}

// 使用 React.memo 包裝組件，只在 props 真正改變時重新渲染
export default React.memo(VideoPlayer);
