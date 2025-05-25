import React, { useRef, useEffect, useState } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

function VideoPlayer({ url, onClose }) {
  const videoRef = useRef();
  const hlsRef = useRef(null);
  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // 追蹤組件掛載狀態
  const isMounted = useRef(false);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  // 處理 video 元素的準備狀態
  useEffect(() => {
    if (videoRef.current) {
      setIsReady(true);
      setIsLoading(false);
    }
  }, [videoRef.current]);

  useEffect(() => {
    if (!isReady || !url) return;
    
    console.log('VideoPlayer useEffect 執行, url:', url);
    setIsLoading(true);

    // 清理上一個 Hls 實例
    if (hlsRef.current) {
      console.log('正在銷毀上一個 HLS 實例');
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    const video = videoRef.current;
    if (!video) return;

    if (url.endsWith(".m3u8") && Hls.isSupported()) {
      const hls = new Hls({
        debug: true,
        enableWorker: true,
        lowLatencyMode: true
      });

      // 添加載入完成的處理
      hls.on(Hls.Events.MANIFEST_PARSED, (event, data) => {
        if (isMounted.current) {
          setIsLoading(false);
          if (videoRef.current) {
            videoRef.current.play().catch(e => console.error('自動播放失敗:', e));
          }
        }
      });

      // 錯誤處理
      hls.on(Hls.Events.ERROR, function (event, data) {
        if (isMounted.current) {
          setIsLoading(false);
          console.error('HLS 錯誤:', data);
        }
      });

      try {
        hls.loadSource(url);
        hls.attachMedia(video);
        hlsRef.current = hls;
      } catch (error) {
        console.error('Hls.js 初始化錯誤:', error);
        setIsLoading(false);
      }
    } else {
      setIsLoading(false);
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [url, isReady]);

  return (
    <Dialog 
      open={!!url} 
      onClose={onClose} 
      fullWidth 
      maxWidth="md"
      TransitionProps={{
        onExited: () => {
          // Dialog 完全關閉後的清理
          if (hlsRef.current) {
            hlsRef.current.destroy();
            hlsRef.current = null;
          }
        }
      }}
    >
      <div style={{ position: "relative", background: "#000" }}>
        {isLoading && (
          <div style={{ 
            position: "absolute", 
            top: "50%", 
            left: "50%", 
            transform: "translate(-50%, -50%)" 
          }}>
            載入中...
          </div>
        )}
        {url && (
          <video
            ref={videoRef}
            src={!url.endsWith(".m3u8") ? url : undefined}
            style={{ 
              width: "100%", 
              height: "100%",
              opacity: isLoading ? 0.3 : 1
            }}
            controls
            autoPlay
          >
            不支援此格式
          </video>
        )}
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

export default React.memo(VideoPlayer, (prevProps, nextProps) => {
  // 自定義比較函數，只在 url 真正改變時才重新渲染
  return prevProps.url === nextProps.url;
});